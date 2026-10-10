"""Small engineering cases with expectations derived independently of outputs.

Distances are metres, times seconds, and comparisons use 1e-8 absolute tolerance.
These tests verify graph/capacity approximations, not vehicle swept geometry.
"""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation


def reference_config():
    return {
        "simulation": {
            "start_datetime": "2026-01-05T00:00:00",
            "end_datetime": "2026-01-05T00:10:00",
            "precompute_static_routes": False,
        },
        "building": {"charge_location": "A", "enable_idle_return": False,
                     "load_unload_time_sec": 2},
        "locations": [
            {"name": "A", "floor": 0, "x": 0, "y": 0},
            {"name": "B", "floor": 0, "x": 6, "y": 8},
        ],
        "corridors": {
            "auto_connect": False,
            "nodes": [{"name": "Door", "floor": 0, "x": 3, "y": 4,
                       "has_door": True, "door_clear_width_m": 0.8}],
            "edges": [{"from": "A", "to": "Door", "width_m": 3},
                      {"from": "Door", "to": "B", "width_m": 3}],
        },
        "payloads": [{"name": "Box", "weight_kg": 10, "length_m": 1.0,
                      "width_m": 0.7, "height_m": 1,
                      "allowed_carry_orientations": ["lengthways"]}],
        "amrs": [{"id": "R", "quantity": 1, "length_m": 1, "width_m": 0.6,
                  "payload_capacity_kg": 100, "payload_length_capacity_m": 2,
                  "payload_width_capacity_m": 2, "payload_height_capacity_m": 2,
                  "speed_m_per_sec": 2, "battery_capacity_kwh": 10,
                  "battery_charge_rate_kw": 2, "recharge_threshold_percent": 1}],
        "lifts": [], "tasks": [], "task_generation": {"enabled": False},
    }


