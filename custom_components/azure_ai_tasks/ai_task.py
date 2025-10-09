"""Azure AI Task entity for Home Assistant."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import aiofiles
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

# API Constants
API_VERSION_CHAT = "2024-02-15-preview"
API_VERSION_IMAGE_LATEST = "2025-04-01-preview"
API_VERSION_IMAGE_LEGACY = "2024-10-21"

# Model Constants
VISION_MODELS = ["gpt-image-1", "flux.1-kontext-pro", "gpt-4v", "gpt-4o"]
FLUX_MODEL = "flux.1-kontext-pro"

# Image Generation Constants
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_MIME_TYPE = "image/png"
MAX_TOKENS = 1000
DEFAULT_TEMPERATURE = 0.7

# Media Source Prefixes
MEDIA_SOURCE_CAMERA = "media-source://camera/"
MEDIA_SOURCE_LOCAL = "media-source://media_source/local/"
MEDIA_SOURCE_IMAGE = "media-source://image/"
MEDIA_LOCAL_PATH = "/media/local/"


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

    def _is_vision_model(self, model: str | None) -> bool:
        """Check if a model supports vision/attachments."""
        return bool(model and model.lower() in VISION_MODELS)

    @property
    def supported_features(self) -> int:
        """Return the supported features of the entity."""
        features = 0
        # Add data generation if chat model is configured
        if self.chat_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_DATA
        # Add image generation if image model is configured
        if self.image_model:
            features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE
        # Add attachment support if chat model or vision image model is present
        if self.chat_model or self._is_vision_model(self.image_model):
            try:
                features |= ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            except AttributeError:
                pass
        return features

    @property
    def supports_attachments(self) -> bool:
        """Return whether the entity supports attachments."""
        return bool(self.chat_model or self._is_vision_model(self.image_model))

    @property 
    def supports_media_attachments(self) -> bool:
        """Return whether the entity supports media attachments."""
        return self.supports_attachments

    def _get_headers(self, use_bearer_auth: bool = False) -> dict[str, str]:
        """Get standard headers for API requests."""
        auth_header = f"Bearer {self._api_key}" if use_bearer_auth else self._api_key
        return {
            "Content-Type": "application/json",
            "Authorization" if use_bearer_auth else "api-key": auth_header
        }

    def _handle_api_error(self, status: int, error_text: str, model: str) -> None:
        """Handle common API errors with consistent messaging."""
        if "contentFilter" in error_text:
            raise HomeAssistantError("Request blocked by content filter")
        elif status == 401:
            raise HomeAssistantError("Authentication failed - check your API key")
        elif status == 404:
            raise HomeAssistantError(f"Model '{model}' not found - check your deployment name")
        else:
            raise HomeAssistantError(f"Azure AI API error: {status}")

    def _extract_image_size(self, size_str: str) -> tuple[int, int]:
        """Extract width and height from size string like '1024x1024'."""
        try:
            parts = size_str.split("x")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
        return DEFAULT_WIDTH, DEFAULT_HEIGHT

    async def _download_image_from_url(self, session: aiohttp.ClientSession, url: str) -> bytes:
        """Download image data from a URL."""
        async with session.get(url) as response:
            if response.status == 200:
                return await response.read()
            else:
                raise HomeAssistantError(f"Failed to download image: {response.status}")

    def _extract_base64_from_vision_response(self, content: str) -> bytes:
        """Extract base64 image data from vision model response."""
        match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', str(content))
        if match:
            return base64.b64decode(match.group(1))
        else:
            raise HomeAssistantError("No image data found in vision model response")

    async def _process_attachment(self, attachment: Any, session: aiohttp.ClientSession) -> str | None:
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

    async def _process_camera_attachment(self, media_id: str, session: aiohttp.ClientSession) -> str | None:
        """Process camera media attachment."""
        try:
            # Extract camera entity ID from media_id
            camera_entity = media_id.replace(MEDIA_SOURCE_CAMERA, '')
            
            # Use Home Assistant's camera component to get image
            from homeassistant.components.camera import async_get_image
            
            image_bytes = await async_get_image(self._hass, camera_entity)
            return base64.b64encode(image_bytes.content).decode('utf-8')
                
        except Exception as err:
            _LOGGER.error("Error processing camera attachment %s: %s", media_id, err)
            return None

    async def _process_media_source_attachment(self, media_id: str, session: aiohttp.ClientSession) -> str | None:
        """Process media source attachment."""
        try:
            # Use Home Assistant's media source to resolve the attachment
            from homeassistant.components.media_source import async_resolve_media
            
            resolved_media = await async_resolve_media(self._hass, media_id, None)
            if resolved_media and resolved_media.url:
                # Get the resolved URL and fetch the content
                image_data = await self._download_image_from_url(session, resolved_media.url)
                return base64.b64encode(image_data).decode('utf-8')
            else:
                _LOGGER.error("Failed to resolve media source %s: No URL returned", media_id)
                
        except Exception as err:
            _LOGGER.error("Failed to resolve media source %s: %s", media_id, err)
            # Try to handle local media files directly if media source resolution fails
            if 'local/' in media_id:
                return await self._process_local_media_file(media_id, session)
                        
        return None

    def _extract_filename_from_media_id(self, media_id: str) -> str | None:
        """Extract filename from media_id."""
        if MEDIA_SOURCE_LOCAL in media_id:
            return media_id.split(MEDIA_SOURCE_LOCAL)[-1]
        elif MEDIA_LOCAL_PATH in media_id:
            return media_id.split(MEDIA_LOCAL_PATH)[-1]
        return None

    def _get_media_file_paths(self, filename: str) -> list[Path]:
        """Get possible paths for a media file."""
        return [
            Path(self._hass.config.path("www", "media", filename)),
            Path("/media") / filename,
            Path(self._hass.config.path("www")) / filename
        ]

    async def _process_local_media_file(self, media_id: str, session: aiohttp.ClientSession) -> str | None:
        """Process local media file directly."""
        try:
            filename = self._extract_filename_from_media_id(media_id)
            if not filename:
                _LOGGER.error("Unable to extract filename from media_id: %s", media_id)
                return None
            
            # Try different possible paths for the media file
            for media_path in self._get_media_file_paths(filename):
                if media_path.exists() and media_path.is_file() and os.access(media_path, os.R_OK):
                    _LOGGER.debug("Reading local media file: %s", media_path)
                    with open(media_path, 'rb') as f:
                        image_data = f.read()
                        return base64.b64encode(image_data).decode('utf-8')
            
            _LOGGER.error("Local media file not found or not readable: %s", filename)
                
        except Exception as err:
            _LOGGER.error("Error processing local media file %s: %s", media_id, err)
            
        return None

    async def _process_image_attachment(self, media_id: str, session: aiohttp.ClientSession) -> str | None:
        """Process direct image attachment."""
        try:
            image_data = await self._download_image_from_url(session, media_id)
            return base64.b64encode(image_data).decode('utf-8')
        except Exception as err:
            _LOGGER.error("Error processing image attachment %s: %s", media_id, err)
            return None

    def _extract_message_and_attachments(
        self, 
        chat_log: conversation.ChatLog, 
        task: ai_task.GenImageTask | ai_task.GenDataTask
    ) -> tuple[str, list[Any]]:
        """Extract user message and attachments from chat log and task."""
        user_message = None
        attachments = []
        
        # Process chat log content
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
        
        # Process task attachments
        if hasattr(task, 'attachments') and task.attachments:
            if isinstance(task.attachments, list):
                attachments.extend(task.attachments)
            else:
                attachments.append(task.attachments)

        if not user_message:
            raise HomeAssistantError("No task instructions found in chat log")
            
        return user_message, attachments

    async def _build_chat_payload(
        self,
        user_message: str,
        attachments: list[Any],
        session: aiohttp.ClientSession,
        model: str
    ) -> dict[str, Any]:
        """Build chat completion payload with or without attachments."""
        if attachments:
            message_content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
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
            
            return {
                "messages": [{"role": "user", "content": message_content}],
                "max_tokens": MAX_TOKENS,
                "temperature": DEFAULT_TEMPERATURE
            }
        else:
            return {
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": MAX_TOKENS,
                "temperature": DEFAULT_TEMPERATURE
            }

    async def _handle_flux_image_edit(
        self, 
        session: aiohttp.ClientSession, 
        user_message: str, 
        attachments: list[Any],
        image_model: str,
        chat_log: conversation.ChatLog
    ) -> ai_task.GenImageTaskResult:
        """Handle FLUX image editing with attachments."""
        # Process the first attachment for editing
        image_data_b64 = await self._process_attachment(attachments[0], session)
        if not image_data_b64:
            _LOGGER.error("Failed to process image attachment for editing. Attachments: %r", attachments)
            raise HomeAssistantError("Failed to process image attachment for editing.")

        url = f"{self._endpoint}/openai/deployments/{image_model}/images/edits"
        headers = self._get_headers()
        payload = {
            "model": image_model,
            "prompt": user_message,
            "image": image_data_b64,
            "response_format": "b64_json",
            "size": DEFAULT_IMAGE_SIZE
        }
        
        async with session.post(
            url,
            headers=headers,
            json=payload,
            params={"api-version": API_VERSION_IMAGE_LATEST}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Azure AI image edit error: %s (status=%s)", error_text, response.status)
                self._handle_api_error(response.status, error_text, image_model)
            
            result = await response.json()
            return await self._process_image_generation_result(
                result, user_message, image_model, chat_log, DEFAULT_WIDTH, DEFAULT_HEIGHT, session
            )

    async def _handle_flux_image_generation(
        self,
        session: aiohttp.ClientSession,
        user_message: str,
        image_model: str,
        chat_log: conversation.ChatLog
    ) -> ai_task.GenImageTaskResult:
        """Handle FLUX image generation without attachments."""
        headers = self._get_headers()
        payload = {
            "prompt": user_message,
            "model": image_model,
            "n": 1,
            "size": DEFAULT_IMAGE_SIZE,
            "response_format": "b64_json"
        }
        url = f"{self._endpoint}/openai/deployments/{image_model}/images/generations"
        
        async with session.post(
            url,
            headers=headers,
            json=payload,
            params={"api-version": API_VERSION_IMAGE_LATEST}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Azure AI image generation error: %s (status=%s)", error_text, response.status)
                self._handle_api_error(response.status, error_text, image_model)
            
            result = await response.json()
            return await self._process_image_generation_result(
                result, user_message, image_model, chat_log, DEFAULT_WIDTH, DEFAULT_HEIGHT, session
            )

    async def _process_image_generation_result(
        self,
        result: dict[str, Any],
        user_message: str,
        model: str,
        chat_log: conversation.ChatLog,
        width: int,
        height: int,
        session: aiohttp.ClientSession
    ) -> ai_task.GenImageTaskResult:
        """Process the result from image generation API calls."""
        # Handle vision model responses (with choices)
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            image_data = self._extract_base64_from_vision_response(content)
            revised_prompt = user_message
            mime_type = DEFAULT_MIME_TYPE
            
        # Handle standard image generation responses (with data)
        elif "data" in result and len(result["data"]) > 0:
            image_item = result["data"][0]
            if "b64_json" in image_item:
                image_data = base64.b64decode(image_item["b64_json"])
            elif "url" in image_item:
                image_data = await self._download_image_from_url(session, image_item["url"])
            else:
                raise HomeAssistantError("No image data found in response")
                
            revised_prompt = image_item.get("revised_prompt", user_message)
            mime_type = DEFAULT_MIME_TYPE
            
        # Handle API errors
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
            model=model,
            revised_prompt=revised_prompt,
        )

    async def _handle_vision_model_request(
        self,
        session: aiohttp.ClientSession,
        user_message: str,
        attachments: list[Any],
        image_model: str,
        chat_log: conversation.ChatLog
    ) -> ai_task.GenImageTaskResult:
        """Handle vision model requests with attachments."""
        message_content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
        
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
            "messages": [{"role": "user", "content": message_content}],
            "max_tokens": MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "model": image_model
        }
        url = f"{self._endpoint}/openai/deployments/{image_model}/chat/completions"
        headers = self._get_headers()
        
        async with session.post(
            url,
            headers=headers,
            json=payload,
            params={"api-version": API_VERSION_IMAGE_LATEST}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Azure AI vision model error: %s", error_text)
                self._handle_api_error(response.status, error_text, image_model)
            
            result = await response.json()
            return await self._process_image_generation_result(
                result, user_message, image_model, chat_log, DEFAULT_WIDTH, DEFAULT_HEIGHT, session
            )

    async def _handle_standard_image_generation(
        self,
        session: aiohttp.ClientSession,
        user_message: str,
        image_model: str,
        chat_log: conversation.ChatLog
    ) -> ai_task.GenImageTaskResult:
        """Handle standard text-to-image generation."""
        payload = {
            "prompt": user_message,
            "model": image_model,
            "n": 1,
        }
        
        # Configure parameters based on the specific model
        api_version = API_VERSION_IMAGE_LEGACY
        if image_model == "gpt-image-1":
            payload.update({
                "size": DEFAULT_IMAGE_SIZE,
                "quality": "high",
                "output_format": "png",
                "output_compression": 100,
            })
            api_version = API_VERSION_IMAGE_LATEST
        elif image_model == "dall-e-3":
            payload.update({
                "size": DEFAULT_IMAGE_SIZE,
                "quality": "standard",
                "style": "vivid",
                "response_format": "b64_json",
            })
        elif image_model == "dall-e-2":
            payload.update({
                "size": DEFAULT_IMAGE_SIZE,
                "response_format": "b64_json",
            })
        else:
            payload.update({
                "size": DEFAULT_IMAGE_SIZE,
                "quality": "standard",
            })

        url = f"{self._endpoint}/openai/deployments/{image_model}/images/generations"
        headers = self._get_headers()
        
        async with session.post(
            url,
            headers=headers,
            json=payload,
            params={"api-version": api_version}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Azure AI image generation error: %s", error_text)
                self._handle_api_error(response.status, error_text, image_model)
            
            result = await response.json()
            width, height = self._extract_image_size(payload.get("size", DEFAULT_IMAGE_SIZE))
            return await self._process_image_generation_result(
                result, user_message, image_model, chat_log, width, height, session
            )

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task, including attachments for vision models."""
        if not self.image_model:
            raise HomeAssistantError("No image model configured for this entity")

        session = async_get_clientsession(self._hass)
        user_message, attachments = self._extract_message_and_attachments(chat_log, task)

        image_model = self.image_model

        # Handle FLUX.1-Kontext-pro model specifically
        if image_model.lower() == FLUX_MODEL:
            if attachments:
                return await self._handle_flux_image_edit(
                    session, user_message, attachments, image_model, chat_log
                )
            else:
                return await self._handle_flux_image_generation(
                    session, user_message, image_model, chat_log
                )

        # Handle other image models
        try:
            # Vision models with attachments
            if self._is_vision_model(image_model) and attachments:
                return await self._handle_vision_model_request(
                    session, user_message, attachments, image_model, chat_log
                )
            # Standard text-to-image generation
            else:
                return await self._handle_standard_image_generation(
                    session, user_message, image_model, chat_log
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
        if not self.chat_model:
            raise HomeAssistantError("No chat model configured for this entity")
            
        session = async_get_clientsession(self._hass)
        user_message, attachments = self._extract_message_and_attachments(chat_log, task)
        
        _LOGGER.debug("Processing data generation task with %d attachments", len(attachments))
        
        # For structured tasks, instruct the model to return properly formatted JSON
        if task.structure:
            try:
                structure_instructions = self._build_structure_instructions(task.structure)
                user_message = (
                    f"{user_message}\n\n{structure_instructions}\n\n"
                    "Respond ONLY with valid JSON matching the exact structure above. "
                    "Do not include markdown, code blocks, or explanations."
                )
            except Exception as e:
                _LOGGER.error("Failed to process structure: %s", e)
                # Fallback to generic structured output instruction
                user_message = (
                    f"{user_message}\n\n"
                    "Return your response as valid JSON with appropriate field names and values. "
                    "Respond ONLY with valid JSON, no markdown, code blocks, or explanations."
                )
        
        # Build the payload using the helper method
        payload = await self._build_chat_payload(user_message, attachments, session, self.chat_model)
        model_to_use = self.chat_model
        headers = self._get_headers(use_bearer_auth=True)

        try:
            async with session.post(
                f"{self._endpoint}/openai/deployments/{model_to_use}/chat/completions",
                headers=headers,
                json=payload,
                params={"api-version": API_VERSION_CHAT}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Azure AI API error: %s", error_text)
                    self._handle_api_error(response.status, error_text, model_to_use)
                    
                result = await response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    text = result["choices"][0]["message"]["content"].strip()
                    
                    # If the task requires structured data, parse as JSON
                    if task.structure:
                        data = self._parse_structured_response(text)
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

    def _build_structure_instructions(self, structure: Any) -> str:
        """Build clear instructions for the AI model based on the structure schema."""
        instructions = ["Return a JSON object with the following structure:"]
        
        try:
            # Try to handle different types of structure objects
            schema_dict = None
            
            # Handle voluptuous Schema objects
            if hasattr(structure, 'schema') and isinstance(structure.schema, dict):
                raw_schema = structure.schema
                schema_dict = {}
                
                # Convert voluptuous keys to string field names
                for key, value in raw_schema.items():
                    try:
                        # Extract field name from voluptuous key objects
                        if hasattr(key, 'schema'):
                            # This is likely a voluptuous key like Optional or Required
                            field_name = str(key.schema)
                        elif hasattr(key, 'key'):
                            # Some voluptuous objects have a 'key' attribute
                            field_name = str(key.key)
                        else:
                            # Fallback to string representation
                            field_name = str(key)
                        
                        # Clean up the field name
                        field_name = field_name.strip("'\"")
                        schema_dict[field_name] = value
                        
                    except Exception as e:
                        _LOGGER.warning("Error processing voluptuous key %s: %s", key, e)
                        # Skip problematic keys
                        continue
            elif isinstance(structure, dict):
                schema_dict = structure
            else:
                # Last resort: try to iterate and build dict
                try:
                    schema_dict = {}
                    for key in structure:
                        field_name = str(key)
                        schema_dict[field_name] = getattr(structure, key, {})
                except Exception:
                    _LOGGER.warning("Unable to parse structure schema of type %s", type(structure))
                    return "Return a JSON object with the requested data structure in a logical format."
            
            if not schema_dict:
                return "Return a JSON object with the requested data structure in a logical format."
            
            # Build the JSON schema example
            example_object = {}
            field_descriptions = []
            
            for field_name, field_config in schema_dict.items():
                try:
                    # Handle different field config formats
                    if isinstance(field_config, dict):
                        # Extract field information
                        description = field_config.get("description", "")
                        is_required = field_config.get("required", False)
                        selector = field_config.get("selector", {})
                        
                        # Determine the field type and example value
                        field_type, example_value = self._get_field_type_and_example(selector, description)
                        example_object[field_name] = example_value
                        
                        # Build field description
                        requirement_text = "REQUIRED" if is_required else "optional"
                        if description:
                            field_descriptions.append(f"- {field_name} ({field_type}, {requirement_text}): {description}")
                        else:
                            field_descriptions.append(f"- {field_name} ({field_type}, {requirement_text})")
                    else:
                        # Handle simple field types, voluptuous validators, or other formats
                        # Try to infer type from the field_config object
                        field_type = "string"  # Default
                        example_value = "example_value"
                        
                        # Check if it's a voluptuous validator that gives us type hints
                        if hasattr(field_config, '__name__'):
                            type_name = field_config.__name__.lower()
                            if 'int' in type_name or 'number' in type_name:
                                field_type = "number"
                                example_value = 0
                            elif 'bool' in type_name:
                                field_type = "boolean" 
                                example_value = True
                            elif 'float' in type_name:
                                field_type = "number"
                                example_value = 0.0
                        
                        example_object[field_name] = example_value
                        field_descriptions.append(f"- {field_name} ({field_type}, optional)")
                        
                except Exception as e:
                    _LOGGER.warning("Error processing field %s: %s", field_name, e)
                    # Fallback for problematic fields
                    example_object[field_name] = "example_value"
                    field_descriptions.append(f"- {field_name} (string, optional)")
            
            # Add the JSON schema example
            if example_object:
                instructions.append(f"\n{json.dumps(example_object, indent=2)}")
            
                # Add field descriptions
                if field_descriptions:
                    instructions.append("\nField descriptions:")
                    instructions.extend(field_descriptions)
                
                # Add requirements note
                required_fields = []
                for name, config in schema_dict.items():
                    if isinstance(config, dict) and config.get("required", False):
                        required_fields.append(name)
                
                if required_fields:
                    instructions.append(f"\nRequired fields: {', '.join(required_fields)}")
            else:
                instructions.append("\n{}")
                instructions.append("\nPlease provide the data in a structured JSON format.")
            
            return "\n".join(instructions)
            
        except Exception as e:
            _LOGGER.error("Error building structure instructions: %s", e)
            return "Return a JSON object with the requested data structure in a logical format."
    
    def _get_field_type_and_example(self, selector: dict[str, Any], description: str) -> tuple[str, Any]:
        """Determine field type and example value from selector config."""
        if not selector:
            # Default to string if no selector specified
            return "string", "example_value"
        
        # Check selector type
        for selector_type, config in selector.items():
            if selector_type == "number":
                min_val = config.get("min", 0) if isinstance(config, dict) else 0
                max_val = config.get("max", 100) if isinstance(config, dict) else 100
                return "number", min_val
            elif selector_type == "boolean":
                return "boolean", True
            elif selector_type == "text":
                return "string", "example text"
            elif selector_type == "select":
                options = config.get("options", []) if isinstance(config, dict) else []
                if options:
                    return "string", options[0] if isinstance(options[0], str) else str(options[0])
                return "string", "option"
            elif selector_type == "date":
                return "string", "2025-01-01"
            elif selector_type == "datetime":
                return "string", "2025-01-01T12:00:00"
            elif selector_type == "time":
                return "string", "12:00:00"
        
        # Default fallback
        return "string", "example_value"

    def _parse_structured_response(self, text: str) -> Any:
        """Parse structured JSON response from AI model."""
        cleaned = text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        try:
            return json_loads(cleaned)
        except JSONDecodeError as err:
            _LOGGER.error(
                "Failed to parse JSON response: %s. Response: %s",
                err,
                cleaned,
            )
            raise HomeAssistantError("Error with Azure AI structured response") from err
