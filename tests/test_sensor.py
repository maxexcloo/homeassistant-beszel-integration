"""Tests for Beszel sensors."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel.const import DOMAIN
from custom_components.beszel.sensor import _create_available_sensors, async_setup_entry


class TestBeszelSensor:
    """Exercise Beszel sensor discovery behaviour."""

    def test_binary_capacities_match_existing_decimal_units_and_keep_ids(self):
        """Correct capacities without changing recorder identities or missing data."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        stats = {"m": 1, "efs": {"data": {"d": 1}}, "g": {"0": {"mt": 1}}}
        coordinator.data = {"system": {"stats": stats}}
        by_id = {
            sensor.unique_id: sensor
            for sensor in _create_available_sensors(coordinator)
        }
        for suffix in ["m", "efs_data_d"]:
            sensor = by_id["beszel_entry_system_stats_" + suffix]
            assert sensor.native_value == 1.07
            assert sensor.native_unit_of_measurement == UnitOfInformation.GIGABYTES
        gpu = by_id["beszel_entry_system_stats_g_0_mt"]
        assert gpu.native_value == 1.05
        assert gpu.native_unit_of_measurement == UnitOfInformation.MEGABYTES
        stats["m"] = None
        stats["g"]["0"]["mt"] = None
        assert by_id["beszel_entry_system_stats_m"].native_value is None
        assert gpu.native_value is None

    @pytest.mark.parametrize(
        "status, age, expected",
        [
            ("up", 0, True),
            ("up", 300, True),
            ("up", 301, False),
            ("down", 0, False),
            ("up", -1, False),
            ("up", None, False),
            ("up", "invalid", False),
        ],
    )
    def test_statistics_availability_uses_native_source_age(
        self, status, age, expected
    ):
        """Only fresh samples from online systems are available."""
        now = dt_util.utcnow()
        created = (
            (now - timedelta(seconds=age)).isoformat() if isinstance(age, int) else age
        )
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        coordinator.data = {
            "system": {"status": status, "stats_created": created, "stats": {"cpu": 10}}
        }
        sensor = next(
            sensor
            for sensor in _create_available_sensors(coordinator)
            if sensor.unique_id.endswith("_stats_cpu")
        )
        with patch("custom_components.beszel.sensor.dt_util.utcnow", return_value=now):
            assert sensor.available is expected
        assert sensor.native_value == 10

    @pytest.mark.parametrize(
        ("stats", "expected"),
        [
            (
                {"efs": {"data": {"rb": 1048576, "wb": 524288}}},
                {"efs_data_r": 1.05, "efs_data_w": 0.52},
            ),
            (
                {"efs": {"data": {"rb": 0, "wb": 0, "r": 1, "w": 2}}},
                {"efs_data_r": 0, "efs_data_w": 0},
            ),
            (
                {"b": [2097152, 1048576], "dio": [524288, 262144]},
                {"ns": 2.1, "nr": 1.05, "dr": 0.52, "dw": 0.26},
            ),
        ],
    )
    def test_data_rates_read_byte_counters(self, stats, expected):
        """Byte rates become MB/s under the existing entity IDs."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        coordinator.data = {"system": {"stats": stats}}
        by_id = {
            sensor.unique_id: sensor
            for sensor in _create_available_sensors(coordinator)
        }
        assert {
            suffix: by_id[f"beszel_entry_system_stats_{suffix}"].native_value
            for suffix in expected
        } == expected

    def test_sensor_discovery_uses_reported_values_and_scoped_ids(self):
        """Discovery omits missing rates and scopes identifiers."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
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
        assert "beszel_entry_system_stats_cpu" in unique_ids
        assert "beszel_entry_system_stats_dr" not in unique_ids
        assert "beszel_entry_system_stats_dw" not in unique_ids
        uptime = next(
            sensor for sensor in sensors if sensor.unique_id.endswith("_info_u")
        )
        status = next(
            sensor for sensor in sensors if sensor.unique_id.endswith("_status_status")
        )
        assert uptime.device_class is SensorDeviceClass.DURATION
        assert uptime.native_unit_of_measurement is UnitOfTime.SECONDS
        assert uptime.native_value == 90
        assert uptime.device_info["identifiers"] == {("beszel", "entry_system")}
        assert uptime.translation_key == "uptime"
        assert status.native_value == "up"
        assert status.options == ["down", "paused", "pending", "unknown", "up"]
        for value in ("UP", "rebooting", None):
            coordinator.data["system"]["status"] = value
            assert status.native_value == ("up" if value == "UP" else "unknown")

    def test_malformed_nested_data_is_unavailable(self):
        """Null and malformed nested values do not interrupt discovery."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
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
        assert {sensor.unique_id for sensor in sensors} == {
            "beszel_entry_system_status_status"
        }

    def test_nested_sensors_keep_ids_metadata_and_live_values(self):
        """Filesystem and GPU discovery retain their distinct data and names."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        stats = {
            "efs": {"data": {"d": 100, "du": 40}},
            "g": {"0": {"n": "Graphics", "u": 25}, "1": {"u": 0}},
        }
        coordinator.data = {"system": {"stats": stats}}
        sensors = _create_available_sensors(coordinator)
        by_id = {sensor.unique_id: sensor for sensor in sensors}
        filesystem = by_id["beszel_entry_system_stats_efs_data_d"]
        gpu = by_id["beszel_entry_system_stats_g_0_u"]
        fallback_gpu = by_id["beszel_entry_system_stats_g_1_u"]
        assert filesystem.native_value == 107.37
        assert filesystem.translation_placeholders == {"filesystem": "data"}
        assert gpu.native_value == 25
        assert gpu.translation_placeholders == {"gpu": "Graphics"}
        assert gpu.translation_key == "gpu_usage"
        assert gpu.native_unit_of_measurement == "%"
        assert fallback_gpu.native_value == 0
        assert fallback_gpu.translation_placeholders == {"gpu": "1"}
        stats["g"]["0"]["u"] = None
        assert gpu.native_value is None
        assert _create_available_sensors(coordinator, set(by_id)) == []

    def test_new_metrics_are_discovered_on_later_data(self):
        """A later coordinator snapshot exposes newly reported metrics."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
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
        coordinator.data["system"]["stats"] = {
            "dio": [1, 2],
            "dios": [1, 2, 3, 4, 5, 6],
        }
        later_ids = {
            sensor.unique_id for sensor in _create_available_sensors(coordinator)
        }
        assert "beszel_entry_system_stats_dr" not in initial_ids
        assert "beszel_entry_system_stats_dr" in later_ids
        assert "beszel_entry_system_stats_disk_io_utilisation_percent" in later_ids

    async def test_platform_adds_new_metrics_after_setup(self, hass):
        """The coordinator listener adds a metric that appears after setup."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Server",
                "status": "up",
                "info": {},
                "stats": {},
            }
        }
        entry = MockConfigEntry(domain=DOMAIN, entry_id="entry")
        entry.add_to_hass(hass)
        entry.runtime_data = coordinator
        async_add_entities = MagicMock()
        await async_setup_entry(hass, entry, async_add_entities)
        initial_entities = async_add_entities.call_args.args[0]
        assert {entity.unique_id for entity in initial_entities} == {
            "beszel_entry_system_status_status"
        }
        coordinator.data["system"]["stats"] = {"cpu": 12.5}
        listener = coordinator.async_add_listener.call_args.args[0]
        listener()
        later_entities = async_add_entities.call_args.args[0]
        assert {entity.unique_id for entity in later_entities} == {
            "beszel_entry_system_stats_cpu"
        }
        with patch(
            "custom_components.beszel.sensor.BeszelSensor",
            side_effect=AssertionError("known sensors should not be reconstructed"),
        ):
            listener()

    async def test_device_details_follow_system_changes(self, hass):
        """Coordinator updates refresh an existing device's Beszel metadata."""
        coordinator = MagicMock()
        coordinator.config_entry.entry_id = "entry"
        coordinator.data = {
            "system": {
                "id": "system",
                "name": "Old Name",
                "status": "up",
                "info": {},
                "stats": {},
            }
        }
        entry = MockConfigEntry(domain=DOMAIN, entry_id="entry")
        entry.add_to_hass(hass)
        entry.runtime_data = coordinator
        await async_setup_entry(hass, entry, MagicMock())
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id="entry",
            identifiers={(DOMAIN, "entry_system")},
            name="Old Name",
        )
        other_entry = MockConfigEntry(domain=DOMAIN)
        other_entry.add_to_hass(hass)
        other_device = dr.async_get(hass).async_get_or_create(
            config_entry_id=other_entry.entry_id,
            identifiers={(DOMAIN, "entry_system")},
            name="Other Hub",
        )
        coordinator.data["system"].update(
            {"name": "New Name", "info": {"os": 0, "v": "1.2.3"}}
        )
        listener = coordinator.async_add_listener.call_args.args[0]
        listener()
        device = dr.async_get(hass).async_get(device.id)
        assert device.model == "Linux"
        assert device.name == "New Name"
        assert device.sw_version == "1.2.3"
        assert dr.async_get(hass).async_get(other_device.id).name == "Other Hub"


