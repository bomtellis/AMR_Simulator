import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from dialogs import SimulationSettingsDialog
from models import JsonStore


class TaskDeferralSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_setting_round_trip_and_unlimited_default(self):
        store = JsonStore({"simulation": {}})
        self.assertEqual(0, store.data["simulation"]["max_task_deferral_minutes"])
        config = {
            "start_datetime": "2026-01-05T00:00:00",
            "end_datetime": "2026-01-05T01:00:00",
        }
        for initial, updated in ((0, 12.5), (12.5, 0)):
            with self.subTest(initial=initial):
                if initial:
                    config["max_task_deferral_minutes"] = initial
                dialog = SimulationSettingsDialog(None, config)
                try:
                    self.assertEqual(initial, dialog.max_task_deferral_minutes_spin.value())
                    if not initial:
                        self.assertEqual("Unlimited", dialog.max_task_deferral_minutes_spin.text())
                    dialog.max_task_deferral_minutes_spin.setValue(updated)
                    dialog.accept()
                    self.assertEqual(updated, dialog.result["max_task_deferral_minutes"])
                finally:
                    dialog.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
