"""Capture Tasks by location / department with representative full task rows."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import TasksByLocationDepartmentDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

rows = []
for index, (task_id, department, start, finish, payload, staff, status) in enumerate((
    ("TASK-0101", "North surgical ward", "Central stores dispatch", "North surgical ward staging bay", "Linen trolley", "Ward porter A", "Complete"),
    ("TASK-0102", "Day treatment centre", "Central stores dispatch", "Day treatment reception", "Supply box", "Ward porter B", "Complete"),
    ("TASK-0201", "North surgical ward", "Sterile supplies store", "North surgical ward staging bay", "Sterile kit", "Ward porter A", "In progress"),
    ("TASK-0202", "Imaging", "Imaging reception", "Central stores dispatch", "Empty trolley", "Unassigned", "Waiting"),
)):
    rows.append({
        "task_id": task_id, "payload": payload,
        "start_time_display": f"2026-10-04 {8 + index:02d}:30:00",
        "end_time_display": f"2026-10-04 {8 + index:02d}:47:00",
        "start_sort_time": f"2026-10-04 {8 + index:02d}:30:00",
        "start_time": float(index * 3600),
        "start_location": start, "finish_location": finish,
        "department": department, "staff": staff, "people_required": 1,
        "duration": "00:17:00", "status": status,
        "source": "Manual" if index == 0 else "Generated",
        "details": f"{task_id}: {start} to {finish}; {status.lower()}",
    })

dialog = TasksByLocationDepartmentDialog(None, rows)
for width, height in ((1024, 768), (1420, 720), (1600, 900)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    for index in range(dialog.tree.topLevelItemCount()):
        dialog.tree.topLevelItem(index).setExpanded(True)
    print("Department", (width, height), "actual", (dialog.width(), dialog.height()),
          "horizontal max", dialog.tree.horizontalScrollBar().maximum(),
          "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"tasks-by-location-department-{width}.png"))
dialog.group_combo.setCurrentText("Location")
dialog.resize(1024, 768)
dialog.show()
for _ in range(6):
    app.processEvents()
for index in range(dialog.tree.topLevelItemCount()):
    dialog.tree.topLevelItem(index).setExpanded(True)
dialog.grab().save(str(OUT / "tasks-by-location-location-1024.png"))
dialog.close()
