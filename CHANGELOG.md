# Changelog

All notable changes to this project are documented in this file.

This project uses [Calendar Versioning](https://calver.org/) — `YYYYMMDDr<N>`.
Same-day releases increment `r`; new-day resets to `r0`.

## [20260601r1] - 2026-06-01

Big tech-debt paydown pass. All P0 + P1 + most P2 items from
[docs/TECH_DEBT.md](docs/TECH_DEBT.md) closed in this release.

### Added
- 44-test pytest baseline covering: `Rogue.from_api` dict/list shapes,
  blocked-flag parsing, BSSID normalization, mark/unmark XML payload
  structure (incl. the `rogue=` vs `mac=` asymmetry guard), TTL eviction
  semantics, simultaneous mass-expiry handling, and translation drift.
- Translation drift CI check (`scripts/check_translations.py`) + a wrapping
  pytest test so local runs catch it too.
- `ruff` lint + format and `mypy` advisory pass in CI; matching
  `pyproject.toml` + `.pre-commit-config.yaml`.
- 4 automation Blueprints under `blueprints/automation/ruckus_wips/`:
  notify-on-new-rogue, autoblock-open-rogue, mobile-actionable-push
  (sender + handler pair).
- HACS install-dialog `info.md`.
- README **Troubleshooting** section.
- `CHANGELOG.md` (this file).

### Changed
- Services now expose a `target:` device selector — HA's standard device
  picker resolves the controller hub, in addition to the existing
  `entry_id` field.
- `_seen_bssids` is age-bounded (24 h TTL) — set bounded over months of
  uptime, and a long-absent BSSID re-fires the new-rogue event on return.
- A `_warmed_up` flag distinguishes "HA just started" (suppress alert
  deluge) from "all rogues timed out simultaneously" (do alert) — the
  latter would previously have been silenced incorrectly.
- `_system` (firmware version, model, serial) is re-fetched every 20th
  poll so firmware upgrades surface in HA without a restart.
- Service handlers always refresh the coordinator after the AJAX call —
  even when Unleashed rejects — so local snapshot stays aligned.
- Narrowed broad `except Exception` blocks to specific transport /
  aioruckus errors across `__init__.py`, `coordinator.py`,
  `config_flow.py`, `services.py`. Unexpected errors are now logged with
  full traceback instead of being silently swallowed.
- `sensor.<network>_total_rogues` now exposes a `rogues` attribute with
  the union list (was bare; inconsistent with active/blocked sensors).

### Fixed
- `aioruckus` upper bound pinned to `<1.0` so a future major version can't
  silently break the integration.

## [20260601r0] - 2026-06-01

### Added
- Switched to CalVer versioning (`YYYYMMDDr<N>`). Tags + GitHub Releases
  mirror this string exactly. All releases default to pre-release.
- GitHub remote moved to `https://github.com/raphael1688dev/RUCKUS-WIPS`.

### Changed
- `manifest.json` `codeowners` updated to `@raphael1688dev`.
- Documentation / issue-tracker URLs updated to the WIPS repo.

## [0.2.1] - 2026-05-22

### Fixed
- Removed `EventDeviceClass.DOORBELL` from the new-rogue event entity.
  HA 2026.5 added enforcement that DOORBELL must fire a `ring` event_type;
  ours fires `new_rogue`, so the mismatch produced a deprecation warning
  promising removal in 2027.4. None of HA's built-in event device classes
  fit "rogue AP detected" semantically — `device_class` is now unset.

## [0.2.0] - 2026-05-22

### Added
- Logbook describer (`logbook.py`) renders bus events as readable
  sentences instead of bare event-type strings.
- Bus event `ruckus_wips_new_rogue` fires alongside the EventEntity
  trigger — usable as `platform: event` automation trigger and visible in
  Developer Tools → Events.
- Local brand assets in `custom_components/ruckus_wips/brand/`. HA 2026.3+
  serves them via `/api/brands/integration/ruckus_wips/...` — no
  brands-repo PR required for the icon to appear in the Devices & Services
  UI.

### Fixed
- Service handlers no longer wrap an async function in a sync lambda when
  registering. HA's executor was not awaiting the wrapped coroutine; the
  websocket response handler then failed JSON-encoding the un-awaited
  coroutine.

## [0.1.0] - 2026-05-22

### Added
- Initial release.
- `sensor.<network>_active_rogues`, `_blocked_rogues`, `_total_rogues`
  count entities with full per-rogue attribute lists.
- `event.<network>_new_rogue_detected` EventEntity firing on each newly
  observed BSSID.
- Services `ruckus_wips.mark_malicious` and `ruckus_wips.unmark_malicious`
  (the latter gated behind an advanced opt-in option).
- Config flow + reauth + options flow (poll interval, RSSI threshold,
  ignore-Known toggle, enable-unblock toggle).
- en + zh-Hant translations.
- GitHub Actions running `hassfest` and `HACS validate`.

### Fixed
- `detection` field handled when Unleashed returns a list (multiple APs
  saw the rogue) — previously crashed on `.get()`. The strongest-RSSI
  detection is surfaced as the primary one.
