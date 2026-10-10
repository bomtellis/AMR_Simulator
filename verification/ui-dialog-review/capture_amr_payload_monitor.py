"""Capture the current AMR payload monitor with representative runtime data."""
from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QTableWidget

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import AmrPayloadMonitorDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
rows = [
    {
        "amr_id": "AMR-01", "payloads": "Bay A: Linen trolley (TASK-0101), Bay B: Sealed clinical supplies (TASK-0102)",
        "payload_count": 2, "slots": "2/3", "task_ids": "TASK-0101, TASK-0102",
        "status": "in transit", "segment_type": "corridor", "from_location": "North surgical ward staging bay",
        "to_location": "Central stores loading area", "floor": 2, "updated": "2026-10-04 11:40:32",
    },
    {
        "amr_id": "AMR-02", "payloads": "-", "payload_count": 0, "slots": "0/2", "task_ids": "TASK-0201",
        "status": "loading", "segment_type": "pickup", "from_location": "East theatre prep",
        "to_location": "East theatre prep", "floor": 2, "updated": "2026-10-04 11:41:05",
    },
    {
        "amr_id": "AMR-03", "payloads": "Flexible slot: Equipment crate (TASK-0301)",
        "payload_count": 1, "slots": "1/1", "task_ids": "TASK-0301",
        "status": "in lift", "segment_type": "lift_loaded", "from_location": "Ground floor reception",
        "to_location": "North surgical ward staging bay", "floor": 1, "updated": "2026-10-04 11:39:48",
    },
]
dialog = AmrPayloadMonitorDialog()
dialog.update_states(rows, datetime(2026, 10, 4, 11, 42, 18))
for width, height in ((900, 540), (1320, 520), (1600, 720)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    table = dialog.findChild(QTableWidget)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", table.horizontalScrollBar().maximum())
    dialog.grab().save(str(OUT / f"amr-payload-monitor-{width}.png"))
dialog.close()
