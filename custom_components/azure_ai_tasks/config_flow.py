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
from homeassistant.core import callback, HomeAssistant

from .const import (
    CONF_API_KEY, 
    CONF_ENDPOINT, 
    CONF_CHAT_MODEL,
    CONF_IMAGE_MODEL,
    CONF_CHAT_REASONING,
    CONF_IMAGE_REASONING,
    DEFAULT_NAME, 
    DEFAULT_CHAT_MODEL,
    DEFAULT_IMAGE_MODEL,
    DOMAIN,
    CHAT_MODELS,
    IMAGE_MODELS,
    legacy_reasoning_default,
)

_LOGGER = logging.getLogger(__name__)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_ENDPOINT): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_CHAT_MODEL, default=""): str,
        vol.Optional(CONF_IMAGE_MODEL, default=""): str,
        vol.Optional(CONF_CHAT_REASONING, default=False): bool,
        vol.Optional(CONF_IMAGE_REASONING, default=False): bool,
    }
)


def _current_reasoning(current: dict[str, Any], conf_key: str, model_key: str) -> bool:
    """Stored reasoning flag, or the legacy default for entries that predate it."""
    if conf_key in current:
        return bool(current[conf_key])
    return legacy_reasoning_default(current.get(model_key, ""))


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Azure AI Tasks."""

    VERSION = 2  # Increment version to trigger migration
    
    @staticmethod
    @callback  
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle migration from version 1 to 2."""
        # Clean up deprecated models during migration
        if "chat_model" in import_data:
            if import_data["chat_model"] == "gpt-35-turbo":
                import_data["chat_model"] = ""  # Remove deprecated model
        
        # Create new entry with migrated data
        return self.async_create_entry(
            title=import_data.get("name", "Azure AI Tasks"),
            data=import_data
        )

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
            # Validate that at least one model is configured
            chat_model = user_input.get(CONF_CHAT_MODEL, "").strip()
            image_model = user_input.get(CONF_IMAGE_MODEL, "").strip()
            
            if not chat_model and not image_model:
                errors["base"] = "no_models_configured"
            else:
                await self._test_credentials(user_input[CONF_ENDPOINT], user_input[CONF_API_KEY])
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reconfigure an existing entry (endpoint, API key, name, models).

        Lets the user update the connection details in place - e.g. when the
        Azure endpoint or API key changes - without removing and re-adding the
        integration.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            chat_model = user_input.get(CONF_CHAT_MODEL, "").strip()
            image_model = user_input.get(CONF_IMAGE_MODEL, "").strip()

            if not chat_model and not image_model:
                errors["base"] = "no_models_configured"
            else:
                try:
                    await self._test_credentials(
                        user_input[CONF_ENDPOINT], user_input[CONF_API_KEY]
                    )
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Reconfigure credential validation failed")
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        title=user_input.get(CONF_NAME, DEFAULT_NAME),
                        data_updates={
                            CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                            CONF_ENDPOINT: user_input[CONF_ENDPOINT],
                            CONF_API_KEY: user_input[CONF_API_KEY],
                            CONF_CHAT_MODEL: chat_model,
                            CONF_IMAGE_MODEL: image_model,
                            CONF_CHAT_REASONING: user_input.get(CONF_CHAT_REASONING, False),
                            CONF_IMAGE_REASONING: user_input.get(CONF_IMAGE_REASONING, False),
                        },
                        # Models now live in data; clear any stale options copy so
                        # they can't shadow the reconfigured values.
                        options={},
                    )

        # Pre-fill from the current entry (options take precedence over data, as
        # the options flow may have updated the model selections).
        current = {**reconfigure_entry.data, **reconfigure_entry.options}
        if user_input is not None:
            current = {**current, **user_input}

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_ENDPOINT, default=current.get(CONF_ENDPOINT, "")): str,
                vol.Required(CONF_API_KEY, default=current.get(CONF_API_KEY, "")): str,
                vol.Optional(CONF_CHAT_MODEL, default=current.get(CONF_CHAT_MODEL, "")): str,
                vol.Optional(CONF_IMAGE_MODEL, default=current.get(CONF_IMAGE_MODEL, "")): str,
                vol.Optional(
                    CONF_CHAT_REASONING,
                    default=_current_reasoning(current, CONF_CHAT_REASONING, CONF_CHAT_MODEL),
                ): bool,
                vol.Optional(
                    CONF_IMAGE_REASONING,
                    default=_current_reasoning(current, CONF_IMAGE_REASONING, CONF_IMAGE_MODEL),
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
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
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            _LOGGER.info("Options flow received input: %s", user_input)
            
            # Get values from form submission
            chat_model = user_input.get(CONF_CHAT_MODEL, "")
            image_model = user_input.get(CONF_IMAGE_MODEL, "")
            
            # Convert to strings and strip whitespace
            chat_model = str(chat_model).strip()
            image_model = str(image_model).strip()
            
            # Handle special placeholder values and clean up whitespace
            if chat_model.startswith("[None") or chat_model.strip() == "":
                chat_model = ""
            if image_model.startswith("[None") or image_model.strip() == "":
                image_model = ""
                
            _LOGGER.info("Final values - chat: '%s', image: '%s'", chat_model, image_model)
            
            # Check if both are empty
            if not chat_model and not image_model:
                _LOGGER.warning("No models configured, showing error")
                errors = {"base": "no_models_configured"}
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._get_options_schema(),
                    errors=errors,
                )
            
            # Create the final data 
            final_data = {
                CONF_CHAT_MODEL: chat_model,
                CONF_IMAGE_MODEL: image_model,
                CONF_CHAT_REASONING: user_input.get(CONF_CHAT_REASONING, False),
                CONF_IMAGE_REASONING: user_input.get(CONF_IMAGE_REASONING, False),
            }
            
            _LOGGER.info("Saving configuration: %s", final_data)
            return self.async_create_entry(title="", data=final_data)

        _LOGGER.info("Showing options form with current config")
        schema = self._get_options_schema()
        _LOGGER.info("Form schema: %s", schema.schema)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

    def _get_options_schema(self) -> vol.Schema:
        """Get the options schema."""
        # Get current values from options first, then data, then defaults
        current_chat_model = (self._config_entry.options.get(CONF_CHAT_MODEL) or 
                            self._config_entry.data.get(CONF_CHAT_MODEL, ""))
        current_image_model = (self._config_entry.options.get(CONF_IMAGE_MODEL) or 
                             self._config_entry.data.get(CONF_IMAGE_MODEL, ""))

        current = {**self._config_entry.data, **self._config_entry.options}
        current[CONF_CHAT_MODEL] = current_chat_model
        current[CONF_IMAGE_MODEL] = current_image_model

        _LOGGER.info("Schema defaults - chat: '%s', image: '%s'", 
                     current_chat_model, current_image_model)

        # Use special placeholder values to indicate "no model"
        # If current value is empty, show a special placeholder
        chat_display = current_chat_model if current_chat_model else "[None - leave empty to disable chat]"
        image_display = current_image_model if current_image_model else "[None - leave empty to disable images]"

        return vol.Schema(
            {
                vol.Optional(CONF_CHAT_MODEL, default=chat_display): str,
                vol.Optional(CONF_IMAGE_MODEL, default=image_display): str,
                vol.Optional(
                    CONF_CHAT_REASONING,
                    default=_current_reasoning(current, CONF_CHAT_REASONING, CONF_CHAT_MODEL),
                ): bool,
                vol.Optional(
                    CONF_IMAGE_REASONING,
                    default=_current_reasoning(current, CONF_IMAGE_REASONING, CONF_IMAGE_MODEL),
                ): bool,
            }
        )