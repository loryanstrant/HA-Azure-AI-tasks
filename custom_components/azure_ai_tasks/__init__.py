"""The Azure AI Tasks integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, __version__ as ha_version
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.AI_TASK]

_LOGGER = logging.getLogger(__name__)

# Minimum Home Assistant version required
MIN_HA_VERSION = "2025.10.0"


def _check_ha_version() -> None:
    """Check if Home Assistant version meets minimum requirements."""
    from packaging import version
    
    try:
        current_version = version.parse(ha_version.split(".dev")[0])  # Remove .dev suffix if present
        min_version = version.parse(MIN_HA_VERSION)
        
        if current_version < min_version:
            raise ConfigEntryNotReady(
                f"Home Assistant {MIN_HA_VERSION} or newer is required. "
                f"Current version: {ha_version}"
            )
    except Exception as err:
        _LOGGER.warning(
            "Unable to verify Home Assistant version compatibility: %s. "
            "Integration may not work correctly if running on older versions.",
            err
        )


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry to new version."""
    _LOGGER.info(f"Migrating Azure AI Tasks config entry {config_entry.entry_id} from version {config_entry.version} to version 2")
    
    if config_entry.version == 1:
        new_data = dict(config_entry.data)
        new_options = dict(config_entry.options)
        migrated = False
        
        # Remove deprecated gpt-35-turbo from both data and options
        if new_data.get("chat_model") == "gpt-35-turbo":
            new_data["chat_model"] = ""
            migrated = True
            _LOGGER.info("Removed deprecated gpt-35-turbo from data.chat_model")
            
        if new_options.get("chat_model") == "gpt-35-turbo":
            new_options["chat_model"] = ""  
            migrated = True
            _LOGGER.info("Removed deprecated gpt-35-turbo from options.chat_model")
        
        # Update the config entry
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            options=new_options,
            version=2
        )
        
        if migrated:
            _LOGGER.info(f"Successfully migrated config entry {config_entry.entry_id}, cleaned deprecated model")
        else:
            _LOGGER.info(f"Migrated config entry {config_entry.entry_id} to version 2, no deprecated models found")
            
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Azure AI Tasks from a config entry."""
    # Check Home Assistant version compatibility
    _check_ha_version()
    
    # Set up the integration
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    # Forward entry setup to AI task platform
    await hass.config_entries.async_forward_entry_setups(entry, ["ai_task"])
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    _LOGGER.info("Azure AI Tasks options updated for entry %s", entry.entry_id)
    _LOGGER.info("New options: %s", entry.options)
    # Reload the integration when options change
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok