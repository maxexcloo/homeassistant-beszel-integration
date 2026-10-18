"""Sensor platform for Beszel."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AGENT_VERSION,
    ATTR_BANDWIDTH,
    ATTR_BATTERY,
    ATTR_CORES,
    ATTR_CPU_MODEL,
    ATTR_CPU_PERCENT,
    ATTR_DISK_IO,
    ATTR_DISK_IO_STATS,
    ATTR_DISK_PERCENT,
    ATTR_DISK_READ_PS_MB,
    ATTR_DISK_TOTAL_GB,
    ATTR_DISK_USED_GB,
    ATTR_DISK_WRITE_PS_MB,
    ATTR_EXTRA_FS,
    ATTR_FS_DISK_IO_STATS,
    ATTR_FS_DISK_PERCENT,
    ATTR_FS_DISK_READ_PS_MB,
    ATTR_FS_DISK_TOTAL_GB,
    ATTR_FS_DISK_USED_GB,
    ATTR_FS_DISK_WRITE_PS_MB,
    ATTR_GPU_DATA,
    ATTR_GPU_MEM_TOTAL_MB,
    ATTR_GPU_MEM_USED_MB,
    ATTR_GPU_NAME,
    ATTR_GPU_POWER_PACKAGE_W,
    ATTR_GPU_POWER_W,
    ATTR_GPU_USAGE_PERCENT,
    ATTR_KERNEL_VERSION,
    ATTR_MEM_BUFF_CACHE_GB,
    ATTR_MEM_PERCENT,
    ATTR_MEM_TOTAL_GB,
    ATTR_MEM_USED_GB,
    ATTR_MEM_ZFS_ARC_GB,
    ATTR_NET_RECV_PS_MB,
    ATTR_NET_SENT_PS_MB,
    ATTR_OS,
    ATTR_SWAP_PERCENT,
    ATTR_SWAP_TOTAL_GB,
    ATTR_SWAP_USED_GB,
    ATTR_TEMPERATURES,
    ATTR_THREADS,
    ATTR_UPTIME,
    DOMAIN,
)

ValueFunction = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, kw_only=True)
class BeszelSensorDescription(SensorEntityDescription):
    """Describe a Beszel sensor."""

    data_source: str = "stats"
    value_fn: ValueFunction | None = None


def _mapping(value):
    """Return a mapping or an empty mapping for unavailable data."""
    return value if isinstance(value, dict) else {}


def _array_value(data, key, index, precision=2):
    """Return a rounded value from a Beszel array metric."""
    values = data.get(key)
    if not isinstance(values, (list, tuple)) or len(values) <= index:
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return round(float(value), precision)
    except TypeError, ValueError:
        return None


def _data_rate_megabytes(data, byte_key, index, legacy_key):
    """Return MB/s from a byte counter with a legacy MB/s fallback."""
    values = data.get(byte_key)
    if (
        isinstance(values, (list, tuple))
        and len(values) > index
        and values[index] is not None
    ):
        try:
            return round(float(values[index]) / (1024 * 1024), 2)
        except TypeError, ValueError:
            pass
    legacy = data.get(legacy_key)
    if legacy is not None:
        try:
            return round(float(legacy), 2)
        except TypeError, ValueError:
            return None
    return None


def _battery_percent(data):
    """Return the Beszel battery percentage."""
    if not _has_battery(data):
        return None
    value = _array_value(data, ATTR_BATTERY, 0, precision=0)
    return int(value) if value is not None else None


def _battery_state(data):
    """Return the Beszel battery charge state."""
    if not _has_battery(data):
        return None
    states = {
        0: "unknown",
        1: "empty",
        2: "full",
        3: "charging",
        4: "discharging",
        5: "idle",
    }
    value = _array_value(data, ATTR_BATTERY, 1, precision=0)
    return states.get(int(value), "unknown") if value is not None else None


def _has_battery(data):
    """Return whether Beszel reports a battery."""
    values = data.get(ATTR_BATTERY)
    return (
        isinstance(values, (list, tuple))
        and len(values) >= 2
        and list(values[:2]) != [0, 0]
    )


def _used_percent(data, total_key, used_key):
    """Return a percentage only when both source values are reported."""
    total = data.get(total_key)
    used = data.get(used_key)
    if total is None or used is None:
        return None
    try:
        numeric_total = float(total)
        return round((float(used) / numeric_total) * 100, 2) if numeric_total else 0
    except TypeError, ValueError:
        return None


def _os_name(value):
    """Return the operating-system name for a Beszel type code."""
    return {
        0: "Linux",
        1: "Darwin (macOS)",
        2: "Windows",
        3: "FreeBSD",
    }.get(value)


def _os_icon(value):
    """Return the operating-system icon for a Beszel type code."""
    return {
        0: "mdi:linux",
        1: "mdi:apple",
        2: "mdi:microsoft-windows",
        3: "mdi:freebsd",
    }.get(value)


def _device_details(system_id, system_data):
    """Return registry details for a Beszel system."""
    info = _mapping(system_data.get("info"))
    os_name = _os_name(info.get(ATTR_OS))
    return {
        "model": os_name,
        "name": system_data.get("name", system_id),
        "sw_version": info.get(ATTR_AGENT_VERSION),
    }


def _normalise_value(value, native_unit):
    """Normalise values whose Home Assistant representation is constrained."""
    if value is not None and native_unit == PERCENTAGE:
        try:
            return round(float(value), 2)
        except TypeError, ValueError:
            return None
    return value


def _uptime_value(value):
    """Return a valid duration from a Beszel uptime value."""
    if value is None:
        return None
    try:
        total_seconds = float(value)
    except TypeError, ValueError:
        return None
    if total_seconds < 0:
        return None
    return int(total_seconds) if total_seconds.is_integer() else total_seconds


def _standard_value(system_data, description):
    """Return a value for a standard sensor description."""
    if description.data_source == "status":
        status = str(system_data.get("status")).lower()
        return status if status in description.options else "unknown"

    data = _mapping(system_data.get(description.data_source))
    if description.value_fn:
        return description.value_fn(data)

    value = data.get(description.key)
    if description.key == ATTR_OS and description.data_source == "info":
        return _os_name(value)
    if description.key == ATTR_UPTIME and description.data_source == "info":
        return _uptime_value(value)
    return _normalise_value(value, description.native_unit_of_measurement)


def _nested_value(system_data, parent_key, item_key, description):
    """Return a value from a nested Beszel statistics mapping."""
    stats = _mapping(system_data.get("stats"))
    parent = _mapping(stats.get(parent_key))
    item = _mapping(parent.get(item_key))
    if description.value_fn:
        return description.value_fn(item)
    return _normalise_value(
        item.get(description.key), description.native_unit_of_measurement
    )


INFO_SENSOR_DESCRIPTIONS = (
    BeszelSensorDescription(
        key=ATTR_AGENT_VERSION,
        translation_key="agent_version",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_CORES,
        translation_key="cpu_cores",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_CPU_MODEL,
        translation_key="cpu_model",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_THREADS,
        translation_key="cpu_threads",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_KERNEL_VERSION,
        translation_key="kernel_version",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_OS,
        translation_key="operating_system",
        data_source="info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BeszelSensorDescription(
        key=ATTR_UPTIME,
        translation_key="uptime",
        data_source="info",
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
)

STATS_SENSOR_DESCRIPTIONS = (
    BeszelSensorDescription(
        key="battery_percent",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_battery_percent,
    ),
    BeszelSensorDescription(
        key="battery_state",
        translation_key="battery_state",
        device_class=SensorDeviceClass.ENUM,
        options=["charging", "discharging", "empty", "full", "idle", "unknown"],
        value_fn=_battery_state,
    ),
    BeszelSensorDescription(
        key=ATTR_CPU_PERCENT,
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key="disk_io_utilisation_percent",
        translation_key="disk_io_utilisation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 2),
    ),
    BeszelSensorDescription(
        key="disk_read_await_ms",
        translation_key="disk_read_await",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 3),
    ),
    BeszelSensorDescription(
        key=ATTR_DISK_READ_PS_MB,
        translation_key="disk_read_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _data_rate_megabytes(
            data, ATTR_DISK_IO, 0, ATTR_DISK_READ_PS_MB
        ),
    ),
    BeszelSensorDescription(
        key="disk_read_time_percent",
        translation_key="disk_read_time",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 0),
    ),
    BeszelSensorDescription(
        key=ATTR_DISK_TOTAL_GB,
        translation_key="disk_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_DISK_PERCENT,
        translation_key="disk_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_DISK_USED_GB,
        translation_key="disk_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key="disk_weighted_io_percent",
        translation_key="disk_weighted_io",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 5),
    ),
    BeszelSensorDescription(
        key="disk_write_await_ms",
        translation_key="disk_write_await",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 4),
    ),
    BeszelSensorDescription(
        key=ATTR_DISK_WRITE_PS_MB,
        translation_key="disk_write_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _data_rate_megabytes(
            data, ATTR_DISK_IO, 1, ATTR_DISK_WRITE_PS_MB
        ),
    ),
    BeszelSensorDescription(
        key="disk_write_time_percent",
        translation_key="disk_write_time",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_DISK_IO_STATS, 1),
    ),
    BeszelSensorDescription(
        key=ATTR_MEM_BUFF_CACHE_GB,
        translation_key="memory_buffer_cache",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_MEM_TOTAL_GB,
        translation_key="memory_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_MEM_PERCENT,
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_MEM_USED_GB,
        translation_key="memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_MEM_ZFS_ARC_GB,
        translation_key="memory_zfs_arc",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_NET_RECV_PS_MB,
        translation_key="network_received_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _data_rate_megabytes(
            data, ATTR_BANDWIDTH, 1, ATTR_NET_RECV_PS_MB
        ),
    ),
    BeszelSensorDescription(
        key=ATTR_NET_SENT_PS_MB,
        translation_key="network_sent_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _data_rate_megabytes(
            data, ATTR_BANDWIDTH, 0, ATTR_NET_SENT_PS_MB
        ),
    ),
    BeszelSensorDescription(
        key="status",
        translation_key="status",
        data_source="status",
        device_class=SensorDeviceClass.ENUM,
        options=["down", "paused", "pending", "unknown", "up"],
    ),
    BeszelSensorDescription(
        key=ATTR_SWAP_TOTAL_GB,
        translation_key="swap_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_SWAP_PERCENT,
        translation_key="swap_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _used_percent(
            data, ATTR_SWAP_TOTAL_GB, ATTR_SWAP_USED_GB
        ),
    ),
    BeszelSensorDescription(
        key=ATTR_SWAP_USED_GB,
        translation_key="swap_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

EXTRA_FS_SENSOR_DESCRIPTIONS = (
    BeszelSensorDescription(
        key="io_utilisation_percent",
        translation_key="filesystem_io_utilisation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 2),
    ),
    BeszelSensorDescription(
        key="read_await_ms",
        translation_key="filesystem_read_await",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 3),
    ),
    BeszelSensorDescription(
        key=ATTR_FS_DISK_READ_PS_MB,
        translation_key="filesystem_read_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key="read_time_percent",
        translation_key="filesystem_read_time",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 0),
    ),
    BeszelSensorDescription(
        key=ATTR_FS_DISK_TOTAL_GB,
        translation_key="filesystem_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_FS_DISK_PERCENT,
        translation_key="filesystem_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _used_percent(
            data, ATTR_FS_DISK_TOTAL_GB, ATTR_FS_DISK_USED_GB
        ),
    ),
    BeszelSensorDescription(
        key=ATTR_FS_DISK_USED_GB,
        translation_key="filesystem_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key="weighted_io_percent",
        translation_key="filesystem_weighted_io",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 5),
    ),
    BeszelSensorDescription(
        key="write_await_ms",
        translation_key="filesystem_write_await",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 4),
    ),
    BeszelSensorDescription(
        key=ATTR_FS_DISK_WRITE_PS_MB,
        translation_key="filesystem_write_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key="write_time_percent",
        translation_key="filesystem_write_time",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _array_value(data, ATTR_FS_DISK_IO_STATS, 1),
    ),
)

GPU_SENSOR_DESCRIPTIONS = (
    BeszelSensorDescription(
        key=ATTR_GPU_MEM_TOTAL_MB,
        translation_key="gpu_memory_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_GPU_MEM_USED_MB,
        translation_key="gpu_memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_GPU_POWER_PACKAGE_W,
        translation_key="gpu_package_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_GPU_POWER_W,
        translation_key="gpu_power_draw",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BeszelSensorDescription(
        key=ATTR_GPU_USAGE_PERCENT,
        translation_key="gpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


def _standard_unique_id(coordinator, system_id, description):
    return (
        f"{DOMAIN}_{coordinator.config_entry.entry_id}_{system_id}_"
        f"{description.data_source}_{description.key}"
    )


def _nested_unique_id(coordinator, system_id, parent_key, item_key, api_key):
    return (
        f"{DOMAIN}_{coordinator.config_entry.entry_id}_{system_id}_stats_"
        f"{parent_key}_{item_key}_{api_key}"
    )


def _temperature_unique_id(coordinator, system_id, temperature_key):
    return f"{DOMAIN}_{coordinator.config_entry.entry_id}_{system_id}_temperature_{temperature_key}"


def _create_available_sensors(coordinator, known_unique_ids=None):
    """Create sensors for newly reported Beszel values."""
    known_unique_ids = known_unique_ids or set()
    entities = []
    for system_id, raw_system_data in (coordinator.data or {}).items():
        system_data = _mapping(raw_system_data)

        for description in (*INFO_SENSOR_DESCRIPTIONS, *STATS_SENSOR_DESCRIPTIONS):
            unique_id = _standard_unique_id(coordinator, system_id, description)
            if unique_id in known_unique_ids:
                continue
            value = _standard_value(system_data, description)
            if value is not None:
                entities.append(BeszelSensor(coordinator, system_id, description))

        stats = _mapping(system_data.get("stats"))
        for parent_key, descriptions, placeholder in (
            (ATTR_EXTRA_FS, EXTRA_FS_SENSOR_DESCRIPTIONS, "filesystem"),
            (ATTR_GPU_DATA, GPU_SENSOR_DESCRIPTIONS, "gpu"),
        ):
            items = _mapping(stats.get(parent_key))
            for item_key in sorted(items, key=str):
                item = _mapping(items.get(item_key))
                item_name = (
                    item.get(ATTR_GPU_NAME) or item_key
                    if parent_key == ATTR_GPU_DATA
                    else item_key
                )
                for description in descriptions:
                    unique_id = _nested_unique_id(
                        coordinator,
                        system_id,
                        parent_key,
                        item_key,
                        description.key,
                    )
                    if unique_id in known_unique_ids:
                        continue
                    if (
                        _nested_value(system_data, parent_key, item_key, description)
                        is None
                    ):
                        continue
                    entities.append(
                        BeszelNestedSensor(
                            coordinator,
                            system_id,
                            parent_key,
                            item_key,
                            description,
                            {placeholder: str(item_name)},
                        )
                    )

        temperatures = _mapping(stats.get(ATTR_TEMPERATURES))
        for temperature_name in sorted(temperatures, key=str):
            unique_id = _temperature_unique_id(coordinator, system_id, temperature_name)
            if unique_id in known_unique_ids:
                continue
            value = temperatures.get(temperature_name)
            try:
                value = round(float(value), 1) if value is not None else None
            except TypeError, ValueError:
                value = None
            if value is None:
                continue
            sensor = BeszelTemperatureSensor(coordinator, system_id, temperature_name)
            entities.append(sensor)

    return entities


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Beszel sensor entities based on a config entry."""
    coordinator = entry.runtime_data
    device_registry = dr.async_get(hass)
    known_unique_ids = set()

    def update_registered_devices():
        for system_id, raw_system_data in (coordinator.data or {}).items():
            device = device_registry.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{system_id}"), entry.entry_id
            )
            if device is None:
                continue
            details = _device_details(system_id, _mapping(raw_system_data))
            changes = {
                key: value
                for key, value in details.items()
                if value is not None and getattr(device, key) != value
            }
            if changes:
                device_registry.async_update_device(device.id, **changes)

    @callback
    def async_discover_entities():
        update_registered_devices()
        new_entities = _create_available_sensors(coordinator, known_unique_ids)
        if new_entities:
            known_unique_ids.update(entity.unique_id for entity in new_entities)
            async_add_entities(new_entities)

    async_discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_discover_entities))


