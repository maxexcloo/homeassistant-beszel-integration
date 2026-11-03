"""The Beszel integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BeszelApiClient
from .const import CONF_CONTAINERS, CONF_NETWORK_PROBES, PLATFORMS
from .coordinator import BeszelDataUpdateCoordinator
from .entity import container_identifier, device_identifier, network_probes_identifier


async def async_setup_entry(hass, entry):
    """Set up Beszel from a config entry."""
    api_client = BeszelApiClient(
        async_get_clientsession(hass),
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
    _async_remove_disabled_devices(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _async_remove_disabled_devices(hass, entry):
    """Remove devices, and their entities, for disabled options."""
    containers = entry.options.get(CONF_CONTAINERS, True)
    network_probes = entry.options.get(CONF_NETWORK_PROBES, True)
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if (
            not containers
            and any("_container_" in identifier for _, identifier in device.identifiers)
        ) or (
            not network_probes
            and network_probes_identifier(entry.entry_id) in device.identifiers
        ):
            device_registry.async_remove_device(device.id)


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device_entry):
    """Allow removing devices for systems the Beszel Hub no longer reports."""
    reported = set()
    for system_id, system in entry.runtime_data.data.items():
        reported.add(device_identifier(entry.entry_id, system_id))
        reported.update(
            container_identifier(entry.entry_id, system_id, container_id)
            for container_id in system.get("containers", {})
        )
    if any(system.get("network_probes") for system in entry.runtime_data.data.values()):
        reported.add(network_probes_identifier(entry.entry_id))
    return reported.isdisjoint(device_entry.identifiers)
