"""Config flow for the Swidget ERV integration.

Supports three ways to add a device:
  1. Manual entry — user provides the device IP address.
  2. SSDP discovery — HA's built-in SSDP scanner detects the device
     broadcasting with ST "urn:swidget:pico:1".
  3. DHCP discovery — HA's DHCP watcher matches the device by hostname
     pattern ("swidget*") or MAC address prefix.

In all cases, the flow validates the device by fetching GET /api/v1/summary
and uses the device MAC as the unique_id to prevent duplicates. If the device
has an access key set, the user is prompted to enter it.

An options flow is also provided so users can adjust the polling interval
from the UI without needing to reload the integration.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol

from homeassistant.components import dhcp, ssdp
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback as ha_callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Schema for manual entry — user provides IP and optional access key
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)


class SwidgetErvConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swidget ERV."""

    VERSION = 1

    @staticmethod
    @ha_callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return SwidgetErvOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        # These are set during discovery and used in the confirmation step
        self._discovered_host: str | None = None
        self._discovered_mac: str | None = None

    # ------------------------------------------------------------------
    # Manual entry
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (manual IP entry)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            password = user_input.get(CONF_PASSWORD)

            # Validate the device by fetching its summary
            summary = await self._async_fetch_summary(host, password)
            if summary is None:
                errors["base"] = "cannot_connect"
            else:
                mac = summary.get("mac", "")
                if not mac:
                    errors["base"] = "cannot_connect"
                else:
                    # Use MAC as unique_id to prevent duplicate entries
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()
                    return self._async_create_entry_from_summary(summary, user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # SSDP discovery
    # ------------------------------------------------------------------

    async def async_step_ssdp(
        self, discovery_info: ssdp.SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle SSDP discovery.

        Swidget devices broadcast with ST "urn:swidget:pico:1". The LOCATION
        header contains the device URL, and the USN header contains the MAC
        as the last segment after a hyphen.
        """
        _LOGGER.debug("SSDP discovery received: %s", discovery_info)

        # Extract host IP from the SSDP LOCATION URL
        location = discovery_info.ssdp_location
        if not location:
            return self.async_abort(reason="cannot_connect")

        host = urlparse(location).hostname
        if not host:
            return self.async_abort(reason="cannot_connect")

        # Extract MAC from USN header (format: uuid:...-MACADDRESS)
        usn = discovery_info.ssdp_usn or ""
        mac = usn.rsplit("-", 1)[-1] if "-" in usn else ""

        return await self._async_handle_discovery(host, mac)

    # ------------------------------------------------------------------
    # DHCP discovery
    # ------------------------------------------------------------------

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle DHCP discovery.

        HA watches DHCP traffic and matches devices by hostname pattern
        or MAC address prefix (OUI). Both are declared in manifest.json.
        """
        _LOGGER.debug("DHCP discovery received: %s", discovery_info)

        host = discovery_info.ip
        mac = discovery_info.macaddress  # Already formatted by HA

        return await self._async_handle_discovery(host, mac)

    # ------------------------------------------------------------------
    # Shared discovery handling
    # ------------------------------------------------------------------

    async def _async_handle_discovery(
        self, host: str, mac: str
    ) -> ConfigFlowResult:
        """Handle a discovered device (shared by SSDP and DHCP).

        Validates the device, sets the unique_id, and presents the
        confirmation form to the user.
        """
        # Validate that this is actually a Swidget device we can talk to
        summary = await self._async_fetch_summary(host)

        if summary is not None:
            # Prefer the MAC from the summary (most reliable source)
            mac = summary.get("mac", mac)

        if mac:
            # Normalize MAC to lowercase, no separators (HA convention)
            mac = mac.replace(":", "").replace("-", "").lower()
            await self.async_set_unique_id(mac)
            # If already configured, update the host IP (device may have moved)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_mac = mac

        # Show the device IP in the notification/title
        self.context["title_placeholders"] = {"host": host}

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device.

        Shows a form so the user can optionally enter an access key.
        The device is validated again with the key before creating the entry.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input.get(CONF_PASSWORD)
            host = self._discovered_host

            summary = await self._async_fetch_summary(host, password)
            if summary is None:
                errors["base"] = "cannot_connect"
            else:
                mac = summary.get("mac", "")
                if mac:
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()

                data = {CONF_HOST: host}
                if password:
                    data[CONF_PASSWORD] = password
                return self._async_create_entry_from_summary(summary, data)

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            description_placeholders={"host": self._discovered_host or ""},
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _async_create_entry_from_summary(
        self, summary: dict[str, Any], data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create a config entry from a validated summary response."""
        model = summary.get("model", "")
        title = f"{DEFAULT_NAME} ({model})" if model else DEFAULT_NAME
        return self.async_create_entry(title=title, data=data)

    async def _async_fetch_summary(
        self, host: str | None, password: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch the device summary, returning None on failure.

        This is used both for validation (is the device reachable and
        a real Swidget?) and to extract device metadata (MAC, model).
        """
        if not host:
            return None
        session = async_get_clientsession(self.hass)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if password:
            headers["x-secret-key"] = password
        try:
            resp = await session.get(
                f"http://{host}/api/v1/summary",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            resp.raise_for_status()
            return await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to connect to Swidget ERV at %s", host)
            return None


class SwidgetErvOptionsFlow(OptionsFlow):
    """Options flow for Swidget ERV — lets users adjust the poll interval.

    Accessible from Settings → Devices & Services → Swidget ERV → Configure.
    """

    def __init__(self, config_entry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Show current value as default
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(int, vol.Range(min=1, max=300)),
                }
            ),
        )
