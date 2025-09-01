"""DataUpdateCoordinator for Beckhoff ADS integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import pyads
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SENSOR_DATA_TYPES
from .hub import BeckhoffADSHub

_LOGGER = logging.getLogger(__name__)


class BeckhoffADSCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator for fetching data from Beckhoff PLC."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: BeckhoffADSHub,
        entities_config: list[dict[str, Any]],
        update_interval: int = 5,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{hub.host}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.hub = hub
        self.entities_config = entities_config
        self._entity_addresses: Dict[str, Dict[str, Any]] = {}
        self._notification_handles: Dict[str, int] = {}
        self._setup_entity_mappings()

    def _setup_entity_mappings(self) -> None:
        """Setup entity address mappings for batch reading."""
        for config in self.entities_config:
            address = config["plc_address"]
            self._entity_addresses[address] = {
                "config": config,
                "plc_type": self._get_plc_type_for_config(config),
                "last_value": None,
                "error_count": 0,
                "use_notifications": config.get("use_notifications", True),
            }

    def _get_plc_type_for_config(self, config: dict[str, Any]) -> type:
        """Get PLC type based on entity configuration."""
        entity_type = config.get("type")
        plc_type_name = config.get("plc_type", "REAL")
        
        # Default types for entity types
        if entity_type in ["binary_sensor", "switch"]:
            return pyads.PLCTYPE_BOOL
        elif entity_type == "select":
            return pyads.PLCTYPE_INT
        
        # Map string type names to pyads types
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
        
        return type_mapping.get(plc_type_name, pyads.PLCTYPE_REAL)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from PLC."""
        if not self.hub.connected:
            raise UpdateFailed("PLC not connected")

        data = {}
        errors = []
        
        # Batch read operations for better performance
        read_tasks = []
        for address, info in self._entity_addresses.items():
            # Skip if using notifications and we have a valid handle
            if info["use_notifications"] and address in self._notification_handles:
                # Use cached notification value if available
                if info["last_value"] is not None:
                    data[address] = info["last_value"]
                continue
            
            # Create read task
            read_tasks.append(self._read_single_value(address, info))
        
        # Execute all reads concurrently
        if read_tasks:
            results = await asyncio.gather(*read_tasks, return_exceptions=True)
            
            for address, result in zip(
                [a for a in self._entity_addresses if a not in self._notification_handles or not self._entity_addresses[a]["use_notifications"]], 
                results
            ):
                if isinstance(result, Exception):
                    errors.append(f"{address}: {result}")
                    self._entity_addresses[address]["error_count"] += 1
                    # Use last known value if available
                    if self._entity_addresses[address]["last_value"] is not None:
                        data[address] = self._entity_addresses[address]["last_value"]
                else:
                    data[address] = result
                    self._entity_addresses[address]["last_value"] = result
                    self._entity_addresses[address]["error_count"] = 0
        
        # Log errors if any occurred
        if errors and len(errors) < 5:  # Only log if not too many errors
            _LOGGER.debug("Some PLC reads failed: %s", "; ".join(errors[:3]))
        elif errors:
            _LOGGER.warning("Multiple PLC read failures: %d errors", len(errors))
        
        # Raise UpdateFailed if all reads failed
        if not data and errors:
            raise UpdateFailed(f"All PLC reads failed: {errors[0] if errors else 'Unknown error'}")
        
        return data

    async def _read_single_value(self, address: str, info: Dict[str, Any]) -> Any:
        """Read a single value from PLC."""
        try:
            value = await self.hub.async_read_value(address, info["plc_type"])
            return value
        except Exception as err:
            # Re-raise with more context
            raise UpdateFailed(f"Failed to read {address}: {err}") from err

    async def async_setup_notifications(self) -> None:
        """Setup notifications for entities that support them."""
        for address, info in self._entity_addresses.items():
            if not info["use_notifications"]:
                continue
                
            try:
                def notification_callback(name: str, value: Any) -> None:
                    """Handle notification from PLC."""
                    # Store the value
                    self._entity_addresses[name]["last_value"] = value
                    self._entity_addresses[name]["error_count"] = 0
                    
                    # Trigger coordinator update to notify entities
                    self.hass.loop.call_soon_threadsafe(
                        lambda: self.hass.async_create_task(
                            self.async_request_refresh()
                        )
                    )
                
                # Setup notification
                handle = await self.hass.async_add_executor_job(
                    self.hub.add_device_notification,
                    address,
                    info["plc_type"],
                    notification_callback
                )
                
                if handle:
                    self._notification_handles[address] = handle
                    _LOGGER.debug("Setup notification for %s", address)
                    
            except Exception as err:
                _LOGGER.debug("Failed to setup notification for %s: %s", address, err)

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and cleanup notifications."""
        # Cleanup is handled by the hub
        self._notification_handles.clear()

    def get_entity_data(self, plc_address: str) -> Any:
        """Get data for a specific entity."""
        return self.data.get(plc_address) if self.data else None

    def get_entity_available(self, plc_address: str) -> bool:
        """Check if entity data is available."""
        if not self.hub.connected:
            return False
        
        # Check if we have data and low error count
        if plc_address in self._entity_addresses:
            entity_info = self._entity_addresses[plc_address]
            return entity_info["error_count"] < 3 and plc_address in (self.data or {})
        
        return False

    def update_entities_config(self, entities_config: list[dict[str, Any]]) -> None:
        """Update entities configuration."""
        self.entities_config = entities_config
        self._entity_addresses.clear()
        self._notification_handles.clear()
        self._setup_entity_mappings()
        
        # Request immediate update
        self.hass.async_create_task(self.async_request_refresh())