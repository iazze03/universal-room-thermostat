"""Config flow for Universal Room Thermostat."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN
from .defaults import default_config


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
