#!/usr/bin/env python3
"""Verify translations/en.json mirrors strings.json structure.

strings.json is the source of truth. translations/en.json must have the
SAME nested key paths (values may differ to allow English wording polish).
This catches drift when a developer adds a string in only one place.

Usage:
    python3 scripts/check_translations.py
    exit code 0 = consistent, 1 = drift detected
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIR = ROOT / "custom_components" / "ruckus_wips"
STRINGS = DOMAIN_DIR / "strings.json"
EN = DOMAIN_DIR / "translations" / "en.json"


def key_paths(obj: object, prefix: str = "") -> set[str]:
    """Return the set of dotted key paths reachable from a nested dict."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.update(key_paths(v, path))
            else:
                out.add(path)
    return out


def main() -> int:
    strings = json.loads(STRINGS.read_text())
    en = json.loads(EN.read_text())

    strings_paths = key_paths(strings)
    en_paths = key_paths(en)

    missing_in_en = strings_paths - en_paths
    extra_in_en = en_paths - strings_paths

    if not missing_in_en and not extra_in_en:
        print("OK — strings.json and translations/en.json have identical key paths.")
        return 0

    if missing_in_en:
        print("Keys in strings.json missing from translations/en.json:")
        for p in sorted(missing_in_en):
            print(f"  + {p}")
    if extra_in_en:
        print("Keys in translations/en.json not present in strings.json:")
        for p in sorted(extra_in_en):
            print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
