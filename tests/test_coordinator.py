"""Tests for the Beszel data coordinator."""

import unittest

import support  # noqa: F401 - install dependency stand-ins before importing HA
from homeassistant.exceptions import ConfigEntryAuthFailed
from support import FakeHomeAssistant

from custom_components.beszel.api import BeszelApiAuthError
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
        return {"cpu": 12.5}

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


class BeszelDataUpdateCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    """Exercise Beszel coordinator update behaviour."""

    async def test_details_failure_retains_cached_info_with_fresh_statistics(self):
        """A partial details outage must not clear static sensors."""

        class DetailsFailureApi(FakeApiClient):
            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

            async def async_get_system_details(self):
                raise RuntimeError("details unavailable")

        coordinator = BeszelDataUpdateCoordinator(
            FakeHomeAssistant(),
            api_client=DetailsFailureApi(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )
        coordinator.data = {
            "system": {"info": {"c": 4, "m": "CPU", "k": "kernel", "os": 0}}
        }
        with self.assertLogs("custom_components.beszel.coordinator", level="WARNING"):
            data = await coordinator._async_update_data()

        self.assertEqual(data["system"]["info"], coordinator.data["system"]["info"])
        self.assertEqual(data["system"]["stats"], {"cpu": 12.5})

    async def test_results_remain_mapped_and_failures_use_cache(self):
        """Malformed systems do not shift results and failures retain cache."""
        coordinator = BeszelDataUpdateCoordinator(
            FakeHomeAssistant(),
            api_client=FakeApiClient(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )
        coordinator.data = {
            "failed": {
                "id": "failed",
                "info": {},
                "name": "Failed",
                "stats": {"cpu": 20},
                "status": "up",
            }
        }

        with self.assertLogs(
            "custom_components.beszel.coordinator", level="WARNING"
        ) as logs:
            data = await coordinator._async_update_data()

        self.assertEqual(data["healthy"]["stats"], {"cpu": 12.5})
        self.assertEqual(data["failed"]["stats"], {"cpu": 20})
        self.assertEqual(data["failed"]["status"], "down")
        self.assertEqual(data["failed"]["error"], "stats unavailable")
        self.assertTrue(
            all("http://beszel.local" in message for message in logs.output)
        )

    async def test_statistics_authentication_failure_starts_reauthentication(self):
        """An authentication failure for one system is not treated as partial."""

        class AuthenticationFailureApi(FakeApiClient):
            async def async_get_latest_system_stats(self, system_id):
                raise BeszelApiAuthError("expired token")

            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

        coordinator = BeszelDataUpdateCoordinator(
            FakeHomeAssistant(),
            api_client=AuthenticationFailureApi(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )

        with self.assertRaisesRegex(ConfigEntryAuthFailed, "beszel.local"):
            await coordinator._async_update_data()

    async def test_missing_statistics_remain_unavailable(self):
        """A missing latest record remains distinct from empty statistics."""

        class MissingStatisticsApi(FakeApiClient):
            async def async_get_latest_system_stats(self, system_id):
                return None

            async def async_get_systems(self):
                return [{"id": "system", "name": "Server", "status": "up"}]

        coordinator = BeszelDataUpdateCoordinator(
            FakeHomeAssistant(),
            api_client=MissingStatisticsApi(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )

        data = await coordinator._async_update_data()

        self.assertIsNone(data["system"]["info"])
        self.assertIsNone(data["system"]["stats"])

    async def test_system_details_merge_into_info(self):
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
            FakeHomeAssistant(),
            api_client=DetailedApi(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )

        data = await coordinator._async_update_data()

        self.assertEqual(data["system"]["info"]["c"], 4)
        self.assertEqual(data["system"]["info"]["m"], "ARM Cortex-A76")
        self.assertEqual(data["system"]["info"]["k"], "6.1.0-rpi8")
        self.assertEqual(data["system"]["info"]["os"], 0)

    async def test_info_fields_are_not_overridden_by_details(self):
        """Existing info values win over the static details fallback."""

        class DetailedApi(FakeApiClient):
            async def async_get_systems(self):
                return [
                    {
                        "id": "system",
                        "name": "Server",
                        "status": "up",
                        "info": {"k": "legacy-kernel"},
                    }
                ]

            async def async_get_system_details(self):
                return {"system": {"kernel": "new-kernel"}}

        coordinator = BeszelDataUpdateCoordinator(
            FakeHomeAssistant(),
            api_client=DetailedApi(),
            config_entry_id="entry",
            update_interval_seconds=60,
        )

        data = await coordinator._async_update_data()

        self.assertEqual(data["system"]["info"]["k"], "legacy-kernel")
