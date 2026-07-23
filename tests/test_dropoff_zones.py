import contextlib
import io
import unittest
from datetime import datetime

from amr_sim_models import Location, PayloadType, Task
from amr_sim_task_generation import TaskGenerationManager
from amr_sim_time_utils import SimulationClock
from simulator import Simulation


class DropoffZoneTests(unittest.TestCase):
    def test_payload_action_times_use_load_unload_completion_not_route_finish(self):
        times = Simulation._payload_action_times(
            [
                {"type": "pickup", "duration": 10},
                {"type": "travel", "duration": 20},
                {"type": "dropoff", "duration": 5},
                {"type": "wash_cycle", "duration": 30},
            ],
            100.0,
        )

        self.assertEqual(110.0, times["pickup"][""])
        self.assertEqual(135.0, times["dropoff"][""])

    def test_multi_stop_payload_action_times_are_recorded_per_task(self):
        times = Simulation._payload_action_times(
            [
                {"type": "pickup", "duration": 5, "task_ids": ["T1", "T2"]},
                {"type": "travel", "duration": 10},
                {"type": "dropoff", "duration": 4, "task_ids": ["T1"]},
                {"type": "travel", "duration": 6},
                {"type": "dropoff", "duration": 4, "task_ids": ["T2"]},
            ],
            50.0,
            multi_stop=True,
        )

        self.assertEqual({"T1": 69.0, "T2": 79.0}, times["dropoff"])

    def test_flexible_space_accepts_any_payload_that_fits_dimensions(self):
        config = self._config()
        zone = next(
            location
            for location in config["locations"]
            if location["name"] == "Zone"
        )
        zone["inventory_spaces"] = [
            {
                "name": "Flexible template space",
                "length_m": 1.2,
                "width_m": 0.8,
                "height_m": 1.5,
                "payload_slots": [{"payload": "Trolley"}],
            }
        ]
        config["payloads"].extend(
            [
                {
                    "name": "Different payload",
                    "weight_kg": 10,
                    "length_m": 0.75,
                    "width_m": 1.1,
                    "height_m": 1.4,
                },
                {
                    "name": "Too tall",
                    "weight_kg": 10,
                    "length_m": 0.7,
                    "width_m": 0.7,
                    "height_m": 1.6,
                },
            ]
        )

        sim = Simulation(config)
        space = sim.inventory_spaces_by_location["Zone"][0]

        self.assertTrue(space["flexible"])
        self.assertTrue(
            sim._inventory_space_can_fit_payload(
                space, sim.payloads["Different payload"]
            )
        )
        self.assertFalse(
            sim._inventory_space_can_fit_payload(space, sim.payloads["Too tall"])
        )

    def test_flexible_assignment_uses_smallest_space_that_fits(self):
        config = self._config()
        zone = next(
            location
            for location in config["locations"]
            if location["name"] == "Zone"
        )
        zone["inventory_spaces"] = [
            {
                "name": "Large",
                "length_m": 2.0,
                "width_m": 2.0,
                "height_m": 2.0,
                "flexible": True,
            },
            {
                "name": "Best fit",
                "length_m": 1.0,
                "width_m": 0.6,
                "height_m": 1.2,
                "flexible": True,
            },
        ]

        sim = Simulation(config)
        selected = sim._find_free_inventory_space(
            "Zone", sim.payloads["Trolley"]
        )

        self.assertIsNotNone(selected)
        self.assertEqual("Best fit", selected["name"])

    def test_department_zone_redirects_generated_amr_task(self):
        locations = {
            name: Location(name, 0, float(index), 0.0)
            for index, name in enumerate(("Store", "Zone", "Ward"))
        }
        payloads = {
            "Trolley": PayloadType("Trolley", 20.0, 1.0, 0.6, 1.2),
            "Empty Trolley": PayloadType("Empty Trolley", 10.0, 1.0, 0.6, 1.2),
        }
        config = self._config()
        manager = TaskGenerationManager(
            config,
            SimulationClock(datetime(2026, 1, 5)),
            locations,
            payloads,
        )

        records = manager.update_until(901.0)

        self.assertEqual(1, len(records))
        task = records[0].task
        self.assertEqual("Store", task.pickup)
        self.assertEqual("Zone", task.dropoff)
        self.assertEqual("Zone", task.dropoff_zone)
        self.assertEqual("Ward", task.final_destination)
        self.assertTrue(task.requires_staff)
        self.assertTrue(task.return_enabled)
        self.assertEqual("Empty Trolley", task.return_payload)
        self.assertEqual("allow_temporary_overflow", task.dropoff_zone_capacity_policy)

    def test_tracked_item_usage_is_shared_between_department_containers(self):
        config = self._config()
        config["departments"][0]["days_active"] = ["mon", "tue", "wed"]
        config["departments"][0]["task_generation_locations"]["stores"][
            "pickup_dropoff_locations"
        ] = ["Ward", "Ward 2"]
        category = config["task_generation"]["categories"]["stores"]["departments"][
            "D1"
        ]
        category.update(
            {
                "generation_mode": "threshold",
                "scheduled_times": [],
                "tracked_item_exchange": True,
                "exchange_mode": "top_up_only",
            }
        )
        locations = {
            name: Location(name, 0, float(index), 0.0)
            for index, name in enumerate(("Store", "Zone", "Ward", "Ward 2"))
        }
        payloads = {
            "Trolley": PayloadType(
                "Trolley",
                20.0,
                1.0,
                0.6,
                1.2,
                track_items=True,
                items={
                    "Supply": {
                        "max": 10,
                        "top_up_threshold": 2,
                        "consumption_per_day": 10,
                        "exchange_payload": "Trolley",
                        "source_location": "Store",
                    }
                },
            ),
            "Empty Trolley": PayloadType(
                "Empty Trolley", 10.0, 1.0, 0.6, 1.2
            ),
        }
        manager = TaskGenerationManager(
            config,
            SimulationClock(datetime(2026, 1, 5)),
            locations,
            payloads,
        )

        # The department consumes ten units/day in total. With two containers,
        # each resource loses five units rather than ten.
        self.assertEqual([], manager.update_until(86400.0))
        runtime = manager.generators[0].item_runtime["stores:D1"]
        self.assertEqual(
            {"Ward": {"Supply": 5.0}, "Ward 2": {"Supply": 5.0}},
            runtime["resource_quantities"],
        )

        records = manager.update_until(172800.0)

        self.assertEqual(2, len(records))
        self.assertEqual(
            {"Ward", "Ward 2"},
            {record.task.final_destination for record in records},
        )

    def test_zone_capacity_policy_is_category_wide(self):
        config = self._config()
        category = config["task_generation"]["categories"]["stores"]
        category["dropoff_zone_capacity_policy"] = "wait_for_space"
        category["departments"]["D1"][
            "dropoff_zone_capacity_policy"
        ] = "allow_temporary_overflow"
        manager = TaskGenerationManager(
            config,
            SimulationClock(datetime(2026, 1, 5)),
            {
                name: Location(name, 0, float(index), 0.0)
                for index, name in enumerate(("Store", "Zone", "Ward"))
            },
            {
                "Trolley": PayloadType("Trolley", 20.0, 1.0, 0.6, 1.2),
                "Empty Trolley": PayloadType(
                    "Empty Trolley", 10.0, 1.0, 0.6, 1.2
                ),
            },
        )

        task = manager.update_until(901.0)[0].task

        self.assertEqual("wait_for_space", task.dropoff_zone_capacity_policy)

    def test_zone_overflow_and_staff_collection_delay_are_configurable(self):
        config = self._config()
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category["scheduled_times"] = ["00:01", "00:02"]
        category["staff_collection_delay_minutes"] = 5
        category["dropoff_zone_capacity_policy"] = "allow_temporary_overflow"

        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        outbound = [
            row
            for row in sim.completed_task_records
            if row.get("pickup") == "Store" and row.get("dropoff") == "Zone"
        ]
        self.assertEqual(2, len(outbound))
        self.assertFalse(sim.failed_task_ids)
        self.assertGreaterEqual(
            sim.location_storage_peak.get("Zone", {}).get("peak_payload_count", 0),
            2,
        )

        first_delivery = next(
            row
            for row in sim.verbose_rows
            if row.get("event_type") == "task_complete"
            and row.get("from_location") == "Store"
            and row.get("to_location") == "Zone"
        )
        first_staff_leg = next(
            row
            for row in sim.verbose_rows
            if row.get("event_type") == "staff_payload_transport"
            and row.get("status") == "staff_payload_delivery"
        )
        self.assertGreaterEqual(
            float(first_staff_leg["sim_time_sec"]),
            float(first_delivery["sim_time_sec"]) + (5 * 60),
        )

    def test_zone_return_delay_includes_handling_instead_of_adding_it(self):
        config = self._config()
        config["simulation"]["end_datetime"] = "2026-01-05T02:00:00"
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category["staff_handling_minutes"] = 15
        category["return_delay_minutes"] = 45

        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        assignment = sim.staff_assignments[0]
        # Zone -> Ward and Ward -> Zone are 10 seconds each. The configured
        # 15-minute handling occurs within the 45-minute return delay.
        self.assertEqual((45 * 60) + 20, assignment["duration_sec"])
        handling = next(
            row
            for row in sim.verbose_rows
            if row.get("event_type") == "staff_payload_handling"
        )
        self.assertEqual(45 * 60, handling["duration_sec"])
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)

    def test_tracked_exchange_leaves_full_payload_and_returns_empty_instance(self):
        config = self._config()
        trolley = next(
            payload
            for payload in config["payloads"]
            if payload["name"] == "Trolley"
        )
        trolley["track_items"] = True
        trolley["items"] = {
            "Supply": {
                "max": 10,
                "top_up_threshold": 2,
                "consumption_per_day": 1,
                "exchange_payload": "Trolley",
                "source_location": "Store",
            }
        }
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category["tracked_item_exchange"] = True
        category["exchange_mode"] = "top_up_only"
        category["return_payload"] = "Trolley"
        category["return_delay_minutes"] = 0
        category["staff_handling_minutes"] = 1

        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        self.assertEqual(2, len(sim.completed_task_records))
        outbound, returned = sim.completed_task_records
        self.assertNotEqual(
            outbound["payload_instance_id"], returned["payload_instance_id"]
        )
        ward_records = sim.payload_instance_store.records_at("Ward")
        self.assertEqual(1, len(ward_records))
        self.assertEqual("full", ward_records[0].metadata.get("container_state"))
        self.assertTrue(
            any(
                row.get("event_type") == "staff_payload_exchange"
                and row.get("status") == "payload_exchange"
                for row in sim.verbose_rows
            )
        )
        self.assertTrue(
            any(
                row.get("event_type") == "amr_exchange_hold"
                and row.get("status") == "waiting_for_exchange"
                for row in sim.verbose_rows
            )
        )
        self.assertFalse(sim.failed_task_ids)

    def test_global_staff_speed_and_handling_control_zone_movement(self):
        config = self._config()
        staff = config["task_generation"]["staff_config"]
        staff["walking_speed_m_per_sec"] = 0.5
        staff["default_handling_minutes"] = 2
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category["staff_handling_minutes"] = 0
        category["return_delay_minutes"] = 0

        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        # Each 10 m staff leg takes 20 seconds at the global 0.5 m/s speed,
        # with the global two-minute handling time between the legs.
        self.assertEqual(160, sim.staff_assignments[0]["duration_sec"])

    def test_full_zone_handoff_returns_payload_to_zone_then_source(self):
        sim = Simulation(self._config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        self.assertEqual(2, len(sim.completed_task_records))
        outbound, returned = sim.completed_task_records
        self.assertEqual(("Store", "Zone"), (outbound["pickup"], outbound["dropoff"]))
        self.assertEqual(("Zone", "Store"), (returned["pickup"], returned["dropoff"]))
        self.assertEqual("Zone", sim.staff_assignments[0]["location"])
        self.assertTrue(
            any(
                row.get("event_type") == "staff_payload_transport"
                and row.get("from_location") == "Zone"
                and row.get("to_location") == "Ward"
                for row in sim.verbose_rows
            )
        )
        staff_legs = [
            row
            for row in sim.verbose_rows
            if row.get("event_type") == "staff_payload_transport"
        ]
        self.assertEqual(2, len(staff_legs))
        self.assertEqual(
            ("Zone", "Ward", "staff_payload_delivery"),
            (
                staff_legs[0]["from_location"],
                staff_legs[0]["to_location"],
                staff_legs[0]["status"],
            ),
        )
        self.assertEqual(
            ("Ward", "Zone", "staff_payload_return"),
            (
                staff_legs[1]["from_location"],
                staff_legs[1]["to_location"],
                staff_legs[1]["status"],
            ),
        )
        self.assertEqual("Empty Trolley", staff_legs[1]["payload"])
        self.assertFalse(sim.payload_instance_store.records_at("Zone"))

    def test_single_stop_rows_publish_onboard_payload_after_pickup(self):
        sim = Simulation(self._config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        pickup_index = next(
            index
            for index, row in enumerate(sim.verbose_rows)
            if row.get("event_type") == "segment_pickup"
        )
        pickup_row = sim.verbose_rows[pickup_index]
        self.assertIn("Trolley", pickup_row["onboard_payloads"])
        travel_row = next(
            row
            for row in sim.verbose_rows[pickup_index + 1:]
            if row.get("event_type") == "segment_corridor"
        )
        self.assertIn("Trolley", travel_row["onboard_payloads"])

    def test_department_team_handles_zone_handoff_outside_primary_hours(self):
        config = self._config()
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category.update(
            {
                "requires_staff": True,
                "staff_resource_name": "Stores team",
                "staff_use_custom_working_hours": True,
                "staff_working_hours": {
                    "mon": {
                        "enabled": True,
                        "start_time": "06:00",
                        "end_time": "14:00",
                    }
                },
                "staff_department_fallback_enabled": True,
                "staff_department_fallback_resource_name": "Ward team",
            }
        )

        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        assignment = sim.staff_assignments[0]
        self.assertTrue(assignment["department_staff_fallback"])
        self.assertFalse(assignment["tracked_staff_resource"])
        self.assertEqual("Ward team", assignment["resource_name"])
        self.assertEqual("D1-team-untracked", assignment["person_id"])
        self.assertEqual(
            assignment["requested_start_time"], assignment["start_time"]
        )
        self.assertLess(assignment["start_time"], 6 * 60 * 60)
        self.assertFalse(sim.staff_resource_pools)
        self.assertEqual(2, len(sim.completed_task_records))
        returned = sim.completed_task_records[1]
        self.assertEqual(("Zone", "Store"), (returned["pickup"], returned["dropoff"]))

    def test_primary_team_remains_tracked_during_its_working_hours(self):
        config = self._config()
        config["simulation"]["end_datetime"] = "2026-01-05T06:20:00"
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category.update(
            {
                "scheduled_times": ["06:01"],
                "requires_staff": True,
                "staff_resource_name": "Stores team",
                "staff_use_custom_working_hours": True,
                "staff_working_hours": {
                    "mon": {
                        "enabled": True,
                        "start_time": "06:00",
                        "end_time": "14:00",
                    }
                },
                "staff_department_fallback_enabled": True,
            }
        )

        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        assignment = sim.staff_assignments[0]
        self.assertFalse(assignment.get("department_staff_fallback", False))
        self.assertEqual("Stores team", assignment["resource_name"])
        self.assertTrue(sim.staff_resource_pools)

    def test_movement_only_handoff_returns_previous_payload_without_dwell(self):
        config = self._config()
        trolley = next(
            payload for payload in config["payloads"] if payload["name"] == "Trolley"
        )
        trolley["track_items"] = True
        trolley["items"] = {
            "Supply": {
                "max": 10,
                "top_up_threshold": 2,
                "consumption_per_day": 1,
                "exchange_payload": "Trolley",
                "source_location": "Store",
            }
        }
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category.update(
            {
                "scheduled_times": ["00:01", "00:05"],
                "tracked_item_exchange": True,
                "exchange_mode": "full_exchange",
                "return_payload": "Trolley",
                "staff_handling_minutes": 15,
                "staff_handoff_only": True,
            }
        )

        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        # The two 10 m walking legs remain, but the configured 15-minute dwell
        # is omitted for this movement-only exchange.
        self.assertEqual([20.0, 20.0], [
            assignment["duration_sec"] for assignment in sim.staff_assignments
        ])
        ward_records = sim.payload_instance_store.records_at("Ward")
        self.assertEqual(1, len(ward_records))
        outbound = [
            row
            for row in sim.completed_task_records
            if row.get("pickup") == "Store" and row.get("dropoff") == "Zone"
        ]
        self.assertEqual(2, len(outbound))
        self.assertTrue(
            any(
                row.get("event_type") == "location_payload_exit"
                and row.get("from_location") == "Ward"
                and row.get("payload_instance_id")
                == outbound[0]["payload_instance_id"]
                for row in sim.verbose_rows
            )
        )
    def test_staff_handoff_uses_shortest_available_department_location(self):
        config = self._config()
        ward = next(item for item in config["locations"] if item["name"] == "Ward")
        ward["inventory_spaces"] = [
            {
                "name": "Ward trolley position",
                "length_m": 2,
                "width_m": 2,
                "height_m": 2,
                "flexible": True,
            }
        ]
        config["locations"].append(
            {
                "name": "Ward 2",
                "floor": 0,
                "x": 30,
                "y": 0,
                "inventory_spaces": [
                    {
                        "name": "Ward 2 trolley position",
                        "length_m": 2,
                        "width_m": 2,
                        "height_m": 2,
                        "flexible": True,
                    }
                ],
            }
        )
        config["corridors"]["edges"].append(
            {"from": "Zone", "to": "Ward 2", "bidirectional": True}
        )
        sim = Simulation(config)
        task = Task(
            id="HANDOFF",
            pickup="Store",
            dropoff="Zone",
            payload="Trolley",
            release_time=0.0,
            dropoff_zone="Zone",
            final_destination="Ward 2",
            final_destination_candidates=["Ward 2", "Ward"],
        )

        self.assertEqual("Ward", sim._select_staff_final_destination(task))
        sim.staff_destination_reservations.clear()
        sim.inventory_spaces_by_location["Ward"][0].update(
            {
                "occupied": True,
                "payload": "Trolley",
                "payload_instance_id": "occupied",
            }
        )

        self.assertEqual("Ward 2", sim._select_staff_final_destination(task))

    @staticmethod
    def _config():
        return {
            "simulation": {
                "start_datetime": "2026-01-05T00:00:00",
                "end_datetime": "2026-01-05T00:20:00",
                "precompute_static_routes": False,
            },
            "building": {
                "charge_location": "Store",
                "load_unload_time_sec": 1,
                "enable_idle_return": False,
            },
            "locations": [
                {"name": "Store", "floor": 0, "x": 0, "y": 0},
                {
                    "name": "Zone",
                    "floor": 0,
                    "x": 10,
                    "y": 0,
                    "inventory_spaces": [
                        {
                            "name": "Flexible",
                            "length_m": 2,
                            "width_m": 2,
                            "height_m": 2,
                        }
                    ],
                },
                {"name": "Ward", "floor": 0, "x": 20, "y": 0},
            ],
            "corridors": {
                "nodes": [],
                "edges": [
                    {"from": "Store", "to": "Zone", "bidirectional": True},
                    {"from": "Zone", "to": "Ward", "bidirectional": True},
                ],
            },
            "payloads": [
                {
                    "name": "Trolley",
                    "weight_kg": 20,
                    "length_m": 1,
                    "width_m": 0.6,
                    "height_m": 1.2,
                },
                {
                    "name": "Empty Trolley",
                    "weight_kg": 10,
                    "length_m": 1,
                    "width_m": 0.6,
                    "height_m": 1.2,
                },
            ],
            "amrs": [
                {
                    "id": "AMR",
                    "quantity": 1,
                    "payload_capacity_kg": 100,
                    "payload_length_capacity_m": 2,
                    "payload_width_capacity_m": 2,
                    "payload_height_capacity_m": 2,
                    "speed_m_per_sec": 2,
                    "battery_capacity_kwh": 10,
                    "battery_charge_rate_kw": 2,
                    "recharge_threshold_percent": 1,
                }
            ],
            "lifts": [],
            "tasks": [],
            "departments": [
                {
                    "id": "D1",
                    "name": "Ward department",
                    "enabled": True,
                    "days_active": ["mon"],
                    "operating_start_time": "00:00",
                    "operating_end_time": "24:00",
                    "task_generation_locations": {
                        "stores": {
                            "pickup_dropoff_locations": ["Ward"],
                            "dropoff_zone_locations": ["Zone"],
                        }
                    },
                }
            ],
            "task_generation": {
                "enabled": True,
                "staff_config": {
                    "walking_speed_m_per_sec": 1,
                    "default_handling_minutes": 1,
                    "shift_patterns": {
                        "none": {
                            "start_time": "00:00",
                            "end_time": "24:00",
                            "days_active": ["mon"],
                        }
                    },
                },
                "categories": {
                    "stores": {
                        "enabled": False,
                        "departments": {
                            "D1": {
                                "enabled": True,
                                "generation_mode": "scheduled",
                                "scheduled_times": ["00:01"],
                                "pickup_location": "Store",
                                "department_location_role": "dropoff",
                                "payload": "Trolley",
                                "return_payload": "Empty Trolley",
                                "staff_handling_minutes": 1,
                                "staff_initial_count": 1,
                            }
                        },
                    }
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
