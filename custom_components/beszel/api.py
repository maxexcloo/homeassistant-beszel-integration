"""API for Beszel."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from pocketbase import PocketBase
from pocketbase.services.record_service import RecordService
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


class _NetworkMonitorStatsService(RecordService):
    """Keep probe timestamps in Unix milliseconds when decoding records."""

    def decode(self, data):
        """Avoid PocketBase's date-string decoder for numeric `created` fields."""
        return SimpleNamespace(**data)


class _ContainerService(RecordService):
    """Preserve the containers collection's numeric Unix millisecond updated."""

    def decode(self, data):
        """Do not use PocketBase's date-string decoder for container reports."""
        return SimpleNamespace(**data)


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

    async def _async_request(self, request):
        """Run a blocking request with the authenticated client in a thread."""
        await self.async_authenticate()
        client = await self._async_client()
        try:
            return await asyncio.to_thread(request, client)
        except ClientResponseError as err:
            if err.status in (401, 403):
                client.auth_store.clear()
                raise BeszelApiAuthError(
                    "Token likely expired, re-authentication needed"
                ) from err
            raise

    async def async_get_latest_system_stats(self, system_id):
        """Fetch the latest statistics record, including its source timestamp."""
        result = await self._async_request(
            lambda client: client.collection("system_stats").get_list(
                1,
                1,
                query_params={
                    "filter": f'system="{system_id}" && type="1m"',
                    "sort": "-created",
                },
            )
        )
        if result.items:
            return _record_fields(result.items[0])
        return None

    async def async_get_system_details(self):
        """Fetch static system details keyed by system ID."""
        records = await self._async_request(
            lambda client: client.collection("system_details").get_full_list()
        )
        details = {}
        for record in records:
            fields = vars(record)
            system_id = fields.get("system")
            if system_id:
                details[str(system_id)] = fields
        return details

    async def async_get_systems(self):
        """Fetch all systems from the Beszel Hub."""
        records = await self._async_request(
            lambda client: client.collection("systems").get_full_list(
                query_params={"sort": "-status,name"}
            )
        )
        return [vars(record) for record in records]

    async def async_get_containers(self):
        """List container reports without decoding numeric updated as a date.

        None means the collection is unsupported; [] is a successful empty list.
        get_full_list handles pagination. Membership filtering is enforced by the
        Hub and repeated against the visible system set by the coordinator.
        """
        try:
            records = await self._async_request(
                lambda client: _ContainerService(client, "containers").get_full_list(
                    query_params={
                        "fields": "id,system,name,image,health,cpu,memory,net,updated",
                    },
                )
            )
        except ClientResponseError as err:
            if err.status == 404:
                return None
            raise
        return [vars(record) for record in records]

    async def async_get_network_monitors(self):
        """Fetch monitors, treating pre-0.20 Hubs as having no probes."""
        try:
            records = await self._async_request(
                lambda client: client.collection("network_monitors").get_full_list()
            )
        except ClientResponseError as err:
            if err.status == 404:
                return []
            raise
        return [vars(record) for record in records]

    async def async_get_latest_network_monitor_stats(self, since):
        """Fetch each monitor's latest one-minute sample created since a Unix ms time."""
        records = await self._async_request(
            lambda client: _NetworkMonitorStatsService(
                client, "network_monitor_stats"
            ).get_full_list(
                query_params={
                    "filter": f'type="1m" && created>={int(since)}',
                    "sort": "-created",
                },
            )
        )
        latest = {}
        for record in records:
            latest.setdefault(record.monitor, vars(record))
        return latest
