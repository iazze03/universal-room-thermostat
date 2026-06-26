"""Unit tests for URT's Home Assistant-independent decision engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "universal_room_thermostat"
PACKAGE = "custom_components.universal_room_thermostat"


def _load(name: str):
    fullname = f"{PACKAGE}.{name}"
    spec = importlib.util.spec_from_file_location(fullname, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
const = _load("const")
models = _load("models")
logic = _load("logic")


class CoolingLogicTests(unittest.TestCase):
    def room(self, key: str, cooling_type: str):
        return models.RoomConfig(
            key=key,
            name=key,
            temperature_sensor=f"sensor.{key}",
            cooling_type=cooling_type,
        )

    def request(
        self,
        key: str,
        delta: float,
        priority: int,
        cooling_type: str = const.COOLING_DUCTED,
    ):
        return models.CoolingRequest(
            room_key=key,
            delta=delta,
            target=25.0,
            priority=priority,
            priority_reason="test",
            cooling_type=cooling_type,
        )

    def test_absent_room_uses_maintenance_instead_of_being_ignored(self):
        room = self.room("camera_fra", const.COOLING_DUCTED)
        runtime = models.RoomRuntime(
            hvac_mode="cool", target_temperature=25.0, current_temperature=28.5
        )
        request = logic.make_cooling_request(
            room,
            runtime,
            owner_present=False,
            occupied=False,
            comfort_signal=False,
            maintenance_target=28.0,
            tolerance=0.3,
        )
        self.assertIsNotNone(request)
        self.assertEqual(request.target, 28.0)
        self.assertEqual(request.priority, 200)
        self.assertEqual(request.priority_reason, "maintenance")

    def test_absent_room_below_maintenance_does_not_request(self):
        room = self.room("camera_fra", const.COOLING_DUCTED)
        runtime = models.RoomRuntime(
            hvac_mode="cool", target_temperature=25.0, current_temperature=27.9
        )
        request = logic.make_cooling_request(
            room,
            runtime,
            owner_present=False,
            occupied=False,
            comfort_signal=False,
            maintenance_target=28.0,
            tolerance=0.3,
        )
        self.assertIsNone(request)
        self.assertFalse(runtime.cooling_request)

    def test_priority_wins_before_delta(self):
        comfort = self.request("camera_fra", 0.5, 500)
        maintenance = self.request("camera_ale", 3.5, 200)
        decision = logic.choose_cooling_decision([maintenance, comfort])
        self.assertEqual(decision.guide_room, "camera_fra")
        self.assertEqual(decision.requested_setpoint, 24.0)
        self.assertEqual(decision.max_delta, 3.5)

    def test_delta_breaks_equal_priority_tie(self):
        low = self.request("camera_fra", 0.8, 400)
        high = self.request("camera_ale", 1.8, 400)
        decision = logic.choose_cooling_decision([low, high])
        self.assertEqual(decision.guide_room, "camera_ale")

    def test_salon_only_uses_split_not_ducted(self):
        salon = self.request("salone", 0.8, 300, const.COOLING_HYBRID)
        decision = logic.choose_cooling_decision([salon])
        self.assertFalse(decision.ducted_on)
        self.assertTrue(decision.split_on)
        self.assertIsNone(decision.requested_setpoint)

    def test_rooms_plus_salon_low_delta_use_only_ducted(self):
        room = self.request("camera_fra", 1.2, 400)
        salon = self.request("salone", 0.8, 300, const.COOLING_HYBRID)
        decision = logic.choose_cooling_decision([room, salon], salon_boost_delta=2.0)
        self.assertTrue(decision.ducted_on)
        self.assertFalse(decision.split_on)

    def test_rooms_plus_hot_salon_use_both(self):
        room = self.request("camera_fra", 1.2, 400)
        salon = self.request("salone", 2.1, 300, const.COOLING_HYBRID)
        decision = logic.choose_cooling_decision([room, salon], salon_boost_delta=2.0)
        self.assertTrue(decision.ducted_on)
        self.assertTrue(decision.split_on)

    def test_daikin_setpoint_thresholds(self):
        self.assertEqual(logic.cooling_setpoint(2.01, 22, 23, 24), 22)
        self.assertEqual(logic.cooling_setpoint(1.01, 22, 23, 24), 23)
        self.assertEqual(logic.cooling_setpoint(1.0, 22, 23, 24), 24)


if __name__ == "__main__":
    unittest.main()
