"""Shared entity helpers for the Beszel integration."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_AGENT_VERSION, ATTR_OS, DOMAIN, MANUFACTURER, OPERATING_SYSTEMS


def mapping(value):
    """Return a mapping or an empty mapping for unavailable data."""
    return value if isinstance(value, dict) else {}


def device_identifier(entry_id, system_id):
    """Return the device registry identifier for a Beszel system."""
    return (DOMAIN, f"{entry_id}_{system_id}")


def entity_unique_id(entry_id, system_id, suffix):
    """Return the unique ID for an entity of a Beszel system."""
    return f"{DOMAIN}_{entry_id}_{system_id}_{suffix}"


def network_probes_identifier(entry_id):
    """Return the identifier of the Hub's shared Network Probes device."""
    return (DOMAIN, f"{entry_id}_network_probes")


def os_name(value):
    """Return the operating-system name for a Beszel type code."""
    return OPERATING_SYSTEMS.get(value, (None, None))[0]


def os_icon(value):
    """Return the operating-system icon for a Beszel type code."""
    return OPERATING_SYSTEMS.get(value, (None, None))[1]


def device_details(system_id, system_data):
    """Return registry details for a Beszel system."""
    info = mapping(system_data.get("info"))
    return {
        "model": os_name(info.get(ATTR_OS)),
        "name": system_data.get("name", system_id),
        "sw_version": info.get(ATTR_AGENT_VERSION),
    }


class BeszelEntity(CoordinatorEntity):
    """Base class for an entity associated with a Beszel system."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, system_id):
        """Initialise the system entity."""
        super().__init__(coordinator)
        self._system_id = system_id

    @property
    def system_data(self):
        """Return current data for this entity's system."""
        return mapping((self.coordinator.data or {}).get(self._system_id))

    @property
    def available(self):
        """Return whether the Hub still reports this system."""
        return super().available and bool(self.system_data)

    @property
    def device_info(self):
        """Return current device information for the system."""
        details = device_details(self._system_id, self.system_data)
        device_info = {
            "identifiers": {
                device_identifier(
                    self.coordinator.config_entry.entry_id, self._system_id
                )
            },
            "manufacturer": MANUFACTURER,
            "name": details["name"],
        }
        if details["model"]:
            device_info["model"] = details["model"]
        if details["sw_version"]:
            device_info["sw_version"] = details["sw_version"]
        return device_info
