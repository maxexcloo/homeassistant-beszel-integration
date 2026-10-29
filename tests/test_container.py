"""Container semantics against Home Assistant's coordinator/entity APIs."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.beszel.container import create_container_sensors
from custom_components.beszel.sensor import BeszelStatisticsTimestamp


def coordinator(report, status="up"):
    """Build only the coordinator state read by these entities."""
    return SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="entry"),
        last_update_success=True,
        data={"system": {"status": status, "containers": {"abcdef": report}}},
    )


@pytest.mark.parametrize(
    "age,available", [(0, True), (300, True), (301, False), (-1, False)]
)
def test_independent_container_age(age, available):
    now = dt_util.utcnow()
    data = {"updated": (now - timedelta(seconds=age)).timestamp() * 1000, "health": 2}
    coord = coordinator(data)
    coord.data["system"]["stats_created"] = now.isoformat()
    with patch("custom_components.beszel.container.dt_util.utcnow", return_value=now):
        sensors = {
            s.entity_description.key: s for s in create_container_sensors(coord, set())
        }
        assert len(sensors) == 5
        assert sensors["health"].available is available
        assert sensors["updated"].available
        assert (sensors["updated"].native_value is None) is (age < 0)


@pytest.mark.parametrize("status", ["down", "pending", "paused", "unknown"])
def test_down_host_keeps_diagnostic_but_hides_measurements(status):
    now = dt_util.utcnow()
    coord = coordinator({"updated": now.timestamp() * 1000, "cpu": 5}, status)
    sensors = create_container_sensors(coord, set())
    for sensor in sensors:
        assert sensor.available is (sensor.entity_description.key == "updated")
    coord.last_update_success = False
    assert all(not sensor.available for sensor in sensors)


def test_identity_rename_recreation_missing_and_discovery():
    coord = coordinator({"name": "Web", "image": "nginx", "updated": 1})
    sensors = create_container_sensors(coord, set())
    ids = {s.unique_id for s in sensors}
    assert create_container_sensors(coord, ids) == []
    assert sensors[0].device_info["via_device"] == ("beszel", "entry_system")
    coord.data["system"]["containers"]["abcdef"]["name"] = "New name"
    assert sensors[0].device_info["name"] == "New name"
    assert {s.unique_id for s in create_container_sensors(coord, set())} == ids
    coord.data["system"]["containers"]["123456"] = {"name": "Web"}
    new = create_container_sensors(coord, ids)
    assert len(new) == 5
    assert ids.isdisjoint({s.unique_id for s in new})
    coord.data["other"] = {"containers": {"abcdef": {"name": "Web"}}}
    assert len({s.unique_id for s in create_container_sensors(coord, set())}) == 15
    coord.data["system"]["containers"] = {}
    assert all(not sensor.available for sensor in sensors)
    assert all(sensor.native_value != "stopped" for sensor in sensors)


def test_host_timestamp_old_down_missing_future_and_disconnect():
    now = dt_util.utcnow()
    coord = coordinator({}, "down")
    old = (now - timedelta(days=1)).isoformat()
    coord.data["system"]["stats_created"] = old
    sensor = BeszelStatisticsTimestamp(coord, "system")
    assert sensor.available
    assert sensor.native_value.isoformat() == old
    for value in (None, "bad", (now + timedelta(days=1)).isoformat()):
        coord.data["system"]["stats_created"] = value
        assert sensor.native_value is None
    coord.last_update_success = False
    assert not sensor.available
    coord.last_update_success = True
    coord.data = {}
    assert not sensor.available
