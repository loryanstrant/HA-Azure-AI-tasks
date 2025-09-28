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

from .const import CONF_API_KEY, CONF_ENDPOINT, CONF_CHAT_MODEL, CONF_IMAGE_MODEL, DOMAIN

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
                 config.get(CONF_CHAT_MODEL, "")).strip()
    
    # Get image model from options if available, otherwise use config data or defaults
    image_model = (config_entry.options.get(CONF_IMAGE_MODEL) or 
                  config.get(CONF_IMAGE_MODEL, "")).strip()
    
    _LOGGER.info("Setting up Azure AI Tasks entity with chat_model='%s', image_model='%s'", 
                 chat_model, image_model)
    
    # Ensure at least one model is configured
    if not chat_model and not image_model:
        _LOGGER.error("No models configured for Azure AI Tasks integration")
        return
    
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
        # Use config entry ID to ensure unique IDs across multiple integrations
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"
        
        # Dynamically set supported features based on configured models
        features = 0
        if self._chat_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_DATA
        if self._image_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE
            
        # Try to add attachment support if the feature exists and we have a chat model
        if self._chat_model:
            try:
                features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            except AttributeError:
                # Feature doesn't exist, that's okay
                pass
                
        self._attr_supported_features = features
    
    @property
    def supports_attachments(self) -> bool:
        """Return whether the entity supports attachments."""
        return bool(self._chat_model)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def chat_model(self) -> str | None:
        """Return the current chat model."""
        configured_model = (self._config_entry.options.get(CONF_CHAT_MODEL) or 
                           self._config_entry.data.get(CONF_CHAT_MODEL, self._chat_model))
        return configured_model.strip() if configured_model else None

    @property
    def image_model(self) -> str | None:
        """Return the current image model."""
        configured_model = (self._config_entry.options.get(CONF_IMAGE_MODEL) or 
                           self._config_entry.data.get(CONF_IMAGE_MODEL, self._image_model))
        return configured_model.strip() if configured_model else None

    @property
    def supported_features(self) -> int:
        """Return the supported features of the entity."""
        features = 0
        
        # Add data generation if chat model is configured
        if self.chat_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_DATA
            # Try to add attachment support if available
            try:
                features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            except AttributeError:
                pass
                
        # Add image generation if image model is configured
        if self.image_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE
            
        return features

    @property
    def supports_attachments(self) -> bool:
        """Return whether the entity supports attachments."""
        return bool(self.chat_model)

    @property 
    def supports_media_attachments(self) -> bool:
        """Return whether the entity supports media attachments."""
        return bool(self.chat_model)

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
                
                # Handle uploaded images and local media files
                elif (media_id.startswith('media-source://media_source/') or 
                      media_id.startswith('/media/local/') or
                      'local/' in media_id):
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
                else:
                    _LOGGER.error("Failed to resolve media source %s: No URL returned", media_id)
            except Exception as err:
                _LOGGER.error("Failed to resolve media source %s: %s", media_id, err)
                
                # Try to handle local media files directly if media source resolution fails
                if 'local/' in media_id:
                    return await self._process_local_media_file(media_id, session)
                        
        except Exception as err:
            _LOGGER.error("Error processing media source attachment: %s", err)
            
        return None

    async def _process_local_media_file(self, media_id: str, session) -> str | None:
        """Process local media file directly."""
        try:
            import os
            from pathlib import Path
            
            # Extract the local file path from media_id
            # Format: media-source://media_source/local/filename.jpg
            if 'media-source://media_source/local/' in media_id:
                filename = media_id.split('media-source://media_source/local/')[-1]
            elif '/media/local/' in media_id:
                filename = media_id.split('/media/local/')[-1]
            else:
                _LOGGER.error("Unable to extract filename from media_id: %s", media_id)
                return None
            
            # Construct the full path to the media file
            # Home Assistant typically stores local media in /media
            media_path = Path(self._hass.config.path("www", "media", filename))
            
            # Also try the standard /media path
            if not media_path.exists():
                media_path = Path("/media") / filename
                
            # Also try /config/www/media (common HA setup)
            if not media_path.exists():
                media_path = Path(self._hass.config.path("www")) / filename
                
            if media_path.exists() and media_path.is_file():
                _LOGGER.debug("Reading local media file: %s", media_path)
                with open(media_path, 'rb') as f:
                    image_data = f.read()
                    return base64.b64encode(image_data).decode('utf-8')
            else:
                _LOGGER.error("Local media file not found: %s", media_path)
                
        except Exception as err:
            _LOGGER.error("Error processing local media file: %s", err)
            
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

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task."""
        # Check if image model is configured
        if not self.image_model:
            raise HomeAssistantError("No image model configured for this entity")
            
        session = async_get_clientsession(self._hass)
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self._api_key
        }
        
        # Extract the task instructions from the chat log
        user_message = None
        for content in chat_log.content:
            if isinstance(content, conversation.UserContent):
                user_message = content.content
                break
        
        if not user_message:
            raise HomeAssistantError("No task instructions found in chat log")
        
        # Get the image model to use
        image_model = self.image_model
        
        # Build the payload for Azure OpenAI image generation API
        payload = {
            "prompt": user_message,
            "model": image_model,
            "n": 1,  # Generate one image
        }
        
        # Configure parameters based on the specific model
        if image_model == "gpt-image-1":
            # GPT-image-1 specific parameters
            payload.update({
                "size": "1024x1024",  # Options: "1024x1024", "1024x1536", "1536x1024"
                "quality": "high",  # Options: "low", "medium", "high"
                "output_format": "png",  # Options: "png", "jpeg"
                "output_compression": 100,  # 0-100, default 100
                # Note: GPT-image-1 always returns base64, no response_format needed
            })
            api_version = "2025-04-01-preview"
            
        elif image_model == "dall-e-3":
            # DALL-E 3 specific parameters  
            payload.update({
                "size": "1024x1024",  # Options: "1024x1024", "1792x1024", "1024x1792"
                "quality": "standard",  # Options: "standard", "hd"
                "style": "vivid",  # Options: "natural", "vivid" 
                "response_format": "b64_json",  # Options: "url", "b64_json"
            })
            api_version = "2024-10-21"
            
        elif image_model == "dall-e-2":
            # DALL-E 2 specific parameters
            payload.update({
                "size": "1024x1024",  # Options: "256x256", "512x512", "1024x1024"
                "response_format": "b64_json",  # Options: "url", "b64_json"
            })
            api_version = "2024-10-21"
            
        else:
            # Default fallback
            payload.update({
                "size": "1024x1024",
                "quality": "standard",
            })
            api_version = "2024-10-21"
        
        try:
            # Make the API call to Azure OpenAI image generation endpoint
            url = f"{self._endpoint}/openai/deployments/{image_model}/images/generations"
            
            async with session.post(
                url,
                headers=headers,
                json=payload,
                params={"api-version": api_version}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Azure AI image generation error: %s", error_text)
                    
                    # Handle specific error cases
                    if "contentFilter" in error_text:
                        raise HomeAssistantError("Image generation blocked by content filter")
                    elif response.status == 401:
                        raise HomeAssistantError("Authentication failed - check your API key")
                    elif response.status == 404:
                        raise HomeAssistantError(f"Model '{image_model}' not found - check your deployment name")
                    else:
                        raise HomeAssistantError(f"Azure AI image generation error: {response.status}")
                
                result = await response.json()
                
                if "data" in result and len(result["data"]) > 0:
                    image_item = result["data"][0]
                    
                    # Handle different response formats
                    if "b64_json" in image_item:
                        # Base64 encoded image (most common)
                        import base64
                        image_data = base64.b64decode(image_item["b64_json"])
                        
                    elif "url" in image_item:
                        # URL to image - fetch it
                        async with session.get(image_item["url"]) as img_response:
                            if img_response.status == 200:
                                image_data = await img_response.read()
                            else:
                                raise HomeAssistantError(f"Failed to download image: {img_response.status}")
                    else:
                        raise HomeAssistantError("No image data found in response")
                    
                    # Extract additional metadata
                    revised_prompt = image_item.get("revised_prompt", user_message)
                    
                    # Parse size from payload
                    width = 1024  # Default
                    height = 1024  # Default
                    if "size" in payload:
                        try:
                            size_parts = payload["size"].split("x")
                            if len(size_parts) == 2:
                                width = int(size_parts[0])
                                height = int(size_parts[1])
                        except (ValueError, IndexError):
                            pass  # Use defaults
                    
                    # Determine MIME type from output format or default
                    if image_model == "gpt-image-1":
                        output_format = payload.get("output_format", "png")
                        mime_type = f"image/{output_format}"
                    else:
                        # DALL-E models typically return PNG
                        mime_type = "image/png"
                    
                    # Add to chat log
                    chat_log.async_add_assistant_content_without_tools(
                        conversation.AssistantContent(
                            agent_id=self.entity_id,
                            content=f"Generated image: {revised_prompt}",
                        )
                    )
                    
                    return ai_task.GenImageTaskResult(
                        image_data=image_data,
                        conversation_id=chat_log.conversation_id,
                        mime_type=mime_type,
                        width=width,
                        height=height,
                        model=image_model,
                        revised_prompt=revised_prompt,
                    )
                    
                elif "error" in result:
                    # Handle API errors
                    error = result["error"]
                    error_code = error.get("code", "unknown")
                    error_message = error.get("message", "Unknown error")
                    
                    if error_code == "contentFilter":
                        raise HomeAssistantError(f"Content filter: {error_message}")
                    else:
                        raise HomeAssistantError(f"API error [{error_code}]: {error_message}")
                        
                else:
                    _LOGGER.error("Unexpected response format from Azure AI: %s", result)
                    raise HomeAssistantError("Unexpected response format from Azure AI")
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error communicating with Azure AI: %s", err)
            raise HomeAssistantError(f"Error communicating with Azure AI: {err}") from err

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        # Check if chat model is configured
        if not self.chat_model:
            raise HomeAssistantError("No chat model configured for this entity")
            
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