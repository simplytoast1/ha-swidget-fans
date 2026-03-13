"""Number platform for the Swidget ERV integration.

Creates a number entity for the supply/exhaust balancing offset.
This allows users to fine-tune the balance between supply and exhaust
airflow. The exact range is not fully documented; we default to -10..+10.

Only created if the device reports "balancing" in its functions list.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwidgetErvConfigEntry
from .coordinator import SwidgetErvCoordinator
from .entity import SwidgetErvEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwidgetErvConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swidget ERV number entities based on device capabilities."""
    coordinator = entry.runtime_data
    functions = coordinator.get_host_functions()
    entities: list[NumberEntity] = []

    if "balancing" in functions:
        entities.append(SwidgetErvBalancingOffset(coordinator))

    async_add_entities(entities)


class SwidgetErvBalancingOffset(SwidgetErvEntity, NumberEntity):
    """Number entity for supply/exhaust balancing offset.

    Adjusts the balance between supply and exhaust airflow. A value of 0
    means balanced; positive values favor supply, negative favor exhaust
    (exact behavior depends on the device firmware).

    Reads from host.components.0.balancing.offset (integer).
    """

    _attr_translation_key = "balancing_offset"
    _attr_native_min_value = -10
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:scale-balance"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_balancing_offset"

    @property
    def native_value(self) -> float | None:
        """Return the current balancing offset."""
        comp = self.coordinator.get_component_state()
        return comp.get("balancing", {}).get("offset")

    async def async_set_native_value(self, value: float) -> None:
        """Set the balancing offset on the device."""
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"balancing": {"offset": int(value)}}}}}
        )
