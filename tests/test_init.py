"""Tests for Beszel integration setup."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel import async_remove_config_entry_device
from custom_components.beszel.const import DOMAIN
from custom_components.beszel.diagnostics import async_get_config_entry_diagnostics


async def test_integration_setup_update_and_unload(hass, freezer):
    """Register real entities, discover updates and remove every listener on unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Beszel",
        data={
            "host": "http://beszel.local",
            "password": "password",
            "username": "user",
        },
        version=3,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    prefix = f"beszel_{entry.entry_id}_system"
    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as api_class:
        api = api_class.return_value
        api.host = "http://beszel.local"
        api.async_get_containers.return_value = [
            {
                "id": "c1",
                "system": "system",
                "cpu": 1,
                "updated": dt_util.utcnow().timestamp() * 1000,
            }
        ]
        api.async_get_network_monitors.return_value = []
        api.async_get_smart_devices.return_value = []
        api.async_get_systems = AsyncMock(
            return_value=[
                {
                    "id": "system",
                    "name": "Server",
                    "status": "up",
                    "info": {
                        "dt": 42.5,
                        "pu": [8, 2],
                        "sv": [60, 1],
                        "u": 90,
                        "v": "0.18.0",
                    },
                }
            ]
        )
        api.async_get_system_details = AsyncMock(return_value={"system": {"os": 0}})
        api.async_get_latest_system_stats = AsyncMock(
            return_value={
                "system": {
                    "created": dt_util.utcnow().isoformat(),
                    "stats": {
                        "bat": [80, 3],
                        "cpu": 12.5,
                        "efs": {"data": {"d": 100}},
                        "g": {"0": {"n": "Graphics", "u": 25}},
                        "t": {"cpu": 45, "cpu_thermal": 46},
                    },
                }
            }
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        def state(suffix, platform="sensor"):
            entity_id = registry.async_get_entity_id(
                platform, DOMAIN, f"{prefix}_{suffix}"
            )
            assert entity_id is not None
            return hass.states.get(entity_id)

        assert state("stats_cpu").state == "12.5"
        assert state("stats_cpu").attributes["unit_of_measurement"] == "%"
        assert state("temperature_cpu").state == "45.0"
        assert state("temperature_cpu").attributes["device_class"] == "temperature"
        assert state("temperature_cpu_thermal").state == "46.0"
        assert state("stats_battery_state").state == "charging"
        assert state("stats_efs_data_d").state == "107.37"
        assert state("stats_g_0_u").state == "25.0"
        assert state("info_os").state == "Linux"
        assert state("info_u").state == "90"
        assert state("info_v").state == "0.18.0"
        assert state("info_dt").state == "42.5"
        assert state("info_dt").attributes["device_class"] == "temperature"
        for suffix, expected in (
            ("services", "60"),
            ("failed_services", "1"),
            ("package_updates", "8"),
            ("security_updates", "2"),
        ):
            assert state(f"info_{suffix}").state == expected
            assert registry.async_get(
                state(f"info_{suffix}").entity_id
            ).entity_category == (EntityCategory.DIAGNOSTIC)
        assert state("container_c1_cpu").state == "1.0"
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 18
        assert state("info_os").attributes.get("icon") == "mdi:linux"
        assert registry.async_get(state("info_os").entity_id).entity_category == (
            EntityCategory.DIAGNOSTIC
        )
        assert "state_class" not in state("info_u").attributes
        assert "state_class" not in state("stats_efs_data_d").attributes
        assert registry.async_get(
            state("stats_efs_data_d").entity_id
        ).entity_category == (EntityCategory.DIAGNOSTIC)

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["config_entry"]["data"] == {
            "host": "http://beszel.local",
            "password": "**REDACTED**",
            "username": "**REDACTED**",
        }
        assert diagnostics["systems"]["system"]["stats"]["cpu"] == 12.5

        api.async_get_systems.return_value[0]["info"] = {}
        api.async_get_system_details.return_value = {}
        disk = {
            "cycles": 0,
            "hours": 120,
            "id": "disk",
            "name": "nvme0",
            "state": "PASSED",
            "system": "system",
            "temp": 37,
        }
        api.async_get_smart_devices.return_value = [disk]
        api.async_get_latest_system_stats.return_value = {
            "system": {
                "stats": {"b": [None, 1572864], "la": [0, 0.3, 0.15], "t": {"cpu": 47}},
                "created": dt_util.utcnow().isoformat(),
            }
        }
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.57"
        for minutes, expected in ((1, "0.0"), (5, "0.3"), (15, "0.15")):
            load = state(f"stats_load_average_{minutes}m")
            assert load.state == expected
            assert load.attributes["state_class"] == "measurement"
            assert "unit_of_measurement" not in load.attributes
        assert state("smart_disk_state", "binary_sensor").state == "off"
        assert state("smart_disk_state", "binary_sensor").attributes[
            "device_class"
        ] == ("problem")
        assert state("smart_disk_temp").state == "37.0"
        assert state("smart_disk_hours").state == "120.0"
        assert state("smart_disk_cycles").state == "0.0"
        assert state("temperature_cpu").state == "47.0"
        assert state("stats_cpu").state == "unknown"
        assert state("info_os").state == "unknown"
        for suffix in (
            "dt",
            "services",
            "failed_services",
            "package_updates",
            "security_updates",
        ):
            assert state(f"info_{suffix}").state == "unknown"
        assert coordinator._listeners

        device_registry = dr.async_get(hass)
        reported = device_registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_system"), entry.entry_id
        )
        removed = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_removed")},
        )
        container = device_registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_system_container_c1"), entry.entry_id
        )
        assert container.via_device_id == reported.id
        assert not await async_remove_config_entry_device(hass, entry, reported)
        assert not await async_remove_config_entry_device(hass, entry, container)
        assert await async_remove_config_entry_device(hass, entry, removed)

        api.async_get_latest_system_stats.side_effect = RuntimeError("stats failed")
        disk["state"] = "FAILED"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.57"
        assert state("smart_disk_state", "binary_sensor").state == "on"
        cached = coordinator.data["system"]["stats"]
        freezer.tick(301)
        api.async_get_smart_devices.side_effect = RuntimeError("S.M.A.R.T. failed")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "unavailable"
        assert state("stats_load_average_1m").state == "unavailable"
        assert state("smart_disk_state", "binary_sensor").state == "on"
        assert coordinator.data["system"]["stats"] == cached
        assert state("info_u").state == "unknown"
        assert state("status_status").state == "up"

        api.async_get_systems.return_value[0]["status"] = "down"
        api.async_get_smart_devices.side_effect = None
        disk["state"] = "UNKNOWN"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "unavailable"
        assert state("status_status").state == "down"
        assert state("smart_disk_state", "binary_sensor").state == "unknown"

        api.async_get_smart_devices.return_value = []
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("smart_disk_state", "binary_sensor").state == "unavailable"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners
        assert state("stats_cpu").state == "unavailable"


