"""Config flow for Beckhoff ADS integration."""
from __future__ import annotations

import logging
from typing import Any

import pyads
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
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
