"""Cooling request binary sensors for Universal Room Thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COOLING_DUCTED, DOMAIN
from .coordinator import URTCoordinator
from .models import RoomConfig


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    coordinator: URTCoordinator = hass.data[DOMAIN]
    entities: list[BinarySensorEntity] = [URTDuctedRequestSensor(coordinator)]
    entities.extend(
        URTRoomRequestSensor(coordinator, room)
        for room in coordinator.rooms.values()
        if room.cooling_type == COOLING_DUCTED
    )
    async_add_entities(entities)


class URTDuctedRequestSensor(CoordinatorEntity[URTCoordinator], BinarySensorEntity):
    _attr_has_entity_name = False
    _attr_name = "URT Ducted Cooling Requested"
    _attr_unique_id = "urt_ducted_cooling_requested"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.ducted_cooling_requested


class URTRoomRequestSensor(CoordinatorEntity[URTCoordinator], BinarySensorEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: URTCoordinator, room: RoomConfig) -> None:
        super().__init__(coordinator)
        self.room = room
        self._attr_name = f"URT {room.name} Cooling Request"
        self._attr_unique_id = f"urt_{room.key}_cooling_request"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.room_requests.get(self.room.key, False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self.coordinator.runtime[self.room.key]
        return {
            "delta": round(runtime.cooling_delta, 2),
            "effective_target": runtime.effective_cooling_target,
            "priority": runtime.priority,
            "priority_reason": runtime.priority_reason,
        }
