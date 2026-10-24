"""Network probe sensors grouped in a single device per Beszel Hub."""

from dataclasses import dataclass
from math import isfinite

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_PROBE_CREATED,
    ATTR_PROBE_RES_MAX,
    ATTR_PROBE_RES_MIN,
    ATTR_PROBE_RES_SUM,
    ATTR_PROBE_SUCCESS_COUNT,
    ATTR_PROBE_TOTAL_COUNT,
    MANUFACTURER,
)
from .entity import BeszelEntity, entity_unique_id, mapping, network_probes_identifier


@dataclass(frozen=True, kw_only=True)
class NetworkProbeDescription(SensorEntityDescription):
    """Describe a value derived from a probe's sample counts."""

    state_class: SensorStateClass = SensorStateClass.MEASUREMENT


PROBE_SENSOR_DESCRIPTIONS = (
    NetworkProbeDescription(
        key="response_time",
        translation_key="probe_response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
    ),
    NetworkProbeDescription(
        key=ATTR_PROBE_RES_MIN,
        translation_key="probe_min_response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
    ),
    NetworkProbeDescription(
        key=ATTR_PROBE_RES_MAX,
        translation_key="probe_max_response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
    ),
    NetworkProbeDescription(
        key="packet_loss",
        translation_key="probe_packet_loss",
        native_unit_of_measurement=PERCENTAGE,
    ),
)


def _number(value):
    """Accept finite measurements, keeping absent or invalid values unknown."""
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        else None
    )


def _probe_value(probe, key):
    stats = mapping(probe.get("stats"))
    total = _number(stats.get(ATTR_PROBE_TOTAL_COUNT))
    successes = _number(stats.get(ATTR_PROBE_SUCCESS_COUNT))
    if total is None or total <= 0 or successes is None or not 0 <= successes <= total:
        return None
    if key == "packet_loss":
        return round(100 * (total - successes) / total, 2)
    if successes == 0:
        return None
    value = _number(stats.get(ATTR_PROBE_RES_SUM if key == "response_time" else key))
    if value is None or value < 0:
        return None
    if key == "response_time":
        value /= successes
    return round(value / 1000, 3)


def create_network_probe_sensors(coordinator, known_unique_ids):
    """Discover probe measurements as they appear on any system."""
    entities = []
    for system_id, system in (coordinator.data or {}).items():
        for monitor_id, probe in mapping(system.get("network_probes")).items():
            for description in PROBE_SENSOR_DESCRIPTIONS:
                unique_id = entity_unique_id(
                    coordinator.config_entry.entry_id,
                    system_id,
                    f"probe_{monitor_id}_{description.key}",
                )
                if (
                    unique_id not in known_unique_ids
                    and _probe_value(probe, description.key) is not None
                ):
                    entities.append(
                        BeszelNetworkProbeSensor(
                            coordinator, system_id, monitor_id, description
                        )
                    )
    return entities


class BeszelNetworkProbeSensor(BeszelEntity, SensorEntity):
    """A probe measurement belonging to the Hub's Network Probes device."""

    def __init__(self, coordinator, system_id, monitor_id, description):
        """Initialise the sensor with stable Hub, system and monitor identities."""
        super().__init__(coordinator, system_id)
        self.entity_description = description
        self._monitor_id = monitor_id
        self._attr_unique_id = entity_unique_id(
            coordinator.config_entry.entry_id,
            system_id,
            f"probe_{monitor_id}_{description.key}",
        )
        probe = self.probe
        target = str(probe.get("target", monitor_id))
        if probe.get("protocol") == "tcp":
            if ":" in target and not target.startswith("["):
                target = f"[{target}]"
            target = f"{target}:{probe.get('port')}"
        self._attr_translation_placeholders = {
            "probe": f"{self.system_data.get('name', system_id)} {target} ({str(probe.get('protocol', '')).upper()})"
        }

    @property
    def probe(self):
        """Return the latest configuration and sample for this monitor."""
        return mapping(
            mapping(self.system_data.get("network_probes")).get(self._monitor_id)
        )

    @property
    def available(self):
        """Require an enabled probe on an online host with a fresh sample."""
        if not super().available or self.system_data.get("status") != "up":
            return False
        probe = self.probe
        if probe.get("enabled") is not True:
            return False
        created = _number(mapping(probe.get("stats")).get(ATTR_PROBE_CREATED))
        if created is None or created <= 0:
            return False
        interval = _number(probe.get("interval"))
        max_age = max(300, (interval or 0) + 120)
        age = dt_util.utcnow().timestamp() - created / 1000
        return 0 <= age <= max_age

    @property
    def device_info(self):
        """Group every system's probes in one device scoped to this Hub entry."""
        return {
            "identifiers": {
                network_probes_identifier(self.coordinator.config_entry.entry_id)
            },
            "manufacturer": MANUFACTURER,
            "name": "Network Probes",
            "configuration_url": f"{self.coordinator.api_client.host}/monitors",
        }

    @property
    def native_value(self):
        """Return packet loss or response time without fabricating measurements."""
        return _probe_value(self.probe, self.entity_description.key)

    @property
    def extra_state_attributes(self):
        """Identify the probing system and target on the shared Hub device."""
        return {
            "system_id": self._system_id,
            "system": self.system_data.get("name", self._system_id),
            **{
                key: self.probe.get(key)
                for key in ("target", "protocol", "port", "interval")
            },
        }
