"""Diagnostics support for Beckhoff ADS integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_AMS_NET_ID, CONF_HOST, DOMAIN
from .coordinator import BeckhoffADSCoordinator
from .hub import BeckhoffADSHub

# Redact sensitive data
TO_REDACT = {
    CONF_HOST,
    CONF_AMS_NET_ID,
    "plc_address",
    "ip_address",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub: BeckhoffADSHub = hass.data[DOMAIN][entry.entry_id]
    coordinator: BeckhoffADSCoordinator | None = hass.data[DOMAIN].get(
        f"{entry.entry_id}_coordinator"
    )
    
    # Gather hub information
    hub_info = {
        "connected": hub.connected,
        "host": hub.host,
        "port": hub.port,
        "ams_net_id": hub.ams_net_id,
        "connection_failures": getattr(hub, "_connection_failures", 0),
        "consecutive_timeouts": getattr(hub, "_consecutive_timeouts", 0),
        "reconnect_delay": getattr(hub, "_reconnect_delay", 0),
        "entities_count": len(hub._entities),
        "notifications_enabled": getattr(hub, "_notification_enabled", True),
        "notification_items_count": len(getattr(hub, "_notification_items", {})),
    }
    
    # Gather coordinator information if available
    coordinator_info = {}
    if coordinator:
        coordinator_info = {
            "update_interval": coordinator.update_interval.total_seconds(),
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "entity_addresses": len(coordinator._entity_addresses),
            "notification_handles": len(coordinator._notification_handles),
            "entity_errors": {
                addr: info["error_count"]
                for addr, info in coordinator._entity_addresses.items()
                if info["error_count"] > 0
            },
        }
    
    # Gather entity configuration
    entities_info = []
    for entity_config in hub.entities_config:
        entity_data = {
            "name": entity_config.get("name"),
            "type": entity_config.get("type"),
            "plc_address": entity_config.get("plc_address"),
            "plc_type": entity_config.get("plc_type", "REAL"),
            "scan_interval": entity_config.get("scan_interval", 5),
            "use_notifications": entity_config.get("use_notifications", True),
        }
        
        # Add entity-specific configuration
        if entity_config.get("type") == "sensor":
            entity_data.update({
                "factor": entity_config.get("factor", 1.0),
                "offset": entity_config.get("offset", 0.0),
                "precision": entity_config.get("precision"),
            })
        elif entity_config.get("type") == "number":
            entity_data.update({
                "min_value": entity_config.get("min_value", 0),
                "max_value": entity_config.get("max_value", 100),
                "step": entity_config.get("step", 1),
            })
        elif entity_config.get("type") == "select":
            entity_data.update({
                "options_count": len(entity_config.get("options", [])),
            })
        
        entities_info.append(entity_data)
    
    # Compile diagnostics data
    diagnostics_data = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "hub": async_redact_data(hub_info, TO_REDACT),
        "coordinator": async_redact_data(coordinator_info, TO_REDACT) if coordinator_info else None,
        "entities": async_redact_data(entities_info, TO_REDACT),
        "statistics": {
            "total_entities": len(entities_info),
            "entities_by_type": {
                entity_type: sum(1 for e in entities_info if e.get("type") == entity_type)
                for entity_type in ["sensor", "binary_sensor", "switch", "number", "select"]
            },
            "notifications_enabled": sum(1 for e in entities_info if e.get("use_notifications", True)),
            "custom_scan_intervals": sum(1 for e in entities_info if e.get("scan_interval") != 5),
        },
    }
    
    return diagnostics_data