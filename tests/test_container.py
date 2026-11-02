"""Tests for container discovery, values and availability."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.beszel.const import DOMAIN
from custom_components.beszel.sensor import _create_available_sensors


def container_sensors(coordinator):
    """Return container sensors from normal platform discovery keyed by field."""
    return {
        sensor.unique_id.rsplit("_", 1)[1]: sensor
        for sensor in _create_available_sensors(coordinator, set())
        if "_container_" in sensor.unique_id
    }


@pytest.fixture
def coordinator():
    """Return one system reporting one container."""
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.data = {
        "system": {
            "name": "Server",
            "status": "up",
            "containers": {
                "abc": {
                    "cpu": 1.234,
                    "health": 2,
                    "image": "nginx:latest",
                    "memory": 100,
                    "name": "web",
                    "net": 2_500_000,
                    "updated": dt_util.utcnow().timestamp() * 1000,
                }
            },
        }
    }
    return coordinator


def test_container_sensors_report_converted_values(coordinator):
    """Container values use the integration's decimal units and health states."""
    sensors = container_sensors(coordinator)
    updated = sensors.pop("updated").native_value
    assert abs(dt_util.utcnow() - updated) < timedelta(seconds=5)
    assert {key: sensor.native_value for key, sensor in sensors.items()} == {
        "cpu": 1.23,
        "health": "healthy",
        "memory": 104.86,
        "net": 2.5,
    }
    assert sensors["cpu"].unique_id == "beszel_entry_system_container_abc_cpu"
    assert sensors["cpu"].available
    assert sensors["cpu"].device_info == {
        "identifiers": {(DOMAIN, "entry_system_container_abc")},
        "manufacturer": "Beszel",
        "model": "nginx:latest",
        "name": "web",
        "via_device": (DOMAIN, "entry_system"),
    }


def test_missing_container_values_are_not_discovered(coordinator):
    """Unreported or unknown values create no sensors."""
    container = coordinator.data["system"]["containers"]["abc"]
    container["health"] = 9
    del container["net"]
    assert set(container_sensors(coordinator)) == {"cpu", "memory", "updated"}


def test_stale_container_reports_keep_only_the_report_time(coordinator):
    """Old reports and stopped systems make measurements unavailable."""
    sensors = container_sensors(coordinator)
    container = coordinator.data["system"]["containers"]["abc"]
    container["updated"] -= timedelta(minutes=5, seconds=1).total_seconds() * 1000
    assert not sensors["cpu"].available
    assert sensors["updated"].available
    container["updated"] = dt_util.utcnow().timestamp() * 1000
    coordinator.data["system"]["status"] = "down"
    assert not sensors["health"].available
    del coordinator.data["system"]["containers"]["abc"]
    assert not sensors["updated"].available
