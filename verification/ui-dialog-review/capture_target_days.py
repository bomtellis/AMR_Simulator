"""Capture the existing target-days calendar with representative selection."""
from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import MultiDaySelectDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = MultiDaySelectDialog(None, initial_date=datetime(2026, 10, 4))
dialog.selected_dates = {"2026-10-05", "2026-10-07", "2026-10-09", "2026-10-12", "2026-10-14"}
dialog.refresh()

for width, height in ((620, 500), (820, 560), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "buttons", (buttons.x(), buttons.y(), buttons.width(), buttons.height()),
          "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"target-days-{width}.png"))
dialog.close()
