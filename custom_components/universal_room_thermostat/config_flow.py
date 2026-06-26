"""Config flow for Universal Room Thermostat."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .defaults import default_config


def _get(config: dict[str, Any], path: str, default: Any = "") -> Any:
    value: Any = config
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def _set(config: dict[str, Any], path: str, value: Any) -> None:
    target = config
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    if value not in (None, ""):
        target[parts[-1]] = value


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _csv_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(value)
    return str(value or "")


class UniversalRoomThermostatConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle a config flow for URT."""

    VERSION = 1

    def __init__(self) -> None:
        self._config = default_config()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure global, ducted and sidebar settings."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            _set(self._config, "global.mode_entity", user_input["mode_entity"])
            _set(
                self._config,
                "global.comfort_cooling_target",
                float(user_input["comfort_cooling_target"]),
            )
            _set(
                self._config,
                "global.maintenance_cooling_target",
                float(user_input["maintenance_cooling_target"]),
            )
            _set(
                self._config,
                "ducted_ac.climate_entity",
                user_input["ducted_climate_entity"],
            )
            _set(self._config, "dashboard.title", user_input["panel_title"])
            _set(self._config, "dashboard.url_path", user_input["panel_url_path"])
            return await self.async_step_bedrooms()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "mode_entity",
                        default=_get(self._config, "global.mode_entity"),
                    ): cv.entity_id,
                    vol.Required(
                        "comfort_cooling_target",
                        default=_get(self._config, "global.comfort_cooling_target"),
                    ): vol.Coerce(float),
                    vol.Required(
                        "maintenance_cooling_target",
                        default=_get(
                            self._config, "global.maintenance_cooling_target"
                        ),
                    ): vol.Coerce(float),
                    vol.Required(
                        "ducted_climate_entity",
                        default=_get(self._config, "ducted_ac.climate_entity"),
                    ): cv.entity_id,
                    vol.Required(
                        "panel_title",
                        default=_get(self._config, "dashboard.title"),
                    ): str,
                    vol.Required(
                        "panel_url_path",
                        default=_get(self._config, "dashboard.url_path"),
                    ): str,
                }
            ),
        )

    async def async_step_bedrooms(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure the three ducted bedrooms."""
        if user_input is not None:
            for room_key in ("camera_fra", "camera_ale", "camera_padronale"):
                prefix = f"{room_key}_"
                _set(
                    self._config,
                    f"rooms.{room_key}.ui_climate",
                    user_input[f"{prefix}ui_climate"],
                )
                _set(
                    self._config,
                    f"rooms.{room_key}.temperature_sensor",
                    user_input[f"{prefix}temperature_sensor"],
                )
                _set(
                    self._config,
                    f"rooms.{room_key}.heat_climate",
                    user_input[f"{prefix}heat_climate"],
                )
                _set(
                    self._config,
                    f"rooms.{room_key}.presence_entity",
                    user_input[f"{prefix}presence_entity"],
                )
                _set(
                    self._config,
                    f"rooms.{room_key}.comfort_entity",
                    user_input[f"{prefix}comfort_entity"],
                )
            return await self.async_step_living_services()

        fields: dict[Any, Any] = {}
        for room_key, label in (
            ("camera_fra", "Camera Fra"),
            ("camera_ale", "Camera Ale"),
            ("camera_padronale", "Camera Padronale"),
        ):
            fields[vol.Required(f"{room_key}_ui_climate", default=_get(self._config, f"rooms.{room_key}.ui_climate"))] = cv.entity_id
            fields[vol.Required(f"{room_key}_temperature_sensor", default=_get(self._config, f"rooms.{room_key}.temperature_sensor"))] = cv.entity_id
            fields[vol.Required(f"{room_key}_heat_climate", default=_get(self._config, f"rooms.{room_key}.heat_climate"))] = cv.entity_id
            fields[vol.Required(f"{room_key}_presence_entity", default=_get(self._config, f"rooms.{room_key}.presence_entity"))] = cv.entity_id
            fields[vol.Required(f"{room_key}_comfort_entity", default=_get(self._config, f"rooms.{room_key}.comfort_entity"))] = cv.entity_id

        return self.async_show_form(
            step_id="bedrooms",
            description_placeholders={"rooms": "Camera Fra, Camera Ale, Camera Padronale"},
            data_schema=vol.Schema(fields),
        )

    async def async_step_living_services(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure living room, kitchen and bathrooms."""
        if user_input is not None:
            _set(
                self._config,
                "rooms.salone.temperature_sensor",
                user_input["salone_temperature_sensor"],
            )
            _set(
                self._config,
                "rooms.salone.humidity_sensor",
                user_input["salone_humidity_sensor"],
            )
            _set(
                self._config,
                "rooms.salone.occupancy_entity",
                user_input["salone_occupancy_entity"],
            )
            _set(
                self._config,
                "rooms.salone.heat_climates",
                _csv(user_input["salone_heat_climates"]),
            )
            _set(
                self._config,
                "rooms.salone.split_climate",
                user_input["salone_split_climate"],
            )
            for room_key in ("cucina", "bagno", "bagnetto"):
                prefix = f"{room_key}_"
                _set(
                    self._config,
                    f"rooms.{room_key}.temperature_sensor",
                    user_input[f"{prefix}temperature_sensor"],
                )
                _set(
                    self._config,
                    f"rooms.{room_key}.heat_climate",
                    user_input[f"{prefix}heat_climate"],
                )
            _set(
                self._config,
                "rooms.cucina.humidity_sensor",
                user_input["cucina_humidity_sensor"],
            )
            return self.async_create_entry(
                title=_get(self._config, "dashboard.title", "Clima Casa"),
                data=self._config,
            )

        return self.async_show_form(
            step_id="living_services",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "salone_temperature_sensor",
                        default=_get(self._config, "rooms.salone.temperature_sensor"),
                    ): cv.entity_id,
                    vol.Required(
                        "salone_humidity_sensor",
                        default=_get(self._config, "rooms.salone.humidity_sensor"),
                    ): cv.entity_id,
                    vol.Required(
                        "salone_occupancy_entity",
                        default=_get(self._config, "rooms.salone.occupancy_entity"),
                    ): cv.entity_id,
                    vol.Required(
                        "salone_heat_climates",
                        default=_csv_text(
                            _get(self._config, "rooms.salone.heat_climates")
                        ),
                    ): str,
                    vol.Required(
                        "salone_split_climate",
                        default=_get(self._config, "rooms.salone.split_climate"),
                    ): cv.entity_id,
                    vol.Required(
                        "cucina_temperature_sensor",
                        default=_get(self._config, "rooms.cucina.temperature_sensor"),
                    ): cv.entity_id,
                    vol.Required(
                        "cucina_humidity_sensor",
                        default=_get(self._config, "rooms.cucina.humidity_sensor"),
                    ): cv.entity_id,
                    vol.Required(
                        "cucina_heat_climate",
                        default=_get(self._config, "rooms.cucina.heat_climate"),
                    ): cv.entity_id,
                    vol.Required(
                        "bagno_temperature_sensor",
                        default=_get(self._config, "rooms.bagno.temperature_sensor"),
                    ): cv.entity_id,
                    vol.Required(
                        "bagno_heat_climate",
                        default=_get(self._config, "rooms.bagno.heat_climate"),
                    ): cv.entity_id,
                    vol.Required(
                        "bagnetto_temperature_sensor",
                        default=_get(
                            self._config, "rooms.bagnetto.temperature_sensor"
                        ),
                    ): cv.entity_id,
                    vol.Required(
                        "bagnetto_heat_climate",
                        default=_get(self._config, "rooms.bagnetto.heat_climate"),
                    ): cv.entity_id,
                }
            ),
        )

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Import YAML configuration into a config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        imported = deepcopy(import_config)
        return self.async_create_entry(
            title=_get(imported, "dashboard.title", "Clima Casa"),
            data=imported,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return UniversalRoomThermostatOptionsFlow(config_entry)


class UniversalRoomThermostatOptionsFlow(config_entries.OptionsFlow):
    """Simple options flow for sidebar and comfort targets."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure commonly changed options."""
        current = deepcopy(dict(self._config_entry.options or self._config_entry.data))
        if user_input is not None:
            _set(current, "global.mode_entity", user_input["mode_entity"])
            _set(
                current,
                "global.comfort_cooling_target",
                float(user_input["comfort_cooling_target"]),
            )
            _set(
                current,
                "global.maintenance_cooling_target",
                float(user_input["maintenance_cooling_target"]),
            )
            _set(current, "dashboard.title", user_input["panel_title"])
            _set(current, "dashboard.show_in_sidebar", user_input["show_in_sidebar"])
            return self.async_create_entry(title="", data=current)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "mode_entity",
                        default=_get(current, "global.mode_entity"),
                    ): cv.entity_id,
                    vol.Required(
                        "comfort_cooling_target",
                        default=_get(current, "global.comfort_cooling_target"),
                    ): vol.Coerce(float),
                    vol.Required(
                        "maintenance_cooling_target",
                        default=_get(current, "global.maintenance_cooling_target"),
                    ): vol.Coerce(float),
                    vol.Required(
                        "panel_title",
                        default=_get(current, "dashboard.title"),
                    ): str,
                    vol.Required(
                        "show_in_sidebar",
                        default=_get(current, "dashboard.show_in_sidebar", True),
                    ): bool,
                }
            ),
        )
