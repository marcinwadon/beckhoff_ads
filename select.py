"""Select platform for Beckhoff ADS."""
from __future__ import annotations

import logging
from typing import Any

import pyads
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BeckhoffADSEntity
from .hub import BeckhoffADSHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for entity_config in hub.entities_config:
        if entity_config.get("type") == "select":
            entities.append(BeckhoffADSSelect(hub, entity_config))
    
    async_add_entities(entities)


class BeckhoffADSSelect(BeckhoffADSEntity, SelectEntity):
    """Representation of a Beckhoff ADS select entity."""

    def __init__(self, hub: BeckhoffADSHub, config: dict[str, Any]) -> None:
        """Initialize the select entity."""
        super().__init__(hub, config)
        self._attr_options = config.get("options", [])
        if not self._attr_options:
            _LOGGER.warning("Select entity %s has no options defined", self._attr_name)

    def _get_plc_type(self) -> type:
        """Get PLC type for notifications."""
        return pyads.PLCTYPE_INT

    def _process_notification_value(self, value: Any) -> None:
        """Process notification value."""
        # Convert enum value to option string
        if 0 <= value < len(self._attr_options):
            self._attr_current_option = self._attr_options[value]
        else:
            _LOGGER.warning(
                "Invalid enum value %s for %s, expected 0-%s",
                value, self.entity_id, len(self._attr_options) - 1
            )
            self._attr_current_option = None

    async def async_update(self) -> None:
        """Update the select entity."""
        if not self._hub.connected:
            self._attr_available = False
            return

        try:
            # Read as integer (enum value)
            value = await self._hub.async_read_value(
                self._plc_address, pyads.PLCTYPE_INT
            )
            
            # Convert enum value to option string
            if 0 <= value < len(self._attr_options):
                self._attr_current_option = self._attr_options[value]
            else:
                _LOGGER.warning(
                    "Invalid enum value %s for %s, expected 0-%s",
                    value, self.entity_id, len(self._attr_options) - 1
                )
                self._attr_current_option = None
                
            self._attr_available = True
            
        except Exception as err:
            # Don't log every error, only when availability changes
            if self._attr_available:
                _LOGGER.warning("Failed to update %s: %s", self.entity_id, err)
            self._attr_available = False

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid option %s for %s", option, self.entity_id)
            return
            
        try:
            # Convert option string to enum value
            enum_value = self._attr_options.index(option)
            await self._hub.async_write_value(
                self._plc_address, enum_value, pyads.PLCTYPE_INT
            )
            self._attr_current_option = option
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Failed to set option %s for %s: %s", option, self.entity_id, err)