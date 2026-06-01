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
  (e.g. *"new rogue AP — Example-SSID (aa:bb:…) · ch157 · rssi 8 · detected by
  AP-South (South Zone)"*).
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
2. Add `https://github.com/raphael1688dev/RUCKUS-WIPS` as type **Integration**
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

After saving you can change the **Name** to anything you want — including
non-ASCII text in your own locale (the Name is display-only and doesn't
affect the underlying entity_id or service).

### 3. Add the dashboard card

In Lovelace edit mode → **Add card → Manual** → paste:

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      ## Active rogue APs
      {% set rogues = state_attr('sensor.ruckus_unleashed_active_rogues', 'rogues') or [] %}
      {% if rogues %}
      {% for r in rogues %}
      - **{{ r.ssid or '(hidden SSID)' }}** `{{ r.bssid }}`
        — ch{{ r.channel }} / rssi {{ r.rssi }} / seen by {{ r.detection_ap }} ({{ r.detection_ap_location }})
      {% endfor %}
      {% else %}
      ✓ No untreated rogue APs
      {% endif %}

  - type: entities
    title: Block action
    show_header_toggle: false
    entities:
      - entity: input_text.ruckus_block_bssid
        name: Paste BSSID
        icon: mdi:identifier
      - type: button
        name: Block the BSSID above
        icon: mdi:wifi-cancel
        action_name: Block
        tap_action:
          action: perform-action
          perform_action: script.ruckus_block_typed_bssid
```

Replace `sensor.ruckus_unleashed_active_rogues` if your hub device name
differs (check **Developer Tools → States** and search `sensor.ruckus`).

**Usage:** copy a BSSID from the top markdown list → paste into the input
field → press **Block**. The script validates the format, calls the
service, and clears the input. ~30 seconds later (next coordinator poll)
the rogue moves to the blocked list and disappears from the top card.

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

## Automation examples

Two trigger styles are available — pick whichever feels natural:
- **EventEntity state trigger:** `platform: state` on
  `event.<network>_new_rogue_detected`. Use `trigger.to_state.attributes.*`
  to read the rogue fields.
- **Bus event trigger:** `platform: event` on `ruckus_wips_new_rogue`. Use
  `trigger.event.data.*` to read the rogue fields. Slightly cleaner syntax
  and what the examples below use.

### Notify the HA bell (built-in, zero external setup)

```yaml
alias: Ruckus Notify New Rogue
description: Show a HA bell notification when a new rogue AP is detected
mode: queued
max: 10
triggers:
  - platform: event
    event_type: ruckus_wips_new_rogue
actions:
  - action: persistent_notification.create
    data:
      title: >
        ⚠️ New rogue AP detected
        {%- if trigger.event.data.encryption | lower == 'open' %} (open!){% endif %}
      message: |
        **{{ trigger.event.data.ssid or '(hidden SSID)' }}**
        BSSID: `{{ trigger.event.data.bssid }}`
        Ch{{ trigger.event.data.channel }} ({{ trigger.event.data.radio_band }}) / RSSI {{ trigger.event.data.rssi }}
        Encryption: {{ trigger.event.data.encryption }}
        Seen by: {{ trigger.event.data.detection_ap }} ({{ trigger.event.data.detection_ap_location }})
        Type: {{ trigger.event.data.rogue_type }}
      notification_id: "ruckus_rogue_{{ trigger.event.data.bssid }}"
```

The `notification_id` includes the BSSID — so if the same rogue is re-detected
on the next poll the notification is *replaced* rather than stacked. With
`mode: queued` + `max: 10`, several distinct rogues appearing within a few
seconds are queued instead of dropped.

### Push to mobile via Home Assistant Companion

```yaml
alias: Ruckus Push New Rogue
mode: queued
max: 10
triggers:
  - platform: event
    event_type: ruckus_wips_new_rogue
actions:
  - action: notify.mobile_app_my_phone   # ← change to your notify service
    data:
      title: >
        ⚠️ New Rogue AP
        {%- if trigger.event.data.encryption | lower == 'open' %} (open){% endif %}
      message: >
        {{ trigger.event.data.ssid or '(hidden)' }} {{ trigger.event.data.bssid }}
        @ {{ trigger.event.data.detection_ap_location }} (rssi {{ trigger.event.data.rssi }})
      data:
        tag: "ruckus_rogue_{{ trigger.event.data.bssid }}"
        group: "ruckus_wips"
        actions:
          - action: "URI"
            title: "Open HA Dashboard"
            uri: "/lovelace/ruckus"
```

### Push to mobile with a one-tap "Block" action

Home Assistant Companion (iOS / Android) supports inline action buttons on
push notifications. This pair of automations lets you block a rogue
straight from the notification — no app open, no copy/paste.

**A. Sender** — fires when a new rogue appears, sends a push with two
buttons (Block / Ignore). The BSSID is encoded into the notification's
`tag` so the handler can recover it later.

```yaml
alias: Ruckus Push w/ Actions
mode: queued
max: 10
triggers:
  - platform: event
    event_type: ruckus_wips_new_rogue
actions:
  - action: notify.mobile_app_my_phone   # ← change to your service
    data:
      title: >
        ⚠️ New Rogue AP
        {%- if trigger.event.data.encryption | lower == 'open' %} (open){% endif %}
      message: >
        {{ trigger.event.data.ssid or '(hidden)' }} {{ trigger.event.data.bssid }}
        @ {{ trigger.event.data.detection_ap_location }} (rssi {{ trigger.event.data.rssi }})
      data:
        tag: "ruckus_rogue_{{ trigger.event.data.bssid }}"
        group: "ruckus_wips"
        actions:
          - action: "RUCKUS_BLOCK"
            title: "Block this BSSID"
            destructive: true
            icon: "sfsymbols:wifi.slash"
          - action: "RUCKUS_IGNORE"
            title: "Ignore"
```

**B. Handler** — fires when the user taps **Block** on the push. It parses
the BSSID out of the notification tag, validates the format, and calls
`ruckus_wips.mark_malicious`. A confirmation push is sent back.

```yaml
alias: Ruckus Handle Push Block Action
mode: parallel
triggers:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: RUCKUS_BLOCK
actions:
  - variables:
      bssid: "{{ trigger.event.data.tag | replace('ruckus_rogue_', '') }}"
  - condition: template
    value_template: "{{ bssid | regex_match('^([0-9a-f]{2}:){5}[0-9a-f]{2}$') }}"
  - action: ruckus_wips.mark_malicious
    data:
      bssid: "{{ bssid }}"
  - action: notify.mobile_app_my_phone   # ← same as Sender
    data:
      message: "✓ Blocked {{ bssid }}"
      data:
        tag: "ruckus_blocked_{{ bssid }}"
```

Why encode the BSSID in `tag` and not in the `action` ID directly?
`mobile_app_notification_action` events don't carry the original
notification's full `data` block — they only carry the action ID and the
tag. Using a generic action ID (`RUCKUS_BLOCK`) + per-item tag keeps
action IDs portable across iOS/Android (which differ in how they tolerate
non-ASCII characters in action IDs).

**First-deploy gotcha:** the Companion app registers an automation's
action set lazily. The very first push may show no buttons. Trigger the
sender once (or use Developer Tools → Events to fake-fire
`ruckus_wips_new_rogue`), then subsequent pushes will have the buttons.

### Filter: only alert on open-encryption or only certain APs

Add `conditions:` to either example above:

```yaml
conditions:
  - "{{ trigger.event.data.encryption | lower == 'open' }}"
  # OR limit to a specific detecting AP location
  - "{{ 'LIVING' in (trigger.event.data.detection_ap_location or '') | upper }}"
```

### Auto-block any open rogue (no human in loop)

⚠️ This issues deauth broadcasts immediately. Be sure none of your own
networks would be flagged as "open" before turning this on.

```yaml
alias: Ruckus Auto-Block Open Rogue
mode: queued
triggers:
  - platform: event
    event_type: ruckus_wips_new_rogue
conditions:
  - "{{ trigger.event.data.encryption | lower == 'open' }}"
actions:
  - action: ruckus_wips.mark_malicious
    data:
      bssid: "{{ trigger.event.data.bssid }}"
  - action: persistent_notification.create
    data:
      title: 🛡️ Auto-blocked open rogue
      message: >
        {{ trigger.event.data.ssid or '(hidden)' }} `{{ trigger.event.data.bssid }}`
        was detected and immediately marked malicious.
      notification_id: "ruckus_auto_block_{{ trigger.event.data.bssid }}"
```

## Troubleshooting

### "icon not available" on the integration card

HA 2026.3+ serves the bundled logo from
`custom_components/ruckus_wips/brand/`. If it doesn't appear:
1. Restart Home Assistant (the brand proxy reads the folder at startup).
2. Hard-refresh the browser (Cmd/Ctrl+Shift+R) — frontend caches the
   "icon not available" placeholder aggressively.
3. Verify all 8 PNGs exist in the `brand/` folder.

### Dashboard "Block" button errors with `Action script.<name> not found`

HA's UI-created scripts have two parallel identifiers — an *entity_id* (the
display name) and a *service name* (what `tap_action: perform_action` calls).
At creation time HA strips non-ASCII characters from the alias when deriving
both. **Renaming the entity_id afterwards does NOT update the service name**
— not even a HA restart or Reload Scripts moves it.

Fix: delete the script and recreate it with an **ASCII English alias** that
matches the desired service name (e.g. `Ruckus Block Typed BSSID` →
`script.ruckus_block_typed_bssid`). After saving, rename the **Name** to
whatever locale you want via the script's Settings; the Name doesn't affect
entity_id or service name.

### `value_json is undefined` errors in the HA log

Not from this integration — `value_json` is a Jinja variable used only by
HA's REST / MQTT / Command-line / SQL sensors. The error means one of
those sensors is failing to parse a JSON response (the source returned an
empty body or HTML).

Search your config for the offending template:
```sh
grep -rn "value_json" /config/.storage/ /config/
```
The culprit is usually a REST or MQTT sensor pointing at a URL that's
returning HTML (login page, 5xx error) instead of JSON.

### Unleashed Web UI kicks you out when HA is running

Unleashed defaults to allowing one admin web session at a time. This
integration holds it continuously, so logging in via the browser bumps
HA out (or vice versa).

Fix: in Unleashed → Admin & Services → System → System Info, enable
multi-session admin. Then HA and your browser coexist.

### Sensor `entity_id` doesn't match the README examples

The README uses `sensor.ruckus_unleashed_active_rogues` as a placeholder
(it assumes the Unleashed master identity name `Ruckus-Unleashed`). Yours
will mirror whatever name your master AP reports. Check the actual value
in Developer Tools → States, filter `sensor.ruckus`, then update your
dashboard YAML to match.

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
