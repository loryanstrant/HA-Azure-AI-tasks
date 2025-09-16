## Azure AI Tasks Integration

This Home Assistant custom integration provides seamless integration with Azure AI services for processing AI tasks.

### Key Features:
- Easy setup through Home Assistant UI
- Secure configuration with Azure AI endpoint and API key
- **User-selectable AI models** for chat responses (GPT-3.5, GPT-4, GPT-4o, etc.)
- **Image generation support** with DALL-E 2 and DALL-E 3
- **Reconfiguration options** to change models without re-setup
- Support for Azure OpenAI and other Azure AI services
- Full compatibility with Home Assistant AI Task framework

### Configuration:
1. Install the integration through HACS
2. Go to Settings → Devices & Services → Add Integration
3. Search for "Azure AI Tasks"
4. Enter your Azure AI endpoint URL and API key
5. Select your preferred chat and image generation models
6. Complete the setup

### Model Selection:
Choose from multiple AI models during setup or reconfigure later:
- **Chat Models**: gpt-35-turbo, gpt-4, gpt-4o, gpt-4o-mini, and more
- **Image Models**: dall-e-2, dall-e-3

### Usage:
Once configured, you can use the AI Task entity in automations and scripts to:
- Generate text responses using your selected chat model
- Create images using DALL-E with customizable prompts and sizes
- Process various AI tasks using your Azure AI service

For detailed documentation, please visit the [GitHub repository](https://github.com/loryanstrant/ha-azure-ai-task).