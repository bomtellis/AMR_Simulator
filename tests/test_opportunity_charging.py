import contextlib
import io
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication

from amr_sim_models import Task
from dialogs import SimulationSettingsDialog
from models import JsonStore
from simulator import Simulation


def _charging_config(enabled=True):
    return {
        "simulation": {
            "start_datetime": "2026-01-05T00:00:00",
            "end_datetime": "2026-01-05T00:20:00",
            "precompute_static_routes": False,
            "enable_opportunity_charging": enabled,
            "opportunity_charging_idle_period_sec": 120.0,
            "opportunity_charging_check_interval_sec": 60.0,
        },
        "building": {
            "charge_location": "Store",
            "load_unload_time_sec": 1.0,
            "enable_idle_return": False,
        },
        "locations": [{"name": "Store", "floor": 0, "x": 0, "y": 0}],
        "corridors": {"nodes": [], "edges": []},
        "payloads": [],
        "amrs": [
            {
                "id": "AMR-B",
                "quantity": 3,
                "payload_capacity_kg": 100,
                "payload_length_capacity_m": 2,
                "payload_width_capacity_m": 2,
                "payload_height_capacity_m": 2,
                "speed_m_per_sec": 1,
                "battery_capacity_kwh": 10,
                "battery_charge_rate_kw": 6,
                "recharge_threshold_percent": 20,
                "battery_soc_percent": 80,
            }
        ],
        "lifts": [],
        "tasks": [],
        "departments": [],
        "task_generation": {"enabled": False, "categories": {}},
    }


class OpportunityChargingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_general_settings_persist_opportunity_charging(self):
        dialog = SimulationSettingsDialog(
            None,
            {
                "start_datetime": "2026-01-05T00:00:00",
                "end_datetime": "2026-01-05T01:00:00",
                "enable_opportunity_charging": True,
                "opportunity_charging_idle_period_sec": 600.0,
            },
        )

        self.assertTrue(dialog.enable_opportunity_charging_check.isChecked())
        self.assertEqual(
            10.0, dialog.opportunity_charging_idle_minutes_spin.value()
        )
        dialog.opportunity_charging_idle_minutes_spin.setValue(12.5)
        dialog.accept()

        self.assertTrue(dialog.result["enable_opportunity_charging"])
        self.assertEqual(
            750.0, dialog.result["opportunity_charging_idle_period_sec"]
        )

    def test_json_store_adds_disabled_backwards_compatible_defaults(self):
        store = JsonStore({"simulation": {}})

        self.assertFalse(
            store.data["simulation"]["enable_opportunity_charging"]
        )
        self.assertEqual(
            900.0,
            store.data["simulation"]["opportunity_charging_idle_period_sec"],
        )

    def test_idle_amrs_are_admitted_one_per_check(self):
        sim = Simulation(_charging_config(enabled=True))

        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

        intervals = sorted(
            sim.charge_intervals,
            key=lambda item: (item["start_time"], item["amr_id"]),
        )
        self.assertEqual(3, len(intervals))
        self.assertEqual([120.0, 180.0, 240.0], [
            item["start_time"] for item in intervals
        ])
        self.assertTrue(
            all(item["reason"] == "opportunity_idle" for item in intervals)
        )

    def test_unassignable_work_no_longer_charges_every_nonfull_amr(self):
        sim = Simulation(_charging_config(enabled=False))
        task = Task(
            id="WAITING",
            pickup="Store",
            dropoff="Store",
            payload="",
            release_time=0.0,
        )
        sim._queue_pending_task(task)
        sim._select_best_assignment = lambda: None
        sim._fail_released_terminal_pending_task = lambda _now: False
        sim._create_wait_event_for_pending_tasks = lambda _now: None

        sim._try_assign_tasks(120.0)

        self.assertEqual([], sim.charge_intervals)
        self.assertFalse(any(amr.is_charging for amr in sim.amrs))


if __name__ == "__main__":
    unittest.main()
