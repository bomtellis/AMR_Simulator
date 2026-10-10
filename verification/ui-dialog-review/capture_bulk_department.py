"""Capture the current bulk department task-generation editor."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import BulkDepartmentTaskGenerationDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

departments = [
    {"id": "D-01", "name": "North surgical ward", "floor": 1,
     "task_generation_locations": {
         "stores": {"pickup_dropoff_locations": ["North ward bay"]},
         "waste": {"pickup_dropoff_locations": ["North waste hold"]}}},
    {"id": "D-02", "name": "Day treatment centre", "floor": 2,
     "task_generation_locations": {
         "stores": {"pickup_dropoff_locations": ["Day treatment bay"]},
         "waste": {"pickup_dropoff_locations": ["Day waste hold"]}}},
]
locations = ["North ward bay", "Day treatment bay", "North waste hold",
             "Day waste hold", "Central stores", "Main waste dock"]
base = {
    "enabled": True, "generation_mode": "hybrid", "priority": 100,
    "dropoff_locations": ["Central stores"], "payload": "Linen trolley",
    "return_enabled": True, "return_payload": "Empty trolley",
    "requires_staff": True, "reusable_return_pool_enabled": True,
    "scheduled_times": ["08:00", "14:00"], "days_active": ["mon", "tue", "wed", "thu", "fri"],
}

for category in ("stores", "waste"):
    dialog = BulkDepartmentTaskGenerationDialog(
        None, category, category.title(), departments, base, locations,
        ["Linen trolley", "Empty trolley"], ["default", "Service route"],
        selected_department_ids=["D-01", "D-02"],
    )
    for width, height in ((920, 720), (1024, 768)):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        buttons = dialog.findChild(QDialogButtonBox)
        print(category, (width, height), "actual", (dialog.width(), dialog.height()),
              "button", (buttons.y(), buttons.height()),
              "screen", (app.primaryScreen().availableGeometry().width(),
                          app.primaryScreen().availableGeometry().height()),
              "dpr", dialog.devicePixelRatioF())
        dialog.grab().save(str(OUT / f"bulk-department-{category}-{width}.png"))
    dialog.close()
