"""Tests for Beszel integration setup and migration."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel import (
    async_migrate_entry,
    async_remove_config_entry_device,
)
from custom_components.beszel.const import DOMAIN


class TestBeszelMigration:
    """Exercise Beszel config-entry migrations."""

    async def test_future_config_version_is_rejected(self, hass):
        """A downgrade must not accept an unknown config-entry schema."""
        entry = MockConfigEntry(
            data={"future": "value"}, domain=DOMAIN, unique_id="future", version=4
        )
        assert not await async_migrate_entry(hass, entry)
        assert entry.data == {"future": "value"}
        assert entry.version == 4

    async def test_current_config_version_is_unchanged(self, hass):
        """Current config entries need no migration."""
        entry = MockConfigEntry(
            data={"host": "http://beszel.local"},
            domain=DOMAIN,
            unique_id="current",
            version=3,
        )
        assert await async_migrate_entry(hass, entry)
        assert entry.data == {"host": "http://beszel.local"}

    async def test_migrate_legacy_config_and_identifiers(self, hass):
        """Version one entries retain entities with scoped identifiers."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"Host": "beszel.local/", "Password": "password", "Username": "user"},
            unique_id="beszel.local/_user",
            version=1,
        )
        entry.add_to_hass(hass)
        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get_or_create(
            "sensor", DOMAIN, "beszel_system_stats_cpu", config_entry=entry
        )
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, "system")}
        )
        assert await async_migrate_entry(hass, entry)
        migrated_entity = entity_registry.async_get(entity.entity_id)
        migrated_device = device_registry.async_get(device.id)
        assert entry.data == {
            "host": "http://beszel.local",
            "password": "password",
            "username": "user",
        }
        assert entry.unique_id == "http://beszel.local_user"
        assert entry.version == 3
        assert migrated_entity.unique_id == f"beszel_{entry.entry_id}_system_stats_cpu"
        assert migrated_device.identifiers == {(DOMAIN, f"{entry.entry_id}_system")}


async def test_temperature_identifier_migration_preserves_registry_entries(hass):
    """Migrate temperatures without changing entity IDs or unrelated metrics."""
    entry = MockConfigEntry(domain=DOMAIN, version=2)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    prefix = f"beszel_{entry.entry_id}_system"
    temperature = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{prefix}_stats_cpu_thermal",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
        original_device_class=SensorDeviceClass.TEMPERATURE,
    )
    registry.async_update_entity(temperature.entity_id, name="Custom Temperature")
    cpu = registry.async_get_or_create(
        "sensor", DOMAIN, f"{prefix}_stats_cpu", config_entry=entry
    )

    assert await async_migrate_entry(hass, entry)
    migrated = registry.async_get(temperature.entity_id)
    assert migrated.unique_id == f"{prefix}_temperature_cpu_thermal"
    assert migrated.name == "Custom Temperature"
    assert migrated.disabled_by is er.RegistryEntryDisabler.USER
    assert registry.async_get(cpu.entity_id).unique_id == f"{prefix}_stats_cpu"
    assert entry.version == 3
    assert await async_migrate_entry(hass, entry)
    assert registry.async_get(temperature.entity_id).unique_id == migrated.unique_id


async def test_integration_setup_update_and_unload(hass):
    """Register real entities, discover updates and remove every listener on unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Beszel",
        data={
            "host": "http://beszel.local",
            "password": "password",
            "username": "user",
        },
        version=2,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    prefix = f"beszel_{entry.entry_id}_system"
    temperature = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{prefix}_stats_cpu_thermal",
        config_entry=entry,
        original_device_class=SensorDeviceClass.TEMPERATURE,
    )
    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as api_class:
        api = api_class.return_value
        api.host = "http://beszel.local"
        api.async_get_systems = AsyncMock(
            return_value=[
                {
                    "id": "system",
                    "name": "Server",
                    "status": "up",
                    "info": {"os": 0, "u": 90},
                }
            ]
        )
        api.async_get_system_details = AsyncMock(return_value={})
        api.async_get_latest_system_stats = AsyncMock(
            return_value={
                "bat": [80, 3],
                "cpu": 12.5,
                "efs": {"data": {"d": 100}},
                "g": {"0": {"n": "Graphics", "u": 25}},
                "t": {"cpu": 45, "cpu_thermal": 46},
            }
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert entry.version == 3
        assert registry.async_get(temperature.entity_id).unique_id == (
            f"{prefix}_temperature_cpu_thermal"
        )

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
        assert state("stats_efs_data_d").state == "100"
        assert state("stats_g_0_u").state == "25.0"
        assert state("info_os").state == "Linux"
        assert state("info_u").state == "90"
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 10
        assert state("info_os").attributes.get("icon") == "mdi:linux"
        assert registry.async_get(state("info_os").entity_id).entity_category == (
            EntityCategory.DIAGNOSTIC
        )
        assert "state_class" not in state("info_u").attributes

        api.async_get_systems.return_value[0]["info"] = {}
        api.async_get_latest_system_stats.return_value = {"nr": 1.5, "t": {"cpu": 47}}
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.5"
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

        api.async_get_systems.return_value[0]["status"] = "down"
        api.async_get_latest_system_stats.side_effect = RuntimeError("stats failed")
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert state("stats_nr").state == "1.5"
        assert state("status_status").state == "down"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners
        assert state("stats_cpu").state == "unavailable"
