"""Capture the current DXF loading dialog during a partial batch failure."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from app import DXFLoadingDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
for width in (420, 720):
    dialog = DXFLoadingDialog()
    dialog.update_progress(2, 4, "Loading 2 remaining DXF file(s)...", failed_count=1)
    dialog.resize(width, 170)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    print(width, "actual", (dialog.width(), dialog.height()))
    dialog.grab().save(str(OUT / f"dxf-loading-{width}.png"))
    dialog.mark_complete()
