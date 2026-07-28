import os
import unittest
from datetime import datetime
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from visualiser.amr_sim_visualiser_pyside6 import (
    FailedTasksDialog,
    SimulationLog,
    SimulationVisualizer,
    VisualEvent,
)


class VisualiserFailedTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_failure_uses_generated_task_final_destination_metadata(self):
        generated_time = datetime(2026, 1, 1, 12, 45)
        failure_time = datetime(2026, 1, 1, 12, 45, 0, 125000)
        log = SimulationLog()
        log.events = [
            VisualEvent(
                generated_time,
                generated_time,
                {
                    "event_type": "task_generated",
                    "task_id": "TASK-1",
                    "details": (
                        "Generated scheduled task; "
                        "AMR drop-off zone=D39-DROP-ZONE; "
                        "final destination=D39-CATERING"
                    ),
                },
            ),
            VisualEvent(
                failure_time,
                failure_time,
                {
                    "event_type": "task_failed",
                    "task_id": "TASK-1",
                    "sim_datetime": "2026-01-01 12:45:00.125",
                    "payload": "Burlodge Trolley",
                    "from_location": "D28-CATERING",
                    "to_location": "D39-DROP-ZONE",
                    "pending_reason": "All compatible inventory spaces are full",
                    "task_source": "task_generation",
                    "department_id": "D39",
                },
            ),
        ]

        rows = log.failed_task_rows()

        self.assertEqual(1, len(rows))
        self.assertEqual("D39-CATERING", rows[0]["final_destination"])
        self.assertEqual("D39-DROP-ZONE", rows[0]["dropoff_zone"])
        self.assertEqual("D39-CATERING", rows[0]["inspection_location"])
        self.assertEqual("2026-01-01 12:45:00.125", rows[0]["failure_time_display"])

    def test_legacy_return_failure_uses_return_destination(self):
        failure_time = datetime(2026, 1, 1, 20, 20, 6, 941000)
        log = SimulationLog()
        log.events = [
            VisualEvent(
                failure_time,
                failure_time,
                {
                    "event_type": "task_failed",
                    "task_id": "RETURN-1",
                    "sim_datetime": "2026-01-01 20:20:06.941",
                    "from_location": "D32-DROP-ZONE",
                    "to_location": "Linen Deliveries",
                    "task_source": "task_generation_return",
                    "details": "No AMR has sufficient payload capacity",
                },
            )
        ]

        row = log.failed_task_rows()[0]

        self.assertEqual("Linen Deliveries", row["final_destination"])
        self.assertEqual("D32-DROP-ZONE", row["dropoff_zone"])
        self.assertEqual("Linen Deliveries", row["inspection_location"])

    def test_dialog_accepts_selected_failure_for_navigation(self):
        failure = {
            "failure_time": datetime(2026, 1, 1, 12, 0),
            "failure_time_display": "2026-01-01 12:00:00",
            "task_id": "TASK-2",
            "payload": "Cage",
            "final_destination": "WARD",
            "dropoff_zone": "WARD-ZONE",
            "pickup": "STORE",
            "department_id": "D1",
            "amr_id": "-",
            "reason": "No route",
        }
        dialog = FailedTasksDialog(None, [failure])

        dialog._view_row(0, 0)

        self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(failure, dialog.selected_failure)

    def test_navigation_seeks_pauses_and_centres_destination(self):
        class _Timer:
            stopped = False

            def stop(self):
                self.stopped = True

        class _Button:
            text = ""

            def setText(self, value):
                self.text = value

        class _Viewport:
            updated = False

            def update(self):
                self.updated = True

        class _View:
            centred = None

            def __init__(self):
                self._viewport = _Viewport()

            def centerOn(self, x, y):
                self.centred = (x, y)

            def viewport(self):
                return self._viewport

        failure_time = datetime(2026, 1, 1, 12, 0, 0, 250000)
        stub = SimpleNamespace(
            is_playing=True,
            play_timer=_Timer(),
            play_btn=_Button(),
            _last_play_tick_wall_time=1.0,
            current_time=None,
            layout_model=SimpleNamespace(
                points={
                    "WARD": {
                        "kind": "location",
                        "floor": 2,
                        "x": 12.5,
                        "y": 7.0,
                    }
                }
            ),
            view=_View(),
            sim_log=SimulationLog(),
            _invalidate_runtime_caches=lambda: None,
            update_time_display=lambda: None,
            refresh_dynamic_scene=lambda: None,
            _scroll_timeline_to_time=lambda _value: None,
            current_floor=lambda: 0,
            set_floor=lambda value: setattr(stub, "selected_floor", value),
            world_to_scene=lambda x, y: (float(x), -float(y)),
            set_status=lambda value: setattr(stub, "status", value),
        )

        focused = SimulationVisualizer.navigate_to_failed_task(
            stub,
            {
                "failure_time": failure_time,
                "task_id": "TASK-3",
                "inspection_location": "WARD",
                "final_destination": "WARD",
                "amr_destination": "WARD-ZONE",
            },
        )

        self.assertEqual("WARD", focused)
        self.assertEqual(failure_time, stub.current_time)
        self.assertFalse(stub.is_playing)
        self.assertTrue(stub.play_timer.stopped)
        self.assertEqual("Play", stub.play_btn.text)
        self.assertEqual(2, stub.selected_floor)
        self.assertEqual((12.5, -7.0), stub.view.centred)
        self.assertIn("2026-01-01 12:00:00.250", stub.status)


if __name__ == "__main__":
    unittest.main()
