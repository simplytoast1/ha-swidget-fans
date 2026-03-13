"""Sensor platform for the Swidget ERV integration.

Creates sensors for monitoring device state:
  - Power (current): Real-time wattage draw.
  - Power (average): Average wattage over time.
  - Exhaust CFM: Current airflow rate (also reflected in the fan entity,
    but a dedicated sensor is useful for history graphs).
  - Wi-Fi RSSI: Signal strength (diagnostic).
  - Condensation: Status of the condensation management module.
  - Self-Diagnostic: Insert-level health check (0 = healthy).

Sensors are conditionally created based on which functions and modules
the device reports in its summary.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwidgetErvConfigEntry
from .coordinator import SwidgetErvCoordinator
from .entity import SwidgetErvEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwidgetErvConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swidget ERV sensors based on device capabilities."""
    coordinator = entry.runtime_data
    functions = coordinator.get_host_functions()
    modules = coordinator.get_host_modules()

    entities: list[SensorEntity] = []

    # Power sensors — only if the device reports a "power" function
    if "power" in functions:
        entities.append(SwidgetErvPowerSensor(coordinator))
        entities.append(SwidgetErvPowerAvgSensor(coordinator))

    # Exhaust CFM sensor — only if the device reports an "exhaust" function
    if "exhaust" in functions:
        entities.append(SwidgetErvExhaustCfmSensor(coordinator))

    # Wi-Fi signal — always available (from the connection object)
    entities.append(SwidgetErvRssiSensor(coordinator))

    # Condensation module — only if the device reports this module
    if "condensation" in modules:
        entities.append(SwidgetErvCondensationSensor(coordinator))

    # Self-diagnostic — always available (from insert errors)
    entities.append(SwidgetErvSelfDiagSensor(coordinator))

    async_add_entities(entities)


class SwidgetErvPowerSensor(SwidgetErvEntity, SensorEntity):
    """Current power consumption in watts.

    Reads from host.components.0.power.current (float, e.g. 3.75).
    """

    _attr_translation_key = "power_current"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_power_current"

    @property
    def native_value(self) -> float | None:
        """Return the current power draw."""
        comp = self.coordinator.get_component_state()
        return comp.get("power", {}).get("current")


class SwidgetErvPowerAvgSensor(SwidgetErvEntity, SensorEntity):
    """Average power consumption in watts.

    Reads from host.components.0.power.avg (float).
    """

    _attr_translation_key = "power_average"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_power_avg"

    @property
    def native_value(self) -> float | None:
        """Return the average power draw."""
        comp = self.coordinator.get_component_state()
        return comp.get("power", {}).get("avg")


class SwidgetErvExhaustCfmSensor(SwidgetErvEntity, SensorEntity):
    """Exhaust airflow rate in CFM (cubic feet per minute).

    Reads from host.components.0.exhaust.cfm (integer).
    Also reflected in the fan entity, but a dedicated sensor is
    useful for history/graphing in dashboards.
    """

    _attr_translation_key = "exhaust_cfm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "CFM"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_exhaust_cfm"

    @property
    def native_value(self) -> int | None:
        """Return the current exhaust CFM."""
        comp = self.coordinator.get_component_state()
        return comp.get("exhaust", {}).get("cfm")


class SwidgetErvRssiSensor(SwidgetErvEntity, SensorEntity):
    """Wi-Fi signal strength in dBm.

    Reads from connection.rssi (integer, e.g. -56).
    Marked as a diagnostic entity since it's not user-actionable.
    """

    _attr_translation_key = "rssi"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_rssi"

    @property
    def native_value(self) -> int | None:
        """Return the Wi-Fi RSSI value."""
        return self.coordinator.get_connection_info().get("rssi")


class SwidgetErvCondensationSensor(SwidgetErvEntity, SensorEntity):
    """Condensation management module status.

    Reads from host.components.0.modules.condensation (string).
    Known values: "dormant". Other possible values TBD (likely "active").
    """

    _attr_translation_key = "condensation"
    _attr_icon = "mdi:water"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_condensation"

    @property
    def native_value(self) -> str | None:
        """Return the condensation module status."""
        comp = self.coordinator.get_component_state()
        return comp.get("modules", {}).get("condensation")


class SwidgetErvSelfDiagSensor(SwidgetErvEntity, SensorEntity):
    """Self-diagnostic health check.

    Reads from insert.errors.self_diag (integer). 0 means healthy;
    any non-zero value indicates a diagnostic issue.
    """

    _attr_translation_key = "self_diagnostic"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: SwidgetErvCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_self_diag"

    @property
    def native_value(self) -> int | None:
        """Return the self-diagnostic value (0 = healthy)."""
        return self.coordinator.get_insert_errors().get("self_diag")
