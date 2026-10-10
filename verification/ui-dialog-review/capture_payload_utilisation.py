"""Capture the current maximum payload-space utilisation dialog."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QTableWidget

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import PayloadSpaceMaximumUtilisationDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

summary = {
    "peak_time": "2026-10-04 11:42:18", "horizon": "2026-10-04 08:00–18:00",
    "maximum_occupied_spaces": 2, "configured_spaces": 3,
    "maximum_utilisation_percent": 66.7, "overflow_at_peak": 1,
    "assignment_note": "Assignments use the recorded payload-space evidence where available; unassigned payloads are reconstructed from location events.",
}
rows = [
    {"space": "North bay 01", "ever_occupied": "Yes", "entries": 6,
     "occupied_duration": "03:20:00", "utilisation_percent": "33.3",
     "first_occupied": "2026-10-04 08:18:00", "last_released": "2026-10-04 16:12:00",
     "occupied_at_peak": "Yes"},
    {"space": "North bay 02", "ever_occupied": "Yes", "entries": 3,
     "occupied_duration": "02:05:00", "utilisation_percent": "20.8",
     "first_occupied": "2026-10-04 09:31:00", "last_released": "2026-10-04 15:04:00",
     "occupied_at_peak": "Yes"},
    {"space": "Flexible overflow area", "ever_occupied": "No", "entries": 0,
     "occupied_duration": "00:00:00", "utilisation_percent": "0.0",
     "first_occupied": "-", "last_released": "-", "occupied_at_peak": "No"},
]
dialog = PayloadSpaceMaximumUtilisationDialog(
    None, "North surgical ward staging bay", summary, rows
)
for width, height in ((900, 560), (1120, 500), (1440, 720)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", dialog.findChild(QTableWidget).horizontalScrollBar().maximum(),
          "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"payload-utilisation-{width}.png"))
dialog.close()
