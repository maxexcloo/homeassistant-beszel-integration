"""Diagnostics support for Beszel."""

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(hass, entry):
    """Return the configuration and latest Hub data for a config entry."""
    return {
        "config_entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "systems": entry.runtime_data.data,
    }
