"""Capture the active bulk task update dialog with seeded values."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import EditMultipleTasksDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = EditMultipleTasksDialog(
    None, ["default", "Service route"], seed={
        "release_datetime": "2026-10-04T08:30:00", "target_time": 900,
        "priority": 10, "labels": ["stores", "morning-round"],
        "route_profile": "Service route",
    },
)
dialog.release_check.setChecked(True)
dialog.priority_check.setChecked(True)
for width, height in ((560, 260), (760, 520), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "buttons", (buttons.y(), buttons.height()), "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"edit-multiple-tasks-{width}.png"))
dialog.close()
