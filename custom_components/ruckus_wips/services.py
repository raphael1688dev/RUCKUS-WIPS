"""Services exposed by the RUCKUS WIPS integration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import aiohttp
from aioruckus.exceptions import AuthenticationError
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

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

    from . import RuckusWipsConfigEntry

_LOGGER = logging.getLogger(__name__)

_MAC_RE = re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", re.IGNORECASE)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BSSID): cv.string,
        vol.Optional("entry_id"): cv.string,
        vol.Optional("device_id"): cv.string,
    }
)

# Errors that "talking to Unleashed" can plausibly raise. Used by service
# handlers to surface a clean HomeAssistantError instead of letting them
# bubble up uncaught.
_TRANSPORT_ERRORS = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
    ConnectionError,
    KeyError,
    ValueError,
    TypeError,
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


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> RuckusWipsConfigEntry:
    """Pick the controller entry for this service call.

    Resolution order:
    1. Explicit `entry_id` in service data.
    2. Explicit `device_id` (via HA's target selector) → look up the hub
       device → resolve to the owning entry.
    3. The single loaded entry, if only one exists.
    4. Error — caller must disambiguate.
    """
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.runtime_data is not None
    ]
    if not entries:
        raise HomeAssistantError("No RUCKUS WIPS integrations are loaded.")

    requested_entry = call.data.get("entry_id")
    if requested_entry:
        for entry in entries:
            if entry.entry_id == requested_entry:
                return entry
        raise ServiceValidationError(
            f"entry_id {requested_entry} not found among loaded RUCKUS WIPS entries"
        )

    requested_device = call.data.get("device_id")
    if requested_device:
        device_reg = dr.async_get(hass)
        device = device_reg.async_get(requested_device)
        if device is None:
            raise ServiceValidationError(
                f"device_id {requested_device} not found"
            )
        for entry_id in device.config_entries:
            for entry in entries:
                if entry.entry_id == entry_id:
                    return entry
        raise ServiceValidationError(
            f"device {requested_device} is not owned by any loaded RUCKUS WIPS entry"
        )

    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple RUCKUS WIPS controllers are configured. "
            "Pass entry_id or pick a device to identify which one to target."
        )
    return entries[0]


def _resolve_session(hass: HomeAssistant, call: ServiceCall) -> AjaxSession:
    return _resolve_entry(hass, call).runtime_data.session


async def _refresh_after_action(hass: HomeAssistant, session: AjaxSession) -> None:
    """Best-effort coordinator refresh — never raises into the caller."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.runtime_data and entry.runtime_data.session is session:
            try:
                await entry.runtime_data.coordinator.async_request_refresh()
            except Exception as err:  # noqa: BLE001 — refresh is fire-and-forget
                _LOGGER.debug("Post-action refresh raised %s: %s", type(err).__name__, err)
            break


async def _async_mark_malicious(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    bssid = _normalize(call.data[ATTR_BSSID])
    session = _resolve_session(hass, call)
    payload = (
        f"<ajax-request action='docmd' xcmd='blockrogue' check-ability='10' comp='stamgr'>"
        f"<xcmd cmd='blockrogue' tag='rogue' rogue='{bssid}'/></ajax-request>"
    )
    try:
        try:
            resp = await session.api.cmdstat(payload)
        except AuthenticationError as err:
            raise HomeAssistantError(
                f"Authentication to Unleashed failed during mark_malicious: {err}"
            ) from err
        except _TRANSPORT_ERRORS as err:
            raise HomeAssistantError(
                f"mark_malicious failed ({type(err).__name__}): {err}"
            ) from err

        xmsg = (resp or {}).get("xmsg") or {}
        if str(xmsg.get("type", "0")) != "0":
            raise HomeAssistantError(
                f"Unleashed rejected mark_malicious for {bssid}: {xmsg.get('lmsg') or xmsg}"
            )
    finally:
        # Always refresh — even if Unleashed rejected, our local snapshot
        # may be stale and re-fetching realigns it with the controller's
        # actual state.
        await _refresh_after_action(hass, session)

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
        try:
            resp = await session.api.cmdstat(payload)
        except AuthenticationError as err:
            raise HomeAssistantError(
                f"Authentication to Unleashed failed during unmark_malicious: {err}"
            ) from err
        except _TRANSPORT_ERRORS as err:
            raise HomeAssistantError(
                f"unmark_malicious failed ({type(err).__name__}): {err}"
            ) from err

        xmsg = (resp or {}).get("xmsg") or {}
        if str(xmsg.get("type", "0")) != "0":
            raise HomeAssistantError(
                f"Unleashed rejected unmark_malicious for {bssid}: {xmsg.get('lmsg') or xmsg}"
            )
    finally:
        await _refresh_after_action(hass, session)

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
