"""Diagnostic sensors for Universal Room Thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import URTCoordinator


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    coordinator: URTCoordinator = hass.data[DOMAIN]
    async_add_entities(
        [
            URTDiagnosticSensor(
                coordinator,
                SensorEntityDescription(
                    key="ducted_active_room",
                    name="URT Ducted Active Room",
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            URTDiagnosticSensor(
                coordinator,
                SensorEntityDescription(
                    key="ducted_max_delta",
                    name="URT Ducted Max Delta",
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            URTDiagnosticSensor(
                coordinator,
                SensorEntityDescription(
                    key="ducted_requested_setpoint",
                    name="URT Ducted Requested Setpoint",
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
        ]
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up URT diagnostic sensors from a config entry."""
    await async_setup_platform(hass, {}, async_add_entities)


class URTDiagnosticSensor(CoordinatorEntity[URTCoordinator], SensorEntity):
    _attr_has_entity_name = False

    def __init__(
        self, coordinator: URTCoordinator, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"urt_{description.key}"

    @property
    def native_value(self) -> str | float | None:
        if self.entity_description.key == "ducted_active_room":
            return self.coordinator.data.active_room
        if self.entity_description.key == "ducted_max_delta":
            return self.coordinator.data.max_delta
        return self.coordinator.data.requested_setpoint

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "ducted_active_room":
            return None
        return self.coordinator.data.extra
