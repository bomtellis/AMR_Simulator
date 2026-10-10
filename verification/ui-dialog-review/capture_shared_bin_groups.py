"""Capture the current shared-bin-group wizard with representative groups."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import TaskCategorySharedBinGroupWizard

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])


def dept(code, name, floor, location, enabled=True, existing=False):
    streams = [
        {"name": "General waste", "shared_container_group":
         "OLD-GROUP" if existing else ""},
        {"name": "Clinical waste", "shared_container_group": ""},
    ]
    return {
        "id": code, "name": name, "floor": floor, "enabled": enabled,
        "task_generation_locations": {
            "waste": {"pickup_dropoff_locations": [location]}
        },
        "waste_streams": streams,
    }


departments = [
    dept("D-01", "Emergency", 0, "Shared Bin Store A", existing=True),
    dept("D-02", "Imaging", 0, "Shared Bin Store A"),
    dept("D-03", "Ward North", 1, "Shared Bin Store A"),
    dept("D-04", "Ward South", 1, "Shared Bin Store B"),
    dept("D-05", "Theatre", 1, "Shared Bin Store B"),
    dept("D-06", "Outpatients", 0, "Shared Bin Store B", enabled=False),
]
dialog = TaskCategorySharedBinGroupWizard(
    None, departments, ["General waste", "Clinical waste"],
    [("stores", "Stores", "-STORES"), ("waste", "Waste", "-WASTE")],
    current_floor=0,
)
dialog.overwrite_existing_check.setChecked(False)
rows = []
for width, height in ((1040, 680), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    first = dialog.preview.topLevelItem(0)
    buttons = dialog.findChild(QDialogButtonBox)
    rows.append({
        "requested": (width, height),
        "actual": (dialog.width(), dialog.height()),
        "button_visible": bool(buttons and buttons.isVisible()),
        "group_rows": dialog.preview.topLevelItemCount(),
        "first_row_rect": tuple(dialog.preview.visualItemRect(first).getRect()) if first else None,
    })
    dialog.grab().save(str(OUT / f"shared-bin-groups-{width}.png"))
print(rows)
dialog.preview.setUniformRowHeights(False)
for _ in range(6):
    app.processEvents()
first = dialog.preview.topLevelItem(0)
print({"uniform_rows_disabled_first_rect": tuple(dialog.preview.visualItemRect(first).getRect()) if first else None})
dialog.grab().save(str(OUT / "shared-bin-groups-rows-visible-probe.png"))
dialog.close()
