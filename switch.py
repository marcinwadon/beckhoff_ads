"""Switch platform for Beckhoff ADS."""
from __future__ import annotations

import logging
from typing import Any

import pyads
from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities from config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for entity_config in hub.entities_config:
        if entity_config.get("type") == "switch":
            entities.append(BeckhoffADSSwitch(hub, entity_config))
    
    async_add_entities(entities)


class BeckhoffADSSwitch(BeckhoffADSEntity, SwitchEntity):
    """Representation of a Beckhoff ADS switch."""

    def __init__(self, hub: BeckhoffADSHub, config: dict[str, Any]) -> None:
        """Initialize the switch."""
        super().__init__(hub, config)

    def _get_plc_type(self) -> type:
        """Get PLC type for notifications."""
        return pyads.PLCTYPE_BOOL

    def _process_notification_value(self, value: Any) -> None:
        """Process notification value."""
        self._attr_is_on = bool(value)

    async def async_update(self) -> None:
        """Update the switch."""
        if not self._hub.connected:
            self._attr_available = False
            return

        try:
            value = await self._hub.async_read_value(
                self._plc_address, pyads.PLCTYPE_BOOL
            )
            self._attr_is_on = bool(value)
            self._attr_available = True
            
        except Exception as err:
            # Don't log every error, only when availability changes
            if self._attr_available:
                _LOGGER.warning("Failed to update %s: %s", self.entity_id, err)
            self._attr_available = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self._hub.async_write_value(
                self._plc_address, True, pyads.PLCTYPE_BOOL
            )
            self._attr_is_on = True
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Failed to turn on %s: %s", self.entity_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self._hub.async_write_value(
                self._plc_address, False, pyads.PLCTYPE_BOOL
            )
            self._attr_is_on = False
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Failed to turn off %s: %s", self.entity_id, err)