"""DataUpdateCoordinator for the Swidget ERV integration.

The coordinator is the central data manager. It:
  - Fetches the device summary once at setup (GET /api/v1/summary) to learn
    what capabilities the device has (functions, modules, allowed CFM values).
  - Polls the device state periodically (GET /api/v1/state) and distributes
    updated data to all entities via HA's CoordinatorEntity pattern.
  - Sends control commands (POST /api/v1/command) and merges the echoed
    response into the local state so entities update instantly without
    needing an extra GET request.

All HTTP communication with the device goes through this coordinator.
A lock serializes requests so the device never handles more than one
HTTP call at a time (these are small embedded controllers that can
easily get overwhelmed).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (mutates base).

    Used to patch the coordinator's cached state with the subset of
    fields echoed back by a command response, so we get an instant
    local update without an extra GET /api/v1/state round-trip.
    """
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class SwidgetErvCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll the Swidget ERV device.

    Attributes:
        host: IP address of the device.
        password: Optional access key for authenticated requests.
        summary: Cached device summary from /api/v1/summary (capabilities, model, etc.).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        password: str | None = None,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.host = host
        self.password = password
        self.config_entry = config_entry
        self._session = async_get_clientsession(hass)
        self.summary: dict[str, Any] = {}
        # Serialize all HTTP requests to avoid overwhelming the device
        self._request_lock = asyncio.Lock()

    @property
    def _base_url(self) -> str:
        """Build the base URL for the device's local HTTP API."""
        return f"http://{self.host}"

    @property
    def _headers(self) -> dict[str, str]:
        """Build request headers, including the access key if configured."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.password:
            headers["x-secret-key"] = self.password
        return headers

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def async_fetch_summary(self) -> dict[str, Any]:
        """Fetch device summary (called once during setup).

        The summary tells us the device model, firmware version, MAC address,
        and—critically—which functions and modules are available so we know
        which HA entities to create.
        """
        async with self._request_lock:
            try:
                resp = await self._session.get(
                    f"{self._base_url}/api/v1/summary",
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                )
                resp.raise_for_status()
                self.summary = await resp.json()
                return self.summary
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UpdateFailed(f"Unable to reach Swidget ERV at {self.host}: {err}") from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest state from the device.

        Called automatically by the coordinator on each polling interval.
        The returned dict is stored as self.data and shared with all entities.
        The lock ensures this never runs concurrently with a command.
        """
        async with self._request_lock:
            try:
                resp = await self._session.get(
                    f"{self._base_url}/api/v1/state",
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                )
                resp.raise_for_status()
                return await resp.json()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UpdateFailed(f"Error communicating with Swidget ERV: {err}") from err

    # ------------------------------------------------------------------
    # Command sending
    # ------------------------------------------------------------------

    async def async_send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a command to the device.

        The device echoes back the accepted command on success, or returns
        an empty object {} if the command was not recognized.

        Instead of firing a separate GET /api/v1/state afterward (which
        would double the load on the device), we merge the echoed response
        directly into the coordinator's cached data. This gives entities
        an instant local update. The next scheduled poll will reconcile
        with the full device state.
        """
        async with self._request_lock:
            try:
                resp = await self._session.post(
                    f"{self._base_url}/api/v1/command",
                    json=payload,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                )
                resp.raise_for_status()
                result = await resp.json()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UpdateFailed(f"Error sending command to Swidget ERV: {err}") from err

        # Merge the echoed fields into our cached state so entities update
        # immediately without an extra HTTP round-trip
        if result and self.data is not None:
            _deep_merge(self.data, result)
            self.async_set_updated_data(self.data)

        return result

    # ------------------------------------------------------------------
    # State accessors — convenience methods for entities
    # ------------------------------------------------------------------

    def get_component_state(self, component_id: str = "0") -> dict[str, Any]:
        """Get the state of a specific host component.

        The ERV typically has a single component with id "0" containing
        all function states (exhaust, boost, light, power, etc.).
        """
        if self.data is None:
            return {}
        return self.data.get("host", {}).get("components", {}).get(component_id, {})

    def get_connection_info(self) -> dict[str, Any]:
        """Get connection info (RSSI, IP, MAC) from the state response."""
        if self.data is None:
            return {}
        return self.data.get("connection", {})

    def get_insert_errors(self) -> dict[str, Any]:
        """Get insert-level error info (e.g. self_diag) from state."""
        if self.data is None:
            return {}
        return self.data.get("insert", {}).get("errors", {})

    # ------------------------------------------------------------------
    # Summary accessors — used during entity setup
    # ------------------------------------------------------------------

    def get_host_functions(self, component_id: str = "0") -> list[str]:
        """Get the list of functions for a host component from the summary.

        Functions determine which entities to create (e.g. "boost", "light",
        "exhaust", "power", "balancing").
        """
        for comp in self.summary.get("host", {}).get("components", []):
            if comp.get("id") == component_id:
                return comp.get("functions", [])
        return []

    def get_host_modules(self, component_id: str = "0") -> list[str]:
        """Get the list of modules for a host component from the summary.

        Modules are optional subsystems like "condensation" management.
        """
        for comp in self.summary.get("host", {}).get("components", []):
            if comp.get("id") == component_id:
                return comp.get("modules", [])
        return []

    def get_max_cfm(self, component_id: str = "0") -> int:
        """Get the maximum CFM rating for the device from the summary."""
        for comp in self.summary.get("host", {}).get("components", []):
            if comp.get("id") == component_id:
                return comp.get("maxCFM", 150)
        return 150

    def get_allowed_cfm(self, component_id: str = "0") -> list[int]:
        """Get the list of allowed CFM values from the current state.

        The device reports exactly which CFM values it accepts (e.g.
        [0, 50, 60, 70, 80, 90, 100, 110, 120, 130, 150]). Only these
        values can be sent in exhaust commands.
        """
        comp = self.get_component_state(component_id)
        return comp.get("exhaust", {}).get("allowed", [0, 50, 60, 70, 80, 90, 100, 110, 120, 130, 150])

    # ------------------------------------------------------------------
    # Device identity properties
    # ------------------------------------------------------------------

    @property
    def mac(self) -> str:
        """Return the device MAC address (used as unique_id)."""
        return self.summary.get("mac", "")

    @property
    def model(self) -> str:
        """Return the device model (e.g. 'FAN_PICO_S3')."""
        return self.summary.get("model", "Unknown")

    @property
    def firmware_version(self) -> str:
        """Return the firmware version string."""
        return self.summary.get("version", "Unknown")

    @property
    def host_type(self) -> str:
        """Return the host type identifier (e.g. 'pesna_fv05')."""
        return self.summary.get("host", {}).get("type", "Unknown")

    @property
    def host_code(self) -> str:
        """Return the hardware code (e.g. '3010')."""
        for comp in self.summary.get("host", {}).get("components", []):
            return comp.get("code", "")
        return ""
