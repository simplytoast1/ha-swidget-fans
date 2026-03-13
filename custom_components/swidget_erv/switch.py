"""Switch platform for the Swidget ERV integration.

Creates switches for device functions that have on/off behavior:
  - Boost mode: runs the fan at full power. Turning boost off also turns off the fan.
  - Light: an optional light output on the ERV unit (may not be
    physically connected on all installations).

Entities are only created if the device reports the corresponding
function in its summary (e.g. "boost" or "light" in the functions list).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Swidget ERV switches based on device capabilities."""
    coordinator = entry.runtime_data
    functions = coordinator.get_host_functions()
    entities: list[SwitchEntity] = []

    # Only create entities for functions the device actually supports
    if "boost" in functions:
        entities.append(SwidgetErvBoostSwitch(coordinator))
    if "light" in functions:
        entities.append(SwidgetErvLightSwitch(coordinator))

    async_add_entities(entities)


class SwidgetErvBoostSwitch(SwidgetErvEntity, SwitchEntity):
    """Switch for ERV boost mode.

    Boost runs the fan at full power. Turning boost off also turns the
    fan off entirely. State is read from host.components.0.boost.mode
    ("on" / "off").
    """

    _attr_translation_key = "boost"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the boost switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_boost"

    @property
    def is_on(self) -> bool | None:
        """Return true if boost mode is active."""
        comp = self.coordinator.get_component_state()
        mode = comp.get("boost", {}).get("mode")
        if mode is None:
            return None
        return mode == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate boost mode (runs fan at full power)."""
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"boost": {"mode": "on"}}}}}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate boost mode (also turns off the fan)."""
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"boost": {"mode": "off"}}}}}
        )


class SwidgetErvLightSwitch(SwidgetErvEntity, SwitchEntity):
    """Switch for ERV light output.

    The device reports a "light" function, but not all installations have
    a light physically wired. The entity is still created so users can
    test it or use it if they add a light later.
    State is read from host.components.0.light.on (true / false).
    """

    _attr_translation_key = "light"
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the light switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_light"

    @property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        comp = self.coordinator.get_component_state()
        return comp.get("light", {}).get("on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"light": {"on": True}}}}}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"light": {"on": False}}}}}
        )
