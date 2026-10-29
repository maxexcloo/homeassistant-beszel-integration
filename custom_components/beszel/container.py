"""Sensors for last-reported container instances, not expected workloads."""

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.util import dt as dt_util

from .const import MANUFACTURER
from .entity import (
    BeszelEntity,
    container_identifier,
    device_identifier,
    entity_unique_id,
    mapping,
)
from .report import (
    CONTAINER_CPU,
    CONTAINER_HEALTH,
    CONTAINER_MEMORY,
    CONTAINER_NET,
    CONTAINER_UPDATED,
    HEALTH_OPTIONS,
    container_timestamp,
    container_value,
)

CONTAINER_DESCRIPTIONS = (
    SensorEntityDescription(
        key=CONTAINER_CPU,
        translation_key="container_cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=CONTAINER_HEALTH,
        translation_key="container_health",
        device_class=SensorDeviceClass.ENUM,
        options=HEALTH_OPTIONS,
    ),
    SensorEntityDescription(
        key=CONTAINER_MEMORY,
        translation_key="container_memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=CONTAINER_NET,
        translation_key="container_network",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=CONTAINER_UPDATED,
        translation_key="container_last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


def container_device_details(container_id, report):
    """Return mutable display metadata while retaining the instance identifier."""
    name, image = report.get("name"), report.get("image")
    return {
        "name": name if isinstance(name, str) and name else container_id,
        "model": image if isinstance(image, str) and image else "Container",
    }


def create_container_sensors(coordinator, known_unique_ids):
    """Discover the five sensor types even before their first usable value."""
    entities = []
    for system_id, system in (coordinator.data or {}).items():
        for container_id in mapping(system.get("containers")):
            for description in CONTAINER_DESCRIPTIONS:
                unique_id = entity_unique_id(
                    coordinator.config_entry.entry_id,
                    system_id,
                    f"container_{container_id}_{description.key}",
                )
                if unique_id not in known_unique_ids:
                    entities.append(
                        BeszelContainerSensor(
                            coordinator, system_id, container_id, description
                        )
                    )
    return entities


class BeszelContainerSensor(BeszelEntity, SensorEntity):
    """A runtime instance report with its own receipt-time freshness guard."""

    def __init__(self, coordinator, system_id, container_id, description):
        """Scope identity to entry, host, runtime instance and measurement."""
        super().__init__(coordinator, system_id)
        self._container_id = container_id
        self.entity_description = description
        self._attr_unique_id = entity_unique_id(
            coordinator.config_entry.entry_id,
            system_id,
            f"container_{container_id}_{description.key}",
        )

    @property
    def report(self):
        """Return only this instance's current or cached report."""
        return mapping(
            mapping(self.system_data.get("containers")).get(self._container_id)
        )

    @property
    def available(self):
        """Stale reports cannot assert current health or resource consumption."""
        if not super().available or not self.report:
            return False
        if self.entity_description.key == CONTAINER_UPDATED:
            return True
        now = dt_util.utcnow()
        timestamp = container_timestamp(self.report.get(CONTAINER_UPDATED), now)
        return (
            str(self.system_data.get("status")).lower() == "up"
            and timestamp is not None
            and timedelta(0) <= now - timestamp <= timedelta(minutes=5)
        )

    @property
    def native_value(self):
        """Report unknown values without manufacturing healthy or zero states."""
        return container_value(
            self.report, self.entity_description.key, dt_util.utcnow()
        )

    @property
    def device_info(self):
        """Link the runtime instance to its host; names are not identifiers."""
        entry_id = self.coordinator.config_entry.entry_id
        return {
            "identifiers": {
                container_identifier(entry_id, self._system_id, self._container_id)
            },
            "via_device": device_identifier(entry_id, self._system_id),
            "manufacturer": MANUFACTURER,
            **container_device_details(self._container_id, self.report),
        }
