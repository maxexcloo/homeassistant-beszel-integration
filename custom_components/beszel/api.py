"""API for Beszel."""

import asyncio
from datetime import UTC, datetime

from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError, validate_token


def normalise_host(host):
    """Return a Beszel Hub URL with a scheme and without a trailing slash."""
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def _record_fields(record):
    """Return a record's fields with its creation time as an aware UTC timestamp."""
    fields = dict(vars(record))
    created = fields.get("created")
    # PocketBase parses record timestamps into naive UTC datetimes.
    if isinstance(created, datetime):
        fields["created"] = created.replace(tzinfo=UTC).isoformat()
    return fields


def unique_id(host, username):
    """Return the config entry unique ID for a Beszel Hub account."""
    return f"{normalise_host(host)}_{username}"


class BeszelApiAuthError(Exception):
    """Custom exception for authentication errors."""


class BeszelApiClient:
    """Beszel API Client."""

    def __init__(self, host, username, password):
        """Initialise the API client."""
        host = normalise_host(host)
        self._client = None
        self._host = host
        self._password = password
        self._username = username

    @property
    def host(self):
        """Return the normalised Beszel Hub URL."""
        return self._host

    async def _async_client(self):
        """Return the PocketBase client, creating it outside the event loop."""
        # Creating the client loads the CA bundle, which blocks.
        if self._client is None:
            self._client = await asyncio.to_thread(PocketBase, self._host)
        return self._client

    async def async_authenticate(self):
        """Authenticate with the Beszel Hub."""
        client = await self._async_client()
        token = client.auth_store.token
        if token and validate_token(token):
            return

        last_error = None
        for collection in ("_superusers", "users"):
            try:
                await asyncio.to_thread(
                    client.collection(collection).auth_with_password,
                    self._username,
                    self._password,
                )
                return
            except ClientResponseError as err:
                if err.status not in (400, 401, 403, 404):
                    raise
                last_error = err

        raise BeszelApiAuthError("Authentication failed") from last_error

    def _raise_if_unauthorised(self, err):
        """Raise an authentication error when the Hub rejects the session."""
        if err.status in (401, 403):
            self._client.auth_store.clear()
            raise BeszelApiAuthError(
                "Token likely expired, re-authentication needed"
            ) from err

    async def async_get_latest_system_stats(self, system_id):
        """Fetch the latest statistics record, including its source timestamp."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            result = await asyncio.to_thread(
                client.collection("system_stats").get_list,
                1,
                1,
                query_params={
                    "filter": f'system="{system_id}" && type="1m"',
                    "sort": "-created",
                },
            )
            if result.items:
                return _record_fields(result.items[0])
            return None
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise

    async def async_get_system_details(self):
        """Fetch static system details keyed by system ID."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            records = await asyncio.to_thread(
                client.collection("system_details").get_full_list,
            )
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise
        details = {}
        for record in records:
            fields = vars(record)
            system_id = fields.get("system")
            if system_id:
                details[str(system_id)] = fields
        return details

    async def async_get_systems(self):
        """Fetch all systems from the Beszel Hub."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            records = await asyncio.to_thread(
                client.collection("systems").get_full_list,
                query_params={"sort": "-status,name"},
            )
            return [vars(record) for record in records]
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise

    async def async_get_network_monitors(self):
        """Fetch monitors, treating pre-0.20 Hubs as having no probes."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            records = await asyncio.to_thread(
                client.collection("network_monitors").get_full_list,
            )
            return [vars(record) for record in records]
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            if err.status == 404:
                return []
            raise

    async def async_get_latest_network_monitor_stats(self, monitor_id):
        """Fetch the latest one-minute probe sample, including its timestamp."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            # Beszel uses Unix milliseconds here. PocketBase Record decoding
            # assumes that `created` is a date string and cannot decode it.
            result = await asyncio.to_thread(
                client.send,
                "/api/collections/network_monitor_stats/records",
                {
                    "method": "GET",
                    "params": {
                        "page": 1,
                        "perPage": 1,
                        "filter": f'monitor="{monitor_id}" && type="1m"',
                        "sort": "-created",
                    },
                },
            )
            return result["items"][0] if result["items"] else None
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise
