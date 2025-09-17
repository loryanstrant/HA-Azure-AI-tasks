"""Azure AI Task entity for Home Assistant."""
from __future__ import annotations

import base64
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

from .const import CONF_API_KEY, CONF_ENDPOINT, CONF_CHAT_MODEL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Azure AI Task entities from a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get chat model from options if available, otherwise use config data or defaults
    chat_model = (config_entry.options.get(CONF_CHAT_MODEL) or 
                 config.get(CONF_CHAT_MODEL, "gpt-35-turbo"))
    
    async_add_entities([
        AzureAITaskEntity(
            config[CONF_NAME],
            config[CONF_ENDPOINT],
            config[CONF_API_KEY],
            chat_model,
            hass,
            config_entry
        )
    ])


class AzureAITaskEntity(ai_task.AITaskEntity):
    """Azure AI Task entity."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
    )
    
    # Indicate that this entity supports attachments
    _attr_supports_attachments = True

    def __init__(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        chat_model: str,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the Azure AI Task entity."""
        self._name = name
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._chat_model = chat_model
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
    def supported_features(self) -> int:
        """Return the supported features of the entity."""
        features = ai_task.AITaskEntityFeature.GENERATE_DATA
        # Try to add attachment support if the feature exists
        try:
            features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        except AttributeError:
            # Feature doesn't exist, that's okay
            pass
        return features

    def supports_attachments(self) -> bool:
        """Return whether the entity supports attachments."""
        return True

    @property 
    def supports_media_attachments(self) -> bool:
        """Return whether the entity supports media attachments."""
        return True

    async def _async_options_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update."""
        # This will trigger a reload of the entity with new options
        await self.async_update_ha_state()

    async def _process_attachment(self, attachment, session) -> str | None:
        """Process an attachment and return base64 encoded image data."""
        try:
            # Handle different media content types
            if hasattr(attachment, 'media_content_id'):
                media_id = attachment.media_content_id
                media_type = getattr(attachment, 'media_content_type', '')
                
                _LOGGER.debug("Processing attachment: %s (type: %s)", media_id, media_type)
                
                # Handle camera streams
                if media_id.startswith('media-source://camera/'):
                    return await self._process_camera_attachment(media_id, session)
                
                # Handle uploaded images
                elif media_id.startswith('media-source://media_source/'):
                    return await self._process_media_source_attachment(media_id, session)
                
                # Handle direct image URLs or other formats
                elif media_type.startswith('image/'):
                    return await self._process_image_attachment(media_id, session)
                
                else:
                    _LOGGER.warning("Unsupported media type: %s", media_type)
                    
        except Exception as err:
            _LOGGER.error("Error processing attachment: %s", err)
            
        return None

    async def _process_camera_attachment(self, media_id: str, session) -> str | None:
        """Process camera media attachment."""
        try:
            # Extract camera entity ID from media_id
            # Format: media-source://camera/camera.front_door_fluent
            camera_entity = media_id.replace('media-source://camera/', '')
            
            # Use Home Assistant's camera component to get image
            from homeassistant.components.camera import async_get_image
            
            try:
                image_bytes = await async_get_image(self._hass, camera_entity)
                return base64.b64encode(image_bytes.content).decode('utf-8')
            except Exception as err:
                _LOGGER.error("Failed to get camera image for %s: %s", camera_entity, err)
                
        except Exception as err:
            _LOGGER.error("Error processing camera attachment: %s", err)
            
        return None

    async def _process_media_source_attachment(self, media_id: str, session) -> str | None:
        """Process media source attachment."""
        try:
            # Use Home Assistant's media source to resolve the attachment
            from homeassistant.components.media_source import async_resolve_media
            
            try:
                resolved_media = await async_resolve_media(self._hass, media_id, None)
                if resolved_media and resolved_media.url:
                    # Get the resolved URL and fetch the content
                    async with session.get(resolved_media.url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            return base64.b64encode(image_data).decode('utf-8')
                        else:
                            _LOGGER.error("Failed to fetch media from resolved URL: %s", response.status)
            except Exception as err:
                _LOGGER.error("Failed to resolve media source %s: %s", media_id, err)
                        
        except Exception as err:
            _LOGGER.error("Error processing media source attachment: %s", err)
            
        return None

    async def _process_image_attachment(self, media_id: str, session) -> str | None:
        """Process direct image attachment."""
        try:
            # Handle direct URLs or other image sources
            async with session.get(media_id) as response:
                if response.status == 200:
                    image_data = await response.read()
                    return base64.b64encode(image_data).decode('utf-8')
                else:
                    _LOGGER.error("Failed to get image: %s", response.status)
                    
        except Exception as err:
            _LOGGER.error("Error processing image attachment: %s", err)
            
        return None

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
        
        # Extract the task instructions and attachments from the chat log and task
        user_message = None
        attachments = []
        
        for content in chat_log.content:
            if isinstance(content, conversation.UserContent):
                user_message = content.content
            # Check for different types of content that might contain attachments
            elif hasattr(content, 'media_content_id'):
                attachments.append(content)
            elif hasattr(content, 'attachments'):
                # Some content types might have an attachments attribute
                if isinstance(content.attachments, list):
                    attachments.extend(content.attachments)
                else:
                    attachments.append(content.attachments)
            # Check for media content type
            elif hasattr(content, 'content_type') and content.content_type.startswith('image/'):
                attachments.append(content)
        
        # Also check if the task itself has attachments
        if hasattr(task, 'attachments') and task.attachments:
            # Handle single attachment or list of attachments
            if isinstance(task.attachments, list):
                attachments.extend(task.attachments)
            else:
                attachments.append(task.attachments)
        
        if not user_message:
            raise HomeAssistantError("No task instructions found in chat log")
        
        _LOGGER.debug("Processing task with %d attachments", len(attachments))
        
        # Check if we have attachments to process
        has_attachments = len(attachments) > 0
        
        if has_attachments:
            # Use vision-capable model for image analysis
            # Build message content with images for vision models
            message_content = [{"type": "text", "text": user_message}]
            
            for attachment in attachments:
                try:
                    # Handle different types of media content
                    image_data = await self._process_attachment(attachment, session)
                    if image_data:
                        message_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        })
                except Exception as err:
                    _LOGGER.warning("Failed to process attachment: %s", err)
                    # Continue without this attachment
            
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            }
        else:
            # Standard text-only message
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
            # Use vision-capable model when we have image attachments
            model_to_use = self.chat_model
            if has_attachments:
                # Use a vision-capable model if available
                if self.chat_model.startswith('gpt-4'):
                    model_to_use = self.chat_model  # GPT-4 models support vision
                else:
                    # Fallback to a vision-capable model
                    model_to_use = "gpt-4o"  # Default vision-capable model
                    _LOGGER.info("Switching to vision-capable model %s for attachment processing", model_to_use)
            
            async with session.post(
                f"{self._endpoint}/openai/deployments/{model_to_use}/chat/completions",
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