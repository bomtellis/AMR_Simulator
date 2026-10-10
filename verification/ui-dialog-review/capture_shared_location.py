"""Capture the current shared task-category location wizard with sample rows."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import TaskCategoryCommonLocationWizard

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
departments = [
    {"id": "D-01", "name": "Emergency", "floor": 0, "enabled": True,
     "task_generation_locations": {"stores": {"pickup_dropoff_locations": ["Stores A"]}}},
    {"id": "D-02", "name": "Imaging", "floor": 0, "enabled": True,
     "task_generation_locations": {"stores": {"pickup_dropoff_locations": ["Stores A"]}}},
    {"id": "D-03", "name": "Ward North", "floor": 1, "enabled": True},
    {"id": "D-04", "name": "Ward South", "floor": 1, "enabled": True,
     "task_generation_locations": {"stores": {"pickup_dropoff_locations": ["Stores B"]}}},
    {"id": "D-05", "name": "Outpatients", "floor": 0, "enabled": False},
    {"id": "D-06", "name": "Theatre", "floor": 2, "enabled": True},
]
dialog = TaskCategoryCommonLocationWizard(
    None, departments, ["Stores A", "Stores B", "Shared Store"],
    [("stores", "Stores", "-STORES"), ("waste", "Waste", "-WASTE")],
    preselected_indexes=[0, 1, 2], current_floor=0,
)
dialog.selected_locations = ["Shared Store"]
dialog.refresh_location_summary()
dialog.refresh_summary()
rows = []
for width, height in ((920, 620), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    first = dialog.department_table.topLevelItem(0)
    rows.append({
        "requested": (width, height),
        "actual": (dialog.width(), dialog.height()),
        "button_visible": bool(buttons and buttons.isVisible()),
        "department_rows": dialog.department_table.topLevelItemCount(),
        "first_row_rect": tuple(dialog.department_table.visualItemRect(first).getRect()) if first else None,
        "first_row_text": first.text(2) if first else None,
    })
    dialog.grab().save(str(OUT / f"shared-location-{width}.png"))
print(rows)
dialog.department_table.setUniformRowHeights(False)
for _ in range(6):
    app.processEvents()
first = dialog.department_table.topLevelItem(0)
print({"uniform_rows_disabled_first_rect": tuple(dialog.department_table.visualItemRect(first).getRect()) if first else None})
dialog.grab().save(str(OUT / "shared-location-rows-visible-probe.png"))
dialog.close()
