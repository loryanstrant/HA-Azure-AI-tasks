"""Constants for the Azure AI Tasks integration."""

DOMAIN = "azure_ai_tasks"

# Configuration keys
CONF_ENDPOINT = "endpoint"
CONF_API_KEY = "api_key"
CONF_CHAT_MODEL = "chat_model"
CONF_IMAGE_MODEL = "image_model"

# Default values
DEFAULT_NAME = "Azure AI Tasks"
DEFAULT_CHAT_MODEL = "gpt-35-turbo"
DEFAULT_IMAGE_MODEL = "dall-e-3"

# Available models
CHAT_MODELS = [
    "gpt-35-turbo",
    "gpt-35-turbo-16k",
    "gpt-4",
    "gpt-4-32k",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini"
]

IMAGE_MODELS = [
    "dall-e-2",
    "dall-e-3"
]