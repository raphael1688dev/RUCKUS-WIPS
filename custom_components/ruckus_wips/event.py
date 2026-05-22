"""Event entity that fires whenever a previously-unseen rogue BSSID appears."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuckusWipsConfigEntry
from .const import DOMAIN, EVENT_NEW_ROGUE
from .coordinator import Rogue, RuckusWipsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RuckusWipsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([RuckusWipsRogueEvent(coordinator, entry)])


class RuckusWipsRogueEvent(EventEntity):
    """Fires `new_rogue` with full rogue details whenever a new BSSID is observed."""

    _attr_has_entity_name = True
    _attr_translation_key = "new_rogue"
    _attr_event_types = [EVENT_NEW_ROGUE]
    _attr_device_class = EventDeviceClass.DOORBELL  # closest semantic — "something arrived"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: RuckusWipsCoordinator,
        entry: RuckusWipsConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_new_rogue"
        sysinfo = ((coordinator.data.system if coordinator.data else {}) or {}).get(
            "sysinfo", {}
        )
        identity = ((coordinator.data.system if coordinator.data else {}) or {}).get(
            "identity", {}
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.unique_id or entry.entry_id)},
            "manufacturer": "RUCKUS",
            "name": identity.get("name") or entry.title,
            "model": sysinfo.get("display-model") or sysinfo.get("model") or "Unleashed",
            "sw_version": sysinfo.get("version"),
            "serial_number": sysinfo.get("serial"),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_new_rogue_listener(self._handle_new_rogue)
        )

    @callback
    def _handle_new_rogue(self, rogue: Rogue) -> None:
        self._trigger_event(
            EVENT_NEW_ROGUE,
            {
                "bssid": rogue.bssid,
                "ssid": rogue.ssid,
                "channel": rogue.channel,
                "radio_band": rogue.radio_band,
                "radio_type": rogue.radio_type,
                "encryption": rogue.encryption,
                "rogue_type": rogue.rogue_type,
                "rssi": rogue.rssi,
                "detection_ap": rogue.detection_ap_name,
                "detection_ap_location": rogue.detection_ap_location,
                "blocked": rogue.blocked,
                "last_seen": rogue.last_seen,
            },
        )
        self.async_write_ha_state()
