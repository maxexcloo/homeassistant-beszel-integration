"""Tests for Beszel sensors."""

import unittest
from unittest.mock import MagicMock, patch

from support import FakeHomeAssistant, SensorDeviceClass, UnitOfTime

from custom_components.beszel.const import DOMAIN
from custom_components.beszel.sensor import (
    _create_available_sensors,
    async_setup_entry,
)


class BeszelSensorTests(unittest.IsolatedAsyncioTestCase):
    """Exercise Beszel sensor discovery behaviour."""

    def test_sensor_discovery_uses_reported_values_and_scoped_ids(self):
        """Discovery omits missing rates and scopes identifiers."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {"u": 90},
                "stats": {"cpu": 12.5},
            }
        }

        sensors = _create_available_sensors(coordinator)
        unique_ids = {sensor.unique_id for sensor in sensors}

        self.assertIn("beszel_entry_system_stats_cpu", unique_ids)
        self.assertNotIn("beszel_entry_system_stats_dr", unique_ids)
        self.assertNotIn("beszel_entry_system_stats_dw", unique_ids)

        uptime = next(
            sensor for sensor in sensors if sensor.unique_id.endswith("_info_u")
        )
        status = next(
            sensor for sensor in sensors if sensor.unique_id.endswith("_status_status")
        )
        self.assertIs(uptime.device_class, SensorDeviceClass.DURATION)
        self.assertIs(uptime.native_unit_of_measurement, UnitOfTime.SECONDS)
        self.assertEqual(uptime.native_value, 90)
        self.assertEqual(
            uptime.device_info["identifiers"], {("beszel", "entry_system")}
        )
        self.assertEqual(uptime.translation_key, "uptime")
        self.assertEqual(status.native_value, "up")
        self.assertEqual(status.options, ["down", "paused", "pending", "unknown", "up"])

    def test_malformed_nested_data_is_unavailable(self):
        """Null and malformed nested values do not interrupt discovery."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "info": None,
                "status": "up",
                "stats": {"efs": {"disk": None}, "g": {"0": None}, "t": []},
            }
        }

        sensors = _create_available_sensors(coordinator)

        self.assertEqual(
            {sensor.unique_id for sensor in sensors},
            {"beszel_entry_system_status_status"},
        )

    def test_data_rates_read_byte_counters(self):
        """Byte counters are converted to megabytes per second."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {},
                "stats": {"b": [2097152, 1048576], "dio": [524288, 262144]},
            }
        }

        sensors = _create_available_sensors(coordinator)
        by_id = {sensor.unique_id: sensor for sensor in sensors}

        self.assertEqual(by_id["beszel_entry_system_stats_ns"].native_value, 2.0)
        self.assertEqual(by_id["beszel_entry_system_stats_nr"].native_value, 1.0)
        self.assertEqual(by_id["beszel_entry_system_stats_dr"].native_value, 0.5)
        self.assertEqual(by_id["beszel_entry_system_stats_dw"].native_value, 0.25)

    def test_data_rates_fall_back_to_legacy_values(self):
        """Legacy MB/s values are used when byte counters are absent."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {},
                "stats": {"nr": 1.5, "ns": 2.5},
            }
        }

        sensors = _create_available_sensors(coordinator)
        by_id = {sensor.unique_id: sensor for sensor in sensors}

        self.assertEqual(by_id["beszel_entry_system_stats_ns"].native_value, 2.5)
        self.assertEqual(by_id["beszel_entry_system_stats_nr"].native_value, 1.5)

    def test_new_metrics_are_discovered_on_later_data(self):
        """A later coordinator snapshot exposes newly reported metrics."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {},
                "stats": {},
            }
        }
        initial_ids = {
            sensor.unique_id for sensor in _create_available_sensors(coordinator)
        }

        coordinator.data["system"]["stats"] = {"dr": 1.5, "dios": [1, 2, 3, 4, 5, 6]}
        later_ids = {
            sensor.unique_id for sensor in _create_available_sensors(coordinator)
        }

        self.assertNotIn("beszel_entry_system_stats_dr", initial_ids)
        self.assertIn("beszel_entry_system_stats_dr", later_ids)
        self.assertIn(
            "beszel_entry_system_stats_disk_io_utilisation_percent", later_ids
        )

    async def test_platform_adds_new_metrics_after_setup(self):
        """The coordinator listener adds a metric that appears after setup."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {},
                "stats": {},
            }
        }
        hass = FakeHomeAssistant()
        hass.data[DOMAIN] = {"entry": coordinator}

        entry = MagicMock()
        entry.entry_id = "entry"
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        initial_entities = async_add_entities.call_args.args[0]
        self.assertEqual(
            {entity.unique_id for entity in initial_entities},
            {"beszel_entry_system_status_status"},
        )

        coordinator.data["system"]["stats"] = {"cpu": 12.5}
        listener = coordinator.async_add_listener.call_args.args[0]
        listener()

        later_entities = async_add_entities.call_args.args[0]
        self.assertEqual(
            {entity.unique_id for entity in later_entities},
            {"beszel_entry_system_stats_cpu"},
        )

        with patch(
            "custom_components.beszel.sensor.BeszelSensor",
            side_effect=AssertionError("known sensors should not be reconstructed"),
        ):
            listener()

    async def test_device_details_follow_system_changes(self):
        """Coordinator updates refresh an existing device's Beszel metadata."""
        coordinator = MagicMock()
        coordinator.config_entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Old Name",
                "status": "up",
                "info": {},
                "stats": {},
            }
        }
        hass = FakeHomeAssistant()
        hass.data[DOMAIN] = {"entry": coordinator}
        entry = MagicMock(entry_id="entry")

        await async_setup_entry(hass, entry, MagicMock())
        device = hass.device_registry.async_get_or_create(
            config_entry_id="entry",
            identifiers={(DOMAIN, "entry_system")},
            name="Old Name",
        )

        coordinator.data["system"].update(
            {"name": "New Name", "info": {"os": 0, "v": "1.2.3"}}
        )
        listener = coordinator.async_add_listener.call_args.args[0]
        listener()

        self.assertEqual(device.model, "Linux")
        self.assertEqual(device.name, "New Name")
        self.assertEqual(device.sw_version, "1.2.3")
