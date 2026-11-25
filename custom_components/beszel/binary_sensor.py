"""Binary sensor platform for Beszel."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .const import ATTR_SMART_STATE
from .smart import BeszelSmartEntity, smart_unique_id

SMART_HEALTH = BinarySensorEntityDescription(
    key=ATTR_SMART_STATE,
    translation_key="smart_problem",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)

_SMART_STATES = {"PASSED": False, "WARNING": True, "FAILED": True}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up disk health sensors and discover later disk reports."""
    coordinator = entry.runtime_data
    known_unique_ids = set()

    @callback
    def async_discover_entities():
        new_entities = []
        for system_id, system in coordinator.data.items():
            for disk_id in system.get("smart_devices", {}):
                unique_id = smart_unique_id(
                    coordinator, system_id, disk_id, SMART_HEALTH.key
                )
                if unique_id not in known_unique_ids:
                    known_unique_ids.add(unique_id)
                    new_entities.append(
                        BeszelSmartProblem(
                            coordinator, system_id, disk_id, SMART_HEALTH
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    async_discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_discover_entities))


class BeszelSmartProblem(BeszelSmartEntity, BinarySensorEntity):
    """Whether Beszel reported a problem with a disk."""

    @property
    def is_on(self):
        """Report known problem and healthy states."""
        return _SMART_STATES.get(self.disk.get(ATTR_SMART_STATE))
