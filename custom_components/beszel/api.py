"""API for Beszel."""

import asyncio

from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError, validate_token


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

    def __init__(self, host, username, password):
        """Initialise the API client."""
        host = normalise_host(host)
        self._client = PocketBase(host)
        self._host = host
        self._is_authenticated = False
        self._password = password
        self._username = username

    @property
    def host(self):
        """Return the normalised Beszel Hub URL."""
        return self._host

    async def async_authenticate(self):
        """Authenticate with the Beszel Hub."""
        if (
            self._is_authenticated
            and self._client.auth_store.token
            and self._client.auth_store.model
            and validate_token(self._client.auth_store.token)
        ):
            return

        last_error = None
        for collection in ("_superusers", "users"):
            try:
                await asyncio.to_thread(
                    self._client.collection(collection).auth_with_password,
                    self._username,
                    self._password,
                )
                self._is_authenticated = True
                return
            except ClientResponseError as err:
                if err.status not in (400, 401, 403, 404):
                    raise
                last_error = err

        self._is_authenticated = False
        raise BeszelApiAuthError("Authentication failed") from last_error

    def _raise_if_unauthorised(self, err):
        """Raise an authentication error when the Hub rejects the session."""
        if err.status in (401, 403):
            self._is_authenticated = False
            raise BeszelApiAuthError(
                "Token likely expired, re-authentication needed"
            ) from err

    async def async_get_latest_system_stats(self, system_id):
        """Fetch the latest statistics record, including its source timestamp."""
        await self.async_authenticate()
        try:
            result = await asyncio.to_thread(
                self._client.collection("system_stats").get_list,
                1,
                1,
                query_params={
                    "filter": f'system="{system_id}" && type="1m"',
                    "sort": "-created",
                },
            )
            if result.items:
                return vars(result.items[0])
            return None
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise

    async def async_get_system_details(self):
        """Fetch static system details keyed by system ID."""
        await self.async_authenticate()
        try:
            records = await asyncio.to_thread(
                self._client.collection("system_details").get_full_list,
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
        try:
            records = await asyncio.to_thread(
                self._client.collection("systems").get_full_list,
                query_params={"sort": "-status,name"},
            )
            return [vars(record) for record in records]
        except ClientResponseError as err:
            self._raise_if_unauthorised(err)
            raise
