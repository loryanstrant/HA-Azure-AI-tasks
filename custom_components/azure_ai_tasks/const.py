"""Constants for the Azure AI Tasks integration."""

DOMAIN = "azure_ai_tasks"

# The config entry schema version this release understands. Bump it alongside
# ConfigFlow.VERSION whenever the stored entry shape changes, and give
# async_migrate_entry a branch for the previous version.
CONFIG_ENTRY_VERSION = 2

# Repair issue IDs (suffixed with the entry ID, so two entries can each raise
# their own issue).
ISSUE_MIGRATION_DOWNGRADE = "migrate_downgrade"
ISSUE_MIGRATION_INCOMPLETE = "migrate_incomplete_config"
# Same problem as ISSUE_MIGRATION_INCOMPLETE, but raised on Home Assistant
# versions without config_entries.async_retry_migration, where we cannot offer
# a Fix button - an entry in the migration_error state is non-recoverable, so
# async_reload refuses to touch it and only a restart re-runs the migration.
ISSUE_MIGRATION_INCOMPLETE_RESTART = "migrate_incomplete_config_restart"

# Configuration keys
CONF_ENDPOINT = "endpoint"
CONF_API_KEY = "api_key"
CONF_CHAT_MODEL = "chat_model"
CONF_IMAGE_MODEL = "image_model"
# Whether each model is a reasoning model (GPT-5, o-series). Reasoning models
# need max_completion_tokens and reject a custom temperature; other models use
# max_tokens and temperature.
CONF_CHAT_REASONING = "chat_reasoning_model"
CONF_IMAGE_REASONING = "image_reasoning_model"


def legacy_reasoning_default(model: str) -> bool:
    """Default for entries saved before the reasoning option existed.

    Those entries relied on automatic detection of GPT-5 by name, so keep that
    result until the user picks a value, instead of breaking working setups.
    """
    return (model or "").strip().lower().startswith(("gpt-5", "gpt-6"))


# Azure exposes two OpenAI-compatible surfaces and this integration supports
# both, picked automatically from the endpoint the user configured:
#   * Classic Azure OpenAI ({resource}.openai.azure.com) - the deployment name is
#     in the URL path and an "api-version" query parameter is required.
#   * Azure AI Foundry "v1" ({resource}.services.ai.azure.com) - a single
#     /openai/v1/... path, the model goes in the request body, and there is no
#     api-version query at all.
# See https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-lifecycle
V1_HOST_MARKER = "services.ai.azure.com"
V1_PATH_MARKER = "/openai/v1"

# Default values
DEFAULT_NAME = "Azure AI Tasks"
DEFAULT_CHAT_MODEL = "gpt-4o"
DEFAULT_IMAGE_MODEL = "dall-e-3"

# Available models
CHAT_MODELS = [
    "gpt-4",
    "gpt-4-32k", 
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-mini"
]

# Available image generation models
IMAGE_MODELS = [
    "dall-e-2",
    "dall-e-3",
    "gpt-image-1"
]