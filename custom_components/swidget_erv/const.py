"""Constants for the Swidget ERV integration.

These values are used across the integration for configuration keys,
default settings, and device metadata.
"""

# Integration domain — must match the folder name and manifest.json
DOMAIN = "swidget_erv"

# Config entry data keys
CONF_HOST = "host"          # IP address of the Swidget ERV device
CONF_PASSWORD = "password"  # Optional access key set during device provisioning

# Options flow keys
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_NAME = "Swidget ERV"
DEFAULT_SCAN_INTERVAL = 30  # Seconds between state polls (configurable via options)

# Device registry metadata
MANUFACTURER = "Swidget"
