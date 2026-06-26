"""Config flow for Universal Room Thermostat."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .defaults import default_config


def _set(config: dict[str, Any], path: str, value: Any) -> None:
    target = config
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _get(config: dict[str, Any], path: str, default: Any = "") -> Any:
    value: Any = config
    for part in path.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part, default)
    return value


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _csv_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(value)
    return str(value or "")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Universal Room Thermostat."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a URT entry using the built-in house defaults."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            config = default_config()
            config["dashboard"]["title"] = user_input["panel_title"]
            config["dashboard"]["show_in_sidebar"] = user_input["show_in_sidebar"]
            return self.async_create_entry(
                title=user_input["panel_title"],
                data=config,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("panel_title", default="Clima Casa"): str,
                    vol.Required("show_in_sidebar", default=True): bool,
                }
            ),
        )

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Import YAML configuration into a config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_config.get("dashboard", {}).get("title", "Clima Casa"),
            data=import_config,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Edit URT entity mapping from the Home Assistant UI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit common URT entities."""
        config = dict(self._config_entry.options or self._config_entry.data)
        if user_input is not None:
            _set(config, "global.mode_entity", user_input["mode_entity"])
            _set(config, "ducted_ac.climate_entity", user_input["ducted_climate"])
            _set(config, "rooms.salone.split_climate", user_input["salone_split"])
            _set(config, "rooms.salone.temperature_sensor", user_input["salone_temp"])
            _set(config, "rooms.salone.humidity_sensor", user_input["salone_humidity"])
            _set(config, "rooms.salone.heat_climates", _csv(user_input["salone_valves"]))
            _set(config, "rooms.camera_fra.temperature_sensor", user_input["fra_temp"])
            _set(config, "rooms.camera_ale.temperature_sensor", user_input["ale_temp"])
            _set(config, "rooms.camera_padronale.temperature_sensor", user_input["pad_temp"])
            _set(config, "rooms.cucina.temperature_sensor", user_input["cucina_temp"])
            _set(config, "rooms.bagno.temperature_sensor", user_input["bagno_temp"])
            _set(config, "rooms.bagnetto.temperature_sensor", user_input["bagnetto_temp"])
            return self.async_create_entry(title="", data=config)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("mode_entity", default=_get(config, "global.mode_entity")): cv.entity_id,
                    vol.Required("ducted_climate", default=_get(config, "ducted_ac.climate_entity")): cv.entity_id,
                    vol.Required("salone_split", default=_get(config, "rooms.salone.split_climate")): cv.entity_id,
                    vol.Required("salone_temp", default=_get(config, "rooms.salone.temperature_sensor")): cv.entity_id,
                    vol.Required("salone_humidity", default=_get(config, "rooms.salone.humidity_sensor")): cv.entity_id,
                    vol.Required("salone_valves", default=_csv_text(_get(config, "rooms.salone.heat_climates"))): str,
                    vol.Required("fra_temp", default=_get(config, "rooms.camera_fra.temperature_sensor")): cv.entity_id,
                    vol.Required("ale_temp", default=_get(config, "rooms.camera_ale.temperature_sensor")): cv.entity_id,
                    vol.Required("pad_temp", default=_get(config, "rooms.camera_padronale.temperature_sensor")): cv.entity_id,
                    vol.Required("cucina_temp", default=_get(config, "rooms.cucina.temperature_sensor")): cv.entity_id,
                    vol.Required("bagno_temp", default=_get(config, "rooms.bagno.temperature_sensor")): cv.entity_id,
                    vol.Required("bagnetto_temp", default=_get(config, "rooms.bagnetto.temperature_sensor")): cv.entity_id,
                }
            ),
        )
