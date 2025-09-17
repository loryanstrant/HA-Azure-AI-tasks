# Azure AI Tasks - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/loryanstrant/HA-Azure-AI-Tasks.svg)](https://github.com/loryanstrant/HA-Azure-AI-Tasks/releases/)

A Home Assistant custom integration that facilitates AI tasks using Azure AI services.

<p align="center"><img width="256" height="256" alt="icon" src="https://github.com/user-attachments/assets/934b88ed-f038-474f-9211-4417717e5e84" /><p>



## Features

- Easy configuration through Home Assistant UI
- Secure API key management  
- **User-configurable AI models for chat responses** (GPT-3.5, GPT-4, GPT-4o, etc.) - type in any model name
- **Image and video analysis with attachment support** - analyze camera streams and uploaded images
- **Reconfiguration support** - change models without re-entering credentials
- **Multiple entry support** - use different API endpoints and keys for different purposes
- Compatible with Azure OpenAI and other Azure AI services
- HACS ready for easy installation

## Installation

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add `https://github.com/loryanstrant/HA-Azure-AI-Tasks` as repository
5. Set category to "Integration"
6. Click "Add"
7. Find "Azure AI Tasks" in the integration list and install it
8. Restart Home Assistant
9. Go to Configuration > Integrations
10. Click "+ Add Integration" and search for "Azure AI Tasks"
11. Press Submit to complete the installation.

Or replace steps 1-6 with this:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=loryanstrant&repository=HA-Azure-AI-Tasks&category=integration)

### Manual Installation

1. Copy the `custom_components/azure_ai_tasks` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI (Settings → Devices & Services → Add Integration)

## Configuration

1. Go to Settings → Devices & Services → Add Integration
2. Search for "Azure AI Tasks"
3. Enter your Azure AI endpoint URL and API key
4. **Enter your preferred chat model** (gpt-35-turbo, gpt-4, gpt-4o, etc.)
5. Give your integration a name
6. Click Submit

<img width="377" height="479" alt="image" src="https://github.com/user-attachments/assets/db283176-b329-4d41-a1f9-4bf181e9f056" />




### Reconfiguration

To change AI models without re-entering credentials:
1. Go to your Azure AI Tasks integration
2. Click "Configure" 
3. Enter a different model as needed
4. Save changes

<img width="1072" height="700" alt="image" src="https://github.com/user-attachments/assets/598b8c28-7663-4507-be63-22413cac4b9d" />



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
![HA Azure AI Task example](https://github.com/user-attachments/assets/592ec039-20ea-436f-a6f0-caf88bef9b56)



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
<img width="1390" height="1247" alt="image" src="https://github.com/user-attachments/assets/c475523b-37af-4e76-9336-bc148c5a1a5d" />
<br><br>


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
<img width="1372" height="1222" alt="image" src="https://github.com/user-attachments/assets/28e81122-463d-4d37-8df9-1a7c0d902f86" />



### Available Models

You can enter any model name that your Azure AI deployment supports.

## Requirements

- Home Assistant 2024.1 or later
- Azure AI service with API access
- Valid Azure AI endpoint and API key

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Development Approach
<img width="256" height="256" alt="Vibe Coding with GitHub Copilot 256x256" src="https://github.com/user-attachments/assets/bb41d075-6b3e-4f2b-a88e-94b2022b5d4f" />


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues, please report them on the [GitHub Issues page](https://github.com/loryanstrant/HA-CustomComponentMonitor/issues).
