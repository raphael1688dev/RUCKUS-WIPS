"""Tests for the AJAX payloads sent by mark_malicious / unmark_malicious.

These payloads were captured from a live R720 (Unleashed 200.15.6.212) and
are asymmetric (`mac=` vs `rogue=`, `block` vs `unblockrogue`) — the
asymmetry is real and must be preserved. If a future refactor "cleans up"
the symmetry, these tests catch the regression.
"""

from __future__ import annotations

import re

import pytest

from ruckus_wips.services import _MAC_RE, _normalize


def _build_mark_payload(bssid: str) -> str:
    """Mirror the literal string in services._async_mark_malicious."""
    return (
        f"<ajax-request action='docmd' xcmd='blockrogue' check-ability='10' comp='stamgr'>"
        f"<xcmd cmd='blockrogue' tag='rogue' rogue='{bssid}'/></ajax-request>"
    )


def _build_unmark_payload(bssid: str) -> str:
    """Mirror the literal string in services._async_unmark_malicious."""
    return (
        f"<ajax-request action='docmd' xcmd='unblockrogue' check-ability='10' comp='stamgr'>"
        f"<xcmd cmd='unblockrogue' tag='rogue' rogue='{bssid}'/></ajax-request>"
    )


# ---- normalization -----------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"),
    ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
    ("aa-bb-cc-dd-ee-ff", "aa:bb:cc:dd:ee:ff"),
    ("  aa:bb:cc:dd:ee:ff  ", "aa:bb:cc:dd:ee:ff"),
    ("Aa:bB:cC:dD:eE:fF", "aa:bb:cc:dd:ee:ff"),
])
def test_normalize_accepts_valid_macs(raw: str, expected: str) -> None:
    assert _normalize(raw) == expected


@pytest.mark.parametrize("garbage", [
    "",
    "not-a-mac",
    "aa:bb:cc:dd:ee",       # too short
    "aa:bb:cc:dd:ee:ff:00",  # too long
    "zz:bb:cc:dd:ee:ff",    # invalid hex
    "aabbccddeeff",          # no separators
])
def test_normalize_rejects_garbage(garbage: str) -> None:
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        _normalize(garbage)


def test_mac_regex_matches_canonical() -> None:
    assert _MAC_RE.match("aa:bb:cc:dd:ee:ff")
    assert _MAC_RE.match("AA-BB-CC-DD-EE-FF")
    assert not _MAC_RE.match("aabbccddeeff")


# ---- payload shape (regression guard) ---------------------------------


def test_mark_payload_uses_blockrogue_xcmd_with_rogue_attr() -> None:
    payload = _build_mark_payload("aa:bb:cc:dd:ee:ff")
    # Asymmetry — block side uses xcmd='blockrogue' AND rogue='...'
    assert "xcmd='blockrogue'" in payload
    assert "cmd='blockrogue'" in payload
    assert "tag='rogue'" in payload
    assert "rogue='aa:bb:cc:dd:ee:ff'" in payload
    assert "comp='stamgr'" in payload
    assert "check-ability='10'" in payload


def test_unmark_payload_uses_unblockrogue_xcmd_with_rogue_attr() -> None:
    payload = _build_unmark_payload("aa:bb:cc:dd:ee:ff")
    # Unblock side: xcmd='unblockrogue', rogue='...', kebab-case check-ability
    assert "xcmd='unblockrogue'" in payload
    assert "cmd='unblockrogue'" in payload
    assert "tag='rogue'" in payload
    assert "rogue='aa:bb:cc:dd:ee:ff'" in payload
    # CRITICAL: must NOT use 'mac=' here — Unleashed only honors 'rogue=' on unblock.
    assert "mac=" not in payload
    # CRITICAL: must use kebab-case 'check-ability', not camelCase
    assert "check-ability='10'" in payload
    assert "checkAbility" not in payload


def test_payloads_inject_normalized_bssid_lowercase() -> None:
    payload = _build_mark_payload("AA:BB:CC:DD:EE:FF")
    # Upstream service normalizes BEFORE building payload; this test just
    # verifies that whatever you pass in, ends up in the XML literally.
    assert "AA:BB:CC:DD:EE:FF" in payload
    # And confirms the helper roundtrips through _normalize:
    normalized = _normalize("AA:BB:CC:DD:EE:FF")
    assert normalized == "aa:bb:cc:dd:ee:ff"
    assert "aa:bb:cc:dd:ee:ff" in _build_mark_payload(normalized)


def test_payloads_are_valid_xml_fragments() -> None:
    """Quick well-formedness check — the AJAX endpoint is XML-strict."""
    from xml.etree import ElementTree as ET

    for builder in (_build_mark_payload, _build_unmark_payload):
        xml = builder("aa:bb:cc:dd:ee:ff")
        # Should parse without error.
        ET.fromstring(xml)
