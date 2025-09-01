# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Beckhoff ADS (Automation Device Specification) that enables communication with Beckhoff TwinCAT PLCs. The integration provides real-time monitoring and control of PLC variables through Home Assistant entities.

## Architecture

### Core Components

- **BeckhoffADSHub** (`hub.py`): Central connection manager that handles PLC communication, reconnection logic, and notification management
- **BeckhoffADSEntity** (`entity.py`): Base class for all entities providing common functionality like notifications and device info
- **Entity Types**: 5 supported entity types each in their own file:
  - `sensor.py` - Read-only numeric/string values with scaling support
  - `binary_sensor.py` - Boolean state monitoring  
  - `switch.py` - Boolean control (on/off)
  - `number.py` - Numeric input controls with min/max/step
  - `select.py` - Dropdown selection controls

### Configuration System

- Uses Home Assistant config flow (`config_flow.py`) for initial setup (host, port, AMS Net ID)
- Entity configuration via YAML file (`beckhoff_ads.yaml`) in Home Assistant config directory
- Dynamic YAML reload service available: `beckhoff_ads.reload_yaml`

### Communication Strategy

- **Primary**: Real-time ADS notifications for immediate updates when PLC variables change
- **Fallback**: Polling-based updates at configurable intervals (default 5 seconds)
- **Error Handling**: Automatic reconnection with exponential backoff, timeout handling, and failure counting

## Development Guidelines

### Testing the Integration

Since this is a Home Assistant integration, testing requires:
1. Home Assistant development environment
2. Access to a Beckhoff PLC or TwinCAT simulator
3. Configuration via Home Assistant UI or YAML

### Code Conventions

- Follow Home Assistant integration patterns and async/await conventions
- Use `_LOGGER` for logging with appropriate levels (debug, info, warning, error)
- Entity unique IDs follow format: `{host}_{ams_net_id}_{plc_address}`
- Threading locks required for PLC operations due to pyads library limitations
- All PLC operations wrapped in executor jobs for thread safety

### Entity Configuration Schema

Required fields for all entities:
- `name`: Display name
- `type`: One of: sensor, binary_sensor, switch, number, select
- `plc_address`: PLC variable address (e.g., "GVL.bStart", "MAIN.rTemperature")

Optional fields:
- `scan_interval`: Update frequency in seconds (default: 5)
- `use_notifications`: Enable real-time updates (default: true)
- `plc_type`: PLC data type (default: "REAL")
- `unit_of_measurement`, `device_class`, `icon`: Home Assistant entity attributes

Entity-specific options:
- **Sensors**: `factor`, `offset`, `precision` for value scaling
- **Numbers**: `min_value`, `max_value`, `step`, `mode` (slider/box)
- **Selects**: `options` array for dropdown choices

### Important Technical Considerations

- PLC communication uses threading locks (`threading.Lock`) due to pyads library requirements
- Notification callbacks run synchronously from ADS thread - use `call_soon_threadsafe` for HA updates
- Connection monitoring with configurable failure thresholds and timeout handling
- Support for all common Beckhoff PLC data types (BOOL, INT, REAL, STRING, etc.)
- YAML configuration changes trigger entity updates without restart

### Dependencies

- `pyads>=3.3.0` - Beckhoff ADS communication library
- Standard Home Assistant dependencies (voluptuous, yaml)