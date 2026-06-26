"""Universal Room Thermostat integration."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import (
    CONF_DASHBOARD,
    CONF_DUCTED_AC,
    CONF_GLOBAL,
    CONF_ROOMS,
    COOLING_NONE,
    COOLING_TYPES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import URTCoordinator
from .defaults import default_config
from .models import RoomConfig

_LOGGER = logging.getLogger(__name__)

PRESET_DEFAULTS_HEAT = {
    "comfort": 21.0,
    "eco": 19.0,
    "sleep": 18.0,
    "away": 16.0,
}
PRESET_DEFAULTS_COOL = {
    "comfort": 25.0,
    "eco": 27.0,
    "sleep": 26.0,
    "away": 28.0,
}

ROOM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Required("temperature_sensor"): cv.entity_id,
        vol.Optional("humidity_sensor"): cv.entity_id,
        vol.Optional("ui_climate"): cv.entity_id,
        vol.Optional("heat_climate"): cv.entity_id,
        vol.Optional("heat_climates", default=[]): vol.All(cv.ensure_list, [cv.entity_id]),
        vol.Optional("presence_entity"): cv.entity_id,
        vol.Optional("occupancy_entity"): cv.entity_id,
        vol.Optional("comfort_entity"): cv.entity_id,
        vol.Optional("cooling_type", default=COOLING_NONE): vol.In(COOLING_TYPES),
        vol.Optional("split_climate"): cv.entity_id,
        # Accepted for readability in hybrid configurations. The physical
        # ducted entity remains globally owned by DuctedACController.
        vol.Optional("ducted_climate"): cv.entity_id,
    },
    extra=vol.PREVENT_EXTRA,
)

GLOBAL_SCHEMA = vol.Schema(
    {
        vol.Required("mode_entity"): cv.entity_id,
        vol.Optional("control_enabled_entity"): cv.entity_id,
        vol.Optional("comfort_cooling_target", default=25.0): vol.Coerce(float),
        vol.Optional("maintenance_cooling_target", default=28.0): vol.Coerce(float),
        vol.Optional("cooling_tolerance", default=0.3): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("min_temperature", default=7.0): vol.Coerce(float),
        vol.Optional("max_temperature", default=35.0): vol.Coerce(float),
        vol.Optional("target_temperature_step", default=0.5): vol.Coerce(float),
        vol.Optional("heating_presets", default=PRESET_DEFAULTS_HEAT): {
            vol.Required(key): vol.Coerce(float) for key in PRESET_DEFAULTS_HEAT
        },
        vol.Optional("cooling_presets", default=PRESET_DEFAULTS_COOL): {
            vol.Required(key): vol.Coerce(float) for key in PRESET_DEFAULTS_COOL
        },
        vol.Optional("sync_ui_climate", default=True): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

DUCTED_SCHEMA = vol.Schema(
    {
        vol.Required("climate_entity"): cv.entity_id,
        vol.Optional("debounce", default=5): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional("min_on_time", default=300): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("min_off_time", default=300): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("off_delay", default=90): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("command_interval", default=15): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("setpoint_high", default=22.0): vol.Coerce(float),
        vol.Optional("setpoint_medium", default=23.0): vol.Coerce(float),
        vol.Optional("setpoint_low", default=24.0): vol.Coerce(float),
        vol.Optional("salon_boost_delta", default=2.0): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("split_heat_enabled", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

DASHBOARD_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("title", default="Clima Casa"): cv.string,
        vol.Optional("icon", default="mdi:thermostat"): cv.icon,
        vol.Optional("url_path", default="urt-clima-casa"): cv.string,
        vol.Optional("show_in_sidebar", default=True): cv.boolean,
        vol.Optional("require_admin", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_GLOBAL): GLOBAL_SCHEMA,
                vol.Required(CONF_DUCTED_AC): DUCTED_SCHEMA,
                vol.Required(CONF_ROOMS): vol.Schema({cv.slug: ROOM_SCHEMA}),
                vol.Optional(CONF_DASHBOARD, default={}): DASHBOARD_SCHEMA,
            },
            extra=vol.PREVENT_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _merged_config(config: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial config-entry/options payload over the URT defaults."""
    merged = default_config()
    for section, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(section), dict):
            if section == CONF_ROOMS:
                for room_key, room_config in value.items():
                    merged[section].setdefault(room_key, {})
                    merged[section][room_key].update(room_config)
            else:
                merged[section].update(value)
        else:
            merged[section] = value
    return merged


def _room_from_config(key: str, config: dict[str, Any]) -> RoomConfig:
    heat = list(config.get("heat_climates", []))
    if entity_id := config.get("heat_climate"):
        heat.insert(0, entity_id)
    cooling_type = config.get("cooling_type", COOLING_NONE)
    if cooling_type != COOLING_NONE and not (
        cooling_type in ("ducted", "hybrid", "split")
    ):
        raise vol.Invalid(f"Invalid cooling_type for room {key}")
    if cooling_type in ("hybrid", "split") and not config.get("split_climate"):
        raise vol.Invalid(f"Room {key} requires split_climate for {cooling_type}")
    return RoomConfig(
        key=key,
        name=config.get(CONF_NAME, key.replace("_", " ").title()),
        temperature_sensor=config["temperature_sensor"],
        humidity_sensor=config.get("humidity_sensor"),
        ui_climate=config.get("ui_climate"),
        heat_climates=tuple(dict.fromkeys(heat)),
        presence_entity=config.get("presence_entity"),
        occupancy_entity=config.get("occupancy_entity"),
        comfort_entity=config.get("comfort_entity"),
        cooling_type=cooling_type,
        split_climate=config.get("split_climate"),
    )


