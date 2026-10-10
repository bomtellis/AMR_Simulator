"""Capture the current Tasks by AMR jump dialog with representative rows."""
from datetime import datetime, timedelta
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import TaskJumpDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

base = datetime(2026, 10, 4, 8, 30)
grouped = {}
for amr_number in (1, 2):
    amr_id = f"AMR-{amr_number:02d}"
    tasks = []
    for task_number in (1, 2):
        moment = base + timedelta(minutes=(amr_number - 1) * 80 + task_number * 18)
        tasks.append({
            "task_id": f"TASK-{amr_number:02d}{task_number:02d}",
            "payload": "Linen trolley" if task_number == 1 else "Supply box",
            "origin": "Central stores dispatch",
            "destination": "North surgical ward staging bay" if task_number == 1 else "Day treatment reception",
            "duration": "00:16:30" if task_number == 1 else "00:11:45",
            "sim_datetime": moment, "start_time": float((moment - base).total_seconds()),
            "segments": [
                {"label": "Pickup and travel", "origin": "Central stores dispatch",
                 "destination": "Main lift lobby", "duration": "00:06:20",
                 "sim_datetime": moment, "start_time": float((moment - base).total_seconds())},
                {"label": "Delivery", "origin": "Main lift lobby",
                 "destination": "North surgical ward staging bay" if task_number == 1 else "Day treatment reception",
                 "duration": "00:10:10", "sim_datetime": moment + timedelta(minutes=6),
                 "start_time": float((moment - base).total_seconds() + 360)},
            ],
        })
    grouped[amr_id] = tasks

dialog = TaskJumpDialog(None, grouped)
for width, height in ((700, 520), (980, 620), (1400, 800)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    for index in range(dialog.tree.topLevelItemCount()):
        dialog.tree.topLevelItem(index).setExpanded(True)
    dialog.tree.topLevelItem(0).child(0).setExpanded(True)
    app.processEvents()
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", dialog.tree.horizontalScrollBar().maximum(),
          "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"task-jump-{width}.png"))
dialog.close()
