"""Capture the current Mass collection editor with representative values."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import MassCollectionEditorDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = MassCollectionEditorDialog(
    None,
    ["Waste Store A", "Waste Store B", "Ward Bay"],
    ["General waste bin", "Clinical waste bin", "Recycling bin"],
    seed={
        "id": "MASS-COLLECTION-1",
        "enabled": True,
        "location": "Waste Store A",
        "payloads": ["General waste bin", "Clinical waste bin"],
        "days_active": ["mon", "tue", "wed", "thu", "fri"],
        "scheduled_times": ["07:00", "15:00", "22:00"],
        "capacity_trigger_fraction": 0.8,
        "capacity_trigger_count": 12,
        "capacity_check_interval_minutes": 15.0,
        "replace_with_empty_equivalents": True,
        "notes": "Check the bin store after the morning round.",
    },
)
rows = []
for width, height in ((760, 620), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    rows.append({
        "requested": (width, height),
        "actual": (dialog.width(), dialog.height()),
        "button_visible": bool(buttons and buttons.isVisible()),
    })
    dialog.grab().save(str(OUT / f"mass-collection-{width}.png"))
print(rows)
dialog.close()
