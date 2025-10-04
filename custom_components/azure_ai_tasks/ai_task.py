"""Azure AI Task entity for Home Assistant."""
from __future__ import annotations

import base64
import logging
from json import JSONDecodeError

import re
import io

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
            
        # Add attachment support if the feature exists and we have a chat or vision-capable image model
        supports_attachments = False
        if self._chat_model:
            supports_attachments = True
        # Add support for image models that accept attachments (vision models)
        if self._image_model and self._image_model.lower() in ["gpt-image-1", "flux.1-kontext-pro", "gpt-4v", "gpt-4o"]:
            supports_attachments = True
        if supports_attachments:
            try:
                features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            except AttributeError:
                pass
                
        self._attr_supported_features = features
    
    @property
    def supports_attachments(self) -> bool:
        """Return whether the entity supports attachments (chat or vision image models)."""
        if self.chat_model:
            return True
        if self.image_model and self.image_model.lower() in ["gpt-image-1", "flux.1-kontext-pro", "gpt-4v", "gpt-4o"]:
            return True
        return False

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
        vision_models = ["gpt-image-1", "flux.1-kontext-pro", "gpt-4v", "gpt-4o"]
        # Add data generation if chat model is configured
        if self.chat_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_DATA
        # Add image generation if image model is configured
        if self.image_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE
        # Add attachment support if chat model or vision image model is present
        if self.chat_model or (self.image_model and self.image_model.lower() in vision_models):
            try:
                features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            except AttributeError:
                pass
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
            _LOGGER.debug("_process_attachment: attachment=%r, type=%r, dir=%r", attachment, type(attachment), dir(attachment))
            # Handle different media content types
            if hasattr(attachment, 'media_content_id'):
                media_id = attachment.media_content_id
                media_type = getattr(attachment, 'media_content_type', '')
                _LOGGER.debug("Processing attachment: media_id=%s, media_type=%s", media_id, media_type)
                # Handle camera streams
                if media_id.startswith('media-source://camera/'):
                    return await self._process_camera_attachment(media_id, session)
                # Handle uploaded images and local media files, including media-source://image/
                elif (
                    media_id.startswith('media-source://media_source/') or
                    media_id.startswith('/media/local/') or
                    'local/' in media_id or
                    media_id.startswith('media-source://image/')
                ):
                    # For media-source://image/, prefer reading from path if available
                    if hasattr(attachment, 'path'):
                        _LOGGER.debug("media-source://image/ detected, using path attribute: %r", getattr(attachment, 'path', None))
                        from pathlib import Path
                        file_path = Path(attachment.path)
                        _LOGGER.debug("Attachment has .path attribute: %r (type: %r)", file_path, type(file_path))
                        _LOGGER.debug("Checking file existence: %r, is_file: %r", file_path.exists(), file_path.is_file())
                        try:
                            import os
                            if not file_path.exists():
                                _LOGGER.error("Attachment path does not exist: %r", file_path)
                                return None
                            if not file_path.is_file():
                                _LOGGER.error("Attachment path is not a file: %r", file_path)
                                return None
                            if not os.access(file_path, os.R_OK):
                                _LOGGER.error("Attachment path is not readable (permission denied): %r", file_path)
                                return None
                            _LOGGER.debug("Opening file for reading: %r", file_path)
                            import aiofiles
                            async with aiofiles.open(file_path, 'rb') as f:
                                image_data = await f.read()
                            _LOGGER.debug("Read %d bytes from file %r", len(image_data), file_path)
                            return base64.b64encode(image_data).decode('utf-8')
                        except Exception as err:
                            import traceback
                            _LOGGER.error("Exception reading attachment path: %s\nTraceback: %s (attachment=%r)", err, traceback.format_exc(), attachment)
                    # fallback to media source handler
                    return await self._process_media_source_attachment(media_id, session)
                # Handle direct image URLs or other formats
                elif media_type.startswith('image/'):
                    return await self._process_image_attachment(media_id, session)
                else:
                    _LOGGER.warning("Unsupported media type: %s (media_id=%s)", media_type, media_id)
            # Try to handle generic file-like or data/content/path attributes (for generate_data and fallback)
            elif hasattr(attachment, 'file'):
                _LOGGER.debug("Attachment has .file attribute, attempting to read and encode.")
                file_obj = getattr(attachment, 'file')
                file_obj.seek(0)
                image_data = file_obj.read()
                return base64.b64encode(image_data).decode('utf-8')
            elif hasattr(attachment, 'data'):
                _LOGGER.debug("Attachment has .data attribute, attempting to encode.")
                image_data = getattr(attachment, 'data')
                return base64.b64encode(image_data).decode('utf-8')
            elif hasattr(attachment, 'content'):
                _LOGGER.debug("Attachment has .content attribute, attempting to encode.")
                image_data = getattr(attachment, 'content')
                return base64.b64encode(image_data).decode('utf-8')
            elif hasattr(attachment, 'path'):
                from pathlib import Path
                file_path = Path(attachment.path)
                _LOGGER.debug("Attachment has .path attribute (fallback): %r (type: %r)", file_path, type(file_path))
                _LOGGER.debug("Checking file existence: %r, is_file: %r", file_path.exists(), file_path.is_file())
                try:
                    import os
                    if not file_path.exists():
                        _LOGGER.error("Attachment path does not exist: %r", file_path)
                        return None
                    if not file_path.is_file():
                        _LOGGER.error("Attachment path is not a file: %r", file_path)
                        return None
                    if not os.access(file_path, os.R_OK):
                        _LOGGER.error("Attachment path is not readable (permission denied): %r", file_path)
                        return None
                    _LOGGER.debug("Opening file for reading: %r", file_path)
                    import aiofiles
                    async with aiofiles.open(file_path, 'rb') as f:
                        image_data = await f.read()
                    _LOGGER.debug("Read %d bytes from file %r", len(image_data), file_path)
                    return base64.b64encode(image_data).decode('utf-8')
                except Exception as err:
                    import traceback
                    _LOGGER.error("Exception reading attachment path (fallback): %s\nTraceback: %s (attachment=%r)", err, traceback.format_exc(), attachment)
            else:
                _LOGGER.warning("Attachment does not have media_content_id, file, data, content, or path: %r", attachment)
        except Exception as err:
            _LOGGER.error("Error processing attachment: %s (attachment=%r)", err, attachment)
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
        """Handle a generate image task, including attachments for vision models."""
        if not self.image_model:
            raise HomeAssistantError("No image model configured for this entity")

        session = async_get_clientsession(self._hass)

        # Extract the task instructions and attachments from the chat log and task
        user_message = None
        attachments = []
        for content in chat_log.content:
            if isinstance(content, conversation.UserContent):
                user_message = content.content
            elif hasattr(content, 'media_content_id'):
                attachments.append(content)
            elif hasattr(content, 'attachments'):
                if isinstance(content.attachments, list):
                    attachments.extend(content.attachments)
                else:
                    attachments.append(content.attachments)
            elif hasattr(content, 'content_type') and content.content_type.startswith('image/'):
                attachments.append(content)
        if hasattr(task, 'attachments') and task.attachments:
            if isinstance(task.attachments, list):
                attachments.extend(task.attachments)
            else:
                attachments.append(task.attachments)

        if not user_message:
            raise HomeAssistantError("No task instructions found in chat log")

        image_model = self.image_model
        vision_models = ["gpt-image-1", "flux.1-kontext-pro", "gpt-4v", "gpt-4o"]

        # Distinguish between image creation and image edit for FLUX.1-Kontext-pro
        if image_model.lower() == "flux.1-kontext-pro":
            if attachments:
                # Image edit: use /images/edits endpoint, JSON payload, image as base64 string
                image_data_b64 = await self._process_attachment(attachments[0], session)
                if not image_data_b64:
                    _LOGGER.error("Failed to process image attachment for editing. Attachments: %r", attachments)
                    raise HomeAssistantError("Failed to process image attachment for editing.")

                url = f"{self._endpoint}/openai/deployments/{image_model}/images/edits"
                api_version = "2025-04-01-preview"
                headers = {
                    "Content-Type": "application/json",
                    "api-key": self._api_key
                }
                payload = {
                    "model": image_model,
                    "prompt": user_message,
                    "image": image_data_b64,
                    "response_format": "b64_json",
                    "size": "1024x1024"
                }
                try:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        params={"api-version": api_version}
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            _LOGGER.error("Azure AI image edit error: %s (status=%s)", error_text, response.status)
                            try:
                                result = await response.json()
                                _LOGGER.error("Azure AI image edit error full response: %r", result)
                            except Exception:
                                pass
                            if "contentFilter" in error_text:
                                raise HomeAssistantError("Image edit blocked by content filter")
                            elif response.status == 401:
                                raise HomeAssistantError("Authentication failed - check your API key")
                            elif response.status == 404:
                                raise HomeAssistantError(f"Model '{image_model}' not found - check your deployment name")
                            else:
                                raise HomeAssistantError(f"Azure AI image edit error: {response.status}")
                        result = await response.json()
                        if "data" in result and len(result["data"]) > 0:
                            image_item = result["data"][0]
                            if "b64_json" in image_item:
                                image_data = base64.b64decode(image_item["b64_json"])
                            elif "url" in image_item:
                                async with session.get(image_item["url"]) as img_response:
                                    if img_response.status == 200:
                                        image_data = await img_response.read()
                                    else:
                                        raise HomeAssistantError(f"Failed to download image: {img_response.status}")
                            else:
                                raise HomeAssistantError("No image data found in response")
                            revised_prompt = user_message
                            width = 1024
                            height = 1024
                            mime_type = "image/png"
                            chat_log.async_add_assistant_content_without_tools(
                                conversation.AssistantContent(
                                    agent_id=self.entity_id,
                                    content=f"Edited image: {revised_prompt}",
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
            else:
                # Image creation: use /images/generations and JSON
                headers = {
                    "Content-Type": "application/json",
                    "api-key": self._api_key
                }
                payload = {
                    "prompt": user_message,
                    "model": image_model,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "b64_json"
                }
                url = f"{self._endpoint}/openai/deployments/{image_model}/images/generations"
                api_version = "2025-04-01-preview"
                try:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        params={"api-version": api_version}
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            _LOGGER.error("Azure AI image generation error: %s (status=%s)", error_text, response.status)
                            try:
                                result = await response.json()
                                _LOGGER.error("Azure AI image generation error full response: %r", result)
                            except Exception:
                                pass
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
                            if "b64_json" in image_item:
                                image_data = base64.b64decode(image_item["b64_json"])
                            elif "url" in image_item:
                                async with session.get(image_item["url"]) as img_response:
                                    if img_response.status == 200:
                                        image_data = await img_response.read()
                                    else:
                                        raise HomeAssistantError(f"Failed to download image: {img_response.status}")
                            else:
                                raise HomeAssistantError("No image data found in response")
                            revised_prompt = user_message
                            width = 1024
                            height = 1024
                            mime_type = "image/png"
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
                # End FLUX.1-Kontext-pro image creation
            return  # Prevent further processing for FLUX.1-Kontext-pro

        # ...existing code for other models...
        headers = {
            "Content-Type": "application/json",
            "api-key": self._api_key
        }
        if image_model.lower() in vision_models and attachments and image_model.lower() != "flux.1-kontext-pro":
            message_content = [{"type": "text", "text": user_message}]
            for attachment in attachments:
                try:
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
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.7,
                "model": image_model
            }
            url = f"{self._endpoint}/openai/deployments/{image_model}/chat/completions"
            api_version = "2025-04-01-preview"
        else:
            # Standard text-to-image
            payload = {
                "prompt": user_message,
                "model": image_model,
                "n": 1,
            }
            # Configure parameters based on the specific model
            if image_model == "gpt-image-1":
                payload.update({
                    "size": "1024x1024",
                    "quality": "high",
                    "output_format": "png",
                    "output_compression": 100,
                })
                api_version = "2025-04-01-preview"
            elif image_model == "dall-e-3":
                payload.update({
                    "size": "1024x1024",
                    "quality": "standard",
                    "style": "vivid",
                    "response_format": "b64_json",
                })
                api_version = "2024-10-21"
            elif image_model == "dall-e-2":
                payload.update({
                    "size": "1024x1024",
                    "response_format": "b64_json",
                })
                api_version = "2024-10-21"
            else:
                payload.update({
                    "size": "1024x1024",
                    "quality": "standard",
                })
                api_version = "2024-10-21"
            url = f"{self._endpoint}/openai/deployments/{image_model}/images/generations"

            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    params={"api-version": api_version}
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Azure AI image generation error: %s", error_text)
                        if "contentFilter" in error_text:
                            raise HomeAssistantError("Image generation blocked by content filter")
                        elif response.status == 401:
                            raise HomeAssistantError("Authentication failed - check your API key")
                        elif response.status == 404:
                            raise HomeAssistantError(f"Model '{image_model}' not found - check your deployment name")
                        else:
                            raise HomeAssistantError(f"Azure AI image generation error: {response.status}")
                    result = await response.json()
                    # Vision models return choices, standard image models return data
                    if "choices" in result and len(result["choices"]) > 0:
                        # Vision model response: extract image from content
                        content = result["choices"][0]["message"]["content"]
                        match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', str(content))
                        if match:
                            image_data = base64.b64decode(match.group(1))
                        else:
                            raise HomeAssistantError("No image data found in vision model response")
                        revised_prompt = user_message
                        width = 1024
                        height = 1024
                        mime_type = "image/png"
                    elif "data" in result and len(result["data"]) > 0:
                        image_item = result["data"][0]
                        if "b64_json" in image_item:
                            image_data = base64.b64decode(image_item["b64_json"])
                        elif "url" in image_item:
                            async with session.get(image_item["url"]) as img_response:
                                if img_response.status == 200:
                                    image_data = await img_response.read()
                                else:
                                    raise HomeAssistantError(f"Failed to download image: {img_response.status}")
                        else:
                            raise HomeAssistantError("No image data found in response")
                        revised_prompt = image_item.get("revised_prompt", user_message)
                        width = 1024
                        height = 1024
                        if "size" in payload:
                            try:
                                size_parts = payload["size"].split("x")
                                if len(size_parts) == 2:
                                    width = int(size_parts[0])
                                    height = int(size_parts[1])
                            except (ValueError, IndexError):
                                pass
                        if image_model == "gpt-image-1":
                            output_format = payload.get("output_format", "png")
                            mime_type = f"image/{output_format}"
                        else:
                            mime_type = "image/png"
                    elif "error" in result:
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
        # For structured tasks, always instruct the model to return raw JSON (no markdown/code blocks)
        if task.structure:
            user_message = (
                f"{user_message}\n\nRespond ONLY with valid JSON, no markdown, no code blocks, no explanation."
            )
        if has_attachments:
            # Always use the configured chat model deployment for attachments (restore previous behavior)
            model_to_use = self.chat_model
            _LOGGER.info("Using configured chat model '%s' for attachment processing", model_to_use)
            message_content = [{"type": "text", "text": user_message}]
            for attachment in attachments:
                try:
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
            model_to_use = self.chat_model

        try:
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
                        import re
                        cleaned = text.strip()
                        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.MULTILINE)
                        cleaned = cleaned.strip()
                        try:
                            data = json_loads(cleaned)
                        except JSONDecodeError as err:
                            _LOGGER.error(
                                "Failed to parse JSON response: %s. Response: %s",
                                err,
                                cleaned,
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