def test_missing_operating_system_is_none():
    """An existing OS sensor exposes missing and unrecognised values as None."""
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.data = {"system": {"info": {"os": 0}}}
    sensor = next(
        sensor
        for sensor in _create_available_sensors(coordinator)
        if sensor.unique_id.endswith("_info_os")
    )
    assert sensor.native_value == "Linux"
    for info in ({}, {"os": None}, {"os": 99}):
        coordinator.data["system"]["info"] = info
        assert sensor.native_value is None
        assert "model" not in sensor.device_info
        assert not any(
            sensor.unique_id.endswith("_info_os")
            for sensor in _create_available_sensors(coordinator)
        )


def test_temperature_names_follow_the_cpu_thermal_rule():
    """Only CPU thermal zones use the CPU name; other keys keep readable names."""
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.data = {
        "system": {
            "stats": {
                "t": {
                    "amd gpu (15e7)": 50,
                    "amdgpu_edge": 45,
                    "cpu_thermal": 40,
                    "nvme_composite": 30,
                }
            }
        }
    }
    by_key = {
        sensor.unique_id.rsplit("_temperature_", 1)[1]: sensor
        for sensor in _create_available_sensors(coordinator)
        if "_temperature_" in sensor.unique_id
    }
    assert by_key["cpu_thermal"].translation_key == "cpu_temperature"
    assert by_key["nvme_composite"].translation_key == "temperature"
    assert {
        key: sensor.translation_placeholders["temperature"]
        for key, sensor in by_key.items()
        if key != "cpu_thermal"
    } == {
        "amd gpu (15e7)": "AMD GPU (15e7)",
        "amdgpu_edge": "AMDGPU Edge",
        "nvme_composite": "NVMe Composite",
    }
