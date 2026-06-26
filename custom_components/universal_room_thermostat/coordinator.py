"""State coordinator for Universal Room Thermostat."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.components.climate import ATTR_TEMPERATURE
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, HOUSE_MODE_AUTO, HOUSE_MODES
from .controller import DuctedACController
from .models import ControllerSnapshot, RoomConfig, RoomRuntime

_LOGGER = logging.getLogger(__name__)


class URTCoordinator(DataUpdateCoordinator[ControllerSnapshot]):
    """Keep a coherent in-memory view of every room and actuator."""

    def __init__(
        self,
        hass: HomeAssistant,
        rooms: Mapping[str, RoomConfig],
        global_config: dict[str, Any],
        ducted_config: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=None,
            name=DOMAIN,
            update_interval=None,
        )
        self.rooms = dict(rooms)
        self.runtime = {key: RoomRuntime() for key in rooms}
        self.global_config = global_config
        self.mode_entity: str = global_config["mode_entity"]
        self.maintenance_cooling_target = float(
            global_config["maintenance_cooling_target"]
        )
        self.cooling_tolerance = float(global_config["cooling_tolerance"])
        self.heating_presets = dict(global_config["heating_presets"])
        self.cooling_presets = dict(global_config["cooling_presets"])
        self.cooling_presets["comfort"] = float(
            global_config["comfort_cooling_target"]
        )
        self.min_temperature = float(global_config["min_temperature"])
        self.max_temperature = float(global_config["max_temperature"])
        self.target_temperature_step = float(global_config["target_temperature_step"])
        self.sync_ui_climate = bool(global_config["sync_ui_climate"])
        self.ducted_entity: str = ducted_config["climate_entity"]
        self.controller = DuctedACController(hass, self, ducted_config)
        self.data = ControllerSnapshot(
            room_requests={key: False for key in rooms}
        )
        self._remove_listener: Any = None

    @property
    def house_mode(self) -> str:
        """Return a sanitized whole-house mode."""
        state = self.hass.states.get(self.mode_entity)
        if state is None:
            return HOUSE_MODE_AUTO
        mode = state.state.lower()
        if mode not in HOUSE_MODES:
            return HOUSE_MODE_AUTO
        return mode

    async def async_start(self) -> None:
        """Subscribe to all relevant entities and take an initial snapshot."""
        entity_ids = {self.mode_entity, self.ducted_entity}
        for room in self.rooms.values():
            entity_ids.update(room.heat_climates)
            entity_ids.update(
                entity_id
                for entity_id in (
                    room.temperature_sensor,
                    room.humidity_sensor,
                    room.ui_climate,
                    room.presence_entity,
                    room.occupancy_entity,
                    room.comfort_entity,
                    room.split_climate,
                )
                if entity_id
            )
        self._remove_listener = async_track_state_change_event(
            self.hass, entity_ids, self._async_state_changed
        )
        self._refresh_measurements()
        self.controller.request_evaluation(immediate=True)

    @callback
    def _async_state_changed(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        new_state: State | None = event.data.get("new_state")
        for key, room in self.rooms.items():
            runtime = self.runtime[key]
            if entity_id == room.temperature_sensor:
                runtime.current_temperature = self._numeric_state(new_state)
            elif entity_id == room.humidity_sensor:
                runtime.current_humidity = self._numeric_state(new_state)
            elif entity_id == room.ui_climate and new_state is not None:
                target = new_state.attributes.get(ATTR_TEMPERATURE)
                if isinstance(target, (int, float)):
                    runtime.target_temperature = self.clamp_temperature(float(target))
                # W100 is an optional wall setpoint interface. Its own HVAC
                # state is intentionally not mirrored: doing so could let a
                # heat-only display overwrite a virtual COOL selection.
        self.controller.request_evaluation()

    def _refresh_measurements(self) -> None:
        for key, room in self.rooms.items():
            self.runtime[key].current_temperature = self._numeric_state(
                self.hass.states.get(room.temperature_sensor)
            )
            if room.humidity_sensor:
                self.runtime[key].current_humidity = self._numeric_state(
                    self.hass.states.get(room.humidity_sensor)
                )

    @staticmethod
    def _numeric_state(state: State | None) -> float | None:
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def is_on(self, entity_id: str | None) -> bool:
        return bool(entity_id and self.hass.states.is_state(entity_id, STATE_ON))

    def clamp_temperature(self, value: float) -> float:
        return max(self.min_temperature, min(self.max_temperature, value))

    @callback
    def publish_snapshot(self, snapshot: ControllerSnapshot) -> None:
        """Notify every CoordinatorEntity after an atomic evaluation."""
        self.async_set_updated_data(snapshot)

    @callback
    def room_changed(self) -> None:
        self.controller.request_evaluation()

    async def async_sync_ui_target(self, room_key: str) -> None:
        """Mirror a virtual target to the optional wall UI climate."""
        room = self.rooms[room_key]
        if not self.sync_ui_climate or not room.ui_climate:
            return
        target = self.runtime[room_key].target_temperature
        state = self.hass.states.get(room.ui_climate)
        existing = state.attributes.get(ATTR_TEMPERATURE) if state else None
        if isinstance(existing, (int, float)) and abs(float(existing) - target) < 0.05:
            return
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": room.ui_climate, ATTR_TEMPERATURE: target},
            blocking=False,
        )
