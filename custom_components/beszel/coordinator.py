"""DataUpdateCoordinator for the Beszel integration."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
        self.api_client = api_client

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            systems = await self.api_client.async_get_systems()
            if not systems:
                _LOGGER.info("No systems found on Beszel Hub %s", self.api_client.host)
                return {}

            details = await self._fetch_system_details()
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
                    "info": _merge_system_info(
                        system.get("info"), details.get(system_id, {})
                    ),
                    "name": name,
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
