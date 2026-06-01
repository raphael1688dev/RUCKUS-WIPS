"""Shared test fixtures.

These tests intentionally avoid pulling in the full Home Assistant test
harness (`pytest-homeassistant-custom-component`) — that would require
installing the entire HA package and slow CI dramatically. Instead we
stub the minimum HA surface that the integration's modules import at
load time, then exercise the pure-logic layers directly.

When the day comes to add real entity / config-flow tests against the
HA harness, layer that suite alongside these — don't replace.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# -- Stub the homeassistant modules our integration imports at top level --
#
# We don't need real HA behavior for the pure-logic tests; we just need
# the imports to succeed.  Each attribute we reference downstream is
# defined as a placeholder class or function below.


def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_ha = _make_module("homeassistant")
_ha_const = _make_module("homeassistant.const")
_ha_core = _make_module("homeassistant.core")
_ha_config_entries = _make_module("homeassistant.config_entries")
_ha_exceptions = _make_module("homeassistant.exceptions")
_ha_helpers = _make_module("homeassistant.helpers")
_ha_helpers_cv = _make_module("homeassistant.helpers.config_validation")
_ha_helpers_dr = _make_module("homeassistant.helpers.device_registry")
_ha_helpers_uc = _make_module("homeassistant.helpers.update_coordinator")
_ha_helpers_selector = _make_module("homeassistant.helpers.selector")
_ha_helpers_ep = _make_module("homeassistant.helpers.entity_platform")
_ha_components = _make_module("homeassistant.components")
_ha_components_sensor = _make_module("homeassistant.components.sensor")
_ha_components_event = _make_module("homeassistant.components.event")
_ha_components_logbook = _make_module("homeassistant.components.logbook")


# --- const ---
_ha_const.CONF_HOST = "host"
_ha_const.CONF_USERNAME = "username"
_ha_const.CONF_PASSWORD = "password"


class _Platform:
    SENSOR = "sensor"
    EVENT = "event"


_ha_const.Platform = _Platform


# --- core ---
class HomeAssistant:  # noqa: D401
    """Stub of homeassistant.core.HomeAssistant."""


def callback(fn):  # noqa: D401
    """Pass-through decorator."""
    return fn


class _ServiceCall:
    def __init__(self, data=None, hass=None):
        self.data = data or {}
        self.hass = hass


class _SupportsResponse:
    NONE = 0
    OPTIONAL = 1
    ONLY = 2


_ha_core.HomeAssistant = HomeAssistant
_ha_core.callback = callback
_ha_core.ServiceCall = _ServiceCall
_ha_core.ServiceResponse = dict  # alias for typing
_ha_core.SupportsResponse = _SupportsResponse
_ha_core.Event = object


# --- exceptions ---
class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(HomeAssistantError):
    pass


class ConfigEntryNotReady(HomeAssistantError):
    pass


class ServiceValidationError(HomeAssistantError):
    def __init__(self, *args, translation_domain=None, translation_key=None, translation_placeholders=None):
        super().__init__(*args)
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders


_ha_exceptions.HomeAssistantError = HomeAssistantError
_ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
_ha_exceptions.ConfigEntryNotReady = ConfigEntryNotReady
_ha_exceptions.ServiceValidationError = ServiceValidationError


# --- config_entries ---
class ConfigEntry:  # noqa: D401
    """Stub."""

    def __class_getitem__(cls, item):
        return cls


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):  # noqa: D401
        # Tolerate `domain=...` kwarg
        return None


class ConfigFlowResult(dict):
    pass


class OptionsFlow:
    pass


_ha_config_entries.ConfigEntry = ConfigEntry
_ha_config_entries.ConfigFlow = ConfigFlow
_ha_config_entries.ConfigFlowResult = ConfigFlowResult
_ha_config_entries.OptionsFlow = OptionsFlow


# --- helpers ---
def _identity(x):
    return x


_ha_helpers_cv.string = _identity


def _async_get(_hass):  # noqa: D401
    """Return a dummy device registry."""
    class _Reg:
        def async_get(self, _id):
            return None

    return _Reg()


_ha_helpers_dr.async_get = _async_get


class DataUpdateCoordinator:
    def __init__(self, *args, **kwargs):
        self.data = None

    def __class_getitem__(cls, item):
        return cls


class UpdateFailed(Exception):
    pass


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


_ha_helpers_uc.DataUpdateCoordinator = DataUpdateCoordinator
_ha_helpers_uc.UpdateFailed = UpdateFailed
_ha_helpers_uc.CoordinatorEntity = CoordinatorEntity


# selector — used by config_flow at import time
class _Selector:
    pass


class _SelectorWithConfig(_Selector):
    def __init__(self, *_args, **_kwargs):
        pass


class _TextSelectorType:
    PASSWORD = "password"


class _NumberSelectorMode:
    SLIDER = "slider"
    BOX = "box"


_ha_helpers_selector.TextSelector = _SelectorWithConfig
_ha_helpers_selector.TextSelectorConfig = _SelectorWithConfig
_ha_helpers_selector.TextSelectorType = _TextSelectorType
_ha_helpers_selector.NumberSelector = _SelectorWithConfig
_ha_helpers_selector.NumberSelectorConfig = _SelectorWithConfig
_ha_helpers_selector.NumberSelectorMode = _NumberSelectorMode
_ha_helpers_selector.selector = _identity


# entity_platform
_ha_helpers_ep.AddEntitiesCallback = object


# components/sensor
class _SensorEntity:
    pass


class _SensorEntityDescription:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _SensorStateClass:
    MEASUREMENT = "measurement"


_ha_components_sensor.SensorEntity = _SensorEntity
_ha_components_sensor.SensorEntityDescription = _SensorEntityDescription
_ha_components_sensor.SensorStateClass = _SensorStateClass


# components/event
class _EventEntity:
    pass


_ha_components_event.EventEntity = _EventEntity


# components/logbook
_ha_components_logbook.LOGBOOK_ENTRY_MESSAGE = "message"
_ha_components_logbook.LOGBOOK_ENTRY_NAME = "name"


# -- Now make the integration importable -----------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
