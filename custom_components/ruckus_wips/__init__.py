"""The RUCKUS WIPS integration."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from aioruckus import AjaxSession
from aioruckus.exceptions import AuthenticationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .coordinator import RuckusWipsCoordinator
from .services import async_register_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.EVENT]


@dataclass
class RuckusWipsData:
    """Runtime data held on the config entry."""

    session: AjaxSession
    coordinator: RuckusWipsCoordinator


type RuckusWipsConfigEntry = ConfigEntry[RuckusWipsData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services once at startup.

    Per the HA quality-scale ``action-setup`` rule, services live here —
    not inside ``async_setup_entry`` — so that automation editors can
    validate references even when no entry is loaded.
    """
    async_register_services(hass)
    return True


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
    except (TimeoutError, aiohttp.ClientError, ConnectionError) as err:
        await session.close()
        raise ConfigEntryNotReady(f"Cannot connect to Unleashed: {err}") from err

    coordinator = RuckusWipsCoordinator(hass, entry, session)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # HA retries setup; without this every retry leaks a logged-in
        # session, and Unleashed allows only one admin session by default.
        await session.close()
        raise

    entry.runtime_data = RuckusWipsData(session=session, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RuckusWipsConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.session.close()
    return unloaded
