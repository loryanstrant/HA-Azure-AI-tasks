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

To change AI models or image generation settings without re-entering credentials:
1. Go to your Azure AI Tasks integration
2. Click "Configure" 
3. Select different models as needed
4. **Configure default image size** (256x256, 512x512, 1024x1024, 1792x1024)
5. **Configure default image quality** (standard, hd)
6. Save changes

## Usage

Once configured, the integration provides an AI Task entity that can be used in automations and scripts to process AI tasks using your Azure AI service.

### Important: Image Size Parameter

**Note:** The `size` parameter is not supported directly in the service call data due to Home Assistant AI task framework limitations. Instead, the integration provides two ways to control image size and quality:

1. **Configure defaults** in the integration options (recommended)
2. **Specify in prompts** using keywords like "512x512" or "HD"

**❌ This will not work:**
```yaml
service: ai_task.generate_image
data:
  entity_id: ai_task.azure_ai_tasks
  instructions: "A duck on a submarine"
  size: "1024x1024"  # ← This parameter is not supported
```

**✅ These approaches work:**
```yaml
# Method 1: Use configured defaults
service: ai_task.generate_image
data:
  entity_id: ai_task.azure_ai_tasks
  instructions: "A duck on a submarine"

# Method 2: Specify size in prompt
service: ai_task.generate_image
data:
  entity_id: ai_task.azure_ai_tasks
  instructions: "A 1024x1024 HD image of a duck on a submarine"
```

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
service: ai_task.generate_image
target:
  entity_id: ai_task.azure_ai_tasks
data:
  instructions: "A beautiful sunset over mountains"
```

The integration will use your configured default image size and quality. You can also specify size and quality in the prompt:

```yaml
service: ai_task.generate_image
target:
  entity_id: ai_task.azure_ai_tasks
data:
  instructions: "A beautiful 512x512 HD sunset over mountains"
```

**Supported size keywords in prompts:**
- `256x256` or `256` → 256x256 pixels
- `512x512` or `512` → 512x512 pixels  
- `1024x1024` or `1024` → 1024x1024 pixels
- `1792x1024` or `1792` → 1792x1024 pixels (DALL-E 3 only)

**Supported quality keywords in prompts:**
- `HD`, `high quality`, `high-quality` → HD quality
- `standard quality`, `standard` → Standard quality

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
