"""Tests for the Beszel data coordinator."""

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel.api import BeszelApiAuthError
from custom_components.beszel.const import DOMAIN
from custom_components.beszel.coordinator import BeszelDataUpdateCoordinator


class FakeApiClient:
    """Return deterministic Beszel data."""

    host = "http://beszel.local"

    async def async_authenticate(self):
        """Authenticate successfully."""

    async def async_get_latest_system_stats(self, system_id):
        """Return stats or fail for one system."""
        if system_id == "failed":
            raise RuntimeError("stats unavailable")
        return {"stats": {"cpu": 12.5}, "created": dt_util.utcnow().isoformat()}

    async def async_get_system_details(self):
        """Return no static system details by default."""
        return {}

    async def async_get_systems(self):
        """Return one malformed and two valid systems."""
        return [
            {"name": "Malformed"},
            {"id": "healthy", "name": "Healthy", "status": "up"},
            {"id": "failed", "name": "Failed", "status": "down"},
        ]


class TestBeszelDataUpdateCoordinator:
    """Exercise Beszel coordinator update behaviour."""

    async def test_details_failure_retains_cached_info_with_fresh_statistics(
        self, hass, caplog
    ):
        """A partial details outage must not clear static sensors."""

        class DetailsFailureApi(FakeApiClient):
            details_available = True

            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

            async def async_get_system_details(self):
                if not self.details_available:
                    raise RuntimeError("details unavailable")
                return {"system": {"cores": 4, "cpu": "CPU", "kernel": "k", "os": 0}}

        api = DetailsFailureApi()
        coordinator = BeszelDataUpdateCoordinator(
            hass,
            api_client=api,
            config_entry=MockConfigEntry(domain=DOMAIN),
            update_interval_seconds=60,
        )
        info = (await coordinator._async_update_data())["system"]["info"]
        api.details_available = False
        with caplog.at_level("WARNING", logger="custom_components.beszel.coordinator"):
            data = await coordinator._async_update_data()
        assert data["system"]["info"] == info == {"c": 4, "k": "k", "m": "CPU", "os": 0}
        assert data["system"]["stats"] == {"cpu": 12.5}
        assert "details unavailable" in caplog.text

    async def test_results_remain_mapped_and_failures_use_cache(self, hass, caplog):
        """Malformed systems do not shift results and failures retain cache."""
        coordinator = BeszelDataUpdateCoordinator(
            hass,
            api_client=FakeApiClient(),
            config_entry=MockConfigEntry(domain=DOMAIN),
            update_interval_seconds=60,
        )
        coordinator.data = {
            "failed": {
                "id": "failed",
                "name": "Failed",
                "status": "up",
                "info": {},
                "stats": {"cpu": 20},
            }
        }
        with caplog.at_level("WARNING", logger="custom_components.beszel.coordinator"):
            data = await coordinator._async_update_data()
        assert data["healthy"]["stats"] == {"cpu": 12.5}
        assert data["failed"]["stats"] == {"cpu": 20}
        assert data["failed"]["status"] == "down"
        assert all("http://beszel.local" in message for message in caplog.messages)

    async def test_statistics_authentication_failure_starts_reauthentication(
        self, hass
    ):
        """An authentication failure for one system is not treated as partial."""

        class AuthenticationFailureApi(FakeApiClient):
            async def async_get_latest_system_stats(self, system_id):
                raise BeszelApiAuthError("expired token")

            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

        coordinator = BeszelDataUpdateCoordinator(
            hass,
            api_client=AuthenticationFailureApi(),
            config_entry=MockConfigEntry(domain=DOMAIN),
            update_interval_seconds=60,
        )
        with pytest.raises(ConfigEntryAuthFailed, match="beszel.local"):
            await coordinator._async_update_data()

    async def test_missing_statistics_remain_unavailable(self, hass):
        """A missing latest record remains distinct from empty statistics."""

        class MissingStatisticsApi(FakeApiClient):
            async def async_get_latest_system_stats(self, system_id):
                return None

            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

        coordinator = BeszelDataUpdateCoordinator(
            hass,
            api_client=MissingStatisticsApi(),
            config_entry=MockConfigEntry(domain=DOMAIN),
            update_interval_seconds=60,
        )
        data = await coordinator._async_update_data()
        assert data["system"]["info"] is None
        assert data["system"]["stats"] is None

    async def test_system_details_merge_into_info(self, hass):
        """Static details populate the info mapping for newer hubs."""

        class DetailedApi(FakeApiClient):
            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

            async def async_get_system_details(self):
                return {
                    "system": {
                        "cores": 4,
                        "cpu": "ARM Cortex-A76",
                        "kernel": "6.1.0-rpi8",
                        "os": 0,
                    }
                }

        coordinator = BeszelDataUpdateCoordinator(
            hass,
            api_client=DetailedApi(),
            config_entry=MockConfigEntry(domain=DOMAIN),
            update_interval_seconds=60,
        )
        data = await coordinator._async_update_data()
        assert data["system"]["info"]["c"] == 4
        assert data["system"]["info"]["m"] == "ARM Cortex-A76"
        assert data["system"]["info"]["k"] == "6.1.0-rpi8"
        assert data["system"]["info"]["os"] == 0
