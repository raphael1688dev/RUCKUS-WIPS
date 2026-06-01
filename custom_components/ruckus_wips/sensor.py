"""Sensor entities for RUCKUS WIPS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RuckusWipsConfigEntry
from .const import DOMAIN
from .coordinator import RuckusWipsCoordinator, RuckusWipsSnapshot


@dataclass(frozen=True, kw_only=True)
class RuckusWipsSensorDescription(SensorEntityDescription):
    """Describes a RUCKUS WIPS sensor."""

    value_fn: Callable[[RuckusWipsSnapshot], int]


SENSORS: tuple[RuckusWipsSensorDescription, ...] = (
    RuckusWipsSensorDescription(
        key="active_rogue_count",
        translation_key="active_rogue_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi-alert",
        value_fn=lambda snap: len(snap.active_unblocked),
    ),
    RuckusWipsSensorDescription(
        key="blocked_rogue_count",
        translation_key="blocked_rogue_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi-cancel",
        value_fn=lambda snap: len(snap.blocked),
    ),
    RuckusWipsSensorDescription(
        key="total_rogue_count",
        translation_key="total_rogue_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
        value_fn=lambda snap: len(snap.rogues),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RuckusWipsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        RuckusWipsSensor(coordinator, entry, desc) for desc in SENSORS
    )


class RuckusWipsSensor(CoordinatorEntity[RuckusWipsCoordinator], SensorEntity):
    """Aggregate counters about the rogue AP state."""

    _attr_has_entity_name = True
    entity_description: RuckusWipsSensorDescription

    def __init__(
        self,
        coordinator: RuckusWipsCoordinator,
        entry: RuckusWipsConfigEntry,
        description: RuckusWipsSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry, coordinator)

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[dict]]:
        if self.coordinator.data is None:
            return {}
        if self.entity_description.key == "active_rogue_count":
            return {"rogues": [_rogue_attrs(r) for r in self.coordinator.data.active_unblocked]}
        if self.entity_description.key == "blocked_rogue_count":
            return {"rogues": [_rogue_attrs(r) for r in self.coordinator.data.blocked]}
        if self.entity_description.key == "total_rogue_count":
            return {"rogues": [_rogue_attrs(r) for r in self.coordinator.data.rogues.values()]}
        return {}


def _rogue_attrs(rogue) -> dict:
    return {
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
        "last_seen": rogue.last_seen,
    }


def _device_info(entry: RuckusWipsConfigEntry, coordinator: RuckusWipsCoordinator) -> dict:
    sysinfo = ((coordinator.data.system if coordinator.data else {}) or {}).get(
        "sysinfo", {}
    )
    identity = ((coordinator.data.system if coordinator.data else {}) or {}).get(
        "identity", {}
    )
    return {
        "identifiers": {(DOMAIN, entry.unique_id or entry.entry_id)},
        "manufacturer": "RUCKUS",
        "name": identity.get("name") or entry.title,
        "model": sysinfo.get("display-model") or sysinfo.get("model") or "Unleashed",
        "sw_version": sysinfo.get("version"),
        "serial_number": sysinfo.get("serial"),
        "configuration_url": f"https://{entry.data.get('host')}",
    }
