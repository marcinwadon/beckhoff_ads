"""Base entity for Beckhoff ADS integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval

from .hub import BeckhoffADSHub

_LOGGER = logging.getLogger(__name__)


class BeckhoffADSEntity(Entity):
    """Base class for Beckhoff ADS entities."""

    def __init__(self, hub: BeckhoffADSHub, config: dict[str, Any]) -> None:
        """Initialize the entity."""
        self._hub = hub
        self._config = config
        self._plc_address = config["plc_address"]
        self._scan_interval = config.get("scan_interval", 5)
        
        # Entity attributes
        self._attr_name = config["name"]
        self._attr_unique_id = f"{hub.host}_{hub.ams_net_id}_{config['plc_address']}"
        self._attr_icon = config.get("icon")
        self._attr_available = False
        
        # Notification support
        self._use_notifications = config.get("use_notifications", True)
        self._notification_handle = None
        
        # Register with hub
        self._hub.register_entity(self)
        self._remove_update_listener = None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        # Try to setup notifications first
        if self._use_notifications:
            await self._async_setup_notification()
        
        # Schedule regular updates as fallback
        self._remove_update_listener = async_track_time_interval(
            self.hass,
            self._async_update_wrapper,
            timedelta(seconds=self._scan_interval)
        )
        
        # Initial update
        await self.async_update()

    async def _async_setup_notification(self) -> None:
        """Setup ADS notification for this entity."""
        plc_type = self._get_plc_type()
        if plc_type:
            def setup_notification():
                return self._hub.add_device_notification(
                    self._plc_address, plc_type, self._notification_callback
                )
            
            try:
                self._notification_handle = await self.hass.async_add_executor_job(
                    setup_notification
                )
                if self._notification_handle:
                    _LOGGER.debug("Setup notification for %s", self.entity_id)
                else:
                    _LOGGER.debug("Failed to setup notification for %s", self.entity_id)
            except Exception as err:
                _LOGGER.debug("Error setting up notification for %s: %s", self.entity_id, err)

    def _get_plc_type(self) -> type:
        """Get PLC type for this entity - to be implemented by subclasses."""
        return None

    def _notification_callback(self, address: str, value: Any) -> None:
        """Handle notification callback - this runs synchronously from ADS thread."""
        try:
            # Update the entity state immediately
            self._process_notification_value(value)
            self._attr_available = True
            
            # Schedule the state update on the HA event loop
            if self.hass and not self.hass.is_stopping:
                self.hass.loop.call_soon_threadsafe(
                    lambda: self.async_write_ha_state()
                )
                
        except Exception as err:
            _LOGGER.debug("Error processing notification for %s: %s", self.entity_id, err)

    def _process_notification_value(self, value: Any) -> None:
        """Process notification value - to be implemented by subclasses."""
        pass

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        if self._remove_update_listener:
            self._remove_update_listener()
            
        self._hub.unregister_entity(self)

    async def async_update(self) -> None:
        """Update the entity - to be implemented by subclasses."""
        raise NotImplementedError

    async def _async_update_wrapper(self, now=None) -> None:
        """Wrapper for async_update with error handling."""
        try:
            await self.async_update()
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.debug("Update failed for %s: %s", self.entity_id, err)
            # Don't set unavailable immediately on single failure
            # Let the entity's async_update method handle availability

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