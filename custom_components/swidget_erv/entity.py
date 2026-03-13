"""Base entity for the Swidget ERV integration.

All platform entities (fan, switch, sensor, number) inherit from this base
class. It provides shared DeviceInfo so that all entities are grouped under
a single device in the Home Assistant device registry.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SwidgetErvCoordinator


class SwidgetErvEntity(CoordinatorEntity[SwidgetErvCoordinator]):
    """Base entity for Swidget ERV devices.

    Sets has_entity_name = True so entity names are derived from the
    translation_key set on each subclass, prefixed by the device name.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the entity with shared device info."""
        super().__init__(coordinator)
        # All entities share a single HA device, keyed by MAC address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            name=coordinator.config_entry.title if coordinator.config_entry else "Swidget ERV",
            manufacturer=MANUFACTURER,
            model=f"{coordinator.model} ({coordinator.host_type})",
            sw_version=coordinator.firmware_version,
            hw_version=coordinator.host_code,
        )
