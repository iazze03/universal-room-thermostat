"""Universal Room Thermostat integration."""

from __future__ import annotations

import inspect
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
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


def _room_from_config(key: str, config: dict[str, Any]) -> RoomConfig:
    heat = list(config.get("heat_climates", []))
    if entity_id := config.get("heat_climate"):
        heat.insert(0, entity_id)
    cooling_type = config["cooling_type"]
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


def _dashboard_config(
    rooms: dict[str, RoomConfig],
    global_config: dict[str, Any],
) -> dict[str, Any]:
    """Build the Lovelace dashboard shown in the sidebar."""
    climate_cards = [
        {
            "type": "tile",
            "entity": _climate_entity_id(room_key),
            "name": room.name,
            "features": [
                {"type": "target-temperature"},
                {"type": "climate-hvac-modes"},
                {"type": "climate-preset-modes"},
            ],
        }
        for room_key, room in rooms.items()
    ]
    cooling_request_entities = [
        {
            "entity": _cooling_request_entity_id(room_key),
            "name": room.name,
        }
        for room_key, room in rooms.items()
        if room.cooling_type == "ducted"
    ]
    diagnostics_entities: list[dict[str, str]] = [
        {"entity": "binary_sensor.urt_ducted_cooling_requested", "name": "Richiesta freddo"},
        {"entity": "sensor.urt_ducted_active_room", "name": "Stanza guida"},
        {"entity": "sensor.urt_ducted_max_delta", "name": "Delta massimo"},
        {"entity": "sensor.urt_ducted_requested_setpoint", "name": "Setpoint Daikin"},
    ]
    return {
        "title": "Clima Casa",
        "views": [
            {
                "title": "Clima",
                "path": "clima",
                "icon": "mdi:thermostat",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {
                        "type": "grid",
                        "title": "Modalità casa",
                        "cards": [
                            {
                                "type": "entities",
                                "entities": [
                                    {
                                        "entity": global_config["mode_entity"],
                                        "name": "Modalità clima casa",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Termostati virtuali",
                        "cards": climate_cards,
                    },
                    {
                        "type": "grid",
                        "title": "Canalizzato",
                        "cards": [
                            {
                                "type": "entities",
                                "entities": diagnostics_entities,
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Richieste freddo camere",
                        "cards": [
                            {
                                "type": "entities",
                                "entities": cooling_request_entities,
                            }
                        ],
                    },
                ],
            }
        ],
    }


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


async def _async_setup_sidebar_dashboard(
    hass: HomeAssistant,
    rooms: dict[str, RoomConfig],
    global_config: dict[str, Any],
    dashboard_config: dict[str, Any],
) -> None:
    """Create/update a Lovelace dashboard and register it in the sidebar."""
    if not dashboard_config["enabled"]:
        return

    title = dashboard_config["title"]
    icon = dashboard_config["icon"]
    url_path = dashboard_config["url_path"].strip("/")
    show_in_sidebar = dashboard_config["show_in_sidebar"]
    require_admin = dashboard_config["require_admin"]
    dashboard_id = url_path

    dashboards_store = Store(hass, 1, "lovelace_dashboards")
    dashboards_data = await dashboards_store.async_load() or {"items": []}
    items = dashboards_data.setdefault("items", [])
    dashboard_item = next(
        (item for item in items if item.get("url_path") == url_path),
        None,
    )
    if dashboard_item is None:
        items.append(
            {
                "id": dashboard_id,
                "url_path": url_path,
                "title": title,
                "icon": icon,
                "show_in_sidebar": show_in_sidebar,
                "require_admin": require_admin,
                "mode": "storage",
            }
        )
    else:
        dashboard_item.update(
            {
                "title": title,
                "icon": icon,
                "show_in_sidebar": show_in_sidebar,
                "require_admin": require_admin,
                "mode": "storage",
            }
        )
        dashboard_id = dashboard_item.get("id", dashboard_id)
    await dashboards_store.async_save(dashboards_data)

    config_store = Store(hass, 1, f"lovelace.{dashboard_id}")
    await config_store.async_save(
        {"config": _dashboard_config(rooms, global_config)}
    )

    if not show_in_sidebar:
        return

    if hasattr(frontend, "async_remove_panel"):
        try:
            await _maybe_await(frontend.async_remove_panel(hass, url_path))
        except ValueError:
            pass

    try:
        await _maybe_await(
            frontend.async_register_built_in_panel(
                hass,
                "lovelace",
                sidebar_title=title,
                sidebar_icon=icon,
                sidebar_default_visible=True,
                frontend_url_path=url_path,
                config={
                    "mode": "storage",
                },
                require_admin=require_admin,
                update=True,
                show_in_sidebar=show_in_sidebar,
            )
        )
    except TypeError:
        # Older Home Assistant versions do not accept all keyword arguments.
        await _maybe_await(
            frontend.async_register_built_in_panel(
                hass,
                "lovelace",
                sidebar_title=title,
                sidebar_icon=icon,
                sidebar_default_visible=True,
                frontend_url_path=url_path,
                config={
                    "mode": "storage",
                },
                require_admin=require_admin,
            )
        )
    except ValueError as err:
        _LOGGER.debug("URT sidebar panel was already registered: %s", err)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up URT from YAML."""
    if DOMAIN not in config:
        return True
    domain_config = config[DOMAIN]
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
    await _async_setup_sidebar_dashboard(
        hass,
        rooms,
        domain_config[CONF_GLOBAL],
        domain_config[CONF_DASHBOARD],
    )
    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )
    return True
