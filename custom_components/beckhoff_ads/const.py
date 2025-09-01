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

# Supported PLC data types
SUPPORTED_PLC_TYPES = [
    "BOOL", "BYTE", "SINT", "USINT", "INT", "UINT", 
    "WORD", "DINT", "UDINT", "DWORD", "REAL", "LREAL",
    "STRING", "TIME", "DATE", "DT", "TOD"
]

# Entity categories for Home Assistant
ENTITY_CATEGORY_CONFIG = "config"
ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"

# Options defaults
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_USE_NOTIFICATIONS = True
DEFAULT_OPERATION_TIMEOUT = 5.0
DEFAULT_MAX_FAILURES = 3