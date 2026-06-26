"""Configuration and runtime models for URT."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import COOLING_NONE


@dataclass(frozen=True, slots=True)
class RoomConfig:
    """Static room configuration."""

    key: str
    name: str
    temperature_sensor: str
    humidity_sensor: str | None = None
    ui_climate: str | None = None
    heat_climates: tuple[str, ...] = ()
    presence_entity: str | None = None
    occupancy_entity: str | None = None
    comfort_entity: str | None = None
    cooling_type: str = COOLING_NONE
    split_climate: str | None = None

    @property
    def supports_cooling(self) -> bool:
        return self.cooling_type != COOLING_NONE


@dataclass(slots=True)
class RoomRuntime:
    """Restorable user state and calculated room state."""

    hvac_mode: str = "off"
    target_temperature: float = 21.0
    preset_mode: str = "comfort"
    current_temperature: float | None = None
    current_humidity: float | None = None
    cooling_request: bool = False
    cooling_delta: float = 0.0
    effective_cooling_target: float | None = None
    priority: int = 0
    priority_reason: str = "inactive"
    hvac_action: str = "off"


@dataclass(frozen=True, slots=True)
class CoolingRequest:
    """A normalized cooling request consumed by the ducted controller."""

    room_key: str
    delta: float
    target: float
    priority: int
    priority_reason: str
    cooling_type: str


@dataclass(frozen=True, slots=True)
class CoolingDecision:
    """Result of cooling arbitration."""

    requests: tuple[CoolingRequest, ...] = ()
    guide_room: str | None = None
    max_delta: float = 0.0
    requested_setpoint: float | None = None
    ducted_on: bool = False
    split_on: bool = False


@dataclass(slots=True)
class ControllerSnapshot:
    """Coordinator data exposed to entities."""

    house_mode: str = "auto"
    active_room: str | None = None
    max_delta: float = 0.0
    requested_setpoint: float | None = None
    ducted_cooling_requested: bool = False
    room_requests: dict[str, bool] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
