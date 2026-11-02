"""Container sensors in a device per container under its Beszel system."""

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
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CONTAINER_CPU,
    ATTR_CONTAINER_HEALTH,
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_MEMORY,
    ATTR_CONTAINER_NAME,
    ATTR_CONTAINER_NET,
    ATTR_CONTAINER_UPDATED,
    MANUFACTURER,
    STATS_MAX_AGE,
)
from .entity import (
    BeszelEntity,
    as_number,
    container_identifier,
    device_identifier,
    entity_unique_id,
)

# Beszel DockerHealth codes in order.
HEALTH_STATES = ["none", "starting", "healthy", "unhealthy"]

CONTAINER_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key=ATTR_CONTAINER_CPU,
        translation_key="container_cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_CONTAINER_HEALTH,
        translation_key="container_health",
        device_class=SensorDeviceClass.ENUM,
        options=HEALTH_STATES,
    ),
    SensorEntityDescription(
        key=ATTR_CONTAINER_MEMORY,
        translation_key="container_memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_CONTAINER_NET,
        translation_key="container_network_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_CONTAINER_UPDATED,
        translation_key="container_last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


def container_details(container_id, container):
    """Return registry details for a container."""
    return {
        "model": container.get(ATTR_CONTAINER_IMAGE) or None,
        "name": container.get(ATTR_CONTAINER_NAME) or container_id,
    }


def _container_value(container, key):
    value = as_number(container.get(key))
    if value is None or value < 0:
        return None
    if key == ATTR_CONTAINER_HEALTH:
        return HEALTH_STATES[int(value)] if value < len(HEALTH_STATES) else None
    if key == ATTR_CONTAINER_MEMORY:
        # Beszel reports binary megabytes.
        return round(value * 1024**2 / 1_000_000, 2)
    if key == ATTR_CONTAINER_NET:
        # Beszel reports combined sent and received bytes per second.
        return round(value / 1_000_000, 2)
    if key == ATTR_CONTAINER_UPDATED:
        return dt_util.utc_from_timestamp(value / 1000) if value else None
    return round(value, 2)


def _container_unique_id(coordinator, system_id, container_id, description):
    return entity_unique_id(
        coordinator.config_entry.entry_id,
        system_id,
        f"container_{container_id}_{description.key}",
    )


def create_container_sensors(coordinator, known_unique_ids):
    """Discover container measurements as they appear on any system."""
    entities = []
    for system_id, system in coordinator.data.items():
        for container_id, container in system.get("containers", {}).items():
            for description in CONTAINER_SENSOR_DESCRIPTIONS:
                unique_id = _container_unique_id(
                    coordinator, system_id, container_id, description
                )
                if (
                    unique_id not in known_unique_ids
                    and _container_value(container, description.key) is not None
                ):
                    entities.append(
                        BeszelContainerSensor(
                            coordinator, system_id, container_id, description
                        )
                    )
    return entities


class BeszelContainerSensor(BeszelEntity, SensorEntity):
    """A container measurement in the container's own device."""

    def __init__(self, coordinator, system_id, container_id, description):
        """Initialise the sensor with stable Hub, system and container identities."""
        super().__init__(coordinator, system_id)
        self.entity_description = description
        self._container_id = container_id
        self._attr_unique_id = _container_unique_id(
            coordinator, system_id, container_id, description
        )

    @property
    def container(self):
        """Return the latest report for this container."""
        return self.system_data.get("containers", {}).get(self._container_id, {})

    @property
    def available(self):
        """Require a reported container and, for measurements, a fresh report."""
        if not super().available or not self.container:
            return False
        if self.entity_description.key == ATTR_CONTAINER_UPDATED:
            return True
        updated = _container_value(self.container, ATTR_CONTAINER_UPDATED)
        return (
            self.is_up
            and updated is not None
            and timedelta(0) <= dt_util.utcnow() - updated <= STATS_MAX_AGE
        )

    @property
    def device_info(self):
        """Group the container's sensors in a device under its system."""
        entry_id = self.coordinator.config_entry.entry_id
        device_info = {
            "identifiers": {
                container_identifier(entry_id, self._system_id, self._container_id)
            },
            "manufacturer": MANUFACTURER,
            **container_details(self._container_id, self.container),
        }
        system = dr.async_get(self.hass).async_get_device_by_identifier(
            device_identifier(entry_id, self._system_id), entry_id
        )
        if system is not None:
            device_info["via_device_id"] = system.id
        return device_info

    @property
    def native_value(self):
        """Return the measurement without fabricating missing values."""
        return _container_value(self.container, self.entity_description.key)
