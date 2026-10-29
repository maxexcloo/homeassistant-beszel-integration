"""Offline HA registry lifecycle and partial-failure regression fixtures."""

from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel import async_remove_config_entry_device
from custom_components.beszel.const import DOMAIN
from custom_components.beszel.container import BeszelContainerSensor
from custom_components.beszel.entity import container_identifier
from custom_components.beszel.sensor import BeszelSensor


async def test_container_registry_lifecycle(hass, freezer):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            "host": "http://beszel.local",
            "username": "user",
            "password": "password",
        },
    )
    entry.add_to_hass(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as cls:
        api = cls.return_value
        api.host = "http://beszel.local"
        api.async_get_systems.return_value = [
            {"id": "system", "status": "up", "name": "Host"}
        ]
        api.async_get_system_details.return_value = {}
        api.async_get_latest_system_stats.return_value = {
            "created": dt_util.utcnow().isoformat(),
            "stats": {"cpu": 10},
        }
        api.async_get_network_monitors.return_value = []
        api.async_get_containers.return_value = []
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coord = entry.runtime_data
        sample = {
            "id": "abcdef",
            "system": "system",
            "name": "Web",
            "image": "nginx",
            "updated": int(dt_util.utcnow().timestamp() * 1000),
            "health": 3,
            "cpu": 0,
            "memory": 100,
            "net": 1000,
        }
        api.async_get_containers.return_value = [sample]
        await coord.async_refresh()
        await hass.async_block_till_done()
        device = devices.async_get_device_by_identifier(
            container_identifier(entry.entry_id, "system", "abcdef"), entry.entry_id
        )
        assert device is not None
        assert device.name == "Web"
        assert len(er.async_entries_for_device(entities, device.id)) == 5

        def state(key):
            entity_id = entities.async_get_entity_id(
                "sensor",
                DOMAIN,
                f"beszel_{entry.entry_id}_system_container_abcdef_{key}",
            )
            return hass.states.get(entity_id)

        assert state("health").state == "unhealthy"
        assert state("cpu").state == "0.0"
        assert state("memory").state == "104.86"
        assert state("net").state == "1000.0"
        timestamp = state("updated").state
        assert not await async_remove_config_entry_device(hass, entry, device)
        sample["name"] = "Renamed"
        sample["image"] = "nginx:new"
        await coord.async_refresh()
        await hass.async_block_till_done()
        device = devices.async_get_device_by_identifier(
            container_identifier(entry.entry_id, "system", "abcdef"), entry.entry_id
        )
        assert device.name == "Renamed"
        assert device.model == "nginx:new"
        api.async_get_containers.side_effect = RuntimeError("partial timeout")
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert not await async_remove_config_entry_device(hass, entry, device)
        assert state("updated").state == timestamp
        freezer.tick(301)
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert state("health").state == "unavailable"
        assert state("updated").state == timestamp
        assert len(er.async_entries_for_device(entities, device.id)) == 5
        api.async_get_containers.side_effect = None
        api.async_get_containers.return_value = []
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert state("updated").state == "unavailable"
        assert await async_remove_config_entry_device(hass, entry, device)
        removed_entities = er.async_entries_for_device(entities, device.id)
        removed_unique_ids = {entity.unique_id for entity in removed_entities}
        removed_entity_ids = {entity.entity_id for entity in removed_entities}
        # Exercise the actual HA device/registry removal events and entity teardown.
        # Merely calling the removal permission hook does not remove anything.
        devices.async_remove_device(device.id)
        await hass.async_block_till_done()
        assert devices.async_get(device.id) is None
        assert all(
            entities.async_get(entity_id) is None for entity_id in removed_entity_ids
        )
        assert all(
            hass.states.get(entity_id) is None for entity_id in removed_entity_ids
        )
        sample["updated"] = int(dt_util.utcnow().timestamp() * 1000)
        api.async_get_containers.return_value = [sample]
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert entry.runtime_data is coord
        device = devices.async_get_device_by_identifier(
            container_identifier(entry.entry_id, "system", "abcdef"), entry.entry_id
        )
        assert device is not None
        restored_entities = er.async_entries_for_device(entities, device.id)
        assert len(restored_entities) == 5
        assert {entity.unique_id for entity in restored_entities} == removed_unique_ids
        assert state("health").state == "unhealthy"
        assert state("cpu").state == "0.0"
        assert state("memory").state == "104.86"
        assert state("net").state == "1000.0"
        assert state("updated").state not in ("unknown", "unavailable")
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert len(er.async_entries_for_device(entities, device.id)) == 5
        assert not await async_remove_config_entry_device(hass, entry, device)
        api.async_get_systems.return_value = []
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert coord.container_inventory_complete
        assert await async_remove_config_entry_device(hass, entry, device)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coord._listeners


async def test_disabled_additions_and_disabled_device_removal(hass):
    """Abort disabled adds once; rediscover only after their registry removal."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            "host": "http://beszel.local",
            "username": "user",
            "password": "password",
        },
    )
    entry.add_to_hass(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    prefix = f"beszel_{entry.entry_id}_system_container_abcdef_"
    keys = ("cpu", "health", "memory", "net", "updated")
    for key in keys:
        entities.async_get_or_create(
            "sensor",
            DOMAIN,
            prefix + key,
            config_entry=entry,
            disabled_by=er.RegistryEntryDisabler.USER,
        )
    with (
        patch("custom_components.beszel.BeszelApiClient", autospec=True) as cls,
        patch(
            "custom_components.beszel.container.BeszelContainerSensor",
            wraps=BeszelContainerSensor,
        ) as container_sensor,
        patch(
            "custom_components.beszel.sensor.BeszelSensor", wraps=BeszelSensor
        ) as host_sensor,
    ):
        api = cls.return_value
        api.host = "http://beszel.local"
        api.async_get_systems.return_value = [{"id": "system", "status": "up"}]
        api.async_get_system_details.return_value = {}
        api.async_get_network_monitors.return_value = []
        api.async_get_latest_system_stats.return_value = {
            "created": dt_util.utcnow().isoformat(),
            "stats": {"cpu": 10, "dios": [1, 2, 3, 4, 5, 6]},
        }
        sample = {
            "id": "abcdef",
            "system": "system",
            "name": "Web",
            "updated": int(dt_util.utcnow().timestamp() * 1000),
            "health": 2,
        }
        api.async_get_containers.return_value = [sample]
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coord = entry.runtime_data
        assert container_sensor.call_count == 5
        initial_host_count = host_sensor.call_count
        disabled_host = entities.async_get_entity_id(
            "sensor", DOMAIN, f"beszel_{entry.entry_id}_system_stats_disk_read_await_ms"
        )
        assert disabled_host is not None
        assert (
            entities.async_get(disabled_host).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert hass.states.get(disabled_host) is None
        for _ in range(3):
            await coord.async_refresh()
            await hass.async_block_till_done()
        assert container_sensor.call_count == 5
        assert host_sensor.call_count == initial_host_count
        device = devices.async_get_device_by_identifier(
            container_identifier(entry.entry_id, "system", "abcdef"), entry.entry_id
        )
        assert device is not None
        disabled_entries = er.async_entries_for_device(
            entities, device.id, include_disabled_entities=True
        )
        assert len(disabled_entries) == 5
        assert all(
            item.disabled_by is er.RegistryEntryDisabler.USER
            for item in disabled_entries
        )
        assert all(hass.states.get(item.entity_id) is None for item in disabled_entries)
        entities.async_update_entity(
            disabled_entries[0].entity_id,
            new_entity_id="sensor.renamed_disabled_container",
        )
        await hass.async_block_till_done()
        disabled_entries = er.async_entries_for_device(
            entities, device.id, include_disabled_entities=True
        )
        api.async_get_containers.return_value = []
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert await async_remove_config_entry_device(hass, entry, device)
        devices.async_remove_device(device.id)
        await hass.async_block_till_done()
        assert all(
            entities.async_get(item.entity_id) is None for item in disabled_entries
        )
        api.async_get_containers.return_value = [sample]
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert entry.runtime_data is coord
        assert container_sensor.call_count == 10
        restored_device = devices.async_get_device_by_identifier(
            container_identifier(entry.entry_id, "system", "abcdef"), entry.entry_id
        )
        assert restored_device is not None
        restored = er.async_entries_for_device(
            entities, restored_device.id, include_disabled_entities=True
        )
        assert len(restored) == 5
        assert {item.unique_id for item in restored} == {prefix + key for key in keys}
        assert all(
            item.disabled_by is er.RegistryEntryDisabler.USER for item in restored
        )
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert container_sensor.call_count == 10
        assert host_sensor.call_count == initial_host_count
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coord._listeners
