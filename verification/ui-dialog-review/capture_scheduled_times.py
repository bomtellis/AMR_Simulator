"""Capture the existing Scheduled Times dialog with grouped times."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import ScheduledTimesDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = ScheduledTimesDialog(
    None, ["08:00", "08:15", "10:30", "12:00", "15:45", "18:30"]
)
for width, height in ((420, 480), (520, 520), (800, 600)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    print((width, height), "actual", (dialog.width(), dialog.height()))
    dialog.grab().save(str(OUT / f"scheduled-times-{width}.png"))
dialog.close()