class RoutingReferenceTests(unittest.TestCase):
    def setUp(self):
        self.config = reference_config()

    def segments(self, sim, payload=True, orientation="lengthways", reverse=False):
        a, b = ("B", "A") if reverse else ("A", "B")
        return sim._same_floor_segments(
            sim.amrs[0], sim.locations[a], sim.locations[b],
            payload=sim.payloads["Box"] if payload else None,
            orientation=orientation,
        )

    def test_three_four_five_triangle_distance_and_duration(self):
        sim = Simulation(self.config)
        segments, duration, distance = self.segments(sim)
        self.assertEqual([("A", "Door"), ("Door", "B")],
                         [(s["from"], s["to"]) for s in segments])
        self.assertAlmostEqual(10, distance, delta=1e-8)  # 5 + 5
        self.assertAlmostEqual(5, duration, delta=1e-8)  # 10 / 2

    def test_door_restricts_both_incident_directions(self):
        sim = Simulation(self.config)
        for start, end in (("A", "B"), ("B", "A")):
            route = sim._shortest_path_same_floor(0, start, end)
            for edge in route["edges"]:
                self.assertEqual(3, edge["configured_width_m"])
                self.assertEqual(0.8, edge["width_m"])
                self.assertTrue(edge["door_restricted"])

    def test_payload_at_clear_width_fits_but_oversize_does_not(self):
        for width, fits in ((0.8, True), (0.80001, False)):
            with self.subTest(width=width):
                config = copy.deepcopy(self.config)
                config["payloads"][0]["width_m"] = width
                sim = Simulation(config)
                self.assertEqual(fits, self.segments(sim) is not None)

    def test_unloaded_robot_must_fit_door(self):
        self.config["amrs"][0]["width_m"] = 0.9
        self.assertIsNone(self.segments(Simulation(self.config), payload=False))

    def test_rotating_payload_changes_required_cross_width(self):
        sim = Simulation(self.config)
        self.assertIsNotNone(self.segments(sim))
        self.assertIsNone(self.segments(sim, orientation="sideways"))

    def test_wider_alternative_is_used_and_cached_separately(self):
        self.config["corridors"]["edges"].append(
            {"from": "A", "to": "B", "distance_m": 20, "width_m": 2})
        self.config["payloads"][0]["width_m"] = 0.9
        sim = Simulation(self.config)
        # A robot alone can use the 10 m route; its wide load needs 20 m.
        self.assertEqual(10, self.segments(sim, payload=False)[2])
        self.assertEqual(20, self.segments(sim)[2])
        self.assertEqual(10, self.segments(sim, payload=False)[2])
        self.assertEqual(20, self.segments(sim, reverse=True)[2])

    def test_one_way_edges_do_not_create_return_path(self):
        for edge in self.config["corridors"]["edges"]:
            edge["bidirectional"] = False
        sim = Simulation(self.config)
        self.assertIsNotNone(self.segments(sim))
        self.assertIsNone(self.segments(sim, reverse=True))

    def test_explicit_distance_overrides_drawing_distance(self):
        self.config["corridors"]["edges"][0]["distance_m"] = 12
        sim = Simulation(self.config)
        self.assertEqual(17, self.segments(sim)[2])
        self.assertEqual(8.5, self.segments(sim)[1])

    def test_width_filter_does_not_bypass_profile_restrictions(self):
        self.config["corridors"]["edges"].append(
            {"from": "A", "to": "B", "distance_m": 20, "width_m": 2})
        sim = Simulation(self.config)
        rules = {"allowed_edges": {("A", "Door"), ("Door", "B")}}
        self.assertIsNone(sim._shortest_path_same_floor(0, "A", "B", rules, minimum_width_m=0.9))
        self.assertEqual(20, sim._shortest_path_same_floor(0, "A", "B", minimum_width_m=0.9)["distance_m"])

    def test_profile_allowed_edges_are_directional_and_empty_means_unrestricted(self):
        self.config["route_profiles"] = {
            "clean": {"allowed_edges": [["A", "Door"], ["Door", "B"]]},
            "default": {},
        }
        sim = Simulation(self.config)
        rules = sim._resolve_task_route_rules(Task("T", "A", "B", "Box", route_profile="clean"))
        self.assertEqual(10, sim._shortest_path_same_floor(0, "A", "B", rules)["distance_m"])
        self.assertIsNone(sim._shortest_path_same_floor(0, "B", "A", rules))
        self.assertIsNotNone(sim._shortest_path_same_floor(0, "B", "A", {}))

    def test_legacy_task_allowances_extend_profile_and_dirty_label_selects_profile(self):
        self.config["route_profiles"] = {"dirty": {"allowed_nodes": ["A", "Door"]}}
        sim = Simulation(self.config)
        task = Task("T", "A", "B", "Box", labels=["dirty"])
        self.assertIsNone(sim._shortest_path_same_floor(0, "A", "B", sim._resolve_task_route_rules(task)))
        task.allowed_nodes = ["B"]
        self.assertIsNotNone(sim._shortest_path_same_floor(0, "A", "B", sim._resolve_task_route_rules(task)))

    def test_capacity_approximation_changes_at_loaded_envelope_boundary(self):
        sim = Simulation(self.config)
        for width, expected in ((2.0, 2), (1.99, 1)):
            edge = {"width_m": width, "bidirectional": True}
            self.assertEqual(expected, sim._corridor_lane_capacity(edge, sim.amrs[0], sim.payloads["Box"])[0])


