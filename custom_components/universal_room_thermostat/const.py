"""Constants for Universal Room Thermostat."""

from __future__ import annotations

DOMAIN = "universal_room_thermostat"
PLATFORMS = ("climate", "sensor", "binary_sensor")

CONF_GLOBAL = "global"
CONF_DUCTED_AC = "ducted_ac"
CONF_ROOMS = "rooms"

HOUSE_MODE_SUMMER = "estate"
HOUSE_MODE_WINTER = "inverno"
HOUSE_MODE_OFF = "spento"
HOUSE_MODE_AUTO = "auto"
HOUSE_MODES = {
    HOUSE_MODE_SUMMER,
    HOUSE_MODE_WINTER,
    HOUSE_MODE_OFF,
    HOUSE_MODE_AUTO,
}

COOLING_DUCTED = "ducted"
COOLING_HYBRID = "hybrid"
COOLING_SPLIT = "split"
COOLING_NONE = "none"
COOLING_TYPES = {
    COOLING_DUCTED,
    COOLING_HYBRID,
    COOLING_SPLIT,
    COOLING_NONE,
}

PRESETS = ("comfort", "eco", "sleep", "away")

DEFAULT_NAME_MAP = {
    "camera_fra": "Camera Fra",
    "camera_ale": "Camera Ale",
    "camera_padronale": "Camera Padronale",
    "salone": "Salone",
    "cucina": "Cucina",
    "bagno": "Bagno",
    "bagnetto": "Bagnetto",
}
