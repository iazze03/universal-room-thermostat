"""Default configuration for the target URT home."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "global": {
        "mode_entity": "input_select.modalita_clima_casa",
        "comfort_cooling_target": 25.0,
        "maintenance_cooling_target": 28.0,
        "cooling_tolerance": 0.3,
        "min_temperature": 7.0,
        "max_temperature": 35.0,
        "target_temperature_step": 0.5,
        "sync_ui_climate": True,
        "heating_presets": {
            "comfort": 21.0,
            "eco": 19.0,
            "sleep": 18.0,
            "away": 16.0,
        },
        "cooling_presets": {
            "comfort": 25.0,
            "eco": 27.0,
            "sleep": 26.0,
            "away": 28.0,
        },
    },
    "ducted_ac": {
        "climate_entity": "climate.gateway_serranda_lora_daikin_canalizzato",
        "debounce": 5.0,
        "min_on_time": 300.0,
        "min_off_time": 300.0,
        "off_delay": 90.0,
        "command_interval": 15.0,
        "setpoint_high": 22.0,
        "setpoint_medium": 23.0,
        "setpoint_low": 24.0,
        "salon_boost_delta": 2.0,
        "split_heat_enabled": False,
    },
    "dashboard": {
        "enabled": True,
        "title": "Clima Casa",
        "icon": "mdi:thermostat",
        "url_path": "urt-clima-casa",
        "show_in_sidebar": True,
        "require_admin": False,
    },
    "rooms": {
        "camera_fra": {
            "name": "Camera Fra",
            "ui_climate": "climate.termostato_camera_fra",
            "temperature_sensor": "sensor.termostato_camera_fra_temperature",
            "heat_climate": "climate.valvola_camera_fra",
            "presence_entity": "binary_sensor.presenza_fra",
            "comfort_entity": "binary_sensor.camera_fra_raffrescabile",
            "cooling_type": "ducted",
        },
        "camera_ale": {
            "name": "Camera Ale",
            "ui_climate": "climate.termostato_camera_ale",
            "temperature_sensor": "sensor.termostato_camera_ale_temperature",
            "heat_climate": "climate.valvola_camera_ale",
            "presence_entity": "binary_sensor.presenza_ale",
            "comfort_entity": "binary_sensor.camera_ale_raffrescabile",
            "cooling_type": "ducted",
        },
        "camera_padronale": {
            "name": "Camera Padronale",
            "ui_climate": "climate.termostato_camera_padronale",
            "temperature_sensor": "sensor.termostato_camera_padronale_temperature",
            "heat_climate": "climate.valvola_camera_padronale",
            "presence_entity": "binary_sensor.presenza_massi",
            "comfort_entity": "binary_sensor.camera_padronale_raffrescabile",
            "cooling_type": "ducted",
        },
        "salone": {
            "name": "Salone",
            "temperature_sensor": "sensor.hub_2_d97c_temperatura",
            "humidity_sensor": "sensor.hub_2_d97c_umidita",
            "occupancy_entity": "binary_sensor.casa_occupata",
            "heat_climates": [
                "climate.valvola_salone_destra",
                "climate.valvola_salone_sinistra",
            ],
            "cooling_type": "hybrid",
            "split_climate": "climate.condizionatore",
            "ducted_climate": "climate.gateway_serranda_lora_daikin_canalizzato",
        },
        "cucina": {
            "name": "Cucina",
            "temperature_sensor": "sensor.cucina_temperatura",
            "humidity_sensor": "sensor.cucina_umidita",
            "heat_climate": "climate.valvola_cucina",
            "cooling_type": "none",
        },
        "bagno": {
            "name": "Bagno",
            "temperature_sensor": "sensor.valvola_bagno_local_temperature",
            "heat_climate": "climate.valvola_bagno",
            "cooling_type": "none",
        },
        "bagnetto": {
            "name": "Bagnetto",
            "temperature_sensor": "sensor.bagnetto_temperatura",
            "heat_climate": "climate.valvola_bagnetto",
            "cooling_type": "none",
        },
    },
}


def default_config() -> dict[str, Any]:
    """Return a mutable copy of the default URT configuration."""
    return deepcopy(DEFAULT_CONFIG)