class ServiceReferenceTests(unittest.TestCase):
    def test_fast_and_full_assignment_estimates_use_the_passable_detour(self):
        for fast in (False, True):
            with self.subTest(fast_assignment_estimates=fast):
                config = reference_config()
                config["simulation"]["fast_assignment_estimates"] = fast
                config["payloads"][0]["width_m"] = 0.9
                config["corridors"]["edges"].append(
                    {"from": "A", "to": "B", "distance_m": 20, "width_m": 2})
                sim = Simulation(config)
                estimate = sim._estimate_task_for_amr(sim.amrs[0], Task("T", "A", "B", "Box"))
                self.assertIsNotNone(estimate)
                self.assertAlmostEqual(14, estimate["duration"], delta=1e-8)

    def test_fast_estimate_rejects_a_door_the_load_cannot_pass(self):
        config = reference_config()
        config["simulation"]["fast_assignment_estimates"] = True
        config["payloads"][0]["width_m"] = 0.9
        sim = Simulation(config)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], Task("T", "A", "B", "Box")))

    def test_charge_estimate_uses_passable_empty_and_loaded_routes(self):
        config = reference_config()
        config["amrs"][0]["width_m"] = 0.9
        config["corridors"]["edges"].append(
            {"from": "A", "to": "B", "distance_m": 20, "width_m": 2})
        sim = Simulation(config)
        with patch.object(sim, "_plan_charge_cycle_if_needed", wraps=sim._plan_charge_cycle_if_needed) as charge:
            estimate = sim._estimate_task_for_amr(sim.amrs[0], Task("T", "B", "A", "Box"))
        self.assertIsNotNone(estimate)
        # The robot is too wide for the 10 m shortcut on both legs.
        # Each passable 20 m leg takes 10 seconds at 2 m/s.
        self.assertEqual((10, 10), charge.call_args.args[2:4])

    def test_saved_review_scenarios_match_hand_calculations(self):
        root = Path(__file__).resolve().parents[1] / "verification/scenarios"
        for name, expected_seconds in (("door-pass", 9), ("door-blocked", None), ("door-detour", 14)):
            with self.subTest(scenario=name):
                config = json.loads((root / f"{name}.json").read_text())
                sim = Simulation(config, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                if expected_seconds is None:
                    self.assertEqual({"T"}, sim.failed_task_ids)
                    self.assertFalse(sim.completed_task_records)
                else:
                    self.assertFalse(sim.failed_task_ids)
                    self.assertEqual(1, len(sim.completed_task_records))
                    self.assertAlmostEqual(expected_seconds, sim.completed_task_records[0]["duration_sec"], delta=1e-8)

    def test_oversize_delivery_fails_instead_of_staying_pending(self):
        config = reference_config()
        config["payloads"][0]["width_m"] = 0.9
        sim = Simulation(config, verbose=True)
        sim.schedule_task_release(Task("T", "A", "B", "Box"))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({"T"}, sim.failed_task_ids)
        self.assertFalse(sim.completed_task_records)
        self.assertIn("width", sim.failed_tasks[0]["reason"])

    def test_one_delivery_duration_and_repeatability(self):
        results = []
        for _ in range(2):
            sim = Simulation(reference_config(), verbose=True)
            sim.schedule_task_release(Task("T", "A", "B", "Box"))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertFalse(sim.failed_task_ids)
            self.assertEqual(1, len(sim.completed_task_records))
            record = sim.completed_task_records[0]
            # 2 s load + (5+5) m / 2 m/s + 2 s unload = 9 s.
            self.assertAlmostEqual(9, record["duration_sec"], delta=1e-8)
            results.append(sim.completed_task_records)
        self.assertEqual(results[0], results[1])

    def test_location_reservations_allow_touching_intervals(self):
        sim = Simulation(reference_config())
        sim.location_max_concurrency["A"] = 1
        sim._reserve_location("A", 0, 10)
        self.assertEqual(10, sim._find_next_available_time("A", 0, 5))
        self.assertEqual(10, sim._find_next_available_time("A", 10, 5))

    def test_sequential_reservations_do_not_count_as_simultaneous(self):
        sim = Simulation(reference_config())
        sim.location_max_concurrency["A"] = 2
        sim._reserve_location("A", 0, 5)
        sim._reserve_location("A", 5, 10)
        # One existing occupant at any instant: the second slot is free throughout.
        self.assertEqual(0, sim._find_next_available_time("A", 0, 10))

    def test_overlapping_reservations_wait_until_capacity_is_available(self):
        sim = Simulation(reference_config())
        sim.location_max_concurrency["A"] = 2
        sim._reserve_location("A", 0, 6)
        sim._reserve_location("A", 4, 10)
        self.assertEqual(6, sim._find_next_available_time("A", 0, 10))


if __name__ == "__main__":
    unittest.main()