async def test_probe_device_is_discovered_updated_and_removable(hass, freezer):
    """Discover probes on later refreshes and maintain the shared device lifecycle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Beszel",
        data={
            "host": "http://beszel.local",
            "password": "password",
            "username": "user",
        },
        version=3,
    )
    entry.add_to_hass(hass)
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    identifier = (DOMAIN, f"{entry.entry_id}_network_probes")
    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as api_class:
        api = api_class.return_value
        api.host = "http://beszel.local"
        api.async_get_systems.return_value = [
            {"id": system, "name": system, "status": "up"} for system in ("one", "two")
        ]
        api.async_get_system_details.return_value = {}
        api.async_get_latest_system_stats.return_value = {}
        api.async_get_containers.return_value = []
        api.async_get_network_monitors.return_value = []
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert (
            devices.async_get_device_by_identifier(identifier, entry.entry_id) is None
        )

        api.async_get_network_monitors.return_value = [
            {
                "id": system,
                "system": system,
                "target": "example.com",
                "protocol": "icmp",
                "enabled": True,
                "interval": 30,
            }
            for system in ("one", "two")
        ]
        sample = {
            "created": int(dt_util.utcnow().timestamp() * 1000),
            "total_count": 2,
            "success_count": 1,
            "res_sum": 12000,
            "res_min": 12000,
            "res_max": 12000,
        }
        api.async_get_latest_network_monitor_stats.return_value = {
            "one": sample,
            "two": sample,
        }
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        device = devices.async_get_device_by_identifier(identifier, entry.entry_id)
        assert device is not None
        assert device.name == "Network Probes"
        probes = [
            entity
            for entity in er.async_entries_for_config_entry(entities, entry.entry_id)
            if entity.device_id == device.id
        ]
        assert len(probes) == 8
        assert not await async_remove_config_entry_device(hass, entry, device)
        entity_id = entities.async_get_entity_id(
            "sensor", DOMAIN, f"beszel_{entry.entry_id}_one_probe_one_response_time"
        )
        assert hass.states.get(entity_id).state == "12.0"
        assert "one example.com (ICMP)" in hass.states.get(entity_id).name

        monitor = api.async_get_network_monitors.return_value[0]
        monitor.update(target="new.example.com", protocol="tcp", port=443)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert "one new.example.com:443 (TCP)" in hass.states.get(entity_id).name
        entities.async_update_entity(entity_id, name="My Probe")
        monitor["target"] = "other.example.com"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).name == "My Probe"
        assert (
            "other.example.com:443 (TCP)" in entities.async_get(entity_id).original_name
        )

        api.async_get_latest_network_monitor_stats.side_effect = RuntimeError(
            "probe failed"
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "12.0"
        freezer.tick(301)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "unavailable"
        assert len(er.async_entries_for_device(entities, device.id)) == 8

        api.async_get_network_monitors.return_value = []
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert await async_remove_config_entry_device(hass, entry, device)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners


async def test_renumbered_gpus_and_temperatures_are_removed(hass):
    """Remove replaced GPU and suffixed temperature entities only from fresh reports."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Beszel",
        data={
            "host": "http://beszel.local",
            "password": "password",
            "username": "user",
        },
        version=3,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    prefix = f"beszel_{entry.entry_id}_system"

    def stats(gpu_key, suffix, temperatures=True):
        return {
            "system": {
                "created": dt_util.utcnow().isoformat(),
                "stats": {
                    "g": {
                        gpu_key: {"n": f"GPU {gpu_key}", "u": 1},
                        "x": {"n": "GPU x", "u": 1},
                    },
                    "t": {
                        "acpitz": 40,
                        "edge": 50,
                        f"edge_{suffix}": 51,
                        f"GPU {gpu_key}": 52,
                    }
                    if temperatures
                    else {},
                },
            }
        }

    def unique_ids():
        return {
            entity.unique_id.removeprefix(f"{prefix}_")
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if "_g_" in entity.unique_id or "temperature_" in entity.unique_id
        }

    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as api_class:
        api = api_class.return_value
        api.host = "http://beszel.local"
        api.async_get_containers.return_value = []
        api.async_get_network_monitors.return_value = []
        api.async_get_systems.return_value = [
            {"id": "system", "name": "Server", "status": "up"}
        ]
        api.async_get_system_details.return_value = {}
        api.async_get_latest_system_stats.return_value = stats("1", 7)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert unique_ids() == {
            "stats_g_1_u",
            "stats_g_x_u",
            "temperature_GPU 1",
            "temperature_acpitz",
            "temperature_edge",
            "temperature_edge_7",
        }

        initial = unique_ids()
        api.async_get_systems.return_value = [
            {"id": "system", "name": "Server", "status": "down"}
        ]
        api.async_get_latest_system_stats.return_value = stats("2", 9)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert initial <= unique_ids()

        api.async_get_systems.return_value = [
            {"id": "system", "name": "Server", "status": "up"}
        ]
        api.async_get_latest_system_stats.return_value = stats("2", 9, False)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert "stats_g_1_u" not in unique_ids()
        assert {"temperature_GPU 1", "temperature_edge_7"} <= unique_ids()

        stats_2 = stats("2", 9)
        del stats_2["system"]["stats"]["t"]["acpitz"]
        api.async_get_latest_system_stats.return_value = stats_2
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert unique_ids() == {
            "stats_g_2_u",
            "stats_g_x_u",
            "temperature_GPU 2",
            "temperature_acpitz",
            "temperature_edge",
            "temperature_edge_9",
        }
        assert await hass.config_entries.async_unload(entry.entry_id)
