# RUCKUS WIPS

Surfaces **RUCKUS Unleashed** rogue AP detection (WIPS) in Home Assistant
and lets you mark rogues as malicious from automations.

Tested with R720 on Unleashed `200.15.6.212`. Requires Home Assistant
`2026.5.0` or newer.

## What you get

- 3 sensors — active rogues, blocked rogues, total rogues — each with the
  full rogue list as state attributes.
- An event entity + matching `ruckus_wips_new_rogue` bus event fired the
  first time a new BSSID is detected.
- `mark_malicious(bssid)` service that triggers Ruckus's deauth broadcast.
- Optional `unmark_malicious(bssid)` (advanced opt-in).
- Rich Logbook entries via a built-in describer.
- Local logo — no brands-repo PR needed.

## Install

1. Click **Download** above.
2. Restart Home Assistant.
3. Settings → Devices & services → **Add integration** → "RUCKUS WIPS".
4. Enter the Unleashed master IP/hostname plus an admin credential.

See the project's [README](https://github.com/raphael1688dev/RUCKUS-WIPS)
for dashboard recipes, automation Blueprints, and the full caveat list.
