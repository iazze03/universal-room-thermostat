"""Pure decision logic for Universal Room Thermostat.

This module deliberately has no Home Assistant imports, making the safety and
priority rules straightforward to unit-test.
"""

from __future__ import annotations

from collections.abc import Mapping

from .const import COOLING_DUCTED, COOLING_HYBRID
from .models import CoolingDecision, CoolingRequest, RoomConfig, RoomRuntime


def cooling_setpoint(delta: float, high: float, medium: float, low: float) -> float:
    """Translate room error into a conservative ducted AC setpoint."""
    if delta > 2.0:
        return high
    if delta > 1.0:
        return medium
    return low


def room_priority(
    room: RoomConfig,
    *,
    occupied: bool,
    owner_present: bool,
    comfort_signal: bool,
) -> tuple[int, str]:
    """Return the explicit priority tier requested by the specification."""
    if comfort_signal:
        return 500, "occupied_comfort"
    if owner_present:
        return 400, "owner_present"
    if room.key == "salone" and occupied:
        return 300, "living_room_occupied"
    if not (comfort_signal or owner_present or occupied):
        return 200, "maintenance"
    return 100, "absent"


def make_cooling_request(
    room: RoomConfig,
    runtime: RoomRuntime,
    *,
    owner_present: bool,
    occupied: bool,
    comfort_signal: bool,
    maintenance_target: float,
    tolerance: float,
) -> CoolingRequest | None:
    """Build a cooling request without ever dropping an absent room outright."""
    runtime.cooling_request = False
    runtime.cooling_delta = 0.0
    runtime.priority = 0
    runtime.priority_reason = "inactive"
    runtime.effective_cooling_target = None

    if runtime.hvac_mode != "cool" or runtime.current_temperature is None:
        return None

    in_comfort = comfort_signal or owner_present or occupied
    target = (
        runtime.target_temperature
        if in_comfort
        else max(runtime.target_temperature, maintenance_target)
    )
    runtime.effective_cooling_target = target
    delta = runtime.current_temperature - target
    runtime.cooling_delta = delta
    if delta <= tolerance:
        return None

    priority, reason = room_priority(
        room,
        occupied=occupied,
        owner_present=owner_present,
        comfort_signal=comfort_signal,
    )
    runtime.cooling_request = True
    runtime.priority = priority
    runtime.priority_reason = reason
    return CoolingRequest(
        room_key=room.key,
        delta=delta,
        target=target,
        priority=priority,
        priority_reason=reason,
        cooling_type=room.cooling_type,
    )


def choose_cooling_decision(
    requests: list[CoolingRequest],
    *,
    setpoint_high: float = 22.0,
    setpoint_medium: float = 23.0,
    setpoint_low: float = 24.0,
    salon_boost_delta: float = 2.0,
) -> CoolingDecision:
    """Choose the guide room and physical cooling systems.

    Priority wins first and temperature delta is only the tie-breaker. A
    salon-only request uses its dedicated split. Any ducted-room request starts
    the distributed system; the salon split joins only as a high-delta boost.
    """
    if not requests:
        return CoolingDecision()

    ordered = sorted(requests, key=lambda item: (item.priority, item.delta), reverse=True)
    guide = ordered[0]
    ducted_rooms = [item for item in requests if item.cooling_type == COOLING_DUCTED]
    salon = next(
        (
            item
            for item in requests
            if item.room_key == "salone" and item.cooling_type == COOLING_HYBRID
        ),
        None,
    )

    ducted_on = bool(ducted_rooms)
    split_on = bool(salon and (not ducted_rooms or salon.delta >= salon_boost_delta))
    max_delta = max(item.delta for item in requests)
    requested_setpoint = (
        cooling_setpoint(guide.delta, setpoint_high, setpoint_medium, setpoint_low)
        if ducted_on
        else None
    )
    return CoolingDecision(
        requests=tuple(ordered),
        guide_room=guide.room_key,
        max_delta=max_delta,
        requested_setpoint=requested_setpoint,
        ducted_on=ducted_on,
        split_on=split_on,
    )


def preset_target(
    preset: str,
    hvac_mode: str,
    heating_targets: Mapping[str, float],
    cooling_targets: Mapping[str, float],
) -> float:
    """Resolve a preset target for the active room mode."""
    targets = cooling_targets if hvac_mode == "cool" else heating_targets
    return float(targets[preset])
