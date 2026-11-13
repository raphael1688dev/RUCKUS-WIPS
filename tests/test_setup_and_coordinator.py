"""Regression tests for setup cleanup, coordinator error mapping and device sync."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aioruckus.exceptions import AuthenticationError
import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
import ruckus_wips
from ruckus_wips.coordinator import SYSTEM_INFO_REFRESH_EVERY_N_POLLS, RuckusWipsCoordinator
from ruckus_wips.sensor import RuckusWipsSensor

SYSTEM = {"sysinfo": {"serial": "402003001468", "version": "200.15.6.212"}}


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry1",
        unique_id="402003001468",
        options={},
        data={"host": "h", "username": "u", "password": "p"},
    )


def _session(**api_overrides) -> MagicMock:
    api = SimpleNamespace(
        get_system_info=AsyncMock(return_value=SYSTEM),
        get_active_rogues=AsyncMock(return_value=[]),
        get_blocked_rogues=AsyncMock(return_value=[]),
    )
    for name, value in api_overrides.items():
        setattr(api, name, value)
    session = MagicMock()
    session.api = api
    session.login = AsyncMock()
    session.close = AsyncMock()
    return session


def _coordinator(session: MagicMock) -> RuckusWipsCoordinator:
    coordinator = RuckusWipsCoordinator(MagicMock(), _entry(), session)
    coordinator.hass = MagicMock()
    return coordinator


@pytest.mark.parametrize(
    "error", [ConfigEntryNotReady("offline"), ConfigEntryAuthFailed("bad credentials")]
)
async def test_session_closed_when_first_refresh_fails(error: Exception) -> None:
    session = _session()
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=error)
    with (
        patch.object(ruckus_wips.AjaxSession, "async_create", return_value=session),
        patch.object(ruckus_wips, "RuckusWipsCoordinator", return_value=coordinator),
        pytest.raises(type(error)),
    ):
        await ruckus_wips.async_setup_entry(MagicMock(), _entry())
    session.close.assert_awaited_once()


@pytest.mark.parametrize("error", [ConnectionError("refused"), TimeoutError(), KeyError("sysinfo")])
async def test_async_setup_maps_errors_to_update_failed(error: Exception) -> None:
    coordinator = _coordinator(_session(get_system_info=AsyncMock(side_effect=error)))
    with pytest.raises(UpdateFailed):
        await coordinator._async_setup()


async def test_async_setup_auth_error_triggers_reauth() -> None:
    coordinator = _coordinator(
        _session(get_system_info=AsyncMock(side_effect=AuthenticationError("x")))
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_setup()


async def test_firmware_change_is_pushed_to_device_registry() -> None:
    upgraded = {"sysinfo": {"serial": "402003001468", "version": "200.16.0.0"}}
    coordinator = _coordinator(_session(get_system_info=AsyncMock(return_value=upgraded)))
    coordinator._system = SYSTEM
    coordinator._poll_count = SYSTEM_INFO_REFRESH_EVERY_N_POLLS - 1
    registry = MagicMock()
    registry.async_get_device_by_identifier.return_value = SimpleNamespace(
        id="dev1", sw_version="200.15.6.212"
    )

    with patch("ruckus_wips.coordinator.dr.async_get", return_value=registry):
        await coordinator._async_update_data()

    registry.async_get_device_by_identifier.assert_called_once_with(
        ("ruckus_wips", "402003001468"), "entry1"
    )
    registry.async_update_device.assert_called_once_with("dev1", sw_version="200.16.0.0")


async def test_unchanged_firmware_does_not_touch_device_registry() -> None:
    coordinator = _coordinator(_session())
    coordinator._system = SYSTEM
    coordinator._poll_count = SYSTEM_INFO_REFRESH_EVERY_N_POLLS - 1
    registry = MagicMock()
    registry.async_get_device_by_identifier.return_value = SimpleNamespace(
        id="dev1", sw_version="200.15.6.212"
    )

    with patch("ruckus_wips.coordinator.dr.async_get", return_value=registry):
        await coordinator._async_update_data()

    registry.async_update_device.assert_not_called()


def test_rogue_lists_are_not_recorded() -> None:
    assert "rogues" in RuckusWipsSensor._unrecorded_attributes
