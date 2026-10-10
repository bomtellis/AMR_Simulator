"""Capture the current lift monitor with several representative lifts."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import LiftMonitorDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
states = [
    {"lift_id": "North service lift", "served_floors": [0, 1, 2, 3, 4],
     "current_floor": 2.4, "occupant": "AMR-01", "waiting_amrs": ["AMR-04", "AMR-07"]},
    {"lift_id": "Theatre goods lift", "served_floors": [1, 2, 3],
     "current_floor": 1, "occupant": None, "waiting_amrs": []},
    {"lift_id": "South logistics lift", "served_floors": [0, 1, 2, 3, 4],
     "current_floor": 3, "occupant": "AMR-03", "waiting_amrs": ["AMR-09"]},
    {"lift_id": "East transfer lift", "served_floors": [0, 1, 2],
     "current_floor": 0.5, "occupant": None, "waiting_amrs": ["AMR-12", "AMR-15"]},
]
dialog = LiftMonitorDialog()
dialog.set_lifts(states)
for width, height in ((700, 520), (980, 520), (1400, 700)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    print((width, height), "actual", (dialog.width(), dialog.height()))
    dialog.grab().save(str(OUT / f"lift-monitor-{width}.png"))
dialog.close()
