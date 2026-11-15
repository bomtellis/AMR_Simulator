"""FM planning contract through resolved demand, runtime and lift exports."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

from amr_fm_forecast import actual_activity, compare, initial_policy, native_demand, validate_application
from amr_fm_logistics import reactive_hold
from amr_project import Project
from report.amr_report_analysis import extract_lift_movements
from simulator import Simulation
from tests.test_floor_waypoints import floor_config


def settings(config):
    preview = native_demand(config)
    return preview, {"enabled": True, "categories": {
        key: initial_policy(preview, key) for key in ("catering", "pharmacy")}}


def fixture():
    config = floor_config(transfer=True, waypoint=False)
    config["simulation"].update(end_datetime="2026-01-05T01:00:00")
    config["departments"] = [
        dict(id=key, name=key, enabled=True, operating_start_time="00:00", operating_end_time="24:00")
        for key in ("D1", "D2", "D3")
    ]
    config["task_generation"] = {"enabled": True, "categories": {}}
    for key, department, pickup, dropoff in (
        ("catering", "D1", "A", "B3"), ("pharmacy", "D2", "B3", "A"),
        ("linen", "D3", "B2", "A")
    ):
        config["task_generation"]["categories"][key] = {
            "enabled": False, "departments": {department: {
                "enabled": True, "generation_mode": "threshold" if key == "linen" else "scheduled",
                "pickup_location": pickup, "dropoff_location": dropoff, "payload": "Box",
                "scheduled_times": ["00:45"], "base_daily_volume_m3": 10, "threshold_volume_m3": 0.1,
                "requires_staff": False, "return_enabled": key == "catering", "return_payload": "Box",
                "return_delay_minutes": 5,
            }}
        }
    return config


class FMLogisticsTests(TestCase):
    def test_coordinated_waves_share_lifts_without_changing_demand(self):
        config = fixture()
        before = deepcopy(config)
        baseline, plan = settings(config)
        results = {option["strategy"]: option for option in compare(config, plan, baseline)["results"]}
        self.assertEqual(before, config)
        coordinated, current = results["coordinated"], results["current"]
        self.assertEqual(2, coordinated["totals"]["tasks"])
        self.assertEqual(2, coordinated["totals"]["outbound_up"])
        self.assertEqual(2, coordinated["totals"]["outbound_down"])
        self.assertEqual(2, coordinated["totals"]["return_down"])
        self.assertLess(coordinated["totals"]["peak_lift_seconds"], current["totals"]["peak_lift_seconds"])
        self.assertEqual(0, coordinated["totals"].get("late", 0))
        self.assertIn("linen", {rule["category"] for rule in compare(config, plan, baseline)["runtime"]})
        validate_application(config, coordinated["settings"], baseline)

    def test_apply_persists_and_normal_generator_releases_each_once(self):
        config = fixture()
        baseline, plan = settings(config)
        validate_application(config, plan, baseline)
        config["task_generation"]["fm_logistics"] = plan
        with TemporaryDirectory() as folder:
            project = Project()
            path = Path(folder) / "fm.amrproj"
            project.save(path, config)
            restored = Project.open(path).configuration()
            self.assertEqual(plan, restored["task_generation"]["fm_logistics"])
            sim = Simulation(restored, verbose=False)
            manager = sim.task_generation_manager
            releases = manager.scheduled_wake_times(3600)
            self.assertIn(900, releases)
            emitted = [row.task for row in manager.update_schedules_until(900)]
            self.assertEqual(2, len(emitted))
            self.assertEqual([], manager.update_schedules_until(900))
            self.assertTrue(all(task.fm_deadline == 2700 and task.fm_original_release == 2700 for task in emitted))

    def test_midnight_window_and_out_of_range_rejected(self):
        config = fixture()
        config["simulation"].update(start_datetime="2026-01-05T22:00:00", end_datetime="2026-01-06T02:00:00")
        category = config["task_generation"]["categories"]["catering"]["departments"]["D1"]
        category["scheduled_times"] = ["00:10"]
        baseline, plan = settings(config)
        validate_application(config, plan, baseline)
        updated = deepcopy(config)
        updated["task_generation"]["fm_logistics"] = plan
        tasks = native_demand(updated)["tasks"]
        self.assertTrue(any(row["release_datetime"].startswith("2026-01-06T00:10") for row in tasks))
        sim = Simulation(updated, verbose=False)
        self.assertIn(6000, sim.task_generation_manager.scheduled_wake_times(14400))
        config["simulation"]["start_datetime"] = "2026-01-05T23:50:00"
        with self.assertRaisesRegex(ValueError, "operating window"):
            validate_application(config, plan, native_demand(config))

    def test_reactive_hold_checks_lift_window_and_protected_capacity(self):
        config = fixture()
        sim = Simulation(config, verbose=False)
        generator = sim.task_generation_manager.generators[0]
        instance = next(row for row in generator.instances if row["category_key"] == "linen")
        task = generator._base_task(instance, "B2", "A", "Box", 100, "threshold")
        task.fm_deadline = 500
        sim.lift_reservations["Low"].append((0, 200, 0, 2, "busy"))
        self.assertEqual(160, reactive_hold(sim, task, 100, 200, instance, generator)[0])
        task.fm_deadline = 120
        self.assertEqual(100, reactive_hold(sim, task, 100, 200, instance, generator)[0])
        task.fm_deadline = 500
        task.container_group = "physical"
        self.assertEqual(100, reactive_hold(sim, task, 100, 200, instance, generator)[0])

    def test_staff_departure_respects_service_start_and_late_arrival(self):
        sim = Simulation(fixture(), verbose=False)
        generator = sim.task_generation_manager.generators[0]
        instance = next(row for row in generator.instances if row["category_key"] == "catering")
        task = generator._base_task(instance, "A", "B2", "Box", 100, "scheduled")
        task.staff_category_key = "catering"
        task.fm_cohort_id, task.fm_deadline = "C1", 600
        task.requires_staff = True
        task.staff_handling_minutes = 1
        task.staff_shift_start_time = '00:00'
        task.staff_shift_end_time = '24:00'
        task.staff_shift_days_active = []
        task.dropoff_zone, task.final_destination = "B2", "B3"
        walk = sim._staff_travel_between_locations("B2", "B3")[0]
        sim._schedule_configured_return_task(task, 200)
        events = [event for event in sim.events if event.event_type == "dropoff_zone_handoff_complete"]
        self.assertEqual(1, len(events))
        self.assertAlmostEqual(900 + walk, events[0].time, places=3)
        before = len(sim.events)
        with patch.object(sim, '_assign_staff_for_handling', return_value=None):
            sim._schedule_configured_return_task(task, 200)
        self.assertEqual(before, len(sim.events))

    def test_normal_run_reports_final_arrivals_and_tagged_movements(self):
        config = fixture()
        baseline, plan = settings(config)
        validate_application(config, plan, baseline)
        config["task_generation"]["fm_logistics"] = plan
        with TemporaryDirectory() as folder:
            path = Path(folder) / "run.csv"
            with redirect_stdout(StringIO()):
                sim = Simulation(config, verbose=True, verbose_csv_path=str(path))
                sim.run()
                sim.write_verbose_csv()
            actual = actual_activity(path)
            catering = [row for row in actual["tasks"] if row["category"] == "catering" and row["deadline"]]
            self.assertEqual(1, len(catering))
            self.assertEqual("on time", catering[0]["status"])
            self.assertEqual(2700, catering[0]["deadline"])
            self.assertLess(catering[0]["actual_release"], catering[0]["deadline"])
            movements = extract_lift_movements(path)
            self.assertIn("catering", set(movements["service_category"]))
            self.assertIn("loaded_outbound", set(movements["activity_type"]))

    def test_movement_tags_preserve_rows_and_duration(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "steps.csv"
            common = dict(sim_time_sec=10, event_type="segment_lift_transfer", segment_type="lift_transfer",
                          lift_id="L", start_node="L-F0", end_node="L-F1", duration_sec=14)
            rows = [
                dict(common, task_id="GEN_CATERING_D1_00001", details=json.dumps({"fm_lift": {
                    "loaded": True, "tasks": [{"category": "catering", "cohort": "C1", "return": False},
                                              {"category": "pharmacy", "return": True}]}})),
                dict(common, task_id="GEN_LINEN_D3_00003", segment_type="lift_reposition",
                     event_type="segment_lift_reposition"),
                dict(common, task_id="legacy-unknown"),
            ]
            pd.DataFrame(rows).to_csv(path, index=False)
            movements = extract_lift_movements(path)
            self.assertEqual(3, len(movements))
            self.assertEqual(42, movements["duration_s"].sum())
            self.assertEqual(["mixed", "linen", "unknown"], movements["service_category"].tolist())
            self.assertEqual(["mixed_load", "empty_lift_reposition", "unknown"], movements["activity_type"].tolist())
            self.assertEqual("catering|pharmacy", movements.iloc[0]["service_categories"])
            self.assertEqual("C1", movements.iloc[0]["fm_cohort_ids"])
            activity = actual_activity(path)
            self.assertEqual(3, sum(activity["totals"].values()))
