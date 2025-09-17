"""Config flow for Azure AI Tasks integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import callback

from .const import (
    CONF_API_KEY, 
    CONF_ENDPOINT, 
    CONF_CHAT_MODEL,
    DEFAULT_NAME, 
    DEFAULT_CHAT_MODEL,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_ENDPOINT): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_CHAT_MODEL, default=DEFAULT_CHAT_MODEL): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Azure AI Tasks."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            await self._test_credentials(user_input[CONF_ENDPOINT], user_input[CONF_API_KEY])
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def _test_credentials(self, endpoint: str, api_key: str) -> bool:
        """Test if we can authenticate with the host."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Basic connectivity test to the endpoint
        async with session.get(endpoint, headers=headers) as response:
            if response.status == 401:
                raise Exception("Invalid API key")
            elif response.status >= 400:
                raise Exception("Cannot connect to Azure AI endpoint")
        
        return True


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Azure AI Tasks."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from options first, then data, then defaults
        current_chat_model = (self.config_entry.options.get(CONF_CHAT_MODEL) or 
                            self.config_entry.data.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL))

        options_schema = vol.Schema(
            {
                vol.Required(CONF_CHAT_MODEL, default=current_chat_model): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )