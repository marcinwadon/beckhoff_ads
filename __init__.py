"""The Beckhoff ADS integration."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import pyads
import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_setup_reload_service

from .const import (
    CONF_AMS_NET_ID,
    CONF_ENTITIES,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    ENTITY_TYPES,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    YAML_CONFIG_FILE,
)
from .hub import BeckhoffADSHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# YAML Schema for entities
ENTITY_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("type"): vol.In(ENTITY_TYPES),
    vol.Required("plc_address"): cv.string,
    vol.Optional("unit_of_measurement"): cv.string,
    vol.Optional("device_class"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("options", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("scan_interval", default=5): cv.positive_int,
    vol.Optional("use_notifications", default=True): cv.boolean,
    vol.Optional("plc_type", default="REAL"): cv.string,  # For sensors/numbers
    vol.Optional("factor", default=1.0): vol.Coerce(float),  # Scaling factor
    vol.Optional("offset", default=0.0): vol.Coerce(float),  # Offset
    vol.Optional("precision", default=None): vol.Any(None, vol.Coerce(int)),  # Decimal places
    # Number-specific options
    vol.Optional("min_value", default=0): vol.Coerce(float),  # Minimum value
    vol.Optional("max_value", default=100): vol.Coerce(float),  # Maximum value
    vol.Optional("step", default=1): vol.Coerce(float),  # Step size
    vol.Optional("mode", default="slider"): vol.In(["slider", "box"]),  # UI mode
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_ENTITIES, default=[]): vol.All(cv.ensure_list, [ENTITY_SCHEMA])
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Beckhoff ADS integration."""
    hass.data.setdefault(DOMAIN, {})
    
    # Register the built-in reload service for platforms
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    
    # Register custom reload service for YAML configuration
    async def reload_yaml_config(call: ServiceCall) -> None:
        """Reload YAML configuration."""
        # Reload all config entries for this domain
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)
    
    hass.services.async_register(DOMAIN, "reload_yaml", reload_yaml_config)
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Beckhoff ADS from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    ams_net_id = entry.data[CONF_AMS_NET_ID]
    
    # Load YAML configuration
    yaml_config = await _load_yaml_config(hass)
    entities_config = yaml_config.get(CONF_ENTITIES, [])
    
    # Create and setup hub
    hub = BeckhoffADSHub(hass, host, port, ams_net_id, entities_config)
    
    try:
        await hub.async_setup()
    except Exception as err:
        _LOGGER.error("Failed to setup Beckhoff ADS hub: %s", err)
        raise ConfigEntryNotReady from err
    
    hass.data[DOMAIN][entry.entry_id] = hub
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hub: BeckhoffADSHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_close()
    
    return unload_ok


async def _load_yaml_config(hass: HomeAssistant) -> dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = hass.config.path(YAML_CONFIG_FILE)
    
    if not os.path.isfile(config_path):
        _LOGGER.debug("YAML config file not found: %s", config_path)
        return {}
    
    try:
        # Use async file reading to avoid blocking
        def read_yaml_file():
            with open(config_path, encoding="utf-8") as file:
                return yaml.safe_load(file) or {}
        
        config = await hass.async_add_executor_job(read_yaml_file)
            
        # Validate configuration
        if DOMAIN in config:
            config[DOMAIN] = CONFIG_SCHEMA({DOMAIN: config[DOMAIN]})[DOMAIN]
            return config[DOMAIN]
            
    except Exception as err:
        _LOGGER.error("Error loading YAML config: %s", err)
    
    return {}