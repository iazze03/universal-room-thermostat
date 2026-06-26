"""Universal Room Thermostat integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery

from .const import (
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

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_GLOBAL): GLOBAL_SCHEMA,
                vol.Required(CONF_DUCTED_AC): DUCTED_SCHEMA,
                vol.Required(CONF_ROOMS): vol.Schema({cv.slug: ROOM_SCHEMA}),
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
    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )
    return True
