# Azure AI Tasks - Home Assistant Integration

A Home Assistant custom integration that facilitates AI tasks using Azure AI services.

## Features

- Easy configuration through Home Assistant UI
- Secure API key management  
- **User-selectable AI models for chat responses** (GPT-3.5, GPT-4, GPT-4o, etc.)
- **Image generation support** with DALL-E 2 and DALL-E 3
- **Image and video analysis with attachment support** - analyze camera streams and uploaded images
- **Reconfiguration support** - change models without re-entering credentials
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
4. **Select your preferred chat model** (gpt-35-turbo, gpt-4, gpt-4o, etc.)
5. **Select your preferred image generation model** (dall-e-2, dall-e-3)
6. Give your integration a name
7. Click Submit

### Reconfiguration

To change AI models without re-entering credentials:
1. Go to your Azure AI Tasks integration
2. Click "Configure" 
3. Select different models as needed
4. Save changes

## Usage

Once configured, the integration provides an AI Task entity that can be used in automations and scripts to process AI tasks using your Azure AI service.

### Chat/Text Generation
Example service call for generating text responses:
```yaml
service: ai_task.process
target:
  entity_id: ai_task.azure_ai_tasks
data:
  task: "Summarize the weather forecast for today"
```

### Image Generation  
Example service call for generating images:
```yaml
service: ai_task.process
target:
  entity_id: ai_task.azure_ai_tasks
data:
  task_type: "generate_image"
  prompt: "A beautiful sunset over mountains"
  size: "1024x1024"
```

### Image/Video Analysis with Attachments
Example service calls for analyzing images or camera streams:

**Analyze Camera Stream:**
```yaml
action: ai_task.generate_data
data:
  task_name: camera analysis
  instructions: What's going on in this picture?
  entity_id: ai_task.azure_ai_tasks
  attachments:
    media_content_id: media-source://camera/camera.front_door_fluent
    media_content_type: application/vnd.apple.mpegurl
    metadata:
      title: Front door camera
      media_class: video
```

**Analyze Uploaded Image:**
```yaml
action: ai_task.generate_data
data:
  task_name: image analysis
  instructions: Describe what you see in this image
  entity_id: ai_task.azure_ai_tasks
  attachments:
    media_content_id: media-source://media_source/local/my_image.jpeg
    media_content_type: image/jpeg
    metadata:
      title: My uploaded image
      media_class: image
```

### Available Models

**Chat Models:**
- gpt-35-turbo (default)
- gpt-35-turbo-16k
- gpt-4
- gpt-4-32k  
- gpt-4-turbo
- gpt-4o
- gpt-4o-mini

**Image Models:**
- dall-e-2
- dall-e-3 (default)

## Requirements

- Home Assistant 2024.1 or later
- Azure AI service with API access
- Valid Azure AI endpoint and API key

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/loryanstrant/ha-azure-ai-task).
