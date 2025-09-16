# Azure AI Tasks - Home Assistant Integration

A Home Assistant custom integration that facilitates AI tasks using Azure AI services.

## Features

- Easy configuration through Home Assistant UI
- Secure API key management
- Compatible with Azure OpenAI and other Azure AI services
- HACS ready for easy installation

## Installation

### Via HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Azure AI Tasks" from HACS
3. Restart Home Assistant
4. Add the integration through the UI (Settings → Devices & Services → Add Integration)

### Manual Installation

1. Copy the `custom_components/azure_ai_tasks` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI (Settings → Devices & Services → Add Integration)

## Configuration

1. Go to Settings → Devices & Services → Add Integration
2. Search for "Azure AI Tasks"
3. Enter your Azure AI endpoint URL and API key
4. Give your integration a name
5. Click Submit

## Usage

Once configured, the integration provides an AI Task entity that can be used in automations and scripts to process AI tasks using your Azure AI service.

Example service call:
```yaml
service: ai_task.process
target:
  entity_id: ai_task.azure_ai_tasks
data:
  task: "Summarize the weather forecast for today"
```

## Requirements

- Home Assistant 2024.1 or later
- Azure AI service with API access
- Valid Azure AI endpoint and API key

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/loryanstrant/ha-azure-ai-task).
