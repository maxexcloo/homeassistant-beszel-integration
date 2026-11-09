"""API for Beszel."""

from aiohttp import ClientResponseError, ClientTimeout

PAGE_SIZE = 500
TIMEOUT = ClientTimeout(total=30)


def normalise_host(host):
    """Return a Beszel Hub URL with a scheme and without a trailing slash."""
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def unique_id(host, username):
    """Return the config entry unique ID for a Beszel Hub account."""
    return f"{normalise_host(host)}_{username}"


class BeszelApiAuthError(Exception):
    """Custom exception for authentication errors."""


class BeszelApiClient:
    """Beszel API Client."""

    def __init__(self, session, host, username, password):
        """Initialise the API client."""
        self._host = normalise_host(host)
        self._password = password
        self._session = session
        self._token = None
        self._username = username

    @property
    def host(self):
        """Return the normalised Beszel Hub URL."""
        return self._host

    async def async_authenticate(self):
        """Authenticate with the Beszel Hub."""
        last_error = None
        for collection in ("_superusers", "users"):
            try:
                async with self._session.post(
                    f"{self._host}/api/collections/{collection}/auth-with-password",
                    json={"identity": self._username, "password": self._password},
                    timeout=TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    self._token = (await response.json())["token"]
                return
            except ClientResponseError as err:
                if err.status not in (400, 401, 403, 404):
                    raise
                last_error = err

        raise BeszelApiAuthError("Authentication failed") from last_error

    async def _async_list(self, collection, params=None):
        """Fetch every record of a collection, logging in again once if rejected."""
        if self._token is None:
            await self.async_authenticate()
        try:
            return await self._async_list_pages(collection, params)
        except ClientResponseError as err:
            if err.status not in (401, 403):
                raise
        # Tokens expire, so only a rejected fresh token means invalid credentials.
        await self.async_authenticate()
        try:
            return await self._async_list_pages(collection, params)
        except ClientResponseError as err:
            if err.status in (401, 403):
                self._token = None
                raise BeszelApiAuthError("Beszel Hub rejected the session") from err
            raise

    async def _async_list_pages(self, collection, params):
        """Fetch every page of a collection's records."""
        records = []
        page = 1
        while True:
            async with self._session.get(
                f"{self._host}/api/collections/{collection}/records",
                headers={"Authorization": self._token},
                params={
                    **(params or {}),
                    "page": page,
                    "perPage": PAGE_SIZE,
                    "skipTotal": "true",
                },
                timeout=TIMEOUT,
            ) as response:
                response.raise_for_status()
                items = (await response.json())["items"]
            records.extend(items)
            if len(items) < PAGE_SIZE:
                return records
            page += 1

    async def _async_optional_list(self, collection):
        """Fetch a collection that older Hubs do not have."""
        try:
            return await self._async_list(collection)
        except ClientResponseError as err:
            if err.status == 404:
                return []
            raise

    async def async_get_latest_system_stats(self, since):
        """Fetch each system's latest one-minute record created since a UTC time."""
        records = await self._async_list(
            "system_stats",
            {
                "filter": f'type="1m" && created>="{since:%Y-%m-%d %H:%M:%S}.000Z"',
                "sort": "-created",
            },
        )
        latest = {}
        for record in records:
            latest.setdefault(record["system"], record)
        return latest

    async def async_get_system_details(self):
        """Fetch static system details keyed by system ID."""
        return {
            str(record["system"]): record
            for record in await self._async_list("system_details")
            if record.get("system")
        }

    async def async_get_systems(self):
        """Fetch all systems from the Beszel Hub."""
        return await self._async_list("systems", {"sort": "-status,name"})

    async def async_get_containers(self):
        """Fetch container records, treating Hubs without containers as having none."""
        return await self._async_optional_list("containers")

    async def async_get_network_monitors(self):
        """Fetch monitors, treating pre-0.20 Hubs as having no probes."""
        return await self._async_optional_list("network_monitors")

    async def async_get_latest_network_monitor_stats(self, since):
        """Fetch each monitor's latest one-minute sample created since a Unix ms time."""
        records = await self._async_list(
            "network_monitor_stats",
            {"filter": f'type="1m" && created>={int(since)}', "sort": "-created"},
        )
        latest = {}
        for record in records:
            latest.setdefault(record["monitor"], record)
        return latest
