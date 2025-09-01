"""Sensor platform for Beckhoff ADS."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
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
    """Set up sensor entities from config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for entity_config in hub.entities_config:
        if entity_config.get("type") == "sensor":
            entities.append(BeckhoffADSSensor(hub, entity_config))
    
    async_add_entities(entities)


class BeckhoffADSSensor(BeckhoffADSEntity, SensorEntity):
    """Representation of a Beckhoff ADS sensor."""

    def __init__(self, hub: BeckhoffADSHub, config: dict[str, Any]) -> None:
        """Initialize the sensor."""
        super().__init__(hub, config)
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        self._plc_type_name = config.get("plc_type", "REAL")
        
        # Scaling and formatting options
        self._factor = config.get("factor", 1.0)
        self._offset = config.get("offset", 0.0)
        self._precision = config.get("precision", None)

    def _apply_scaling(self, raw_value: Any) -> float:
        """Apply scaling factor and offset to raw PLC value."""
        try:
            # Convert to float and apply scaling: scaled = (raw * factor) + offset
            scaled_value = (float(raw_value) * self._factor) + self._offset
            
            # Apply precision if specified
            if self._precision is not None:
                scaled_value = round(scaled_value, self._precision)
                
            return scaled_value
        except (ValueError, TypeError):
            _LOGGER.warning("Could not scale value %s for %s", raw_value, self.entity_id)
            return raw_value

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
            "STRING": pyads.PLCTYPE_STRING,
            "TIME": pyads.PLCTYPE_TIME,
            "DATE": pyads.PLCTYPE_DATE,
            "DT": pyads.PLCTYPE_DT,
            "TOD": pyads.PLCTYPE_TOD,
        }
        return type_mapping.get(self._plc_type_name, pyads.PLCTYPE_REAL)

    def _process_notification_value(self, value: Any) -> None:
        """Process notification value with scaling."""
        scaled_value = self._apply_scaling(value)
        self._attr_native_value = scaled_value

    async def async_update(self) -> None:
        """Update the sensor."""
        if not self._hub.connected:
            self._attr_available = False
            return

        try:
            # Use the configured PLC type for reading
            raw_value = await self._hub.async_read_value(
                self._plc_address, self._get_plc_type()
            )
            # Apply scaling to the raw value
            scaled_value = self._apply_scaling(raw_value)
            self._attr_native_value = scaled_value
            self._attr_available = True
            
        except Exception as err:
            # Don't log every error, only when availability changes
            if self._attr_available:
                _LOGGER.warning("Failed to update %s: %s", self.entity_id, err)
            self._attr_available = False