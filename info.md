# Beckhoff ADS Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

## Overview

This integration allows Home Assistant to connect to Beckhoff TwinCAT PLCs using the ADS (Automation Device Specification) protocol. It provides real-time monitoring and control of PLC variables through various Home Assistant entity types.

## Features

- 🔄 Real-time updates via ADS notifications
- 📊 Multiple entity types (sensors, switches, numbers, selects)
- 🔌 Automatic reconnection with circuit breaker pattern
- ⚙️ Runtime configuration via Options flow
- 📈 Long-term statistics support
- 🔧 Built-in diagnostics for troubleshooting

## Quick Start

1. Install via HACS (add this repository as custom repository)
2. Configure connection to your PLC via UI
3. Create `beckhoff_ads.yaml` in your config directory
4. Define your PLC variables as entities
5. Restart Home Assistant

## Example Configuration

```yaml
beckhoff_ads:
  entities:
    - name: "Reactor Temperature"
      type: sensor
      plc_address: "GVL.rReactorTemp"
      plc_type: "REAL"
      unit_of_measurement: "°C"
      device_class: "temperature"
```

## Requirements

- Home Assistant 2023.1 or newer
- Beckhoff PLC with TwinCAT runtime
- Network connectivity between HA and PLC

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/marcinwadon/beckhoff_ads).