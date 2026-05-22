"""Constants for the RUCKUS WIPS integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ruckus_wips"

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_RSSI_THRESHOLD: Final = "rssi_threshold"
CONF_ENABLE_UNBLOCK: Final = "enable_unblock"
CONF_IGNORE_KNOWN: Final = "ignore_known"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 300

DEFAULT_RSSI_THRESHOLD: Final = 0
DEFAULT_ENABLE_UNBLOCK: Final = False
DEFAULT_IGNORE_KNOWN: Final = True

EVENT_NEW_ROGUE: Final = "new_rogue"
EVENT_ROGUE_BLOCKED: Final = "rogue_blocked"

SERVICE_MARK_MALICIOUS: Final = "mark_malicious"
SERVICE_UNMARK_MALICIOUS: Final = "unmark_malicious"

ATTR_BSSID: Final = "bssid"