class BeszelCoordinatorSensor(CoordinatorEntity, SensorEntity):
    """Base class for a sensor associated with a Beszel system."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, system_id, description):
        """Initialise the system sensor."""
        super().__init__(coordinator)
        self._system_id = system_id
        self.entity_description = description

    @property
    def system_data(self):
        """Return current data for this sensor's system."""
        return _mapping((self.coordinator.data or {}).get(self._system_id))

    @property
    def available(self):
        """Return whether the Hub still reports this system."""
        return super().available and bool(self.system_data)

    @property
    def device_info(self):
        """Return current device information for the system."""
        details = _device_details(self._system_id, self.system_data)
        device_info = {
            "identifiers": {
                (DOMAIN, f"{self.coordinator.config_entry.entry_id}_{self._system_id}")
            },
            "manufacturer": "Beszel",
            "name": details["name"],
        }
        if details["model"]:
            device_info["model"] = details["model"]
        if details["sw_version"]:
            device_info["sw_version"] = details["sw_version"]
        return device_info


class BeszelNestedSensor(BeszelCoordinatorSensor):
    """Sensor for a value nested within a Beszel statistics mapping."""

    def __init__(
        self,
        coordinator,
        system_id,
        parent_key,
        item_key,
        description,
        translation_placeholders,
    ):
        """Initialise the nested sensor."""
        super().__init__(coordinator, system_id, description)
        self._item_key = item_key
        self._parent_key = parent_key
        self._attr_translation_placeholders = translation_placeholders
        self._attr_unique_id = _nested_unique_id(
            coordinator,
            system_id,
            parent_key,
            item_key,
            description.key,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return _nested_value(
            self.system_data,
            self._parent_key,
            self._item_key,
            self.entity_description,
        )


class BeszelSensor(BeszelCoordinatorSensor):
    """Representation of a Beszel sensor."""

    def __init__(self, coordinator, system_id, description):
        """Initialise the sensor."""
        super().__init__(coordinator, system_id, description)
        self._attr_unique_id = _standard_unique_id(coordinator, system_id, description)

    @property
    def icon(self):
        """Return the sensor icon."""
        if (
            self.entity_description.key == ATTR_OS
            and self.entity_description.data_source == "info"
        ):
            info = _mapping(self.system_data.get("info"))
            return _os_icon(info.get(ATTR_OS))
        return None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return _standard_value(self.system_data, self.entity_description)


class BeszelTemperatureSensor(BeszelCoordinatorSensor):
    """Representation of a Beszel temperature sensor."""

    def __init__(self, coordinator, system_id, temperature_key):
        """Initialise the temperature sensor."""
        self._temperature_key = temperature_key
        key_lower = temperature_key.lower()
        is_cpu_temperature = "cpu" in key_lower and "thermal" in key_lower
        translation_key = "cpu_temperature" if is_cpu_temperature else "temperature"
        super().__init__(
            coordinator,
            system_id,
            BeszelSensorDescription(
                key=temperature_key,
                translation_key=translation_key,
                data_source="stats",
                device_class=SensorDeviceClass.TEMPERATURE,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )
        self._attr_unique_id = _temperature_unique_id(
            coordinator, system_id, temperature_key
        )
        if not is_cpu_temperature:
            processed_name = temperature_key.replace("_", " ").title()
            self._attr_translation_placeholders = {
                "temperature": processed_name.replace("Nvme", "NVMe")
            }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        stats = _mapping(self.system_data.get("stats"))
        temperatures = _mapping(stats.get(ATTR_TEMPERATURES))
        value = temperatures.get(self._temperature_key)
        if value is None:
            return None
        try:
            return round(float(value), 1)
        except TypeError, ValueError:
            return None
