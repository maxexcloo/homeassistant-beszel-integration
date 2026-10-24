"""Tests for the Beszel API client."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pocketbase.utils import ClientResponseError

from custom_components.beszel.api import BeszelApiAuthError, BeszelApiClient


class BeszelApiClientTests(unittest.IsolatedAsyncioTestCase):
    """Exercise Beszel API authentication behaviour."""

    async def test_network_monitors_and_native_stats_query(self):
        """Discover all monitors and query the newest one-minute sample by ID."""
        monitors = MagicMock()
        monitors.get_full_list.return_value = [
            SimpleNamespace(id="probe", system="one")
        ]
        sample = {"created": 1792717200000, "total_count": 2, "success_count": 1}
        pocketbase = MagicMock()
        pocketbase.send.return_value = {"items": [sample]}
        pocketbase.collection.side_effect = {
            "network_monitors": monitors,
        }.__getitem__
        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            assert await client.async_get_network_monitors() == [
                {"id": "probe", "system": "one"}
            ]
            assert (
                await client.async_get_latest_network_monitor_stats("probe") == sample
            )
            pocketbase.send.assert_called_once_with(
                "/api/collections/network_monitor_stats/records",
                {
                    "method": "GET",
                    "params": {
                        "page": 1,
                        "perPage": 1,
                        "filter": 'monitor="probe" && type="1m"',
                        "sort": "-created",
                    },
                },
            )
            pocketbase.send.return_value = {"items": []}
            assert await client.async_get_latest_network_monitor_stats("probe") is None

    async def test_only_missing_monitor_collection_is_optional(self):
        """Old Hubs remain supported; auth and temporary failures remain errors."""
        for status in (404, 401, 403, 429, 500):
            with self.subTest(status=status):
                pocketbase = MagicMock()
                pocketbase.collection.return_value.get_full_list.side_effect = (
                    ClientResponseError(status=status)
                )
                with patch(
                    "custom_components.beszel.api.PocketBase", return_value=pocketbase
                ):
                    client = BeszelApiClient("beszel.local", "user", "password")
                    client.async_authenticate = AsyncMock()
                    if status == 404:
                        assert await client.async_get_network_monitors() == []
                    else:
                        error = (
                            BeszelApiAuthError
                            if status in (401, 403)
                            else ClientResponseError
                        )
                        with self.assertRaises(error):
                            await client.async_get_network_monitors()

    async def test_probe_statistics_auth_failure_clears_session(self):
        """Probe statistics authentication errors must trigger reauthentication."""
        pocketbase = MagicMock()
        pocketbase.send.side_effect = ClientResponseError(status=401)
        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            with self.assertRaises(BeszelApiAuthError):
                await client.async_get_latest_network_monitor_stats("probe")
        pocketbase.auth_store.clear.assert_called_once_with()

    async def test_authentication_connection_failures_are_not_invalid_credentials(self):
        """Connection failures and rate limits must remain retryable errors."""
        for status in (0, 408, 429, 500, 503):
            with self.subTest(status=status):
                pocketbase = MagicMock()
                error = ClientResponseError(status=status)
                pocketbase.collection.return_value.auth_with_password.side_effect = (
                    error
                )
                with patch(
                    "custom_components.beszel.api.PocketBase", return_value=pocketbase
                ):
                    client = BeszelApiClient("beszel.local", "user", "password")
                    with self.assertRaises(ClientResponseError) as raised:
                        await client.async_authenticate()

                self.assertIs(raised.exception, error)
                pocketbase.collection.assert_called_once_with("_superusers")

    async def test_invalid_credentials_raise_authentication_failure(self):
        """Rejected credentials still trigger Home Assistant reauthentication."""
        pocketbase = MagicMock()
        pocketbase.collection.return_value.auth_with_password.side_effect = (
            ClientResponseError(status=400)
        )
        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "wrong")
            with self.assertRaises(BeszelApiAuthError):
                await client.async_authenticate()

        self.assertEqual(pocketbase.collection.call_count, 2)

    async def test_authentication_falls_back_to_users(self):
        """Authentication supports current and legacy PocketBase collections."""
        superusers = MagicMock()
        superusers.auth_with_password.side_effect = ClientResponseError(status=404)
        users = MagicMock()

        pocketbase = MagicMock()
        pocketbase.collection.side_effect = {
            "_superusers": superusers,
            "users": users,
        }.get

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local/", "user", "password")
            await client.async_authenticate()

        self.assertEqual(client.host, "http://beszel.local")
        superusers.auth_with_password.assert_called_once_with("user", "password")
        users.auth_with_password.assert_called_once_with("user", "password")

    async def test_authentication_prefers_superusers(self):
        """Authentication stops after the current collection succeeds."""
        superusers = MagicMock()
        users = MagicMock()

        pocketbase = MagicMock()
        pocketbase.collection.side_effect = {
            "_superusers": superusers,
            "users": users,
        }.get

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("https://beszel.local", "user", "password")
            await client.async_authenticate()

        superusers.auth_with_password.assert_called_once_with("user", "password")
        users.auth_with_password.assert_not_called()

    async def test_missing_latest_statistics_returns_none(self):
        """The absence of a statistics record remains unavailable data."""
        collection = MagicMock()
        collection.get_list.return_value = SimpleNamespace(items=[])
        pocketbase = MagicMock()
        pocketbase.collection.return_value = collection

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            result = await client.async_get_latest_system_stats("system")

        self.assertIsNone(result)

    async def test_latest_statistics_query_one_minute_records(self):
        """Longer averaged records must not replace the latest live sample."""
        collection = MagicMock()
        # PocketBase returns record timestamps as naive UTC datetimes.
        collection.get_list.return_value = SimpleNamespace(
            items=[
                SimpleNamespace(stats={"cpu": 12.5}, created=datetime(2026, 10, 22, 1))
            ]
        )
        pocketbase = MagicMock()
        pocketbase.collection.return_value = collection

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            result = await client.async_get_latest_system_stats("system")

        self.assertEqual(
            result, {"stats": {"cpu": 12.5}, "created": "2026-10-22T01:00:00+00:00"}
        )
        pocketbase.collection.assert_called_once_with("system_stats")
        collection.get_list.assert_called_once_with(
            1,
            1,
            query_params={
                "filter": 'system="system" && type="1m"',
                "sort": "-created",
            },
        )

    async def test_statistics_authentication_failure_is_raised(self):
        """An expired statistics token is exposed as an authentication error."""
        collection = MagicMock()
        collection.get_list.side_effect = ClientResponseError(status=401)
        pocketbase = MagicMock()
        pocketbase.collection.return_value = collection

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            with self.assertRaises(BeszelApiAuthError):
                await client.async_get_latest_system_stats("system")

        pocketbase.auth_store.clear.assert_called_once_with()

    async def test_system_details_are_keyed_by_system(self):
        """System details are returned keyed by their system identifier."""
        records = [
            SimpleNamespace(system="one", kernel="6.1"),
            SimpleNamespace(system="two", kernel="5.15"),
            SimpleNamespace(name="orphan"),
        ]
        collection = MagicMock()
        collection.get_full_list.return_value = records
        pocketbase = MagicMock()
        pocketbase.collection.return_value = collection

        with patch("custom_components.beszel.api.PocketBase", return_value=pocketbase):
            client = BeszelApiClient("beszel.local", "user", "password")
            client.async_authenticate = AsyncMock()
            result = await client.async_get_system_details()

        self.assertEqual(set(result), {"one", "two"})
        self.assertEqual(result["one"]["kernel"], "6.1")

    async def test_statistics_requests_reuse_valid_authentication(self):
        """Request methods authenticate once and reuse a still-valid session."""
        pocketbase = MagicMock()
        pocketbase.auth_store.token = ""
        authentication = MagicMock()
        authentication.auth_with_password.side_effect = lambda *_: setattr(
            pocketbase.auth_store, "token", "token"
        )
        statistics = MagicMock()
        statistics.get_list.return_value = SimpleNamespace(items=[])
        pocketbase.collection.side_effect = {
            "_superusers": authentication,
            "system_stats": statistics,
        }.__getitem__
        with (
            patch("custom_components.beszel.api.PocketBase", return_value=pocketbase),
            patch("custom_components.beszel.api.validate_token", return_value=True),
        ):
            client = BeszelApiClient("beszel.local", "user", "password")
            assert await client.async_get_latest_system_stats("system") is None
            assert await client.async_get_latest_system_stats("system") is None

        authentication.auth_with_password.assert_called_once_with("user", "password")
        assert statistics.get_list.call_count == 2
