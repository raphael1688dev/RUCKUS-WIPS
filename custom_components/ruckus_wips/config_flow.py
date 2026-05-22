"""Config flow for the RUCKUS WIPS integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aioruckus import AjaxSession
from aioruckus.exceptions import AuthenticationError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_UNBLOCK,
    CONF_IGNORE_KNOWN,
    CONF_RSSI_THRESHOLD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_UNBLOCK,
    DEFAULT_IGNORE_KNOWN,
    DEFAULT_RSSI_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


async def _async_probe(host: str, username: str, password: str) -> dict[str, Any]:
    """Try to log in and pull system info. Raise on failure."""
    session = AjaxSession.async_create(host, username, password)
    try:
        await session.login()
        return await session.api.get_system_info()
    finally:
        await session.close()


class RuckusWipsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RUCKUS WIPS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                system = await _async_probe(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001 — surface anything else as a generic connect error
                errors["base"] = "cannot_connect"
            else:
                serial = (system.get("sysinfo") or {}).get("serial")
                if serial:
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured(updates=user_input)
                name = (system.get("identity") or {}).get("name") or "RUCKUS WIPS"
                return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry_data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**self._reauth_entry_data, **user_input}
            try:
                await _async_probe(
                    merged[CONF_HOST], merged[CONF_USERNAME], merged[CONF_PASSWORD]
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> RuckusWipsOptionsFlow:
        return RuckusWipsOptionsFlow()


class RuckusWipsOptionsFlow(OptionsFlow):
    """Options for poll cadence, RSSI filter, and the advanced unblock toggle."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_RSSI_THRESHOLD,
                    default=opts.get(CONF_RSSI_THRESHOLD, DEFAULT_RSSI_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=80, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_IGNORE_KNOWN,
                    default=opts.get(CONF_IGNORE_KNOWN, DEFAULT_IGNORE_KNOWN),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_UNBLOCK,
                    default=opts.get(CONF_ENABLE_UNBLOCK, DEFAULT_ENABLE_UNBLOCK),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
