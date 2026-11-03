"""Tests for the Beszel API client."""

from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from aiohttp import ClientResponseError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.beszel.api import PAGE_SIZE, BeszelApiAuthError, BeszelApiClient

HOST = "http://beszel.local"
SUPERUSERS = f"{HOST}/api/collections/_superusers/auth-with-password"
USERS = f"{HOST}/api/collections/users/auth-with-password"


def records_url(collection):
    """Return the records endpoint of a collection."""
    return f"{HOST}/api/collections/{collection}/records"


def queries(aioclient_mock, collection):
    """Return the query of each request made to a collection."""
    return [
        dict(url.query)
        for method, url, *_ in aioclient_mock.mock_calls
        if method.lower() == "get" and url.path.endswith(f"/{collection}/records")
    ]


@pytest.fixture
async def client(hass, aioclient_mock):
    """Return a client for the mocked Hub."""
    return BeszelApiClient(async_get_clientsession(hass), HOST, "user", "password")


async def test_authentication_prefers_superusers(hass, aioclient_mock):
    """Authentication normalises the host and stops after superusers succeed."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    client = BeszelApiClient(async_get_clientsession(hass), "beszel.local/", "u", "p")
    await client.async_authenticate()
    assert client.host == HOST
    assert [str(call[1]) for call in aioclient_mock.mock_calls] == [SUPERUSERS]


async def test_authentication_falls_back_to_users(client, aioclient_mock):
    """Authentication supports current and legacy PocketBase collections."""
    aioclient_mock.post(SUPERUSERS, status=HTTPStatus.NOT_FOUND)
    aioclient_mock.post(USERS, json={"token": "token"})
    await client.async_authenticate()
    assert aioclient_mock.call_count == 2


async def test_invalid_credentials_raise_authentication_failure(client, aioclient_mock):
    """Rejected credentials trigger Home Assistant reauthentication."""
    aioclient_mock.post(SUPERUSERS, status=HTTPStatus.BAD_REQUEST)
    aioclient_mock.post(USERS, status=HTTPStatus.BAD_REQUEST)
    with pytest.raises(BeszelApiAuthError):
        await client.async_authenticate()


@pytest.mark.parametrize("status", [408, 429, 500, 503])
async def test_authentication_failures_are_not_invalid_credentials(
    client, aioclient_mock, status
):
    """Connection failures and rate limits remain retryable errors."""
    aioclient_mock.post(SUPERUSERS, status=status)
    with pytest.raises(ClientResponseError):
        await client.async_authenticate()
    assert aioclient_mock.call_count == 1


async def test_latest_statistics_query_recent_one_minute_records(
    client, aioclient_mock
):
    """Fetch recent one-minute records once and keep each system's newest."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    newest = {
        "system": "one",
        "stats": {"cpu": 2},
        "created": "2026-10-22 01:01:00.123Z",
    }
    older = {
        "system": "one",
        "stats": {"cpu": 1},
        "created": "2026-10-22 01:00:00.000Z",
    }
    other = {
        "system": "two",
        "stats": {"cpu": 3},
        "created": "2026-10-22 01:00:00.000Z",
    }
    aioclient_mock.get(
        records_url("system_stats"), json={"items": [newest, older, other]}
    )

    result = await client.async_get_latest_system_stats(
        datetime(2026, 10, 22, 0, 56, tzinfo=UTC)
    )

    assert result == {"one": newest, "two": other}
    assert dt_util.parse_datetime(newest["created"]) == datetime(
        2026, 10, 22, 1, 1, 0, 123000, tzinfo=UTC
    )
    [query] = queries(aioclient_mock, "system_stats")
    assert query["filter"] == 'type="1m" && created>="2026-10-22 00:56:00.000Z"'
    assert query["sort"] == "-created"


async def test_network_monitors_and_latest_stats_query(client, aioclient_mock):
    """Query the newest probe record without losing its numeric timestamp."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    newest = {"created": 1792717260000, "monitor": "probe", "total_count": 2}
    older = {"created": 1792717200000, "monitor": "probe", "total_count": 1}
    other = {"created": 1792717200000, "monitor": "other", "total_count": 3}
    aioclient_mock.get(
        records_url("network_monitors"), json={"items": [{"id": "probe"}]}
    )
    aioclient_mock.get(
        records_url("network_monitor_stats"), json={"items": [newest, older, other]}
    )

    assert await client.async_get_network_monitors() == [{"id": "probe"}]
    assert await client.async_get_latest_network_monitor_stats(1792717140000.5) == {
        "other": other,
        "probe": newest,
    }
    [query] = queries(aioclient_mock, "network_monitor_stats")
    assert query["filter"] == 'type="1m" && created>=1792717140000'


@pytest.mark.parametrize("status", [404, 500])
async def test_only_missing_optional_collections_are_empty(
    client, aioclient_mock, status
):
    """Old Hubs without containers or monitors work; other failures are errors."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    aioclient_mock.get(records_url("containers"), status=status)
    aioclient_mock.get(records_url("network_monitors"), status=status)
    if status == 404:
        assert await client.async_get_containers() == []
        assert await client.async_get_network_monitors() == []
    else:
        with pytest.raises(ClientResponseError):
            await client.async_get_containers()


async def test_requests_reuse_authentication_and_page(client, aioclient_mock):
    """Requests log in once and fetch every page of a collection."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    first = [{"id": str(index)} for index in range(PAGE_SIZE)]
    aioclient_mock.get(
        records_url("systems"), params={"page": 1}, json={"items": first}
    )
    aioclient_mock.get(
        records_url("systems"), params={"page": 2}, json={"items": [{"id": "last"}]}
    )

    assert len(await client.async_get_systems()) == PAGE_SIZE + 1
    assert len(await client.async_get_systems()) == PAGE_SIZE + 1
    assert sum(call[0].lower() == "post" for call in aioclient_mock.mock_calls) == 1
    assert aioclient_mock.mock_calls[1][3] == {"Authorization": "token"}


async def test_expired_token_logs_in_again(client, aioclient_mock):
    """A rejected session is renewed once before credentials count as invalid."""
    responses = iter([HTTPStatus.UNAUTHORIZED, HTTPStatus.OK])

    async def expire_once(method, url, data):
        return AiohttpClientMockResponse(
            method, url, status=next(responses), json={"items": []}
        )

    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    aioclient_mock.get(records_url("systems"), side_effect=expire_once)
    assert await client.async_get_systems() == []
    assert sum(call[0].lower() == "post" for call in aioclient_mock.mock_calls) == 2


async def test_rejected_fresh_token_raises_authentication_failure(
    client, aioclient_mock
):
    """A fresh session that is still rejected requires reauthentication."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    aioclient_mock.get(records_url("system_stats"), status=HTTPStatus.FORBIDDEN)
    with pytest.raises(BeszelApiAuthError):
        await client.async_get_latest_system_stats(datetime.now(UTC))


async def test_system_details_are_keyed_by_system(client, aioclient_mock):
    """System details are returned keyed by their system identifier."""
    aioclient_mock.post(SUPERUSERS, json={"token": "token"})
    aioclient_mock.get(
        records_url("system_details"),
        json={
            "items": [
                {"system": "one", "kernel": "6.1"},
                {"system": "two", "kernel": "5.15"},
                {"name": "orphan"},
            ]
        },
    )
    result = await client.async_get_system_details()
    assert set(result) == {"one", "two"}
    assert result["one"]["kernel"] == "6.1"
