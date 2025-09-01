"""Beckhoff ADS Hub for managing PLC connection."""
from __future__ import annotations

import asyncio
import ctypes
import logging
import struct
import threading
from collections import namedtuple
from datetime import timedelta
from typing import Any, Callable, Optional

import pyads
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DEFAULT_MAX_FAILURES,
    DEFAULT_OPERATION_TIMEOUT,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
)
from .helpers import CircuitBreaker, format_plc_error

_LOGGER = logging.getLogger(__name__)

# Tuple to hold notification data
NotificationItem = namedtuple(
    "NotificationItem", "hnotify huser name plc_datatype callback"
)


class BeckhoffADSHub:
    """Beckhoff ADS Hub class."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        ams_net_id: str,
        entities_config: list[dict[str, Any]],
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the hub."""
        self.hass = hass
        self.host = host
        self.port = port
        self.ams_net_id = ams_net_id
        self.entities_config = entities_config
        self.options = options or {}
        
        self._plc: pyads.Connection | None = None
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_delay = RECONNECT_INITIAL_DELAY
        self._entities: list[Any] = []
        
        # Use threading lock like the original integration
        self._lock = threading.Lock()
        self._connection_failures = 0
        self._max_failures_before_reconnect = self.options.get(
            "max_connection_failures", DEFAULT_MAX_FAILURES
        )
        
        # Notification system
        self._notification_items = {}
        self._notification_enabled = self.options.get("use_notifications", True)
        
        # Timeout and recovery settings
        self._operation_timeout = self.options.get(
            "operation_timeout", DEFAULT_OPERATION_TIMEOUT
        )
        self._consecutive_timeouts = 0
        self._max_consecutive_timeouts = 5
        
        # Circuit breaker for connection management
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self._max_failures_before_reconnect,
            recovery_timeout=self.options.get("reconnect_max_delay", RECONNECT_MAX_DELAY),
        )

    async def async_setup(self) -> None:
        """Set up the hub."""
        await self._async_connect()
        
        # Start reconnection monitoring
        async_track_time_interval(
            self.hass, self._async_check_connection, timedelta(seconds=5)
        )

    async def async_update_entities_config(self, entities_config: list[dict[str, Any]]) -> None:
        """Update entities configuration after YAML reload."""
        _LOGGER.info("Updating entities configuration with %d entities", len(entities_config))
        self.entities_config = entities_config
        
        # Notify existing entities about config update
        for entity in self._entities:
            if hasattr(entity, 'async_update_config'):
                await entity.async_update_config()
            # Force update all entities
            if hasattr(entity, 'async_update'):
                try:
                    await entity.async_update()
                    entity.async_write_ha_state()
                except Exception as err:
                    _LOGGER.debug("Failed to update entity after config reload: %s", err)

    async def async_close(self) -> None:
        """Close the hub."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
        
        # Clean up notifications
        await self._async_cleanup_notifications()
        await self._async_disconnect()

    async def _async_cleanup_notifications(self) -> None:
        """Clean up all ADS notifications."""
        if not self._plc or not self._notification_items:
            return
            
        def cleanup_notifications():
            with self._lock:
                for notification_item in list(self._notification_items.values()):
                    _LOGGER.debug(
                        "Deleting device notification %d, %d",
                        notification_item.hnotify,
                        notification_item.huser,
                    )
                    try:
                        self._plc.del_device_notification(
                            notification_item.hnotify, notification_item.huser
                        )
                    except Exception as err:
                        _LOGGER.debug("Error deleting notification: %s", err)
                self._notification_items.clear()
        
        await self.hass.async_add_executor_job(cleanup_notifications)

    async def _async_connect(self) -> None:
        """Connect to PLC."""
        try:
            # Clean up any existing connection first
            if self._plc:
                try:
                    await self.hass.async_add_executor_job(self._plc.close)
                except Exception:
                    pass
                self._plc = None
            
            self._plc = pyads.Connection(self.ams_net_id, self.port, self.host)
            await self.hass.async_add_executor_job(self._plc.open)
            
            # Test the connection
            await self.hass.async_add_executor_job(self._plc.read_state)
            
            self._connected = True
            self._reconnect_delay = RECONNECT_INITIAL_DELAY
            self._connection_failures = 0
            self._consecutive_timeouts = 0
            
            _LOGGER.info("Connected to Beckhoff PLC at %s:%s (AMS: %s)", 
                        self.host, self.port, self.ams_net_id)
            
        except Exception as err:
            _LOGGER.error("Failed to connect to PLC: %s", err)
            self._connected = False
            if self._plc:
                try:
                    await self.hass.async_add_executor_job(self._plc.close)
                except Exception:
                    pass
                self._plc = None
            raise

    def add_device_notification(self, address: str, plc_type: type, callback: Callable):
        """Add a notification for real-time updates - synchronous like original."""
        if not self._connected or not self._plc or not self._notification_enabled:
            return None
            
        with self._lock:
            try:
                attr = pyads.NotificationAttrib(ctypes.sizeof(plc_type))
                hnotify, huser = self._plc.add_device_notification(
                    address, attr, self._device_notification_callback
                )
                
                hnotify = int(hnotify)
                self._notification_items[hnotify] = NotificationItem(
                    hnotify, huser, address, plc_type, callback
                )
                
                _LOGGER.debug(
                    "Added device notification %d for variable %s", hnotify, address
                )
                _LOGGER.info("Successfully setup notification for %s", address)
                return hnotify
                
            except Exception as err:
                _LOGGER.warning("Error subscribing to %s: %s", address, err)
                return None

    def _device_notification_callback(self, notification, name):
        """Handle device notifications."""
        try:
            contents = notification.contents
            hnotify = int(contents.hNotification)
            _LOGGER.debug("Received notification %d for variable change", hnotify)

            # Get dynamically sized data array
            data_size = contents.cbSampleSize
            data_address = (
                ctypes.addressof(contents)
                + pyads.structs.SAdsNotificationHeader.data.offset
            )
            data = (ctypes.c_ubyte * data_size).from_address(data_address)

            # Get notification item
            with self._lock:
                notification_item = self._notification_items.get(hnotify)

            if not notification_item:
                _LOGGER.debug("Unknown device notification handle: %d", hnotify)
                return

            # Parse data based on PLC data type
            plc_datatype = notification_item.plc_datatype
            
            if plc_datatype == pyads.PLCTYPE_BOOL:
                value = bool(struct.unpack("<?", bytearray(data))[0])
            elif plc_datatype == pyads.PLCTYPE_INT:
                value = struct.unpack("<h", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_UINT:
                value = struct.unpack("<H", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_DINT:
                value = struct.unpack("<i", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_UDINT:
                value = struct.unpack("<I", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_WORD:
                value = struct.unpack("<H", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_DWORD:
                value = struct.unpack("<I", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_BYTE:
                value = struct.unpack("<B", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_SINT:
                value = struct.unpack("<b", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_USINT:
                value = struct.unpack("<B", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_REAL:
                value = struct.unpack("<f", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_LREAL:
                value = struct.unpack("<d", bytearray(data))[0]
            elif plc_datatype == pyads.PLCTYPE_STRING:
                value = bytearray(data).split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
            elif plc_datatype in [pyads.PLCTYPE_TIME, pyads.PLCTYPE_DATE, pyads.PLCTYPE_DT, pyads.PLCTYPE_TOD]:
                value = struct.unpack("<i", bytearray(data))[0]  # Treat as DINT
            else:
                value = bytearray(data)
                _LOGGER.debug("Unsupported datatype for notification")
                return

            # Call the callback with parsed value
            notification_item.callback(notification_item.name, value)
            
        except Exception as err:
            _LOGGER.debug("Error in notification callback: %s", err)

    async def _async_disconnect(self) -> None:
        """Disconnect from PLC."""
        if self._plc:
            # Clean up notifications first
            await self._async_cleanup_notifications()
            
            try:
                await self.hass.async_add_executor_job(self._plc.close)
            except Exception as err:
                _LOGGER.debug("Error closing PLC connection: %s", err)
            finally:
                self._plc = None
                self._connected = False

    async def _async_check_connection(self, now=None) -> None:
        """Check PLC connection and reconnect if needed."""
        if not self._connected or not self._plc:
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = self.hass.async_create_task(
                    self._async_reconnect()
                )
            return

        # Only check connection if we've had recent failures or timeouts
        if (self._connection_failures < self._max_failures_before_reconnect and 
            self._consecutive_timeouts < self._max_consecutive_timeouts):
            return

        # Test connection with a simple read
        try:
            def test_connection():
                with self._lock:
                    return self._plc.read_state()
            
            await asyncio.wait_for(
                self.hass.async_add_executor_job(test_connection),
                timeout=self._operation_timeout
            )
            
            # Connection test successful - reset counters
            self._connection_failures = 0
            self._consecutive_timeouts = 0
            self._reconnect_delay = RECONNECT_INITIAL_DELAY
            
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.warning("Connection test failed: %s", err)
            self._connected = False
            await self._async_disconnect()
            
            # Start reconnection task
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = self.hass.async_create_task(
                    self._async_reconnect()
                )

    async def _async_reconnect(self) -> None:
        """Reconnect to PLC with exponential backoff."""
        while not self._connected:
            try:
                _LOGGER.info("Attempting to reconnect to PLC...")
                await self._async_connect()
                
                # Notify entities about successful reconnection
                await self._async_notify_entities_reconnected()
                        
            except Exception as err:
                _LOGGER.debug("Reconnection failed: %s", err)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * RECONNECT_BACKOFF_FACTOR,
                    RECONNECT_MAX_DELAY
                )

    async def _async_notify_entities_reconnected(self) -> None:
        """Notify all entities that connection has been restored."""
        _LOGGER.info("Connection restored, updating %d entities", len(self._entities))
        
        # Re-establish notifications for all entities
        for entity in self._entities:
            if hasattr(entity, '_use_notifications') and entity._use_notifications:
                try:
                    await entity._async_setup_notification()
                except Exception as err:
                    _LOGGER.debug("Failed to re-setup notification for %s: %s", 
                                getattr(entity, 'entity_id', 'unknown'), err)
        
        # Update all entities
        for entity in self._entities:
            try:
                await entity.async_update()
                entity.async_write_ha_state()
            except Exception as err:
                _LOGGER.debug("Failed to update entity %s after reconnection: %s", 
                            getattr(entity, 'entity_id', 'unknown'), err)

    def register_entity(self, entity) -> None:
        """Register an entity with the hub."""
        self._entities.append(entity)

    def unregister_entity(self, entity) -> None:
        """Unregister an entity from the hub."""
        if entity in self._entities:
            self._entities.remove(entity)

    @property
    def connected(self) -> bool:
        """Return if PLC is connected."""
        return self._connected

    @property
    def is_healthy(self) -> bool:
        """Return if the connection is healthy (low failure rate)."""
        return (self._connected and 
                self._circuit_breaker.is_healthy and
                self._connection_failures < self._max_failures_before_reconnect and
                self._consecutive_timeouts < self._max_consecutive_timeouts)

    async def async_force_reconnect(self) -> None:
        """Force a reconnection (can be called from service)."""
        _LOGGER.info("Forcing reconnection...")
        self._connected = False
        self._connection_failures = 0
        self._consecutive_timeouts = 0
        await self._async_disconnect()
        
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = self.hass.async_create_task(
                self._async_reconnect()
            )

    async def async_read_value(self, address: str, plc_type: type = None):
        """Read value from PLC using threading lock with timeout handling."""
        if not self._connected or not self._plc:
            raise Exception("PLC not connected")
        
        # Check circuit breaker
        if not self._circuit_breaker.can_execute():
            raise Exception(f"Circuit breaker open - too many failures")
        
        def read_value():
            """Synchronous read with lock and timeout handling."""
            with self._lock:
                try:
                    if plc_type:
                        return self._plc.read_by_name(address, plc_type)
                    else:
                        return self._plc.read_by_name(address)
                except pyads.ADSError as err:
                    if "timeout" in str(err).lower():
                        raise TimeoutError(f"ADS timeout reading {address}: {err}")
                    else:
                        raise Exception(f"ADS Error: {err}")
                except Exception as err:
                    if "timeout" in str(err).lower():
                        raise TimeoutError(f"Timeout reading {address}: {err}")
                    raise
        
        try:
            # Use asyncio.wait_for to add an overall timeout
            value = await asyncio.wait_for(
                self.hass.async_add_executor_job(read_value),
                timeout=self._operation_timeout
            )
            
            # Reset counters on successful read
            self._connection_failures = 0
            self._consecutive_timeouts = 0
            self._circuit_breaker.call_succeeded()
            return value
            
        except asyncio.TimeoutError:
            self._consecutive_timeouts += 1
            self._connection_failures += 1
            self._circuit_breaker.call_failed()
            
            error_msg = format_plc_error(
                TimeoutError(f"Operation timeout ({self._operation_timeout}s)"),
                address
            )
            _LOGGER.warning("%s (timeout %d/%d)", 
                          error_msg, self._consecutive_timeouts, self._max_consecutive_timeouts)
            
            # Force reconnection after too many consecutive timeouts
            if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                _LOGGER.error("Too many consecutive timeouts, forcing reconnection")
                self._connected = False
                await self._async_disconnect()
            
            raise Exception(error_msg)
            
        except TimeoutError as err:
            self._consecutive_timeouts += 1
            self._connection_failures += 1
            self._circuit_breaker.call_failed()
            
            error_msg = format_plc_error(err, address)
            _LOGGER.warning("%s (timeout %d/%d)", 
                          error_msg, self._consecutive_timeouts, self._max_consecutive_timeouts)
            
            if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                _LOGGER.error("Too many consecutive timeouts, forcing reconnection")
                self._connected = False
                await self._async_disconnect()
            
            raise Exception(error_msg)
            
        except Exception as err:
            # Increment failure count but don't immediately disconnect
            self._connection_failures += 1
            self._circuit_breaker.call_failed()
            
            error_msg = format_plc_error(err, address)
            _LOGGER.debug("%s (failure %d/%d)", 
                         error_msg, self._connection_failures, 
                         self._max_failures_before_reconnect)
            
            # Only trigger reconnection after multiple failures
            if self._connection_failures >= self._max_failures_before_reconnect:
                _LOGGER.warning("Multiple read failures, will test connection")
            
            raise Exception(error_msg)

    async def async_write_value(self, address: str, value: Any, plc_type: type = None):
        """Write value to PLC using threading lock with timeout handling."""
        if not self._connected or not self._plc:
            raise Exception("PLC not connected")
        
        def write_value():
            """Synchronous write with lock and timeout handling."""
            with self._lock:
                try:
                    if plc_type:
                        return self._plc.write_by_name(address, value, plc_type)
                    else:
                        return self._plc.write_by_name(address, value)
                except pyads.ADSError as err:
                    if "timeout" in str(err).lower():
                        raise TimeoutError(f"ADS timeout writing to {address}: {err}")
                    else:
                        raise Exception(f"ADS Error: {err}")
                except Exception as err:
                    if "timeout" in str(err).lower():
                        raise TimeoutError(f"Timeout writing to {address}: {err}")
                    raise
        
        try:
            # Use asyncio.wait_for to add an overall timeout
            await asyncio.wait_for(
                self.hass.async_add_executor_job(write_value),
                timeout=self._operation_timeout
            )
            
            # Reset counters on successful write
            self._connection_failures = 0
            self._consecutive_timeouts = 0
            
        except asyncio.TimeoutError:
            self._consecutive_timeouts += 1
            self._connection_failures += 1
            _LOGGER.warning("Write timeout for %s (timeout %d/%d, failure %d/%d)", 
                          address, self._consecutive_timeouts, self._max_consecutive_timeouts,
                          self._connection_failures, self._max_failures_before_reconnect)
            
            # Force reconnection after too many consecutive timeouts
            if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                _LOGGER.error("Too many consecutive timeouts, forcing reconnection")
                self._connected = False
                await self._async_disconnect()
            
            raise Exception(f"Timeout writing to {address}")
            
        except TimeoutError as err:
            self._consecutive_timeouts += 1
            self._connection_failures += 1
            _LOGGER.warning("ADS timeout writing to %s: %s (timeout %d/%d)", 
                          address, err, self._consecutive_timeouts, self._max_consecutive_timeouts)
            
            if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                _LOGGER.error("Too many consecutive timeouts, forcing reconnection")
                self._connected = False
                await self._async_disconnect()
            
            raise
            
        except Exception as err:
            # Increment failure count but don't immediately disconnect
            self._connection_failures += 1
            _LOGGER.debug("Failed to write %s to %s (failure %d/%d): %s", 
                         value, address, self._connection_failures, 
                         self._max_failures_before_reconnect, err)
            
            # Only trigger reconnection after multiple failures
            if self._connection_failures >= self._max_failures_before_reconnect:
                _LOGGER.warning("Multiple write failures, will test connection")
            
            raise