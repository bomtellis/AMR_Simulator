"""Capture the current Failed Tasks dialog with representative failures."""
from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QTableWidget

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import FailedTasksDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
rows = [
    {"failure_time": datetime(2026, 10, 4, 9, 12, 43),
     "failure_time_display": "2026-10-04 09:12:43", "task_id": "TASK-0101",
     "payload": "Linen trolley", "final_destination": "North surgical ward staging bay",
     "dropoff_zone": "Ward AMR drop-off", "pickup": "Central linen collection",
     "department_id": "SURG-N", "amr_id": "AMR-01",
     "reason": "No viable route to the final destination after the north service corridor was closed."},
    {"failure_time": datetime(2026, 10, 4, 10, 25, 11),
     "failure_time_display": "2026-10-04 10:25:11", "task_id": "TASK-0204",
     "payload": "Sterile equipment crate", "final_destination": "East theatre preparation",
     "dropoff_zone": "Theatre goods drop-off", "pickup": "Ground floor stores",
     "department_id": "THEATRE", "amr_id": "AMR-03",
     "reason": "Required payload slot was unavailable on the assigned AMR."},
    {"failure_time": datetime(2026, 10, 4, 11, 42, 18),
     "failure_time_display": "2026-10-04 11:42:18", "task_id": "TASK-0309",
     "payload": "Sealed clinical supplies", "final_destination": "South diagnostics ward",
     "dropoff_zone": "South diagnostics receiving", "pickup": "Central stores loading area",
     "department_id": "DIAG-S", "amr_id": "AMR-05",
     "reason": "Destination inventory space was fully occupied; delivery could not be completed before the task deadline."},
    {"failure_time": datetime(2026, 10, 4, 12, 6, 51),
     "failure_time_display": "2026-10-04 12:06:51", "task_id": "TASK-0402",
     "payload": "Waste bin", "final_destination": "Waste processing hub",
     "dropoff_zone": "-", "pickup": "West outpatient clinic",
     "department_id": "OUT-W", "amr_id": "-",
     "reason": "No AMR was available within the configured dispatch window."},
]
dialog = FailedTasksDialog(None, rows)
for width, height in ((1000, 600), (1600, 720), (1920, 900)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    table = dialog.findChild(QTableWidget)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", table.horizontalScrollBar().maximum())
    dialog.grab().save(str(OUT / f"failed-tasks-{width}.png"))
dialog.close()
