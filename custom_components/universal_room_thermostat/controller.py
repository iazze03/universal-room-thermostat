"""Physical actuator controller for Universal Room Thermostat."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.components.climate import ATTR_HVAC_MODE, ATTR_TEMPERATURE
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .const import (
    HOUSE_MODE_AUTO,
    HOUSE_MODE_OFF,
    HOUSE_MODE_SUMMER,
    HOUSE_MODE_WINTER,
)
from .logic import choose_cooling_decision, make_cooling_request
from .models import ControllerSnapshot, CoolingDecision

_LOGGER = logging.getLogger(__name__)


class DuctedACController:
    """Arbitrate all HVAC demands and safely command shared equipment."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, config: dict[str, Any]) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.climate_entity: str = config["climate_entity"]
        self.debounce = float(config["debounce"])
        self.min_on_time = float(config["min_on_time"])
        self.min_off_time = float(config["min_off_time"])
        self.off_delay = float(config["off_delay"])
        self.command_interval = float(config["command_interval"])
        self.setpoint_high = float(config["setpoint_high"])
        self.setpoint_medium = float(config["setpoint_medium"])
        self.setpoint_low = float(config["setpoint_low"])
        self.salon_boost_delta = float(config["salon_boost_delta"])
        self.split_heat_enabled = bool(config["split_heat_enabled"])

        self._cancel_timer: Callable[[], None] | None = None
        self._lock = asyncio.Lock()
        self._last_on: float | None = None
        self._last_off: float | None = None
        self._no_duct_request_since: float | None = None
        self._last_commands: dict[str, tuple[float, str, tuple[tuple[str, Any], ...]]] = {}

    @callback
    def request_evaluation(self, *, immediate: bool = False) -> None:
        """Debounce state bursts into one complete evaluation."""
        if self._cancel_timer is not None:
            self._cancel_timer()
        delay = 0.0 if immediate else self.debounce
        self._cancel_timer = async_call_later(self.hass, delay, self._async_timer_fired)

    async def _async_timer_fired(self, _now: Any) -> None:
        self._cancel_timer = None
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        """Recalculate room requests and reconcile every actuator."""
        async with self._lock:
            coordinator = self.coordinator
            house_mode = coordinator.house_mode
            if not coordinator.control_enabled:
                decision = CoolingDecision()
                for runtime in coordinator.runtime.values():
                    runtime.cooling_request = False
                    runtime.hvac_action = "off"
                coordinator.publish_snapshot(
                    self._snapshot(
                        house_mode,
                        decision,
                        extra={"control_enabled": False},
                    )
                )
                return

            cooling_allowed = house_mode in (HOUSE_MODE_SUMMER, HOUSE_MODE_AUTO)

            requests = []
            for key, room in coordinator.rooms.items():
                runtime = coordinator.runtime[key]
                request = make_cooling_request(
                    room,
                    runtime,
                    owner_present=coordinator.is_on(room.presence_entity),
                    occupied=coordinator.is_on(room.occupancy_entity),
                    comfort_signal=coordinator.is_on(room.comfort_entity),
                    maintenance_target=coordinator.maintenance_cooling_target,
                    tolerance=coordinator.cooling_tolerance,
                )
                if request is not None and cooling_allowed:
                    requests.append(request)
                elif not cooling_allowed:
                    runtime.cooling_request = False

            decision = choose_cooling_decision(
                requests,
                setpoint_high=self.setpoint_high,
                setpoint_medium=self.setpoint_medium,
                setpoint_low=self.setpoint_low,
                salon_boost_delta=self.salon_boost_delta,
            )

            # In auto, cooling demand owns the current season and suppresses heat.
            heat_allowed = house_mode == HOUSE_MODE_WINTER or (
                house_mode == HOUSE_MODE_AUTO and not decision.requests
            )
            if house_mode == HOUSE_MODE_AUTO and self._cooling_equipment_active():
                heat_allowed = False
            if house_mode == HOUSE_MODE_OFF:
                heat_allowed = False

            await self._async_reconcile_heat(heat_allowed)
            await self._async_reconcile_cooling(decision, cooling_allowed)
            self._update_actions(decision, heat_allowed)
            coordinator.publish_snapshot(
                self._snapshot(house_mode, decision, extra={"control_enabled": True})
            )

    async def _async_reconcile_heat(self, heat_allowed: bool) -> None:
        """Propagate virtual targets to all configured radiator climates."""
        for key, room in self.coordinator.rooms.items():
            runtime = self.coordinator.runtime[key]
            desired_on = heat_allowed and runtime.hvac_mode == HVACMode.HEAT
            for entity_id in room.heat_climates:
                if desired_on:
                    await self._async_set_temperature(entity_id, runtime.target_temperature)
                    await self._async_set_mode(entity_id, HVACMode.HEAT)
                else:
                    await self._async_set_mode(entity_id, HVACMode.OFF)

    async def _async_reconcile_cooling(
        self, decision: CoolingDecision, cooling_allowed: bool
    ) -> None:
        """Apply hybrid rules, timing constraints, and anti-conflict ordering."""
        split_entities = {
            room.split_climate
            for room in self.coordinator.rooms.values()
            if room.split_climate is not None
        }
        split_entity = next(iter(split_entities), None)

        ducted_on = cooling_allowed and decision.ducted_on
        split_on = cooling_allowed and decision.split_on

        if ducted_on or split_on:
            # Absolute invariant: both peers must have left HEAT/AUTO before
            # either one may receive COOL. Forced OFF calls are blocking.
            if split_entity:
                await self._async_ensure_not_heat_or_auto(split_entity)
            await self._async_ensure_not_heat_or_auto(self.climate_entity)

        if cooling_allowed:
            await self._async_apply_ducted(ducted_on, decision.requested_setpoint)
        else:
            # Whole-house winter/off changes are safety transitions, not normal
            # demand expiry: do not hold the ducted unit through off_delay.
            await self._async_set_mode(
                self.climate_entity, HVACMode.OFF, force=True
            )

        if split_entity:
            if split_on:
                await self._async_set_mode(split_entity, HVACMode.COOL)
                salon = self.coordinator.runtime.get("salone")
                if salon is not None:
                    await self._async_set_temperature(split_entity, salon.target_temperature)
            elif (
                self.split_heat_enabled
                and self.coordinator.house_mode == HOUSE_MODE_WINTER
                and self.coordinator.runtime.get("salone")
                and self.coordinator.runtime["salone"].hvac_mode == HVACMode.HEAT
            ):
                # Ducted is already forced OFF in winter before split HEAT.
                await self._async_set_mode(
                    self.climate_entity, HVACMode.OFF, force=True
                )
                await self._async_set_mode(split_entity, HVACMode.HEAT)
                await self._async_set_temperature(
                    split_entity, self.coordinator.runtime["salone"].target_temperature
                )
            else:
                await self._async_set_mode(split_entity, HVACMode.OFF)

    async def _async_apply_ducted(self, desired_on: bool, setpoint: float | None) -> None:
        now = monotonic()
        state = self.hass.states.get(self.climate_entity)
        is_on = state is not None and state.state in {
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.AUTO,
            HVACMode.HEAT_COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        }

        # An unsafe external mode never gets a grace period: canalizzato AUTO
        # and HEAT are prohibited regardless of min-on/off settings.
        if state and state.state in (HVACMode.HEAT, HVACMode.AUTO, HVACMode.HEAT_COOL):
            await self._async_set_mode(self.climate_entity, HVACMode.OFF, force=True)
            self._last_off = now
            self._no_duct_request_since = None
            if not desired_on:
                return
            is_on = False

        if desired_on:
            self._no_duct_request_since = None
            if not is_on and self._last_off is not None:
                remaining = self.min_off_time - (now - self._last_off)
                if remaining > 0:
                    self._schedule_after(remaining)
                    return
            await self._async_set_mode(self.climate_entity, HVACMode.COOL)
            if setpoint is not None:
                await self._async_set_temperature(self.climate_entity, setpoint)
            if not is_on:
                self._last_on = now
            return

        if not is_on:
            self._no_duct_request_since = None
            await self._async_set_mode(self.climate_entity, HVACMode.OFF)
            return

        if self._no_duct_request_since is None:
            self._no_duct_request_since = now
        waits = [self.off_delay - (now - self._no_duct_request_since)]
        if self._last_on is not None:
            waits.append(self.min_on_time - (now - self._last_on))
        remaining = max(waits)
        if remaining > 0:
            self._schedule_after(remaining)
            return
        await self._async_set_mode(self.climate_entity, HVACMode.OFF)
        self._last_off = now
        self._no_duct_request_since = None

    async def _async_ensure_not_heat_or_auto(self, entity_id: str) -> None:
        state = self.hass.states.get(entity_id)
        if state and state.state in (HVACMode.HEAT, HVACMode.AUTO, HVACMode.HEAT_COOL):
            await self._async_set_mode(entity_id, HVACMode.OFF, force=True)

    async def _async_set_mode(
        self, entity_id: str, mode: HVACMode, *, force: bool = False
    ) -> None:
        state = self.hass.states.get(entity_id)
        if state is not None and state.state == mode:
            return
        await self._async_command(
            entity_id,
            "set_hvac_mode",
            {ATTR_HVAC_MODE: mode},
            force=force,
        )

    async def _async_set_temperature(self, entity_id: str, temperature: float) -> None:
        state = self.hass.states.get(entity_id)
        current = state.attributes.get(ATTR_TEMPERATURE) if state else None
        if isinstance(current, (int, float)) and abs(float(current) - temperature) < 0.05:
            return
        await self._async_command(
            entity_id, "set_temperature", {ATTR_TEMPERATURE: temperature}
        )

    async def _async_command(
        self,
        entity_id: str,
        service: str,
        payload: dict[str, Any],
        *,
        force: bool = False,
    ) -> None:
        now = monotonic()
        signature = tuple(sorted(payload.items()))
        previous = self._last_commands.get(entity_id)
        if (
            not force
            and previous is not None
            and previous[1:] == (service, signature)
            and now - previous[0] < self.command_interval
        ):
            return
        data = {ATTR_ENTITY_ID: entity_id, **payload}
        _LOGGER.debug("URT command climate.%s %s", service, data)
        await self.hass.services.async_call(
            "climate", service, data, blocking=force
        )
        self._last_commands[entity_id] = (now, service, signature)

    def _schedule_after(self, seconds: float) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
        self._cancel_timer = async_call_later(
            self.hass, timedelta(seconds=max(0.1, seconds)), self._async_timer_fired
        )

    def _update_actions(self, decision: CoolingDecision, heat_allowed: bool) -> None:
        for key, runtime in self.coordinator.runtime.items():
            room = self.coordinator.rooms[key]
            ducted_cooling = self.hass.states.is_state(
                self.climate_entity, HVACMode.COOL
            )
            split_cooling = bool(
                room.split_climate
                and self.hass.states.is_state(room.split_climate, HVACMode.COOL)
            )
            if runtime.hvac_mode == HVACMode.OFF:
                runtime.hvac_action = "off"
            elif runtime.cooling_request and (
                (room.cooling_type == "ducted" and ducted_cooling)
                or (key == "salone" and (ducted_cooling or split_cooling))
            ):
                runtime.hvac_action = "cooling"
            elif runtime.hvac_mode == HVACMode.HEAT and heat_allowed:
                runtime.hvac_action = (
                    "heating"
                    if any(
                        (
                            state := self.hass.states.get(entity_id)
                        ) is not None
                        and state.attributes.get("hvac_action") == "heating"
                        for entity_id in room.heat_climates
                    )
                    else "idle"
                )
            else:
                runtime.hvac_action = "idle"

    def _cooling_equipment_active(self) -> bool:
        if self.hass.states.is_state(self.climate_entity, HVACMode.COOL):
            return True
        return any(
            room.split_climate
            and self.hass.states.is_state(room.split_climate, HVACMode.COOL)
            for room in self.coordinator.rooms.values()
        )

    def _snapshot(
        self,
        house_mode: str,
        decision: CoolingDecision,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ControllerSnapshot:
        snapshot_extra = {
            "request_order": [request.room_key for request in decision.requests],
            "priorities": {
                request.room_key: request.priority for request in decision.requests
            },
        }
        if extra:
            snapshot_extra.update(extra)
        return ControllerSnapshot(
            house_mode=house_mode,
            active_room=decision.guide_room,
            max_delta=round(decision.max_delta, 2),
            requested_setpoint=decision.requested_setpoint,
            ducted_cooling_requested=decision.ducted_on,
            room_requests={
                key: runtime.cooling_request
                for key, runtime in self.coordinator.runtime.items()
            },
            extra=snapshot_extra,
        )
