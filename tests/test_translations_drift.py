"""Pytest wrapper around scripts/check_translations.py.

Keeps the drift check in the regular pytest suite so it runs locally too,
not only in CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strings_and_translations_en_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_translations.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Translation drift detected:\n{result.stdout}{result.stderr}"
    )
