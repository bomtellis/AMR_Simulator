"""Capture the current one-to-many task creation dialog."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import BulkOneToManyTaskDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

dialog = BulkOneToManyTaskDialog(
    None,
    ["Central stores", "North surgical ward", "Day treatment centre", "Imaging reception"],
    ["Linen trolley", "Supply box"], ["default", "Service route"],
    default_task_id="BULK-021",
)
dialog.pickup_combo.setCurrentText("Central stores")
dialog.selected_dropoffs = ["North surgical ward", "Day treatment centre", "Imaging reception"]
dialog.dropoff_summary.setText(", ".join(dialog.selected_dropoffs))
dialog.payload_combo.setCurrentText("Linen trolley")
dialog.route_combo.setCurrentText("Service route")
dialog.labels_edit.setText("stores, morning-round")

for width, height in ((620, 500), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "button", (buttons.y(), buttons.height()), "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"one-to-many-{width}.png"))
dialog.close()
