"""Capture the current manual task form with a populated recovery state."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import TaskFormDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

seed = {
    "id": "RECOVER-017", "pickup": "Ward North staging bay",
    "dropoff": "Central sterile stores", "payload": "Linen trolley",
    "release_datetime": "2026-10-04T08:30:00", "target_time": 900,
    "priority": 10, "labels": ["recovery", "ward-north"],
    "route_profile": "Service route", "payload_instance_id": "TROLLEY-0042",
    "recover_staged_payload": True,
}
dialog = TaskFormDialog(None, [seed["pickup"], seed["dropoff"]],
                        ["Linen trolley"], ["default", "Service route"], seed=seed)
for width, height in ((560, 360), (700, 600), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "button", (buttons.y(), buttons.height()), "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"task-form-{width}.png"))
dialog.close()
