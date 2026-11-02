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
    STATS_MAX_AGE,
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


def _system_names(systems):
    """Describe systems by name and ID for log messages."""
    return ", ".join(
        f"{system.get('name', system['id'])} ({system['id']})" for system in systems
    )


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
        self.api_client = api_client

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            systems = await self.api_client.async_get_systems()
            if not systems:
                _LOGGER.info("No systems found on Beszel Hub %s", self.api_client.host)
                return {}

            containers, details, probes, records = await asyncio.gather(
                self._fetch_containers(systems),
                self._fetch_system_details(),
                self._fetch_network_probes(systems),
                self._fetch_system_stats(systems),
            )

            all_system_data = {}
            for system in systems:
                system_id = system["id"]
                record = records.get(system_id, {})
                all_system_data[system_id] = {
                    "containers": containers.get(system_id, {}),
                    "info": _merge_system_info(
                        system.get("info"), details.get(system_id, {})
                    ),
                    "name": system.get("name", system_id),
                    "network_probes": probes.get(system_id, {}),
                    "stats": record.get("stats"),
                    "stats_created": record.get("created"),
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
        """Fetch container reports, reusing the cached reports on failure."""
        try:
            records = await self.api_client.async_get_containers()
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - containers are best-effort
            _LOGGER.warning(
                "Error fetching containers from Beszel Hub %s for systems %s: %s",
                self.api_client.host,
                _system_names(systems),
                err,
            )
            return {
                system_id: system.get("containers", {})
                for system_id, system in (self.data or {}).items()
            }
        containers = {}
        for record in records:
            containers.setdefault(record["system"], {})[record["id"]] = record
        return containers

    async def _fetch_network_probes(self, systems):
        """Fetch probes independently, preserving each failed sample's cache."""
        cached = {
            system["id"]: (self.data or {})
            .get(system["id"], {})
            .get("network_probes", {})
            for system in systems
        }
        try:
            monitors = await self.api_client.async_get_network_monitors()
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - probes are best-effort
            _LOGGER.warning(
                "Error fetching network monitors from Beszel Hub %s for systems %s: %s",
                self.api_client.host,
                _system_names(systems),
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
                _system_names(systems),
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

    async def _fetch_system_stats(self, systems):
        """Fetch fresh statistics records, reusing cached records on failure."""
        try:
            return await self.api_client.async_get_latest_system_stats(
                dt_util.utcnow() - STATS_MAX_AGE
            )
        except BeszelApiAuthError:
            raise
        except Exception as err:  # noqa: BLE001 - statistics keep their cache
            _LOGGER.error(
                "Error fetching statistics from Beszel Hub %s for systems %s: %s",
                self.api_client.host,
                _system_names(systems),
                err,
            )
            return {
                system_id: {
                    "created": system.get("stats_created"),
                    "stats": system.get("stats"),
                }
                for system_id, system in (self.data or {}).items()
            }
