"""Number platform for Beckhoff ADS."""
from __future__ import annotations

import logging
from typing import Any

import pyads
from homeassistant.components.number import NumberEntity
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
    """Set up number entities from config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for entity_config in hub.entities_config:
        if entity_config.get("type") == "number":
            entities.append(BeckhoffADSNumber(hub, entity_config))
    
    async_add_entities(entities)


class BeckhoffADSNumber(BeckhoffADSEntity, NumberEntity):
    """Representation of a Beckhoff ADS number entity."""

    def __init__(self, hub: BeckhoffADSHub, config: dict[str, Any]) -> None:
        """Initialize the number entity."""
        super().__init__(hub, config)
        
        # Number-specific attributes
        self._attr_native_min_value = config.get("min_value", 0)
        self._attr_native_max_value = config.get("max_value", 100)
        self._attr_native_step = config.get("step", 1)
        self._attr_mode = config.get("mode", "slider")
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        
        # Scaling options
        self._factor = config.get("factor", 1.0)
        self._offset = config.get("offset", 0.0)
        self._precision = config.get("precision", None)
        self._plc_type_name = config.get("plc_type", "REAL")

    def _get_plc_type(self) -> type:
        """Get PLC type for notifications based on configuration."""
        import pyads
        type_mapping = {
            "BOOL": pyads.PLCTYPE_BOOL,
            "BYTE": pyads.PLCTYPE_BYTE,
            "SINT": pyads.PLCTYPE_SINT,
            "USINT": pyads.PLCTYPE_USINT,
            "INT": pyads.PLCTYPE_INT,
            "UINT": pyads.PLCTYPE_UINT,
            "WORD": pyads.PLCTYPE_WORD,
            "DINT": pyads.PLCTYPE_DINT,
            "UDINT": pyads.PLCTYPE_UDINT,
            "DWORD": pyads.PLCTYPE_DWORD,
            "REAL": pyads.PLCTYPE_REAL,
            "LREAL": pyads.PLCTYPE_LREAL,
        }
        return type_mapping.get(self._plc_type_name, pyads.PLCTYPE_REAL)

    def _apply_scaling_from_plc(self, raw_value: Any) -> float:
        """Apply scaling when reading from PLC (PLC -> HA)."""
        try:
            # Convert to float and apply scaling: scaled = (raw * factor) + offset
            raw_float = float(raw_value)
            scaled_value = (raw_float * self._factor) + self._offset
            
            # Apply precision if specified
            if self._precision is not None:
                scaled_value = round(scaled_value, self._precision)
            
            return scaled_value
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Could not scale value %s for %s: %s", raw_value, self.entity_id, err)
            return raw_value

    def _apply_scaling_to_plc(self, ha_value: float) -> Any:
        """Apply reverse scaling when writing to PLC (HA -> PLC)."""
        try:
            # Reverse the scaling: raw = (scaled - offset) / factor
            raw_value = (ha_value - self._offset) / self._factor
            
            # Convert to appropriate type based on PLC type
            if self._plc_type_name in ["INT", "SINT"]:
                return int(raw_value)
            elif self._plc_type_name in ["UINT", "USINT", "WORD", "BYTE"]:
                return int(max(0, raw_value))  # Ensure positive for unsigned types
            elif self._plc_type_name in ["DINT"]:
                return int(raw_value)
            elif self._plc_type_name in ["UDINT", "DWORD"]:
                return int(max(0, raw_value))  # Ensure positive for unsigned types
            else:  # REAL, LREAL
                return float(raw_value)
                
        except (ValueError, TypeError, ZeroDivisionError) as err:
            _LOGGER.warning("Could not reverse scale value %s for %s: %s", ha_value, self.entity_id, err)
            return ha_value

    def _process_notification_value(self, value: Any) -> None:
        """Process notification value with scaling."""
        scaled_value = self._apply_scaling_from_plc(value)
        self._attr_native_value = scaled_value

    async def async_update(self) -> None:
        """Update the number entity."""
        if not self._hub.connected:
            self._attr_available = False
            return

        try:
            # Read raw value from PLC
            raw_value = await self._hub.async_read_value(
                self._plc_address, self._get_plc_type()
            )
            # Apply scaling to convert PLC value to HA value
            scaled_value = self._apply_scaling_from_plc(raw_value)
            self._attr_native_value = scaled_value
            self._attr_available = True
            
        except Exception as err:
            # Don't log every error, only when availability changes
            if self._attr_available:
                _LOGGER.warning("Failed to update %s: %s", self.entity_id, err)
            self._attr_available = False

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            # Apply reverse scaling to convert HA value to PLC value
            plc_value = self._apply_scaling_to_plc(value)
            
            # Write to PLC
            await self._hub.async_write_value(
                self._plc_address, plc_value, self._get_plc_type()
            )
            
            # Update local state immediately for responsiveness
            self._attr_native_value = value
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Failed to set value %s for %s: %s", value, self.entity_id, err)