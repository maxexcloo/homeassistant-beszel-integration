"""Tests for Network Probes discovery, grouping and unavailable measurements."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import UnitOfTime
from homeassistant.util import dt as dt_util

from custom_components.beszel.const import DOMAIN
from custom_components.beszel.sensor import _create_available_sensors


@pytest.fixture
def probe_coordinator():
    """Return two probing systems using the same target."""
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "hub-one"
    coordinator.api_client.host = "http://beszel.local"
    probe = {
        "target": "example.com",
        "protocol": "tcp",
        "port": 443,
        "interval": 30,
        "enabled": True,
        "stats": {
            "created": int(dt_util.utcnow().timestamp() * 1000),
            "total_count": 4,
            "success_count": 3,
            "res_sum": 15000,
            "res_min": 3000,
            "res_max": 8000,
        },
    }
    coordinator.data = {
        system: {
            "name": system,
            "status": "up",
            "network_probes": {"monitor": deepcopy(probe)},
        }
        for system in ("one", "two")
    }
    return coordinator


def probe_sensors(coordinator):
    """Select just the probe sensors from normal platform discovery."""
    return [
        sensor
        for sensor in _create_available_sensors(coordinator)
        if "_probe_" in sensor.unique_id
    ]


def test_discovery_groups_all_systems_per_hub_and_preserves_identities(
    probe_coordinator,
):
    """One shared device per Hub, with distinct sensors for each probing system."""
    sensors = probe_sensors(probe_coordinator)
    assert len(sensors) == 8
    assert len({sensor.unique_id for sensor in sensors}) == 8
    for sensor in sensors:
        assert sensor.device_info["identifiers"] == {(DOMAIN, "hub-one_network_probes")}
        assert sensor.device_info["name"] == "Network Probes"
        assert sensor.device_info["configuration_url"] == "http://beszel.local/monitors"
        assert "example.com:443 (TCP)" in sensor.translation_placeholders["probe"]
        assert sensor.extra_state_attributes["system"] in ("one", "two")
        assert sensor.available
    known_ids = {
        sensor.unique_id for sensor in _create_available_sensors(probe_coordinator)
    }
    assert _create_available_sensors(probe_coordinator, known_ids) == []
    probe_coordinator.data["one"]["network_probes"]["new"] = deepcopy(
        probe_coordinator.data["one"]["network_probes"]["monitor"]
    )
    assert len(_create_available_sensors(probe_coordinator, known_ids)) == 4
    probe_coordinator.config_entry.entry_id = "hub-two"
    other_sensors = probe_sensors(probe_coordinator)
    assert {sensor.unique_id for sensor in other_sensors}.isdisjoint(known_ids)
    assert other_sensors[0].device_info["identifiers"] == {
        (DOMAIN, "hub-two_network_probes")
    }


def test_response_times_and_loss_use_native_counts_and_microseconds(probe_coordinator):
    """Weighted averages become milliseconds and loss remains a percentage."""
    sensors = {
        sensor.entity_description.key: sensor
        for sensor in probe_sensors(probe_coordinator)
    }
    assert {key: sensor.native_value for key, sensor in sensors.items()} == {
        "response_time": 5,
        "res_min": 3,
        "res_max": 8,
        "packet_loss": 25,
    }
    assert (
        sensors["response_time"].native_unit_of_measurement == UnitOfTime.MILLISECONDS
    )
    assert sensors["packet_loss"].native_unit_of_measurement == "%"
    for system in probe_coordinator.data.values():
        system["network_probes"]["monitor"]["stats"]["success_count"] = 0
    assert sensors["packet_loss"].native_value == 100
    assert sensors["response_time"].native_value is None
    assert sensors["res_min"].native_value is None
    assert sensors["res_max"].native_value is None


@pytest.mark.parametrize(
    "stats",
    [
        None,
        {},
        {"total_count": 0, "success_count": 0},
        {"total_count": 1},
        {"total_count": 1, "success_count": 2},
    ],
)
def test_missing_samples_do_not_create_zero_measurements(probe_coordinator, stats):
    """Absent, empty and invalid samples never produce fabricated zero values."""
    sensors = probe_sensors(probe_coordinator)
    for system in probe_coordinator.data.values():
        system["network_probes"]["monitor"]["stats"] = stats
    assert probe_sensors(probe_coordinator) == []
    assert all(sensor.native_value is None for sensor in sensors)


@pytest.mark.parametrize(
    "age,interval,expected",
    [
        (0, 30, True),
        (300, 30, True),
        (301, 30, False),
        (-1, 30, False),
        (3601, 3600, True),
        (3721, 3600, False),
    ],
)
def test_probe_freshness_uses_numeric_timestamp_and_interval(
    probe_coordinator, age, interval, expected
):
    """Source age, including long probe intervals, determines availability."""
    now = dt_util.utcnow().replace(microsecond=0)
    for system in probe_coordinator.data.values():
        probe = system["network_probes"]["monitor"]
        probe["interval"] = interval
        probe["stats"]["created"] = (now.timestamp() - age) * 1000
    with patch(
        "custom_components.beszel.network_probe.dt_util.utcnow", return_value=now
    ):
        assert all(
            sensor.available is expected for sensor in probe_sensors(probe_coordinator)
        )


@pytest.mark.parametrize(
    "change",
    [
        "disabled",
        "down",
        "removed_probe",
        "removed_system",
        "missing_timestamp",
        "invalid_timestamp",
    ],
)
def test_disabled_removed_offline_and_undated_probes_are_unavailable(
    probe_coordinator, change
):
    """An existing sensor becomes unavailable when its source stops reporting."""
    sensor = probe_sensors(probe_coordinator)[0]
    system = probe_coordinator.data["one"]
    probe = system["network_probes"]["monitor"]
    if change == "disabled":
        probe["enabled"] = False
    elif change == "down":
        system["status"] = "down"
    elif change == "removed_probe":
        system["network_probes"] = {}
    elif change == "removed_system":
        del probe_coordinator.data["one"]
    else:
        probe["stats"]["created"] = None if change == "missing_timestamp" else "invalid"
    assert not sensor.available


def test_ipv6_tcp_target_is_unambiguous(probe_coordinator):
    """IPv6 targets include brackets before the TCP port."""
    probe_coordinator.data["one"]["network_probes"]["monitor"]["target"] = "2001:db8::1"
    assert (
        "[2001:db8::1]:443"
        in probe_sensors(probe_coordinator)[0].translation_placeholders["probe"]
    )
