# RUCKUS WIPS for Home Assistant

A HACS-installable Home Assistant integration that surfaces **RUCKUS Unleashed**
rogue AP detection (WIPS) in Home Assistant and lets you mark rogues as
malicious from automations.

Tested with R720 on Unleashed `200.15.6.212`. Requires Home Assistant
`2026.5.0` or newer.

> The official Home Assistant **Ruckus** integration only provides presence
> detection (`device_tracker`). This integration adds the WIPS surface that the
> official one does not cover.

## What you get

- **`sensor.<network>_active_rogues`** — count of currently-visible rogue APs
  that have not been marked malicious. Attributes include the full list with
  BSSID, SSID, channel, RSSI, encryption, detecting AP and room/location.
- **`sensor.<network>_blocked_rogues`** — count of rogues currently being
  deauthed.
- **`sensor.<network>_total_rogues`** — sum of the above.
- **`event.<network>_new_rogue_detected`** — fires `new_rogue` the first time
  a BSSID is seen. Full metadata (SSID, channel, RSSI, detecting AP, location,
  encryption, rogue_type, last_seen) is exposed as state attributes.
  Survive-on-restart logic suppresses alerts for previously-known BSSIDs.
- **Bus event `ruckus_wips_new_rogue`** — fired on Home Assistant's event bus
  with the same payload, alongside the EventEntity trigger. Use this when you
  prefer the `platform: event` automation trigger, or to subscribe from
  custom integrations. Logbook renders these with a human-readable line
  (e.g. *"new rogue AP — realme C51 (5e:a6:…) · ch157 · rssi 8 · detected by
  R720-2F (MASTER ROOM)"*).
- **Service `ruckus_wips.mark_malicious`** — `bssid: aa:bb:cc:dd:ee:ff`
  triggers Unleashed to broadcast deauth, blocking clients from associating to
  that rogue.
- **Service `ruckus_wips.unmark_malicious`** — undoes the above. Hidden by
  default; enable in the integration's *Configure* menu under
  **Expose unmark_malicious service (advanced)**.

## Brand assets

Logo and icon are bundled inside the integration (HA 2026.3+ supports local
brand assets via `custom_components/<domain>/brand/`). No brands-repo PR is
required for the icon to appear in the Settings → Devices & Services UI.

A second copy of the same assets is staged at
[`brands/custom_integrations/ruckus_wips/`](brands/custom_integrations/ruckus_wips/)
for an optional future PR to `home-assistant/brands` — useful only for HACS
browse-page thumbnails before users install.

## Install via HACS

1. HACS → ⋯ menu → **Custom repositories**
2. Add `https://github.com/raphael1688dev/RUCKUS-HACS` as type **Integration**
3. Install **RUCKUS WIPS**, restart Home Assistant
4. Settings → Devices & services → **Add integration** → "RUCKUS WIPS"
5. Enter the Unleashed master IP or hostname and an admin credential

## Options

| Option | Default | Range | Notes |
| ------ | ------- | ----- | ----- |
| Poll interval | 30 s | 15–300 s | Below 30 s gives no extra freshness (Ruckus background scan is ~30 s). |
| RSSI threshold | 0 | 0–80 | Filter out very weak detections. Ruckus reports RSSI as a small positive number; higher = stronger. |
| Hide Known | true | bool | Drop entries whose Ruckus classification contains *Known* (your whitelisted neighbors). |
| Enable unblock | false | bool | Registers `unmark_malicious`. Off to prevent accidental un-blocking. |

## Dashboard recipe — list current rogues with a one-click block button

The integration intentionally exposes one hub device plus services (not one
entity per rogue). To get a per-row block button in the dashboard, pair a
markdown card with an `input_text` helper and a thin script that bridges
the input value into `ruckus_wips.mark_malicious`.

### 1. Create the `input_text` helper

Settings → Devices & services → **Helpers** → **Create helper** → **Text**:

| Field | Value |
| ----- | ----- |
| Name | `Ruckus Block BSSID` |
| (advanced) ID | `ruckus_block_bssid` |
| Min length | `17` |
| Max length | `17` |

(Don't set a regex Pattern on the helper itself — the script below validates
inputs more robustly and a Pattern that rejects empty values leaves the
helper stuck on `unknown`.)

Result: `input_text.ruckus_block_bssid`.

### 2. Create the bridge script

Settings → Automations & scenes → **Scripts tab** (it's a top tab inside the
page, not a sub-menu) → **Add Script** → **Start with an empty script** →
⋮ → **Edit in YAML**, then paste:

```yaml
alias: Ruckus Block Typed BSSID
description: Read input_text.ruckus_block_bssid and call ruckus_wips.mark_malicious
mode: single
sequence:
  - variables:
      bssid: "{{ states('input_text.ruckus_block_bssid') | lower | trim }}"
  - condition: template
    value_template: "{{ bssid | regex_match('^([0-9a-f]{2}:){5}[0-9a-f]{2}$') }}"
  - action: ruckus_wips.mark_malicious
    data:
      bssid: "{{ bssid }}"
  - action: input_text.set_value
    target:
      entity_id: input_text.ruckus_block_bssid
    data:
      value: ""
```

⚠️ **Keep the `alias:` in ASCII English.** HA derives the script's service
name (used by dashboard `tap_action`) from the alias at creation time by
stripping non-ASCII characters. Once registered, the service name is
sticky — renaming the entity_id afterwards (even with a full HA restart)
will NOT update the service name. With this ASCII alias both the entity_id
and the service become `script.ruckus_block_typed_bssid`.

After saving you can change the **Name** to whatever you want (e.g.
`Ruckus 封鎖貼上的 BSSID`) — the Name is display-only and doesn't affect
the underlying entity_id or service.

### 3. Add the dashboard card

In Lovelace edit mode → **Add card → Manual** → paste:

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      ## 目前未封鎖的 Rogue AP
      {% set rogues = state_attr('sensor.ruckus_unleashed_active_rogues', 'rogues') or [] %}
      {% if rogues %}
      {% for r in rogues %}
      - **{{ r.ssid or '(隱藏 SSID)' }}** `{{ r.bssid }}`
        — ch{{ r.channel }} / rssi {{ r.rssi }} / 偵測者 {{ r.detection_ap }} ({{ r.detection_ap_location }})
      {% endfor %}
      {% else %}
      ✓ 目前沒有未處理的 rogue AP
      {% endif %}

  - type: entities
    title: 執行封鎖
    show_header_toggle: false
    entities:
      - entity: input_text.ruckus_block_bssid
        name: 貼上 BSSID
        icon: mdi:identifier
      - type: button
        name: 對上方 BSSID 執行封鎖
        icon: mdi:wifi-cancel
        action_name: 封鎖
        tap_action:
          action: perform-action
          perform_action: script.ruckus_block_typed_bssid
```

Replace `sensor.ruckus_unleashed_active_rogues` if your hub device name
differs (check **Developer Tools → States** and search `sensor.ruckus`).

**Usage:** copy a BSSID from the top markdown list → paste into the input
field → press **封鎖**. The script validates the format, calls the service,
and clears the input. ~30 seconds later (next coordinator poll) the rogue
moves to the blocked list and disappears from the top card.

### Optional — also show blocked list with an unblock button

First, enable the advanced option: Settings → Devices & services → RUCKUS
WIPS → **Configure** → tick **Expose unmark_malicious service (advanced)**.

Then create a second helper (`input_text.ruckus_unblock_bssid`) and a
second script (alias `Ruckus Unblock Typed BSSID`, same body but calling
`ruckus_wips.unmark_malicious`). Mirror the dashboard pattern with that
service. Same ASCII-alias rule applies.

## Seeing what was detected

Three places show the full rogue details:

- **Developer Tools → States** → search the event entity → right panel shows
  all attributes (`bssid`, `ssid`, `channel`, `rssi`, `detection_ap`,
  `detection_ap_location`, etc.) for the most recent rogue.
- **Logbook** → entries are formatted by `logbook.py` so each new rogue
  shows up as a readable line, not just "new_rogue".
- **Developer Tools → Events** → subscribe to `ruckus_wips_new_rogue` to
  watch payloads live as they fire.

## Automation example

Notify when an open-encryption rogue appears in the living room area:

### Via the EventEntity (state-platform trigger)

```yaml
- alias: "Alert: open rogue near living room"
  triggers:
    - platform: state
      entity_id: event.ruckus_unleashed_new_rogue_detected
  conditions:
    - "{{ trigger.to_state.attributes.encryption | lower == 'open' }}"
    - "{{ 'LIVING' in (trigger.to_state.attributes.detection_ap_location or '') | upper }}"
  actions:
    - action: notify.mobile_app_phone
      data:
        title: "New open rogue near living room"
        message: >
          {{ trigger.to_state.attributes.ssid }}
          ({{ trigger.to_state.attributes.bssid }})
          ch {{ trigger.to_state.attributes.channel }}
          rssi {{ trigger.to_state.attributes.rssi }}
```

### Via the bus event (event-platform trigger — simpler payload access)

```yaml
- alias: "Auto-block any open rogue"
  triggers:
    - platform: event
      event_type: ruckus_wips_new_rogue
  conditions:
    - "{{ trigger.event.data.encryption | lower == 'open' }}"
  actions:
    - action: ruckus_wips.mark_malicious
      data:
        bssid: "{{ trigger.event.data.bssid }}"
```

## Caveats

- "Real-time" is bounded by Ruckus's own background scan cadence (~30 s) plus
  the poll interval. Worst case ≈ poll interval + 30 s.
- Unleashed allows one admin web session by default. This integration consumes
  one. If you cannot log in to the Unleashed UI while it is running, enable
  multi-session in Unleashed → Admin & Services → System → System Info.
- aioruckus is **unofficial** (reverse-engineered AJAX). It works reliably on
  modern Unleashed (verified on `200.15.6.212`) but Ruckus could change
  endpoints without notice.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install "aioruckus>=0.42"

# Verify connectivity against your own controller
.venv/bin/python probe.py <host> <user> <pass>
```

## License

MIT.
