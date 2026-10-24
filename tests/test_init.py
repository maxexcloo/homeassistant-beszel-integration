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
        api.async_get_systems = AsyncMock(
            return_value=[
                {
                    "id": "system",
                    "name": "Server",
                    "status": "up",
                    "info": {"u": 90},
                }
            ]
        )
        api.async_get_system_details = AsyncMock(return_value={"system": {"os": 0}})
        api.async_get_latest_system_stats = AsyncMock(
            return_value={
                "created": dt_util.utcnow().isoformat(),
                "stats": {
                    "bat": [80, 3],
                    "cpu": 12.5,
                    "efs": {"data": {"d": 100}},
                    "g": {"0": {"n": "Graphics", "u": 25}},
                    "t": {"cpu": 45, "cpu_thermal": 46},
                },
            }
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        def state(suffix):
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{prefix}_{suffix}"
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
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 10
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
        api.async_get_latest_system_stats.return_value = {
            "stats": {"b": [None, 1572864], "t": {"cpu": 47}},
            "created": dt_util.utcnow().isoformat(),
        }
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.57"
        assert state("temperature_cpu").state == "47.0"
        assert state("stats_cpu").state == "unknown"
        assert state("info_os").state == "unknown"
        assert coordinator._listeners

        device_registry = dr.async_get(hass)
        reported = device_registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_system"), entry.entry_id
        )
        removed = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_removed")},
        )
        assert not await async_remove_config_entry_device(hass, entry, reported)
        assert await async_remove_config_entry_device(hass, entry, removed)

        api.async_get_latest_system_stats.side_effect = RuntimeError("stats failed")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.57"
        cached = coordinator.data["system"]["stats"]
        freezer.tick(301)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "unavailable"
        assert coordinator.data["system"]["stats"] == cached
        assert state("info_u").state == "unknown"
        assert state("status_status").state == "up"

        api.async_get_systems.return_value[0]["status"] = "down"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "unavailable"
        assert state("status_status").state == "down"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners
        assert state("stats_cpu").state == "unavailable"
