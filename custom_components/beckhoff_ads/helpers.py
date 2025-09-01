"""Helper functions for Beckhoff ADS integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

import pyads

_LOGGER = logging.getLogger(__name__)

# PLC type mapping
PLC_TYPE_MAPPING: Dict[str, Type] = {
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


def get_plc_type(type_name: str) -> Type:
    """Get PLC type from string name."""
    return PLC_TYPE_MAPPING.get(type_name, pyads.PLCTYPE_REAL)


def apply_scaling(
    raw_value: Any,
    factor: float = 1.0,
    offset: float = 0.0,
    precision: Optional[int] = None,
) -> float:
    """Apply scaling factor and offset to raw PLC value.
    
    Args:
        raw_value: The raw value from PLC
        factor: Multiplication factor
        offset: Offset to add after multiplication
        precision: Number of decimal places to round to
        
    Returns:
        Scaled value: (raw * factor) + offset
    """
    try:
        # Convert to float and apply scaling
        scaled_value = (float(raw_value) * factor) + offset
        
        # Apply precision if specified
        if precision is not None:
            scaled_value = round(scaled_value, precision)
            
        return scaled_value
    except (ValueError, TypeError) as err:
        _LOGGER.warning("Could not scale value %s: %s", raw_value, err)
        return raw_value


def reverse_scaling(
    scaled_value: float,
    factor: float = 1.0,
    offset: float = 0.0,
    target_type: str = "REAL",
) -> Any:
    """Reverse scaling to convert HA value back to PLC value.
    
    Args:
        scaled_value: The scaled value from HA
        factor: Multiplication factor to reverse
        offset: Offset to subtract before division
        target_type: Target PLC type name
        
    Returns:
        Raw value: (scaled - offset) / factor
    """
    try:
        # Avoid division by zero
        if factor == 0:
            _LOGGER.error("Cannot reverse scale with factor of 0")
            return scaled_value
            
        # Reverse the scaling
        raw_value = (scaled_value - offset) / factor
        
        # Convert to appropriate type
        if target_type in ["INT", "SINT"]:
            return int(raw_value)
        elif target_type in ["UINT", "USINT", "WORD", "BYTE"]:
            return int(max(0, raw_value))  # Ensure positive for unsigned
        elif target_type in ["DINT"]:
            return int(raw_value)
        elif target_type in ["UDINT", "DWORD"]:
            return int(max(0, raw_value))  # Ensure positive for unsigned
        elif target_type == "BOOL":
            return bool(raw_value)
        else:  # REAL, LREAL, etc.
            return float(raw_value)
            
    except (ValueError, TypeError, ZeroDivisionError) as err:
        _LOGGER.warning("Could not reverse scale value %s: %s", scaled_value, err)
        return scaled_value


def validate_plc_address(address: str) -> bool:
    """Validate PLC address format.
    
    Args:
        address: PLC variable address
        
    Returns:
        True if address appears valid
    """
    if not address or not isinstance(address, str):
        return False
    
    # Basic validation - should contain at least one dot or be a simple name
    # Examples: "GVL.Variable", "MAIN.bStart", "SimpleVar"
    return len(address.strip()) > 0


def get_entity_category(entity_config: Dict[str, Any]) -> Optional[str]:
    """Determine entity category based on configuration.
    
    Args:
        entity_config: Entity configuration dictionary
        
    Returns:
        Entity category: "config", "diagnostic", or None
    """
    name = entity_config.get("name", "").lower()
    plc_address = entity_config.get("plc_address", "").lower()
    
    # Check for diagnostic entities
    diagnostic_keywords = [
        "error", "fault", "alarm", "warning", "status",
        "heartbeat", "connection", "diagnostic", "debug"
    ]
    if any(keyword in name or keyword in plc_address for keyword in diagnostic_keywords):
        return "diagnostic"
    
    # Check for config entities
    config_keywords = [
        "config", "setting", "parameter", "threshold",
        "setpoint", "limit", "calibration"
    ]
    if any(keyword in name or keyword in plc_address for keyword in config_keywords):
        return "config"
    
    # Check if explicitly set in config
    return entity_config.get("entity_category")


def format_plc_error(error: Exception, address: str) -> str:
    """Format PLC error message for logging.
    
    Args:
        error: The exception that occurred
        address: PLC address that caused the error
        
    Returns:
        Formatted error message
    """
    error_str = str(error).lower()
    
    if "timeout" in error_str:
        return f"Timeout accessing {address}"
    elif "1861" in str(error):  # ADS error code for invalid handle
        return f"Invalid handle for {address} - variable may not exist"
    elif "1864" in str(error):  # ADS error code for not found
        return f"Variable {address} not found in PLC"
    elif "connection" in error_str:
        return f"Connection lost while accessing {address}"
    else:
        return f"Error accessing {address}: {error}"


class CircuitBreaker:
    """Circuit breaker pattern for connection management."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_requests: int = 1,
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds to wait before half-open
            half_open_requests: Requests allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open
        self.half_open_count = 0
        
    def call_succeeded(self) -> None:
        """Record successful call."""
        self.failure_count = 0
        self.state = "closed"
        self.half_open_count = 0
        
    def call_failed(self) -> None:
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = self._get_time()
        
        if self.state == "half_open":
            self.state = "open"
            self.half_open_count = 0
        elif self.failure_count >= self.failure_threshold:
            self.state = "open"
            
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == "closed":
            return True
            
        if self.state == "open":
            # Check if we should transition to half-open
            if self.last_failure_time and \
               (self._get_time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "half_open"
                self.half_open_count = 0
                return True
            return False
            
        if self.state == "half_open":
            if self.half_open_count < self.half_open_requests:
                self.half_open_count += 1
                return True
            return False
            
        return False
        
    def _get_time(self) -> float:
        """Get current time for testing."""
        import time
        return time.time()
        
    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        return self.state == "open"
        
    @property
    def is_healthy(self) -> bool:
        """Check if circuit breaker is healthy."""
        return self.state == "closed"