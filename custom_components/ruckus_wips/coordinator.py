"""DataUpdateCoordinator for RUCKUS WIPS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from aioruckus import AjaxSession
from aioruckus.exceptions import AuthenticationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
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
        self._seen_bssids: set[str] = set()
        self._new_rogue_listeners: list[Callable[[Rogue], None]] = []

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
        try:
            api = self.session.api
            active_raw = await api.get_active_rogues()
            blocked_raw = await api.get_blocked_rogues()
            system = getattr(self, "_system", None) or await api.get_system_info()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            raise UpdateFailed(f"Failed to query Unleashed: {err}") from err

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
        """Fire callbacks for BSSIDs we haven't observed before in this session."""
        if not self._seen_bssids:
            # First poll: seed without firing — avoid burying the user in alerts on restart.
            self._seen_bssids.update(rogues)
            return

        for bssid, rogue in rogues.items():
            if bssid in self._seen_bssids:
                continue
            self._seen_bssids.add(bssid)
            for cb in list(self._new_rogue_listeners):
                cb(rogue)
