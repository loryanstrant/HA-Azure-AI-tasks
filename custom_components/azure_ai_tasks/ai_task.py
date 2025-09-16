"""Azure AI Task entity for Home Assistant."""
from __future__ import annotations

import logging
from json import JSONDecodeError

import aiohttp

from homeassistant.components import ai_task, conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.json import json_loads

from .const import CONF_API_KEY, CONF_ENDPOINT, CONF_CHAT_MODEL, CONF_IMAGE_MODEL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Azure AI Task entities from a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get models from options if available, otherwise use config data or defaults
    chat_model = (config_entry.options.get(CONF_CHAT_MODEL) or 
                 config.get(CONF_CHAT_MODEL, "gpt-35-turbo"))
    image_model = (config_entry.options.get(CONF_IMAGE_MODEL) or 
                  config.get(CONF_IMAGE_MODEL, "dall-e-3"))
    
    async_add_entities([
        AzureAITaskEntity(
            config[CONF_NAME],
            config[CONF_ENDPOINT],
            config[CONF_API_KEY],
            chat_model,
            image_model,
            hass,
            config_entry
        )
    ])


class AzureAITaskEntity(ai_task.AITaskEntity):
    """Azure AI Task entity."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA |
        ai_task.AITaskEntityFeature.GENERATE_IMAGE
    )

    def __init__(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        chat_model: str,
        image_model: str,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the Azure AI Task entity."""
        self._name = name
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._chat_model = chat_model
        self._image_model = image_model
        self._hass = hass
        self._config_entry = config_entry
        self._attr_unique_id = f"azure_ai_tasks_{name.lower().replace(' ', '_')}"
        
        # Listen for options updates
        self._config_entry.add_update_listener(self._async_options_updated)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def chat_model(self) -> str:
        """Return the current chat model."""
        return (self._config_entry.options.get(CONF_CHAT_MODEL) or 
                self._config_entry.data.get(CONF_CHAT_MODEL, self._chat_model))

    @property
    def image_model(self) -> str:
        """Return the current image model."""
        return (self._config_entry.options.get(CONF_IMAGE_MODEL) or 
                self._config_entry.data.get(CONF_IMAGE_MODEL, self._image_model))

    async def _async_options_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update."""
        # This will trigger a reload of the entity with new options
        await self.async_update_ha_state()

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        session = async_get_clientsession(self._hass)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        
        # Extract the task instructions from the chat log
        # Get the user's message content from the chat log
        user_message = None
        for content in chat_log.content:
            if isinstance(content, conversation.UserContent):
                user_message = content.content
                break
        
        if not user_message:
            raise HomeAssistantError("No task instructions found in chat log")
        
        # This is a generic implementation - in practice, you would customize
        # this based on the specific Azure AI service you're using
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        try:
            async with session.post(
                f"{self._endpoint}/openai/deployments/{self.chat_model}/chat/completions",
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
                    text = result["choices"][0]["message"]["content"].strip()
                    
                    # If the task requires structured data, try to parse as JSON
                    if task.structure:
                        try:
                            data = json_loads(text)
                        except JSONDecodeError as err:
                            _LOGGER.error(
                                "Failed to parse JSON response: %s. Response: %s",
                                err,
                                text,
                            )
                            raise HomeAssistantError("Error with Azure AI structured response") from err
                        
                        return ai_task.GenDataTaskResult(
                            conversation_id=chat_log.conversation_id,
                            data=data,
                        )
                    else:
                        return ai_task.GenDataTaskResult(
                            conversation_id=chat_log.conversation_id,
                            data=text,
                        )
                else:
                    _LOGGER.error("Unexpected response format from Azure AI: %s", result)
                    raise HomeAssistantError("Unexpected response format from Azure AI")
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error communicating with Azure AI: %s", err)
            raise HomeAssistantError(f"Error communicating with Azure AI: {err}") from err

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
    ) -> ai_task.GenImageTaskResult:
        """Handle an image generation task."""
        session = async_get_clientsession(self._hass)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        
        # Prepare the image generation payload
        payload = {
            "prompt": task.prompt,
            "size": "1024x1024",  # Default size, could be made configurable
            "n": 1,
            "quality": "standard"
        }
        
        # Add size and quality parameters based on the model
        if self.image_model == "dall-e-3":
            payload.update({
                "quality": "hd" if task.size and ("hd" in task.size.lower() or "high" in task.size.lower()) else "standard",
                "style": "natural"  # Could be "vivid" or "natural"
            })
        
        # Handle size parameter if provided
        if task.size:
            if any(size in task.size.lower() for size in ["256", "512", "1024", "1792"]):
                if "256" in task.size:
                    payload["size"] = "256x256"
                elif "512" in task.size:
                    payload["size"] = "512x512"
                elif "1792" in task.size:
                    payload["size"] = "1792x1024" if self.image_model == "dall-e-3" else "1024x1024"
                else:
                    payload["size"] = "1024x1024"
        
        try:
            async with session.post(
                f"{self._endpoint}/openai/deployments/{self.image_model}/images/generations",
                headers=headers,
                json=payload,
                params={"api-version": "2024-02-15-preview"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Azure AI Image API error: %s", error_text)
                    raise HomeAssistantError(f"Azure AI Image API error: {response.status}")
                
                result = await response.json()
                
                if "data" in result and len(result["data"]) > 0:
                    image_url = result["data"][0]["url"]
                    
                    # Download the image
                    async with session.get(image_url) as img_response:
                        if img_response.status == 200:
                            image_data = await img_response.read()
                            
                            return ai_task.GenImageTaskResult(
                                image_data=image_data,
                                image_format="png"
                            )
                        else:
                            raise HomeAssistantError(f"Failed to download generated image: {img_response.status}")
                else:
                    _LOGGER.error("Unexpected response format from Azure AI Image API: %s", result)
                    raise HomeAssistantError("Unexpected response format from Azure AI Image API")
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error communicating with Azure AI Image API: %s", err)
            raise HomeAssistantError(f"Error communicating with Azure AI Image API: {err}") from err