"""S.M.A.R.T. disk measurements reported by Beszel."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime

from .const import (
    ATTR_SMART_CYCLES,
    ATTR_SMART_HOURS,
    ATTR_SMART_NAME,
    ATTR_SMART_TEMPERATURE,
)
from .entity import BeszelEntity, as_number, entity_unique_id

SMART_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key=ATTR_SMART_CYCLES,
        translation_key="smart_power_cycles",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key=ATTR_SMART_HOURS,
        translation_key="smart_power_on_hours",
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key=ATTR_SMART_TEMPERATURE,
        translation_key="smart_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


def _smart_value(disk, key):
    """Return the reported number, treating zero temperature as missing."""
    value = as_number(disk.get(key))
    if value == 0 and key == ATTR_SMART_TEMPERATURE:
        return None
    return value


def smart_unique_id(coordinator, system_id, disk_id, key):
    """Return an entity ID scoped to the Hub, system and stable disk record."""
    return entity_unique_id(
        coordinator.config_entry.entry_id, system_id, f"smart_{disk_id}_{key}"
    )


def create_smart_sensors(coordinator, known_unique_ids):
    """Discover disk measurements as they appear."""
    entities = []
    for system_id, system in coordinator.data.items():
        for disk_id, disk in system.get("smart_devices", {}).items():
            for description in SMART_SENSOR_DESCRIPTIONS:
                unique_id = smart_unique_id(
                    coordinator, system_id, disk_id, description.key
                )
                if (
                    unique_id not in known_unique_ids
                    and _smart_value(disk, description.key) is not None
                ):
                    entities.append(
                        BeszelSmartSensor(coordinator, system_id, disk_id, description)
                    )
    return entities


class BeszelSmartEntity(BeszelEntity):
    """An entity scoped to a disk record on a Beszel system."""

    def __init__(self, coordinator, system_id, disk_id, description):
        """Initialise the entity with the disk's stable Hub ID."""
        super().__init__(coordinator, system_id)
        self.entity_description = description
        self._disk_id = disk_id
        self._attr_unique_id = smart_unique_id(
            coordinator, system_id, disk_id, description.key
        )
        self._attr_translation_placeholders = {
            "disk": self.disk.get(ATTR_SMART_NAME) or disk_id
        }

    @property
    def disk(self):
        """Return the last disk report from the Hub."""
        return self.system_data.get("smart_devices", {}).get(self._disk_id, {})

    @property
    def available(self):
        """Keep the last report available until the Hub stops reporting the disk."""
        return super().available and bool(self.disk)


class BeszelSmartSensor(BeszelSmartEntity, SensorEntity):
    """A disk temperature or lifetime counter."""

    @property
    def native_value(self):
        """Return the disk measurement."""
        return _smart_value(self.disk, self.entity_description.key)
