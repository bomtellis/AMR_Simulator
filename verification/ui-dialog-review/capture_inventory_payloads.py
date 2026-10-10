"""Capture the active read-only location inventory-payload dialog."""
from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QTableWidget

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import LocationInventoryPayloadDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
rows = [
    {"space": "North bay 01", "payload": "Sealed clinical waste bin",
     "waste_stream": "Clinical waste", "container_group": "Ward clinical bins",
     "task_id": "TASK-0101", "amr_id": "AMR-01", "status": "Occupied",
     "timestamp": "2026-10-04 11:39:02", "source": "Simulation CSV",
     "tooltip": "Payload: Sealed clinical waste bin\nDetails: Size 0.80 x 0.60 x 1.20 m | Weight 28.0 kg\nWaste volume filled: 0.240 / 0.500 m³ (48%)\nFill rate: 0.032 m³/day\nWaste stream: Clinical waste\nContainer group: Ward clinical bins\nInstance: BIN-009\nTask: TASK-0101\nStatus: Occupied\nSource: Simulation CSV"},
    {"space": "North bay 02", "payload": "Linen trolley", "waste_stream": "-",
     "container_group": "-", "task_id": "TASK-0102", "amr_id": "AMR-03",
     "status": "Occupied", "timestamp": "2026-10-04 11:41:15", "source": "Simulation CSV",
     "tooltip": "Payload: Linen trolley\nDetails: Size 1.20 x 0.70 x 1.60 m | Weight 85.0 kg\nInstance: LINEN-204\nTask: TASK-0102\nStatus: Occupied\nSource: Simulation CSV"},
    {"space": "Flexible overflow area", "payload": "-", "waste_stream": "-",
     "container_group": "-", "task_id": "-", "amr_id": "-", "status": "Empty",
     "timestamp": "-", "source": "Layout JSON", "details": "-"},
    {"space": "Unassigned overflow 1", "payload": "Replacement container",
     "waste_stream": "General waste", "container_group": "Ward general bins",
     "task_id": "TASK-0304", "amr_id": "AMR-05", "status": "Capacity overflow",
     "timestamp": "2026-10-04 11:42:18", "source": "Simulation CSV (capacity overflow)",
     "tooltip": "Payload: Replacement container\nDetails: Size 0.80 x 0.60 x 1.20 m\nWaste volume filled: 0.000 / 0.500 m³ (0%)\nWaste stream: General waste\nContainer group: Ward general bins\nTask: TASK-0304\nStatus: Capacity overflow\nSource: Simulation CSV (capacity overflow)"},
]
dialog = LocationInventoryPayloadDialog(
    None, "North surgical ward staging bay", rows, datetime(2026, 10, 4, 11, 42, 18)
)
for width, height in ((900, 520), (1420, 520), (1600, 800)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    table = dialog.findChild(QTableWidget)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", table.horizontalScrollBar().maximum())
    dialog.grab().save(str(OUT / f"inventory-payloads-{width}.png"))
dialog.close()
