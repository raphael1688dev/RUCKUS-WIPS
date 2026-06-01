"""Tests for ``Rogue.from_api`` and ``_pick_strongest_detection``.

These are the two places we shipped bugs in v0.1.x:
- ``detection`` may be a dict OR a list (regressed once → AttributeError)
- ``blocked`` is a string ``"true"``/``"false"`` (not a bool)
- ``rssi`` may be string or int

The fixture records mirror the *structure* of live Unleashed responses, but
the BSSIDs / SSIDs / AP names are intentionally fake placeholder values.
"""

from __future__ import annotations

import pytest

from ruckus_wips.coordinator import Rogue, _pick_strongest_detection


# ---- _pick_strongest_detection -----------------------------------------


def test_pick_strongest_returns_dict_unchanged() -> None:
    detection = {"ap": "aa:bb", "rssi": "20"}
    assert _pick_strongest_detection(detection) is detection


def test_pick_strongest_handles_list_by_max_rssi() -> None:
    detections = [
        {"ap": "ap1", "rssi": "10"},
        {"ap": "ap2", "rssi": "33"},
        {"ap": "ap3", "rssi": "21"},
    ]
    best = _pick_strongest_detection(detections)
    assert best["ap"] == "ap2"


def test_pick_strongest_handles_empty_list() -> None:
    assert _pick_strongest_detection([]) == {}


def test_pick_strongest_handles_none() -> None:
    assert _pick_strongest_detection(None) == {}


def test_pick_strongest_handles_missing_rssi() -> None:
    detections = [
        {"ap": "ap1"},  # no rssi → 0
        {"ap": "ap2", "rssi": "5"},
    ]
    assert _pick_strongest_detection(detections)["ap"] == "ap2"


def test_pick_strongest_handles_non_dict_items() -> None:
    detections = ["garbage", {"ap": "ap1", "rssi": "10"}]
    best = _pick_strongest_detection(detections)
    assert best["ap"] == "ap1"


# ---- Rogue.from_api ----------------------------------------------------


def _example_record_single_detection() -> dict:
    """Mirrors the shape of an Unleashed ``rogue`` AJAX record.

    Field values are placeholders — do NOT use real BSSIDs or AP info here.
    """
    return {
        "blocked": "true",
        "mac": "aa:bb:cc:dd:ee:ff",
        "id": "44",
        "ieee80211-radio-type": "g/n",
        "rogue-type": "malicious AP (User-blocked)",
        "radio-type": "802.11g/n",
        "radio-band": "2.4g",
        "channel": "1",
        "ssid": "Example-SSID",
        "is-open": "Encrypted",
        "last-seen": "1776144464",
        "detection": {
            "ap": "02:11:22:33:44:55",
            "sys-name": "AP-North",
            "location": "North Zone",
            "rssi": "33",
            "last-seen": "1776144464",
        },
    }


def _example_record_multi_detection() -> dict:
    record = _example_record_single_detection()
    record["detection"] = [
        {"ap": "ap1", "sys-name": "AP-North", "location": "North Zone", "rssi": "10"},
        {"ap": "ap2", "sys-name": "AP-South", "location": "South Zone", "rssi": "44"},
    ]
    return record


def test_rogue_parses_example_record() -> None:
    rogue = Rogue.from_api(_example_record_single_detection())
    assert rogue.bssid == "aa:bb:cc:dd:ee:ff"
    assert rogue.ssid == "Example-SSID"
    assert rogue.channel == "1"
    assert rogue.radio_band == "2.4g"
    assert rogue.encryption == "Encrypted"
    assert rogue.blocked is True
    assert rogue.last_seen == 1776144464
    assert rogue.detection_ap_mac == "02:11:22:33:44:55"
    assert rogue.detection_ap_name == "AP-North"
    assert rogue.detection_ap_location == "North Zone"
    assert rogue.rssi == 33


def test_rogue_parses_list_detection_pick_strongest() -> None:
    rogue = Rogue.from_api(_example_record_multi_detection())
    assert rogue.rssi == 44
    assert rogue.detection_ap_name == "AP-South"


def test_rogue_blocked_false_when_attribute_absent() -> None:
    record = _example_record_single_detection()
    del record["blocked"]
    rogue = Rogue.from_api(record)
    assert rogue.blocked is False


@pytest.mark.parametrize("blocked_str,expected", [
    ("true", True),
    ("True", True),
    ("TRUE", True),
    ("false", False),
    ("False", False),
    ("", False),
    ("anything-else", False),
])
def test_rogue_blocked_is_case_insensitive_truthy_check(blocked_str: str, expected: bool) -> None:
    record = _example_record_single_detection()
    record["blocked"] = blocked_str
    assert Rogue.from_api(record).blocked is expected


def test_rogue_bssid_lowercased() -> None:
    record = _example_record_single_detection()
    record["mac"] = "AA:BB:CC:DD:EE:FF"
    assert Rogue.from_api(record).bssid == "aa:bb:cc:dd:ee:ff"


def test_rogue_missing_optional_fields_safe() -> None:
    """Sparse record (only mac) should not crash."""
    rogue = Rogue.from_api({"mac": "11:22:33:44:55:66"})
    assert rogue.bssid == "11:22:33:44:55:66"
    assert rogue.ssid == ""
    assert rogue.rssi == 0
    assert rogue.last_seen == 0


def test_rogue_falls_back_to_ieee80211_radio_type() -> None:
    record = {
        "mac": "11:22:33:44:55:66",
        "ieee80211-radio-type": "g/n",
        # no radio-type
    }
    assert Rogue.from_api(record).radio_type == "g/n"
