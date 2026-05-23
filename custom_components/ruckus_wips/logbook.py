"""Logbook descriptions for RUCKUS WIPS bus events.

Without this module, Logbook entries for our events would render as a bare
event-type string. The describer turns each `ruckus_wips_new_rogue` bus event
into a human-readable line like:

    New rogue AP detected: realme C51 (5e:a6:e6:78:a0:b8)
    ch157 rssi 8 — detected by R720-2F (MASTER ROOM)
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import BUS_EVENT_NEW_ROGUE, DOMAIN


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Register Logbook describer callbacks for RUCKUS WIPS bus events."""

    @callback
    def describe_new_rogue(event: Event) -> dict[str, str]:
        data = event.data or {}
        ssid = data.get("ssid") or "(hidden SSID)"
        bssid = data.get("bssid") or "?"
        channel = data.get("channel") or "?"
        rssi = data.get("rssi")
        ap_name = data.get("detection_ap") or "?"
        ap_loc = data.get("detection_ap_location") or ""
        rogue_type = data.get("rogue_type") or ""

        details: list[str] = [f"{ssid} ({bssid})"]
        details.append(f"ch{channel}")
        if rssi is not None:
            details.append(f"rssi {rssi}")
        if ap_loc:
            details.append(f"detected by {ap_name} ({ap_loc})")
        else:
            details.append(f"detected by {ap_name}")
        if rogue_type:
            details.append(f"[{rogue_type}]")

        return {
            LOGBOOK_ENTRY_NAME: "RUCKUS WIPS",
            LOGBOOK_ENTRY_MESSAGE: "new rogue AP — " + " · ".join(details),
        }

    async_describe_event(DOMAIN, BUS_EVENT_NEW_ROGUE, describe_new_rogue)
