import contextlib
import io
import unittest
from datetime import datetime

from amr_sim_models import Location, PayloadType
from amr_sim_task_generation import TaskGenerationManager
from amr_sim_time_utils import SimulationClock
from simulator import Simulation


class DropoffZoneTests(unittest.TestCase):
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
