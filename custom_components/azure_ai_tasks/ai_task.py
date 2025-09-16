"""Azure AI Task entity for Home Assistant."""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from homeassistant.components.ai_task import AITaskEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_API_KEY, CONF_ENDPOINT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Azure AI Task entities from a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([
        AzureAITaskEntity(
            config[CONF_NAME],
            config[CONF_ENDPOINT],
            config[CONF_API_KEY],
            hass
        )
    ])


class AzureAITaskEntity(AITaskEntity):
    """Azure AI Task entity."""

    def __init__(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the Azure AI Task entity."""
        self._name = name
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._hass = hass
        self._attr_unique_id = f"azure_ai_tasks_{name.lower().replace(' ', '_')}"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    async def async_process_task(self, task: str) -> str:
        """Process an AI task using Azure AI."""
        session = async_get_clientsession(self._hass)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        
        # This is a generic implementation - in practice, you would customize
        # this based on the specific Azure AI service you're using
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": task
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        try:
            async with session.post(
                f"{self._endpoint}/openai/deployments/gpt-35-turbo/chat/completions",
                headers=headers,
                json=payload,
                params={"api-version": "2024-02-15-preview"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Azure AI API error: %s", error_text)
                    raise HomeAssistantError(f"Azure AI API error: {response.status}")
                
                result = await response.json()
                
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    _LOGGER.error("Unexpected response format from Azure AI: %s", result)
                    raise HomeAssistantError("Unexpected response format from Azure AI")
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error communicating with Azure AI: %s", err)
            raise HomeAssistantError(f"Error communicating with Azure AI: {err}") from err