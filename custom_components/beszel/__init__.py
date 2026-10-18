"""The Beszel integration."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import BeszelApiClient
from .const import DEFAULT_UPDATE_INTERVAL_SECONDS, DOMAIN, PLATFORMS
from .coordinator import BeszelDataUpdateCoordinator


async def async_setup_entry(hass, entry):
    """Set up Beszel from a config entry."""
    api_client = BeszelApiClient(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    coordinator = BeszelDataUpdateCoordinator(
        hass,
        api_client=api_client,
        config_entry=entry,
        update_interval_seconds=DEFAULT_UPDATE_INTERVAL_SECONDS,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(hass, entry):
    """Migrate legacy config and registry identifiers."""
    if entry.version > 3:
        return False
    if entry.version == 3:
        return True

    if entry.version == 1:
        data = {
            CONF_HOST: entry.data["Host"],
            CONF_PASSWORD: entry.data["Password"],
            CONF_USERNAME: entry.data["Username"],
        }
        api_client = BeszelApiClient(
            data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD]
        )

        entity_registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            prefix = f"{DOMAIN}_"
            scoped_prefix = f"{DOMAIN}_{entry.entry_id}_"
            if entity.unique_id.startswith(prefix) and not entity.unique_id.startswith(
                scoped_prefix
            ):
                entity_registry.async_update_entity(
                    entity.entity_id,
                    new_unique_id=f"{scoped_prefix}{entity.unique_id[len(prefix) :]}",
                )

        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        ):
            if device.config_entries != {entry.entry_id}:
                continue
            identifiers = {
                (domain, f"{entry.entry_id}_{identifier}")
                if domain == DOMAIN and not identifier.startswith(f"{entry.entry_id}_")
                else (domain, identifier)
                for domain, identifier in device.identifiers
            }
            if identifiers != device.identifiers:
                device_registry.async_update_device(
                    device.id, new_identifiers=identifiers
                )

        hass.config_entries.async_update_entry(
            entry,
            data={**data, CONF_HOST: api_client.host},
            unique_id=f"{api_client.host}_{data[CONF_USERNAME]}",
            version=2,
        )

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.original_device_class != SensorDeviceClass.TEMPERATURE:
            continue
        prefix, separator, temperature_key = entity.unique_id.partition("_stats_")
        if separator:
            entity_registry.async_update_entity(
                entity.entity_id,
                new_unique_id=f"{prefix}_temperature_{temperature_key}",
            )

    hass.config_entries.async_update_entry(entry, version=3)
    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
