"""DataUpdateCoordinator for RUCKUS WIPS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp
from aioruckus import AjaxSession
from aioruckus.exceptions import AuthenticationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BUS_EVENT_NEW_ROGUE,
    CONF_IGNORE_KNOWN,
    CONF_RSSI_THRESHOLD,
    CONF_SCAN_INTERVAL,
    DEFAULT_IGNORE_KNOWN,
    DEFAULT_RSSI_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

# A BSSID stays in the "seen" set for this long after its last detection.
# Older entries are pruned each refresh to keep memory bounded over months
# of uptime in dense RF environments. When the same BSSID reappears after
# this window, it counts as "new" and re-fires the new_rogue event.
SEEN_BSSID_TTL_SECONDS: int = 24 * 60 * 60

# Re-fetch system_info every Nth poll (so firmware-version updates surface
# without requiring a HA restart). Cheap call; small N is fine.
SYSTEM_INFO_REFRESH_EVERY_N_POLLS: int = 20


@dataclass
class Rogue:
    """Normalized rogue device record."""

    bssid: str
    ssid: str
    channel: str
    radio_band: str
    radio_type: str
    encryption: str
    rogue_type: str
    blocked: bool
    last_seen: int
    detection_ap_mac: str
    detection_ap_name: str
    detection_ap_location: str
    rssi: int
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_api(cls, record: dict[str, Any]) -> Rogue:
        """Build a Rogue from the AJAX response dict.

        ``detection`` may be a single dict (one AP saw the rogue) or a list
        (multiple APs saw it). When it's a list, we surface the strongest
        signal — Ruckus RSSI is a small positive value where higher = stronger.
        """
        detection = _pick_strongest_detection(record.get("detection"))
        return cls(
            bssid=(record.get("mac") or "").lower(),
            ssid=record.get("ssid") or "",
            channel=str(record.get("channel") or ""),
            radio_band=record.get("radio-band") or "",
            radio_type=record.get("radio-type") or record.get("ieee80211-radio-type") or "",
            encryption=record.get("is-open") or "",
            rogue_type=record.get("rogue-type") or "",
            blocked=str(record.get("blocked", "")).lower() == "true",
            last_seen=int(record.get("last-seen") or 0),
            detection_ap_mac=(detection.get("ap") or "").lower(),
            detection_ap_name=detection.get("sys-name") or "",
            detection_ap_location=detection.get("location") or "",
            rssi=int(detection.get("rssi") or 0),
            raw=record,
        )


def _pick_strongest_detection(detection: Any) -> dict[str, Any]:
    """Normalize a ``detection`` field to a single dict, picking the strongest RSSI."""
    if isinstance(detection, dict):
        return detection
    if isinstance(detection, list) and detection:
        def rssi_of(d: Any) -> int:
            if not isinstance(d, dict):
                return -1
            try:
                return int(d.get("rssi") or 0)
            except (TypeError, ValueError):
                return 0
        best = max(detection, key=rssi_of)
        return best if isinstance(best, dict) else {}
    return {}


@dataclass
class RuckusWipsSnapshot:
    """Aggregated view returned by the coordinator each refresh."""

    rogues: dict[str, Rogue]
    """All currently visible rogues, keyed by BSSID."""

    active_unblocked: list[Rogue]
    """Rogues currently visible AND not yet marked malicious."""

    blocked: list[Rogue]
    """Rogues marked malicious (User Blocked)."""

    system: dict[str, Any]
    """System info from the Unleashed master."""


class RuckusWipsCoordinator(DataUpdateCoordinator[RuckusWipsSnapshot]):
    """Polls Unleashed for rogue AP state and detects newly-seen BSSIDs."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: AjaxSession,
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self.session = session
        # bssid → unix-timestamp of most recent observation. Bounded by TTL
        # eviction in `_dispatch_new_rogues`.
        self._seen_bssids: dict[str, int] = {}
        # True after the first non-empty seed. Distinguishes "HA just started"
        # (suppress alerts) from "everything timed out simultaneously"
        # (do alert — rogues genuinely went away and came back).
        self._warmed_up: bool = False
        self._new_rogue_listeners: list[Callable[[Rogue], None]] = []
        self._system: dict[str, Any] | None = None
        self._poll_count: int = 0

    @callback
    def async_add_new_rogue_listener(self, cb: Callable[[Rogue], None]) -> Callable[[], None]:
        """Register a callback fired every time a never-before-seen BSSID appears."""
        self._new_rogue_listeners.append(cb)

        @callback
        def _unsub() -> None:
            self._new_rogue_listeners.remove(cb)

        return _unsub

    async def _async_setup(self) -> None:
        """One-time setup: pull system info so devices can have a proper identity."""
        try:
            self._system = await self.session.api.get_system_info()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err

    async def _async_update_data(self) -> RuckusWipsSnapshot:
        api = self.session.api
        self._poll_count += 1
        refresh_system = (
            self._system is None
            or self._poll_count % SYSTEM_INFO_REFRESH_EVERY_N_POLLS == 0
        )
        try:
            active_raw = await api.get_active_rogues()
            blocked_raw = await api.get_blocked_rogues()
            if refresh_system:
                self._system = await api.get_system_info()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Network error talking to Unleashed: {err}") from err
        except (KeyError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Unexpected response from Unleashed: {err}") from err
        system = self._system or {}

        ignore_known = self.entry.options.get(CONF_IGNORE_KNOWN, DEFAULT_IGNORE_KNOWN)
        rssi_threshold = self.entry.options.get(CONF_RSSI_THRESHOLD, DEFAULT_RSSI_THRESHOLD)

        rogues: dict[str, Rogue] = {}
        for record in active_raw:
            rogue = Rogue.from_api(record)
            if not rogue.bssid:
                continue
            if rssi_threshold and rogue.rssi < rssi_threshold:
                continue
            if ignore_known and "known" in rogue.rogue_type.lower():
                continue
            rogues[rogue.bssid] = rogue

        # Blocked endpoint may surface rogues that the active scan missed; merge.
        for record in blocked_raw:
            rogue = Rogue.from_api(record)
            if not rogue.bssid:
                continue
            rogues.setdefault(rogue.bssid, rogue)

        active_unblocked = [r for r in rogues.values() if not r.blocked]
        blocked = [r for r in rogues.values() if r.blocked]

        snapshot = RuckusWipsSnapshot(
            rogues=rogues,
            active_unblocked=active_unblocked,
            blocked=blocked,
            system=system,
        )

        await self._dispatch_new_rogues(rogues)

        return snapshot

    async def _dispatch_new_rogues(self, rogues: dict[str, Rogue]) -> None:
        """Fire callbacks AND bus events for BSSIDs we haven't observed before.

        Maintains an age-bounded `_seen_bssids` map so memory stays flat over
        long uptimes — entries older than `SEEN_BSSID_TTL_SECONDS` are pruned
        each refresh. A BSSID that disappears and reappears beyond the TTL
        counts as "new" again and re-fires the event.
        """
        now = int(time.time())

        # Prune entries older than TTL so the map can't grow unbounded.
        cutoff = now - SEEN_BSSID_TTL_SECONDS
        if self._seen_bssids:
            stale = [b for b, ts in self._seen_bssids.items() if ts < cutoff]
            for b in stale:
                del self._seen_bssids[b]

        if not self._warmed_up:
            # The very first non-empty poll seeds the map without firing.
            # This suppresses the "you have N rogues!" deluge on HA restart.
            # A simultaneous mass-eviction does NOT re-enter this branch —
            # `_warmed_up` stays true for the lifetime of the coordinator.
            if rogues:
                for bssid in rogues:
                    self._seen_bssids[bssid] = now
                self._warmed_up = True
            return

        for bssid, rogue in rogues.items():
            previously_seen = bssid in self._seen_bssids
            self._seen_bssids[bssid] = now  # refresh timestamp every time
            if previously_seen:
                continue
            event_data = {
                "bssid": rogue.bssid,
                "ssid": rogue.ssid,
                "channel": rogue.channel,
                "radio_band": rogue.radio_band,
                "radio_type": rogue.radio_type,
                "encryption": rogue.encryption,
                "rogue_type": rogue.rogue_type,
                "rssi": rogue.rssi,
                "detection_ap": rogue.detection_ap_name,
                "detection_ap_location": rogue.detection_ap_location,
                "blocked": rogue.blocked,
                "last_seen": rogue.last_seen,
            }
            # HA bus event — visible in Developer Tools → Events, picked up by
            # the Logbook describer, and usable as `event:` automation trigger.
            self.hass.bus.async_fire(BUS_EVENT_NEW_ROGUE, event_data)
            for cb in list(self._new_rogue_listeners):
                cb(rogue)
