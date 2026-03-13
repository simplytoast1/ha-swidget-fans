"""Fan platform for the Swidget ERV integration.

Creates a single fan entity representing the ERV exhaust fan. The device
only accepts specific CFM values (e.g. 0, 50, 60, 70, ... 150), so the
fan supports both:
  - Preset modes: each allowed CFM value as a named preset (e.g. "50", "100")
  - Percentage: evenly distributed across the available speed steps

Setting CFM to 0 turns the fan off. Any non-zero CFM turns it on.
When turning on without specifying a speed, the last known non-zero
CFM is used (defaults to 50 CFM if never set).
"""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwidgetErvConfigEntry
from .coordinator import SwidgetErvCoordinator
from .entity import SwidgetErvEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwidgetErvConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Swidget ERV fan entity."""
    coordinator = entry.runtime_data
    async_add_entities([SwidgetErvFan(coordinator)])


class SwidgetErvFan(SwidgetErvEntity, FanEntity):
    """Representation of the Swidget ERV exhaust fan."""

    _attr_translation_key = "exhaust_fan"
    _enable_turn_on_off_backwards_compat = False

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_fan"
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )
        # Remember the last non-zero CFM so turn_on can restore it
        self._last_cfm: int = 50

    @property
    def _non_zero_cfm_values(self) -> list[int]:
        """Get the allowed CFM values excluding 0 (off)."""
        return [v for v in self.coordinator.get_allowed_cfm() if v > 0]

    @property
    def speed_count(self) -> int:
        """Return the number of discrete speed steps.

        HA uses this to map percentages to steps. For example, with
        10 steps, each step represents 10% of the speed range.
        """
        return len(self._non_zero_cfm_values)

    @property
    def preset_modes(self) -> list[str]:
        """Return available preset modes (CFM values as strings)."""
        return [str(v) for v in self._non_zero_cfm_values]

    @property
    def is_on(self) -> bool | None:
        """Return true if the fan is running (CFM > 0)."""
        comp = self.coordinator.get_component_state()
        cfm = comp.get("exhaust", {}).get("cfm")
        if cfm is None:
            return None
        return cfm > 0

    @property
    def percentage(self) -> int | None:
        """Return the current speed as a percentage (0-100).

        Maps the current CFM to a percentage based on its position
        in the list of allowed non-zero CFM values.
        """
        comp = self.coordinator.get_component_state()
        cfm = comp.get("exhaust", {}).get("cfm")
        if cfm is None or cfm == 0:
            return 0
        values = self._non_zero_cfm_values
        if not values or cfm not in values:
            return 0
        # Position-based percentage: first speed = ~10%, last speed = 100%
        idx = values.index(cfm) + 1
        return math.ceil(idx * 100 / len(values))

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode (CFM value as string)."""
        comp = self.coordinator.get_component_state()
        cfm = comp.get("exhaust", {}).get("cfm")
        if cfm is None or cfm == 0:
            return None
        return str(cfm)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan.

        If a preset_mode or percentage is given, use that speed.
        Otherwise, restore the last known non-zero CFM value.
        """
        if preset_mode is not None:
            await self._async_set_cfm(int(preset_mode))
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._async_set_cfm(self._last_cfm)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan by setting CFM to 0."""
        await self._async_set_cfm(0)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed by percentage.

        Maps the percentage to the nearest allowed CFM value.
        0% turns the fan off.
        """
        if percentage == 0:
            await self._async_set_cfm(0)
            return
        values = self._non_zero_cfm_values
        # Map percentage to an index in the allowed values list
        idx = max(0, min(len(values) - 1, round(percentage * len(values) / 100) - 1))
        await self._async_set_cfm(values[idx])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the fan to a specific CFM preset mode."""
        await self._async_set_cfm(int(preset_mode))

    async def _async_set_cfm(self, cfm: int) -> None:
        """Send a CFM command to the device.

        Remembers the value if non-zero so turn_on can restore it later.
        """
        if cfm > 0:
            self._last_cfm = cfm
        await self.coordinator.async_send_command(
            {"host": {"components": {"0": {"exhaust": {"cfm": cfm}}}}}
        )

    # ------------------------------------------------------------------
    # State tracking
    # ------------------------------------------------------------------

    @callback
    def _handle_coordinator_update(self) -> None:
        """Track the last non-zero CFM whenever state updates.

        This ensures that if the CFM was changed externally (e.g. via
        the device's own controls or another client), we still remember
        the correct speed to restore on turn_on.
        """
        comp = self.coordinator.get_component_state()
        cfm = comp.get("exhaust", {}).get("cfm", 0)
        if cfm > 0:
            self._last_cfm = cfm
        super()._handle_coordinator_update()
