# Beckhoff ADS Home Assistant Integration

A Home Assistant custom integration for connecting to Beckhoff TwinCAT PLCs using the ADS (Automation Device Specification) protocol. Monitor and control PLC variables in real-time with automatic reconnection and comprehensive error handling.

## Features

- **Real-time monitoring** with ADS notifications for instant updates
- **Multiple entity types**: sensors, binary sensors, switches, number inputs, and select dropdowns
- **Automatic reconnection** with exponential backoff when PLC connection is lost
- **YAML-based configuration** for easy entity management
- **Value scaling and formatting** for sensors (factor, offset, precision)
- **Comprehensive error handling** with timeout management
- **Live YAML reload** without restarting Home Assistant

## Prerequisites

- Home Assistant Core 2023.1 or newer
- Beckhoff PLC with TwinCAT runtime
- Network connectivity between Home Assistant and PLC
- ADS route configured on the PLC (if required by your setup)

## Installation

### Manual Installation

1. Copy this entire folder to your `custom_components` directory:
   ```
   config/custom_components/beckhoff_ads/
   ```

2. Restart Home Assistant

3. Go to **Settings** > **Devices & Services** > **Add Integration**

4. Search for "Beckhoff ADS" and configure your PLC connection

### HACS Installation

This integration can be installed via HACS by adding this repository as a custom repository.

## Configuration

### Initial Setup

Configure the PLC connection through the Home Assistant UI:

- **Host**: IP address of your Beckhoff PLC
- **Port**: ADS port (default: 851)
- **AMS Net ID**: Your PLC's AMS Net ID (e.g., "5.151.200.65.1.1")

### Entity Configuration

Create a `beckhoff_ads.yaml` file in your Home Assistant configuration directory to define your PLC variables:

```yaml
beckhoff_ads:
  entities:
    # Temperature sensor with scaling
    - name: "Reactor Temperature"
      type: sensor
      plc_address: "GVL.rReactorTemp"
      plc_type: "REAL"
      unit_of_measurement: "°C"
      device_class: "temperature"
      factor: 0.1  # Scale by factor of 0.1
      precision: 1  # One decimal place
      scan_interval: 2  # Update every 2 seconds

    # Process running status
    - name: "Process Running"
      type: binary_sensor
      plc_address: "MAIN.bProcessRunning"
      plc_type: "BOOL"
      device_class: "running"

    # Motor control
    - name: "Main Motor"
      type: switch
      plc_address: "IO.bMotorStart"
      plc_type: "BOOL"

    # Speed setpoint
    - name: "Motor Speed"
      type: number
      plc_address: "MAIN.iMotorSpeed"
      plc_type: "INT"
      min_value: 0
      max_value: 3000
      step: 10
      unit_of_measurement: "RPM"

    # Operating mode selection
    - name: "Operating Mode"
      type: select
      plc_address: "MAIN.eOperatingMode"
      plc_type: "INT"
      options:
        - "Manual"
        - "Automatic"
        - "Maintenance"
```

### Configuration Options

#### Required Fields
- `name`: Display name for the entity
- `type`: Entity type (`sensor`, `binary_sensor`, `switch`, `number`, `select`)
- `plc_address`: PLC variable address

#### Optional Fields
- `plc_type`: PLC data type (default: "REAL")
- `scan_interval`: Update frequency in seconds (default: 5)
- `use_notifications`: Enable real-time updates (default: true)
- `unit_of_measurement`: Unit for display
- `device_class`: Home Assistant device class
- `icon`: Custom icon (e.g., "mdi:thermometer")

#### Sensor-Specific Options
- `factor`: Scaling factor (default: 1.0)
- `offset`: Offset value (default: 0.0)
- `precision`: Decimal places (default: none)

#### Number-Specific Options
- `min_value`: Minimum value (default: 0)
- `max_value`: Maximum value (default: 100)
- `step`: Step size (default: 1)
- `mode`: UI mode - "slider" or "box" (default: "slider")

#### Select-Specific Options
- `options`: Array of string options for dropdown

## Supported PLC Data Types

| Type | Description | Example Use |
|------|-------------|-------------|
| BOOL | Boolean | Digital inputs/outputs |
| BYTE | 8-bit unsigned | Status codes |
| SINT | 8-bit signed | Small integers |
| USINT | 8-bit unsigned | Small positive values |
| INT | 16-bit signed | Standard integers |
| UINT | 16-bit unsigned | Counters |
| WORD | 16-bit | Raw data |
| DINT | 32-bit signed | Large integers |
| UDINT | 32-bit unsigned | Large counters |
| DWORD | 32-bit | Raw data |
| REAL | 32-bit float | Measurements |
| LREAL | 64-bit float | High precision |
| STRING | Text | Alarms, messages |
| TIME | Time duration | Timers |

## Services

The integration provides several services for management:

### `beckhoff_ads.reload_yaml`
Reloads entity configuration from YAML without restarting Home Assistant.

### `beckhoff_ads.force_reconnect`
Forces a reconnection to the PLC when the integration becomes unresponsive.

## Usage Examples

### Automation Example

```yaml
automation:
  - alias: "Start Process When Temperature OK"
    trigger:
      platform: numeric_state
      entity_id: sensor.reactor_temperature
      above: 80
      below: 120
    action:
      service: switch.turn_on
      entity_id: switch.main_motor
```

### Dashboard Card Example

```yaml
type: entities
title: "PLC Status"
entities:
  - sensor.reactor_temperature
  - binary_sensor.process_running
  - switch.main_motor
  - number.motor_speed
  - select.operating_mode
```

## Troubleshooting

### Connection Issues

1. **Verify network connectivity**: Ping the PLC IP address
2. **Check ADS port**: Default is 851, verify in TwinCAT System Manager
3. **AMS Net ID**: Must match exactly what's configured in TwinCAT
4. **Firewall**: Ensure ADS port (851) is open
5. **ADS Route**: May need to add route in TwinCAT

### Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.beckhoff_ads: debug
    pyads: debug
```

### Common Issues

**"PLC not connected" errors**:
- Check if PLC is running and accessible
- Verify ADS service is running on PLC
- Use `beckhoff_ads.force_reconnect` service

**"Timeout reading/writing" errors**:
- PLC may be overloaded
- Network latency issues
- Reduce scan frequency or number of entities

**Entity not updating**:
- Check PLC variable address spelling
- Verify PLC data type matches configuration
- Enable debug logging to see detailed error messages

### Performance Tips

- Use notifications (`use_notifications: true`) for best performance
- Increase `scan_interval` for less critical variables
- Group related variables with similar scan intervals
- Monitor PLC CPU usage if many entities are configured

## Technical Details

### Connection Management
- Automatic reconnection with exponential backoff (5s to 60s)
- Connection health monitoring with failure thresholds
- Thread-safe PLC operations using locks

### Notification System
- Real-time updates via ADS device notifications
- Automatic notification re-establishment after reconnection
- Fallback to polling if notifications fail

### Data Type Handling
- Automatic type conversion based on PLC data type
- Support for all common Beckhoff/TwinCAT data types
- Proper handling of strings, timestamps, and raw data

## Contributing

Issues and pull requests are welcome at: https://github.com/marcinwadon/beckhoff_ads

## License

This project is licensed under the MIT License.

## Acknowledgments

- Built on the excellent [pyads](https://github.com/stlehmann/pyads) library
- Inspired by the Home Assistant community's industrial automation needs
