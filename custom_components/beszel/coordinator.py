"""DataUpdateCoordinator for the Beszel integration."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BeszelApiAuthError
from .const import (
    ATTR_CORES,
    ATTR_CPU_MODEL,
    ATTR_KERNEL_VERSION,
    ATTR_OS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .network_probe import probe_max_age

_LOGGER = logging.getLogger(__name__)

# Beszel system_details fields mapped onto the info keys used in entity IDs.
_DETAILS_TO_INFO = {
    "cores": ATTR_CORES,
    "cpu": ATTR_CPU_MODEL,
    "kernel": ATTR_KERNEL_VERSION,
    "os": ATTR_OS,
}


def _merge_system_info(info, details):
    """Merge static Beszel details into a system info mapping."""
    merged = {
        **(info or {}),
        **{
            info_key: details[detail_key]
            for detail_key, info_key in _DETAILS_TO_INFO.items()
            if details.get(detail_key) not in (None, "")
        },
    }
    return merged or None


class BeszelDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages fetching data from the Beszel API."""

    def __init__(self, hass, api_client, config_entry):
        """Initialise the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=config_entry.options.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                )
            ),
        )
        self._details = {}
        self.container_inventory_complete = False
        self.api_client = api_client

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        self.container_inventory_complete = False
        try:
            systems = await self.api_client.async_get_systems()
            if not systems:
                self.container_inventory_complete = True
                _LOGGER.info("No systems found on Beszel Hub %s", self.api_client.host)
                return {}

            details = await self._fetch_system_details()
            probes = await self._fetch_network_probes(systems)
            containers = await self._fetch_containers(systems)
            records = await asyncio.gather(
                *(
                    self.api_client.async_get_latest_system_stats(system["id"])
                    for system in systems
                ),
                return_exceptions=True,
            )

            all_system_data = {}
            for system, record in zip(systems, records, strict=True):
                system_id = system["id"]
                name = system.get("name", system_id)
                if isinstance(record, (asyncio.CancelledError, BeszelApiAuthError)):
                    raise record
                if isinstance(record, Exception):
                    _LOGGER.error(
                        "Error fetching data from Beszel Hub %s for system %s (%s): %s",
                        self.api_client.host,
                        name,
                        system_id,
                        record,
                    )
                    cached = (self.data or {}).get(system_id, {})
                    record = {
                        "created": cached.get("stats_created"),
                        "stats": cached.get("stats"),
                    }
                all_system_data[system_id] = {
                    "containers": containers.get(system_id, {}),
                    "info": _merge_system_info(
                        system.get("info"), details.get(system_id, {})
                    ),
                    "name": name,
                    "network_probes": probes.get(system_id, {}),
                    "stats": record.get("stats") if record else None,
                    "stats_created": record.get("created") if record else None,
                    "status": system.get("status", "unknown"),
                }

            return all_system_data

        except BeszelApiAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for Beszel Hub {self.api_client.host}: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with Beszel Hub {self.api_client.host}: {err}"
            ) from err

    async def _fetch_containers(self, systems):
        """Keep reports and their original receipt times on partial failure."""
        cached = {
            system["id"]: (self.data or {}).get(system["id"], {}).get("containers", {})
            for system in systems
        }
        try:
            records = await self.api_client.async_get_containers()
            if records is None:
                return {system_id: {} for system_id in cached}
            if not isinstance(records, list):
                raise TypeError("Invalid container inventory")
            containers = {system_id: {} for system_id in cached}
            for record in records:
                if not isinstance(record, dict):
                    raise TypeError("Invalid container record")
                system_id = record.get("system")
                container_id = record.get("id")
                if not isinstance(system_id, str) or not isinstance(container_id, str):
                    raise TypeError("Invalid container identity")
                if not container_id:
                    raise ValueError("Empty container identity")
                if system_id not in containers:
                    continue
                if container_id in containers[system_id]:
                    raise ValueError("Duplicate container identity")
                containers[system_id][container_id] = record
            self.container_inventory_complete = True
            return containers
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - containers are best-effort
            _LOGGER.warning(
                "Error fetching containers from Beszel Hub %s for systems %s: %s",
                self.api_client.host,
                ", ".join(f"{s.get('name', s['id'])} ({s['id']})" for s in systems),
                err,
            )
            return cached

    async def _fetch_network_probes(self, systems):
        """Fetch probes independently, preserving each failed sample's cache."""
        cached = {
            system["id"]: (self.data or {})
            .get(system["id"], {})
            .get("network_probes", {})
            for system in systems
        }
        system_names = ", ".join(
            f"{system.get('name', system['id'])} ({system['id']})" for system in systems
        )
        try:
            monitors = await self.api_client.async_get_network_monitors()
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - probes are best-effort
            _LOGGER.warning(
                "Error fetching network monitors from Beszel Hub %s for systems %s: %s",
                self.api_client.host,
                system_names,
                err,
            )
            return cached

        monitors = [monitor for monitor in monitors if monitor.get("system") in cached]
        probes = {system["id"]: {} for system in systems}
        if not monitors:
            return probes
        # Older samples would be unavailable, so fetch only those still fresh enough.
        max_age = max(probe_max_age(monitor.get("interval")) for monitor in monitors)
        since = (dt_util.utcnow().timestamp() - max_age) * 1000
        try:
            records = await self.api_client.async_get_latest_network_monitor_stats(
                since
            )
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - probes are best-effort
            _LOGGER.warning(
                "Error fetching network probe statistics from Beszel Hub %s "
                "for systems %s: %s",
                self.api_client.host,
                system_names,
                err,
            )
            records = {
                monitor["id"]: cached[monitor["system"]]
                .get(monitor["id"], {})
                .get("stats")
                for monitor in monitors
            }
        for monitor in monitors:
            probes[monitor["system"]][monitor["id"]] = {
                **monitor,
                "stats": records.get(monitor["id"]),
            }
        return probes

    async def _fetch_system_details(self):
        """Fetch static system details, reusing the last details on failure."""
        try:
            self._details = await self.api_client.async_get_system_details()
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - details are best-effort
            _LOGGER.warning(
                "Error fetching system details from Beszel Hub %s: %s",
                self.api_client.host,
                err,
            )
        return self._details
