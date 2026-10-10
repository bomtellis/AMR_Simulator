"""Capture the current location inventory-spaces table."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import LocationInventorySpacesDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

rows = [
    {"name": "North bay 01", "length_m": "2.2", "width_m": "1.4", "height_m": "1.8",
     "flexible": "No", "occupied": "Yes", "payload": "Linen trolley",
     "task_id": "TASK-0101", "reserved_by_task": "-", "points": "N-101"},
    {"name": "North bay 02", "length_m": "2.2", "width_m": "1.4", "height_m": "1.8",
     "flexible": "No", "occupied": "No", "payload": "-",
     "task_id": "-", "reserved_by_task": "TASK-0201", "points": "N-102"},
    {"name": "Flexible overflow area", "length_m": "3.5", "width_m": "2.0", "height_m": "2.4",
     "flexible": "Yes", "occupied": "Yes", "payload": "Supply box",
     "task_id": "TASK-0102", "reserved_by_task": "-", "points": "N-103, N-104"},
]
dialog = LocationInventorySpacesDialog(None, "North surgical ward staging bay", rows)
for width, height in ((800, 500), (1080, 460), (1440, 720)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", dialog.table.horizontalScrollBar().maximum(),
          "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"inventory-spaces-{width}.png"))
dialog.close()
