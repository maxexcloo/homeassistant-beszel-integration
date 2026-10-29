"""The Beszel integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import BeszelApiClient
from .const import DOMAIN, PLATFORMS
from .coordinator import BeszelDataUpdateCoordinator
from .entity import container_identifier, device_identifier, network_probes_identifier


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
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device_entry):
    """Allow removing devices for systems the Beszel Hub no longer reports."""
    reported = {
        device_identifier(entry.entry_id, system_id)
        for system_id in entry.runtime_data.data
    }
    if any(system.get("network_probes") for system in entry.runtime_data.data.values()):
        reported.add(network_probes_identifier(entry.entry_id))
    for system_id, system in entry.runtime_data.data.items():
        for container_id in system.get("containers", {}):
            reported.add(container_identifier(entry.entry_id, system_id, container_id))
    is_container = any(
        domain == DOMAIN and "_container_" in identifier
        for domain, identifier in device_entry.identifiers
    )
    if is_container and (
        not entry.runtime_data.last_update_success
        or not entry.runtime_data.container_inventory_complete
    ):
        return False
    return reported.isdisjoint(device_entry.identifiers)