def _climate_entity_id(room_key: str) -> str:
    return f"climate.urt_{room_key}"


def _cooling_request_entity_id(room_key: str) -> str:
    return f"binary_sensor.urt_{room_key}_cooling_request"


def _panel_config(
    rooms: dict[str, RoomConfig],
    global_config: dict[str, Any],
    sidebar_config: dict[str, Any],
) -> dict[str, Any]:
    """Build the config passed to the URT custom panel."""
    return {
        "title": sidebar_config["title"],
        "mode_entity": global_config["mode_entity"],
        "control_enabled_entity": global_config.get("control_enabled_entity"),
        "rooms": [
            {
                "key": room_key,
                "name": room.name,
                "climate_entity": _climate_entity_id(room_key),
                "temperature_sensor": room.temperature_sensor,
                "humidity_sensor": room.humidity_sensor,
                "presence_entity": room.presence_entity or room.occupancy_entity,
                "cooling_type": room.cooling_type,
                "cooling_request_entity": (
                    _cooling_request_entity_id(room_key)
                    if room.cooling_type == "ducted"
                    else None
                ),
            }
            for room_key, room in rooms.items()
        ],
        "diagnostics": {
            "cooling_requested": "binary_sensor.urt_ducted_cooling_requested",
            "active_room": "sensor.urt_ducted_active_room",
            "max_delta": "sensor.urt_ducted_max_delta",
            "requested_setpoint": "sensor.urt_ducted_requested_setpoint",
        },
    }


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


async def _async_remove_legacy_lovelace_dashboard(
    hass: HomeAssistant,
    url_path: str,
) -> None:
    """Remove the old Lovelace dashboard created by URT 1.0.1/1.0.2."""
    dashboards_store = Store(hass, 1, "lovelace_dashboards")
    dashboards_data = await dashboards_store.async_load()
    if not dashboards_data:
        return
    items = dashboards_data.get("items")
    if not isinstance(items, list):
        return
    filtered_items = [item for item in items if item.get("url_path") != url_path]
    if len(filtered_items) == len(items):
        return
    dashboards_data["items"] = filtered_items
    await dashboards_store.async_save(dashboards_data)


async def _async_setup_sidebar_panel(
    hass: HomeAssistant,
    rooms: dict[str, RoomConfig],
    global_config: dict[str, Any],
    sidebar_config: dict[str, Any],
) -> None:
    """Register the URT custom panel in the Home Assistant sidebar."""
    if not sidebar_config["enabled"]:
        return

    title = sidebar_config["title"]
    icon = sidebar_config["icon"]
    url_path = sidebar_config["url_path"].strip("/")
    show_in_sidebar = sidebar_config["show_in_sidebar"]
    require_admin = sidebar_config["require_admin"]
    if not show_in_sidebar:
        return

    await _async_remove_legacy_lovelace_dashboard(hass, url_path)

    panel_dir = Path(__file__).parent / "frontend"
    panel_url = f"/{DOMAIN}/urt-panel.js"
    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    panel_url,
                    str(panel_dir / "urt-panel.js"),
                    cache_headers=False,
                )
            ]
        )
    except RuntimeError as err:
        # The path may already be registered after a config-entry reload.
        _LOGGER.debug("URT panel static path already registered: %s", err)

    try:
        await _maybe_await(
            panel_custom.async_register_panel(
                hass,
                frontend_url_path=url_path,
                webcomponent_name="urt-climate-panel",
                sidebar_title=title,
                sidebar_icon=icon,
                module_url=panel_url,
                config=_panel_config(rooms, global_config, sidebar_config),
                require_admin=require_admin,
            )
        )
    except ValueError as err:
        _LOGGER.debug("URT sidebar panel was already registered: %s", err)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up URT and import YAML when present."""
    if DOMAIN not in config:
        return True
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=config[DOMAIN],
        )
    )
    return True


async def _async_setup_from_config(
    hass: HomeAssistant,
    domain_config: dict[str, Any],
) -> bool:
    """Set up URT from a normalized domain config."""
    domain_config = _merged_config(domain_config)
    rooms = {
        key: _room_from_config(key, room_config)
        for key, room_config in domain_config[CONF_ROOMS].items()
    }
    ducted_entity = domain_config[CONF_DUCTED_AC]["climate_entity"]
    for key, room_config in domain_config[CONF_ROOMS].items():
        if (
            room_config.get("ducted_climate")
            and room_config["ducted_climate"] != ducted_entity
        ):
            raise vol.Invalid(
                f"Room {key} ducted_climate must match ducted_ac.climate_entity"
            )
    coordinator = URTCoordinator(
        hass,
        rooms,
        domain_config[CONF_GLOBAL],
        domain_config[CONF_DUCTED_AC],
    )
    hass.data[DOMAIN] = coordinator
    await coordinator.async_start()
    await _async_setup_sidebar_panel(
        hass,
        rooms,
        domain_config[CONF_GLOBAL],
        domain_config[CONF_DASHBOARD],
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up URT from the UI config entry."""
    domain_config = dict(entry.options or entry.data)
    if not await _async_setup_from_config(hass, domain_config):
        return False
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UI-configured URT entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data.pop(DOMAIN, None)
        if coordinator and getattr(coordinator, "_remove_listener", None):
            coordinator._remove_listener()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload URT when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
