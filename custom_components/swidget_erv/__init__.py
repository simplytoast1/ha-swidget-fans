"""The Swidget ERV integration.

This integration communicates with Swidget ERV (Energy Recovery Ventilator)
controllers over their local HTTP API. No cloud connection is required.

Setup flow:
  1. Config entry is created (via manual IP entry or SSDP/DHCP discovery).
  2. async_setup_entry creates a coordinator, fetches the device summary
     to learn capabilities, then performs the first state poll.
  3. The coordinator is stored on the config entry's runtime_data and
     shared with all platform entities (fan, switch, sensor, number).
  4. An options update listener watches for poll interval changes from the UI.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import SwidgetErvCoordinator

_LOGGER = logging.getLogger(__name__)

# Platforms this integration provides
PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Type alias so platform modules can import a typed config entry
type SwidgetErvConfigEntry = ConfigEntry[SwidgetErvCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SwidgetErvConfigEntry) -> bool:
    """Set up Swidget ERV from a config entry."""
    host = entry.data[CONF_HOST]
    password = entry.data.get(CONF_PASSWORD)

    # Read the poll interval from options (user-configurable), falling back to default
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = SwidgetErvCoordinator(hass, host, password, scan_interval, config_entry=entry)

    # Fetch the device summary once to learn capabilities (functions, modules,
    # allowed CFM values, model info). This determines which entities to create.
    await coordinator.async_fetch_summary()

    # Perform the first state poll — raises ConfigEntryNotReady on failure
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator on the entry so platform setup can access it
    entry.runtime_data = coordinator

    # Listen for options changes (e.g. poll interval adjusted in the UI)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Forward setup to each platform (fan.py, switch.py, sensor.py, number.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: SwidgetErvConfigEntry) -> None:
    """Handle options update — adjust the coordinator poll interval live."""
    coordinator: SwidgetErvCoordinator = entry.runtime_data
    new_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=new_interval)
    _LOGGER.debug("Poll interval updated to %s seconds", new_interval)


async def async_unload_entry(hass: HomeAssistant, entry: SwidgetErvConfigEntry) -> bool:
    """Unload a Swidget ERV config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
