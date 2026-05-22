"""The RUCKUS WIPS integration."""

from __future__ import annotations

from dataclasses import dataclass

from aioruckus import AjaxSession
from aioruckus.exceptions import AuthenticationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .coordinator import RuckusWipsCoordinator
from .services import async_register_services, async_unregister_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.EVENT]


@dataclass
class RuckusWipsData:
    """Runtime data held on the config entry."""

    session: AjaxSession
    coordinator: RuckusWipsCoordinator


type RuckusWipsConfigEntry = ConfigEntry[RuckusWipsData]


async def async_setup_entry(hass: HomeAssistant, entry: RuckusWipsConfigEntry) -> bool:
    """Set up RUCKUS WIPS from a config entry."""
    session = AjaxSession.async_create(
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    try:
        await session.login()
    except AuthenticationError as err:
        await session.close()
        raise ConfigEntryAuthFailed("Authentication failed") from err
    except Exception as err:
        await session.close()
        raise ConfigEntryNotReady(f"Cannot connect to Unleashed: {err}") from err

    coordinator = RuckusWipsCoordinator(hass, entry, session)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RuckusWipsData(session=session, coordinator=coordinator)

    await async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RuckusWipsConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.session.close()
        remaining = [
            other
            for other in hass.config_entries.async_loaded_entries(entry.domain)
            if other.entry_id != entry.entry_id
        ]
        if not remaining:
            await async_unregister_services(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: RuckusWipsConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
