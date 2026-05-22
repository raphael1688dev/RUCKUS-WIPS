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
- **`event.<network>_new_rogue_detected`** — fires `new_rogue` with full
  metadata the first time a BSSID is seen. Survive-on-restart logic suppresses
  alerts for previously-known BSSIDs.
- **Service `ruckus_wips.mark_malicious`** — `bssid: aa:bb:cc:dd:ee:ff`
  triggers Unleashed to broadcast deauth, blocking clients from associating to
  that rogue.
- **Service `ruckus_wips.unmark_malicious`** — undoes the above. Hidden by
  default; enable in the integration's *Configure* menu under
  **Expose unmark_malicious service (advanced)**.

## Install via HACS

1. HACS → ⋯ menu → **Custom repositories**
2. Add `https://github.com/raphaelchen/RUCKUS-HACS` as type **Integration**
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

## Automation example

Notify when an open-encryption rogue appears in the living room area:

```yaml
- alias: "Alert: open rogue near living room"
  trigger:
    - platform: state
      entity_id: event.ruckus_unleashed_new_rogue_detected
  condition:
    - "{{ trigger.to_state.attributes.encryption | lower == 'open' }}"
    - "{{ 'LIVING' in (trigger.to_state.attributes.detection_ap_location or '') | upper }}"
  action:
    - service: notify.mobile_app_phone
      data:
        title: "New open rogue near living room"
        message: >
          {{ trigger.to_state.attributes.ssid }}
          ({{ trigger.to_state.attributes.bssid }})
          ch {{ trigger.to_state.attributes.channel }}
          rssi {{ trigger.to_state.attributes.rssi }}

- alias: "Auto-block any open rogue"
  trigger:
    - platform: state
      entity_id: event.ruckus_unleashed_new_rogue_detected
  condition:
    - "{{ trigger.to_state.attributes.encryption | lower == 'open' }}"
  action:
    - service: ruckus_wips.mark_malicious
      data:
        bssid: "{{ trigger.to_state.attributes.bssid }}"
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
