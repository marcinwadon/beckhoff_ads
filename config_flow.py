"""Config flow for Beckhoff ADS integration."""
from __future__ import annotations

import logging
from typing import Any

import pyads
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_AMS_NET_ID, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST, default=""): str,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Required(CONF_AMS_NET_ID, default=""): str,
})


class BeckhoffADSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beckhoff ADS."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BeckhoffADSOptionsFlow:
        """Get the options flow for this handler."""
        return BeckhoffADSOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            ams_net_id = user_input[CONF_AMS_NET_ID]

            # Test connection
            try:
                await self._test_connection(host, port, ams_net_id)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create entry
                await self.async_set_unique_id(f"{host}_{ams_net_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Beckhoff PLC ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, host: str, port: int, ams_net_id: str) -> None:
        """Test connection to PLC."""
        try:
            plc = pyads.Connection(ams_net_id, port, host)
            await self.hass.async_add_executor_job(plc.open)
            await self.hass.async_add_executor_job(plc.read_state)
            await self.hass.async_add_executor_job(plc.close)
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            raise ConnectionError from err


class BeckhoffADSOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Beckhoff ADS integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current options with defaults
        scan_interval = self.config_entry.options.get("scan_interval", 5)
        use_notifications = self.config_entry.options.get("use_notifications", True)
        operation_timeout = self.config_entry.options.get("operation_timeout", 5.0)
        reconnect_max_delay = self.config_entry.options.get("reconnect_max_delay", 60)
        max_connection_failures = self.config_entry.options.get("max_connection_failures", 3)

        options_schema = vol.Schema({
            vol.Optional(
                "scan_interval",
                default=scan_interval,
                description="Default update interval in seconds",
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(
                "use_notifications",
                default=use_notifications,
                description="Enable real-time notifications from PLC",
            ): bool,
            vol.Optional(
                "operation_timeout",
                default=operation_timeout,
                description="Timeout for PLC operations in seconds",
            ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=30.0)),
            vol.Optional(
                "reconnect_max_delay",
                default=reconnect_max_delay,
                description="Maximum reconnection delay in seconds",
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            vol.Optional(
                "max_connection_failures",
                default=max_connection_failures,
                description="Failures before triggering reconnection",
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "current_host": self.config_entry.data.get(CONF_HOST, "Unknown"),
            },
        )
