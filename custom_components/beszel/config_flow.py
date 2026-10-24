"""Config flow for the Beszel integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from pocketbase.utils import ClientResponseError

from .api import BeszelApiAuthError, BeszelApiClient, normalise_host, unique_id
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            NumberSelector(
                NumberSelectorConfig(
                    max=60,
                    min=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Coerce(int),
        ),
    }
)


async def _async_validate_input(data):
    """Return form errors for Beszel connection details."""
    api_client = BeszelApiClient(
        data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    try:
        await api_client.async_authenticate()
    except BeszelApiAuthError:
        return {"base": "invalid_auth"}
    except ClientResponseError:
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception(
            "Unexpected exception validating Beszel Hub %s", api_client.host
        )
        return {"base": "unknown"}
    return {}


class BeszelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beszel."""

    VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow for an entry."""
        return BeszelOptionsFlow()

    async def async_step_reauth(self, entry_data):
        """Start reauthentication for an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Confirm updated credentials for an existing entry."""
        entry = self._get_reauth_entry()
        errors = {}

        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            errors = await _async_validate_input(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure an existing entry."""
        entry = self._get_reconfigure_entry()
        errors = {}

        if user_input is not None:
            errors = await _async_validate_input(user_input)
            if not errors:
                entry_unique_id = unique_id(
                    user_input[CONF_HOST], user_input[CONF_USERNAME]
                )
                existing_entry = (
                    self.hass.config_entries.async_entry_for_domain_unique_id(
                        DOMAIN, entry_unique_id
                    )
                )
                if existing_entry and existing_entry.entry_id != entry.entry_id:
                    errors["base"] = "already_configured"
                else:
                    host = normalise_host(user_input[CONF_HOST])
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=entry_unique_id,
                        title=host,
                        data={**user_input, CONF_HOST: host},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                {key: entry.data[key] for key in (CONF_HOST, CONF_USERNAME)},
            ),
            errors=errors,
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            errors = await _async_validate_input(user_input)
            if not errors:
                await self.async_set_unique_id(
                    unique_id(user_input[CONF_HOST], user_input[CONF_USERNAME])
                )
                self._abort_if_unique_id_configured()
                host = normalise_host(user_input[CONF_HOST])
                return self.async_create_entry(
                    title=host, data={**user_input, CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class BeszelOptionsFlow(OptionsFlowWithReload):
    """Handle Beszel options."""

    async def async_step_init(self, user_input=None):
        """Manage the update interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
