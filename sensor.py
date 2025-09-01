"""Sensor platform for Beckhoff ADS."""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENTITY_CATEGORY_CONFIG, ENTITY_CATEGORY_DIAGNOSTIC
from .coordinator import BeckhoffADSCoordinator
from .helpers import apply_scaling, get_entity_category, get_plc_type
from .hub import BeckhoffADSHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: BeckhoffADSCoordinator = hass.data[DOMAIN][f"{config_entry.entry_id}_coordinator"]
    
    entities = []
    for entity_config in hub.entities_config:
        if entity_config.get("type") == "sensor":
            entities.append(BeckhoffADSSensor(coordinator, hub, entity_config))
    
    async_add_entities(entities)


class BeckhoffADSSensor(CoordinatorEntity[BeckhoffADSCoordinator], SensorEntity):
    """Representation of a Beckhoff ADS sensor."""

    def __init__(
        self,
        coordinator: BeckhoffADSCoordinator,
        hub: BeckhoffADSHub,
        config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._hub = hub
        self._config = config
        self._plc_address = config["plc_address"]
        self._plc_type_name = config.get("plc_type", "REAL")
        
        # Entity attributes
        self._attr_name = config["name"]
        self._attr_unique_id = f"{hub.host}_{hub.ams_net_id}_{config['plc_address']}"
        self._attr_icon = config.get("icon")
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        
        # Modern HA features
        category = get_entity_category(config)
        if category == ENTITY_CATEGORY_CONFIG:
            self._attr_entity_category = EntityCategory.CONFIG
        elif category == ENTITY_CATEGORY_DIAGNOSTIC:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # State class for statistics
        if config.get("state_class"):
            self._attr_state_class = SensorStateClass(config["state_class"])
        elif self._plc_type_name in ["REAL", "LREAL", "INT", "DINT", "UINT", "UDINT"]:
            # Automatically determine state class for numeric types
            if "total" in config["name"].lower() or "count" in config["name"].lower():
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            else:
                self._attr_state_class = SensorStateClass.MEASUREMENT
        
        # Suggested display precision
        if config.get("precision") is not None:
            self._attr_suggested_display_precision = config["precision"]
        
        # Scaling and formatting options
        self._factor = config.get("factor", 1.0)
        self._offset = config.get("offset", 0.0)
        self._precision = config.get("precision", None)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        raw_value = self.coordinator.get_entity_data(self._plc_address)
        if raw_value is not None:
            # Apply scaling
            scaled_value = apply_scaling(
                raw_value, self._factor, self._offset, self._precision
            )
            self._attr_native_value = scaled_value
        else:
            self._attr_native_value = None
        
        # Update availability
        self._attr_available = self.coordinator.get_entity_available(self._plc_address)
        
        super()._handle_coordinator_update()

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {("beckhoff_ads", f"{self._hub.host}_{self._hub.ams_net_id}")},
            "name": f"Beckhoff PLC ({self._hub.host})",
            "manufacturer": "Beckhoff",
            "model": "TwinCAT PLC",
            "sw_version": "TwinCAT 3",
        }
    
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Initial update from coordinator data
        self._handle_coordinator_update()