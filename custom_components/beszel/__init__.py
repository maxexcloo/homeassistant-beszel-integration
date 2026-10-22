"""The Beszel integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import BeszelApiClient
from .const import DEFAULT_UPDATE_INTERVAL_SECONDS, PLATFORMS
from .coordinator import BeszelDataUpdateCoordinator
from .entity import device_identifier


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


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device_entry):
    """Allow removing devices for systems the Beszel Hub no longer reports."""
    reported = {
        device_identifier(entry.entry_id, system_id)
        for system_id in entry.runtime_data.data
    }
    return reported.isdisjoint(device_entry.identifiers)
