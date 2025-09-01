"""Constants for the Beckhoff ADS integration."""

DOMAIN = "beckhoff_ads"

# Configuration keys
CONF_AMS_NET_ID = "ams_net_id"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ENTITIES = "entities"

# Default values
DEFAULT_PORT = 851
DEFAULT_SCAN_INTERVAL = 5  # seconds

# Entity types
ENTITY_TYPES = [
    "binary_sensor",
    "number",
    "select", 
    "sensor",
    "switch"
]

# Reconnection settings
RECONNECT_INITIAL_DELAY = 5  # seconds
RECONNECT_MAX_DELAY = 60     # seconds
RECONNECT_BACKOFF_FACTOR = 2

# YAML configuration file name
YAML_CONFIG_FILE = "beckhoff_ads.yaml"

# Supported PLC data types for sensors
SENSOR_DATA_TYPES = {
    "BOOL": "pyads.PLCTYPE_BOOL",
    "BYTE": "pyads.PLCTYPE_BYTE", 
    "SINT": "pyads.PLCTYPE_SINT",
    "USINT": "pyads.PLCTYPE_USINT",
    "INT": "pyads.PLCTYPE_INT",
    "UINT": "pyads.PLCTYPE_UINT", 
    "WORD": "pyads.PLCTYPE_WORD",
    "DINT": "pyads.PLCTYPE_DINT",
    "UDINT": "pyads.PLCTYPE_UDINT",
    "DWORD": "pyads.PLCTYPE_DWORD",
    "REAL": "pyads.PLCTYPE_REAL",
    "LREAL": "pyads.PLCTYPE_LREAL",
    "STRING": "pyads.PLCTYPE_STRING",
    "TIME": "pyads.PLCTYPE_TIME",
    "DATE": "pyads.PLCTYPE_DATE", 
    "DT": "pyads.PLCTYPE_DT",
    "TOD": "pyads.PLCTYPE_TOD"
}