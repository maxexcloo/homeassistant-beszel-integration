"""Tests for the Beszel config flow."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pocketbase.utils import ClientResponseError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.beszel.api import BeszelApiAuthError
from custom_components.beszel.const import CONF_UPDATE_INTERVAL, DOMAIN


async def test_user_flow_normalises_host(hass):
    """The user flow stores lower-case keys and a normalised host."""
    with (
        patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class,
        patch("custom_components.beszel.async_setup_entry", return_value=True),
    ):
        api_class.return_value.async_authenticate = AsyncMock()
        api_class.return_value.host = "http://beszel.local"
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={
                CONF_HOST: "beszel.local/",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: "http://beszel.local",
        CONF_PASSWORD: "password",
        CONF_USERNAME: "user",
    }
    assert result["result"].unique_id == "http://beszel.local_user"


async def test_user_flow_reports_invalid_authentication(hass):
    """Invalid credentials return the translated authentication error."""
    with patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class:
        api_class.return_value.async_authenticate = AsyncMock(
            side_effect=BeszelApiAuthError("invalid credentials")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={
                CONF_HOST: "beszel.local",
                CONF_PASSWORD: "wrong",
                CONF_USERNAME: "user",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauthentication_updates_only_the_password(hass):
    """Reauthentication retains the configured Hub and username."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "http://beszel.local",
            CONF_PASSWORD: "old",
            CONF_USERNAME: "user",
        },
        unique_id="http://beszel.local_user",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"entry_id": entry.entry_id, "source": SOURCE_REAUTH},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {"name": entry.title}
    with (
        patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class,
        patch.object(hass.config_entries, "async_reload", return_value=True) as reload,
    ):
        api_class.return_value.async_authenticate = AsyncMock()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_HOST: "http://beszel.local",
        CONF_PASSWORD: "new-password",
        CONF_USERNAME: "user",
    }
    reload.assert_awaited_once_with(entry.entry_id)


async def test_user_flow_aborts_for_configured_account(hass):
    """Adding the same Hub account twice aborts before creating an entry."""
    MockConfigEntry(domain=DOMAIN, unique_id="http://beszel.local_user").add_to_hass(
        hass
    )
    with patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class:
        api_class.return_value.async_authenticate = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={
                CONF_HOST: "beszel.local/",
                CONF_PASSWORD: "password",
                CONF_USERNAME: "user",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ClientResponseError(status=0), "cannot_connect"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_user_flow_reports_connection_and_unexpected_errors(hass, error, reason):
    """Connection failures and unexpected errors use distinct form errors."""
    with patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class:
        api_class.return_value.async_authenticate = AsyncMock(side_effect=error)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={
                CONF_HOST: "beszel.local",
                CONF_PASSWORD: "password",
                CONF_USERNAME: "user",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}


async def test_reconfigure_updates_host_and_unique_id(hass):
    """Reconfiguration stores the normalised Hub and refreshes the entry identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "http://old.local",
            CONF_PASSWORD: "password",
            CONF_USERNAME: "user",
        },
        title="http://old.local",
        unique_id="http://old.local_user",
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with (
        patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class,
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        api_class.return_value.async_authenticate = AsyncMock()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "new.local/",
                CONF_PASSWORD: "password",
                CONF_USERNAME: "user",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "http://new.local"
    assert entry.title == "http://new.local"
    assert entry.unique_id == "http://new.local_user"


async def test_reconfigure_rejects_another_configured_account(hass):
    """Reconfiguration cannot point an entry at another entry's Hub account."""
    MockConfigEntry(domain=DOMAIN, unique_id="http://other.local_user").add_to_hass(
        hass
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "http://old.local",
            CONF_PASSWORD: "password",
            CONF_USERNAME: "user",
        },
        unique_id="http://old.local_user",
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.beszel.config_flow.BeszelApiClient") as api_class:
        api_class.return_value.async_authenticate = AsyncMock()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "other.local",
                CONF_PASSWORD: "password",
                CONF_USERNAME: "user",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}
    assert entry.unique_id == "http://old.local_user"


async def test_options_flow_sets_update_interval(hass):
    """The update interval option reloads the entry with the new polling rate."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "http://beszel.local",
            CONF_PASSWORD: "password",
            CONF_USERNAME: "user",
        },
        version=3,
    )
    entry.add_to_hass(hass)
    with patch("custom_components.beszel.BeszelApiClient", autospec=True) as api_class:
        api_class.return_value.async_get_systems = AsyncMock(return_value=[])
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.update_interval == timedelta(minutes=1)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_UPDATE_INTERVAL: 5}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_UPDATE_INTERVAL: 5}
    assert entry.runtime_data.update_interval == timedelta(minutes=5)
