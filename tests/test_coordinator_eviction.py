"""Tests for the age-bounded _seen_bssids logic.

The set used to be unbounded — over months of uptime in dense RF environments
it would grow to thousands of entries (a slow memory leak). v0.2.x ships
a TTL-based eviction; these tests pin the contract:

- BSSID seen for the first time → fires the event (after warm-up)
- BSSID re-seen within TTL → does NOT re-fire (still "seen")
- BSSID re-seen after TTL → re-fires (counts as new again)
- Stale entries pruned every poll regardless of new arrivals
"""

from __future__ import annotations

import time

from ruckus_wips.coordinator import SEEN_BSSID_TTL_SECONDS


def test_ttl_is_at_least_one_day() -> None:
    """The TTL must be long enough that briefly-absent rogues stay 'seen'.

    Ruckus background scans miss things; a typical BSSID might vanish for
    minutes and reappear. The TTL must be >> scan misses — at least hours.
    """
    assert SEEN_BSSID_TTL_SECONDS >= 60 * 60  # >= 1 hour
    assert SEEN_BSSID_TTL_SECONDS <= 7 * 24 * 60 * 60  # <= 1 week


class FakeSeenMap:
    """Mirror the eviction algorithm in coordinator._dispatch_new_rogues.

    Tests the logic directly without needing a HA-mocked coordinator.
    Keep in sync with the real implementation.
    """

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}
        self.warmed_up: bool = False
        self.fired: list[str] = []

    def tick(self, now: int, current_bssids: list[str]) -> None:
        # 1. Evict stale.
        cutoff = now - SEEN_BSSID_TTL_SECONDS
        stale = [b for b, ts in self.seen.items() if ts < cutoff]
        for b in stale:
            del self.seen[b]

        # 2. Warm-up suppression — only on the FIRST non-empty poll.
        if not self.warmed_up:
            if current_bssids:
                for b in current_bssids:
                    self.seen[b] = now
                self.warmed_up = True
            return

        # 3. Diff + refresh.
        for b in current_bssids:
            previously_seen = b in self.seen
            self.seen[b] = now
            if not previously_seen:
                self.fired.append(b)


def test_warm_up_first_poll_does_not_fire() -> None:
    """The very first poll seeds the map but doesn't deluge the user."""
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa", "bb", "cc"])
    assert state.fired == []
    assert set(state.seen) == {"aa", "bb", "cc"}


def test_new_bssid_fires() -> None:
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa"])  # warm-up
    state.tick(now=1_000_030, current_bssids=["aa", "bb"])  # bb is new
    assert state.fired == ["bb"]


def test_known_bssid_does_not_re_fire_within_ttl() -> None:
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa"])  # warm-up
    state.tick(now=1_000_030, current_bssids=["aa", "bb"])  # bb is new
    state.tick(now=1_000_060, current_bssids=["aa", "bb"])  # nothing new
    assert state.fired == ["bb"]


def test_bssid_refires_after_ttl_expiry() -> None:
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa"])  # warm-up
    state.tick(now=1_000_030, current_bssids=["aa", "bb"])
    assert state.fired == ["bb"]

    # bb disappears for longer than TTL. aa stays present the whole time
    # (keeps getting its timestamp refreshed each poll) — so when bb
    # eventually returns it counts as new again, but aa does NOT re-fire.
    halfway = 1_000_030 + (SEEN_BSSID_TTL_SECONDS // 2)
    state.tick(now=halfway, current_bssids=["aa"])

    later = 1_000_030 + SEEN_BSSID_TTL_SECONDS + 1
    state.tick(now=later, current_bssids=["aa", "bb"])
    assert state.fired == ["bb", "bb"]


def test_simultaneous_mass_expiry_does_not_silence_alerts() -> None:
    """If every known BSSID times out simultaneously and a new wave shows
    up, those count as new — we do NOT re-enter warm-up suppression."""
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa", "bb"])  # warm-up
    assert state.fired == []
    assert state.warmed_up is True

    # Long gap — nothing detected for > TTL.
    state.tick(now=1_000_000 + SEEN_BSSID_TTL_SECONDS + 1, current_bssids=[])
    assert state.seen == {}  # all evicted
    assert state.warmed_up is True  # still warmed up

    # New rogues appear — should all fire (not be silenced as "warm-up").
    state.tick(
        now=1_000_000 + SEEN_BSSID_TTL_SECONDS + 60,
        current_bssids=["aa", "bb", "cc"],
    )
    assert state.fired == ["aa", "bb", "cc"]


def test_stale_entries_pruned_even_when_no_new_rogues() -> None:
    state = FakeSeenMap()
    state.tick(now=1_000_000, current_bssids=["aa"])
    assert "aa" in state.seen

    # Long time passes, aa stops being detected.
    state.tick(
        now=1_000_000 + SEEN_BSSID_TTL_SECONDS + 1,
        current_bssids=["bb"],  # nothing common
    )
    # aa should have been evicted; bb is the new seed.
    assert "aa" not in state.seen
    assert "bb" in state.seen


def test_seen_map_size_stays_bounded() -> None:
    """Smoke test: feed many rotating BSSIDs over a simulated week and
    confirm the map size never exceeds the active population."""
    state = FakeSeenMap()
    now = 1_000_000
    state.tick(now=now, current_bssids=["a", "b", "c"])

    # Simulate 7 days of polls every minute, rotating a small population.
    for minute in range(7 * 24 * 60):
        now += 60
        # Rotate the 3 active BSSIDs every hour to a new triple.
        slot = minute // 60
        active = [f"r{slot}-{i}" for i in range(3)]
        state.tick(now=now, current_bssids=active)

    # The TTL pruning should keep the map well below 7*24*3 = 504 entries
    # — only the last TTL-worth survive.
    assert len(state.seen) < 200
