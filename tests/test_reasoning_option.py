"""Tests for the per-model "reasoning model" setting."""
from unittest.mock import MagicMock

import pytest

from custom_components.azure_ai_tasks.ai_task import AzureAITaskEntity
from custom_components.azure_ai_tasks.const import (
    CONF_CHAT_MODEL,
    CONF_CHAT_REASONING,
    CONF_IMAGE_REASONING,
)


def _entity(data: dict, options: dict | None = None) -> AzureAITaskEntity:
    config_entry = MagicMock()
    config_entry.entry_id = "test-entry"
    config_entry.data = data
    config_entry.options = options or {}
    return AzureAITaskEntity(
        name="Azure AI Tasks",
        endpoint="https://my-resource.openai.azure.com",
        api_key="secret",
        chat_model=data.get(CONF_CHAT_MODEL, ""),
        image_model="",
        hass=MagicMock(),
        config_entry=config_entry,
    )


@pytest.mark.parametrize(
    ("data", "options", "expected"),
    [
        ({CONF_CHAT_REASONING: True}, {}, True),
        ({CONF_CHAT_REASONING: False}, {}, False),
        # Options win over data, including an explicit False.
        ({CONF_CHAT_REASONING: True}, {CONF_CHAT_REASONING: False}, False),
        ({CONF_CHAT_REASONING: False}, {CONF_CHAT_REASONING: True}, True),
        # Entries saved before the setting existed keep the old gpt-5 behaviour.
        ({CONF_CHAT_MODEL: "gpt-5-mini"}, {}, True),
        ({CONF_CHAT_MODEL: "gpt-6"}, {}, True),
        ({CONF_CHAT_MODEL: "gpt-4o"}, {}, False),
        # A deployment name the old check never recognised can now be flagged.
        ({CONF_CHAT_MODEL: "my-deployment", CONF_CHAT_REASONING: True}, {}, True),
    ],
)
def test_is_reasoning(data: dict, options: dict, expected: bool) -> None:
    entity = _entity(data, options)
    assert entity._is_reasoning(CONF_CHAT_REASONING, data.get(CONF_CHAT_MODEL)) is expected


def test_image_flag_is_independent() -> None:
    entity = _entity({CONF_CHAT_REASONING: True, CONF_IMAGE_REASONING: False})
    assert entity._is_reasoning(CONF_CHAT_REASONING, "x") is True
    assert entity._is_reasoning(CONF_IMAGE_REASONING, "x") is False


def test_completion_params() -> None:
    reasoning = AzureAITaskEntity._completion_params(True)
    assert reasoning == {"max_completion_tokens": 4000}

    standard = AzureAITaskEntity._completion_params(False)
    assert "max_completion_tokens" not in standard
    assert standard["max_tokens"] == 1000
    assert standard["temperature"] == 0.7


async def test_chat_payload_follows_setting() -> None:
    reasoning = await _entity({CONF_CHAT_REASONING: True})._build_chat_payload(
        "hi", [], MagicMock(), "anything"
    )
    assert reasoning["max_completion_tokens"] == 4000
    assert "max_tokens" not in reasoning and "temperature" not in reasoning

    standard = await _entity({CONF_CHAT_REASONING: False})._build_chat_payload(
        "hi", [], MagicMock(), "anything"
    )
    assert standard["max_tokens"] == 1000
    assert standard["temperature"] == 0.7
    assert "max_completion_tokens" not in standard
