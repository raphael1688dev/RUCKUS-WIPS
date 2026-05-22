"""Services exposed by the RUCKUS WIPS integration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_BSSID,
    CONF_ENABLE_UNBLOCK,
    DEFAULT_ENABLE_UNBLOCK,
    DOMAIN,
    SERVICE_MARK_MALICIOUS,
    SERVICE_UNMARK_MALICIOUS,
)

if TYPE_CHECKING:
    from aioruckus import AjaxSession

_LOGGER = logging.getLogger(__name__)

_MAC_RE = re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", re.IGNORECASE)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BSSID): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)


def _normalize(bssid: str) -> str:
    bssid = bssid.strip().lower().replace("-", ":")
    if not _MAC_RE.match(bssid):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_bssid",
            translation_placeholders={"bssid": bssid},
        )
    return bssid


def _resolve_session(hass: HomeAssistant, call: ServiceCall) -> AjaxSession:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.runtime_data is not None
    ]
    if not entries:
        raise HomeAssistantError("No RUCKUS WIPS integrations are loaded.")

    requested = call.data.get("entry_id")
    if requested:
        for entry in entries:
            if entry.entry_id == requested:
                return entry.runtime_data.session
        raise ServiceValidationError(
            f"entry_id {requested} not found among loaded RUCKUS WIPS entries"
        )

    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple RUCKUS WIPS controllers are configured. "
            "Pass entry_id to identify which one to target."
        )
    return entries[0].runtime_data.session


async def _async_mark_malicious(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    bssid = _normalize(call.data[ATTR_BSSID])
    session = _resolve_session(hass, call)
    payload = (
        f"<ajax-request action='docmd' xcmd='blockrogue' check-ability='10' comp='stamgr'>"
        f"<xcmd cmd='blockrogue' tag='rogue' rogue='{bssid}'/></ajax-request>"
    )
    try:
        resp = await session.api.cmdstat(payload)
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError(f"mark_malicious failed: {err}") from err

    xmsg = (resp or {}).get("xmsg") or {}
    if str(xmsg.get("type", "0")) != "0":
        raise HomeAssistantError(
            f"Unleashed rejected mark_malicious for {bssid}: {xmsg.get('lmsg') or xmsg}"
        )

    # Pull a fresh snapshot so sensors / event entity reflect the change quickly.
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.runtime_data and entry.runtime_data.session is session:
            await entry.runtime_data.coordinator.async_request_refresh()
            break

    return {"bssid": bssid, "blocked": True}


async def _async_unmark_malicious(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    bssid = _normalize(call.data[ATTR_BSSID])
    session = _resolve_session(hass, call)
    payload = (
        f"<ajax-request action='docmd' xcmd='unblockrogue' check-ability='10' comp='stamgr'>"
        f"<xcmd cmd='unblockrogue' tag='rogue' rogue='{bssid}'/></ajax-request>"
    )
    try:
        resp = await session.api.cmdstat(payload)
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError(f"unmark_malicious failed: {err}") from err

    xmsg = (resp or {}).get("xmsg") or {}
    if str(xmsg.get("type", "0")) != "0":
        raise HomeAssistantError(
            f"Unleashed rejected unmark_malicious for {bssid}: {xmsg.get('lmsg') or xmsg}"
        )

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.runtime_data and entry.runtime_data.session is session:
            await entry.runtime_data.coordinator.async_request_refresh()
            break

    return {"bssid": bssid, "blocked": False}


async def async_register_services(hass: HomeAssistant) -> None:
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_MALICIOUS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_MALICIOUS,
            _async_mark_malicious,
            schema=SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    enable_unblock = any(
        entry.options.get(CONF_ENABLE_UNBLOCK, DEFAULT_ENABLE_UNBLOCK)
        for entry in hass.config_entries.async_entries(DOMAIN)
    )
    if enable_unblock and not hass.services.has_service(DOMAIN, SERVICE_UNMARK_MALICIOUS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UNMARK_MALICIOUS,
            _async_unmark_malicious,
            schema=SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    elif not enable_unblock and hass.services.has_service(DOMAIN, SERVICE_UNMARK_MALICIOUS):
        hass.services.async_remove(DOMAIN, SERVICE_UNMARK_MALICIOUS)


async def async_unregister_services(hass: HomeAssistant) -> None:
    for name in (SERVICE_MARK_MALICIOUS, SERVICE_UNMARK_MALICIOUS):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
