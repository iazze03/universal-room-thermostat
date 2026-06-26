"""Virtual room climate entities for Universal Room Thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ATTR_TEMPERATURE, ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PRESETS
from .coordinator import URTCoordinator
from .logic import preset_target
from .models import RoomConfig


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up one virtual climate per configured room."""
    coordinator: URTCoordinator = hass.data[DOMAIN]
    async_add_entities(
        URTRoomClimate(coordinator, room) for room in coordinator.rooms.values()
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up URT climate entities from a config entry."""
    coordinator: URTCoordinator = hass.data[DOMAIN]
    async_add_entities(
        URTRoomClimate(coordinator, room) for room in coordinator.rooms.values()
    )


class URTRoomClimate(
    CoordinatorEntity[URTCoordinator], ClimateEntity, RestoreEntity
):
    """The only climate entity the user needs to operate for a room."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = list(PRESETS)

    def __init__(self, coordinator: URTCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator)
        self.room = room
        self._attr_name = f"URT {room.name}"
        self._attr_unique_id = f"urt_{room.key}"
        self._attr_temperature_unit = coordinator.hass.config.units.temperature_unit
        self._attr_min_temp = coordinator.min_temperature
        self._attr_max_temp = coordinator.max_temperature
        self._attr_target_temperature_step = coordinator.target_temperature_step

    @property
    def runtime(self):
        return self.coordinator.runtime[self.room.key]

    @property
    def available(self) -> bool:
        return self.runtime.current_temperature is not None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if self.room.supports_cooling:
            modes.append(HVACMode.COOL)
        return modes

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self.runtime.hvac_mode)

    @property
    def hvac_action(self) -> HVACAction:
        try:
            return HVACAction(self.runtime.hvac_action)
        except ValueError:
            return HVACAction.IDLE

    @property
    def target_temperature(self) -> float:
        return self.runtime.target_temperature

    @property
    def current_temperature(self) -> float | None:
        return self.runtime.current_temperature

    @property
    def current_humidity(self) -> float | None:
        return self.runtime.current_humidity

    @property
    def preset_mode(self) -> str:
        return self.runtime.preset_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "cooling_type": self.room.cooling_type,
            "cooling_request": self.runtime.cooling_request,
            "cooling_delta": round(self.runtime.cooling_delta, 2),
            "effective_cooling_target": self.runtime.effective_cooling_target,
            "priority": self.runtime.priority,
            "priority_reason": self.runtime.priority_reason,
            "house_mode": self.coordinator.house_mode,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_state()
        if restored is None:
            return
        if restored.state in {mode.value for mode in self.hvac_modes}:
            self.runtime.hvac_mode = restored.state
        target = restored.attributes.get(ATTR_TEMPERATURE)
        if isinstance(target, (int, float)):
            self.runtime.target_temperature = self.coordinator.clamp_temperature(
                float(target)
            )
        preset = restored.attributes.get("preset_mode")
        if preset in PRESETS:
            self.runtime.preset_mode = preset
        self.coordinator.room_changed()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"HVAC mode {hvac_mode} is unavailable for {self.room.key}")
        previous = self.runtime.hvac_mode
        self.runtime.hvac_mode = hvac_mode
        if previous != hvac_mode and hvac_mode != HVACMode.OFF:
            self.runtime.target_temperature = preset_target(
                self.runtime.preset_mode,
                hvac_mode,
                self.coordinator.heating_presets,
                self.coordinator.cooling_presets,
            )
            await self.coordinator.async_sync_ui_target(self.room.key)
        self.async_write_ha_state()
        self.coordinator.room_changed()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self.runtime.target_temperature = self.coordinator.clamp_temperature(
            float(temperature)
        )
        await self.coordinator.async_sync_ui_target(self.room.key)
        self.async_write_ha_state()
        self.coordinator.room_changed()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in PRESETS:
            raise ValueError(f"Unknown URT preset: {preset_mode}")
        self.runtime.preset_mode = preset_mode
        self.runtime.target_temperature = preset_target(
            preset_mode,
            self.runtime.hvac_mode,
            self.coordinator.heating_presets,
            self.coordinator.cooling_presets,
        )
        await self.coordinator.async_sync_ui_target(self.room.key)
        self.async_write_ha_state()
        self.coordinator.room_changed()
