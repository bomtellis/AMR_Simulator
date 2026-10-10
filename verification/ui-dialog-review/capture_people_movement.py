"""Capture the current people movement editor for the sequential design review."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import PeopleMovementEditorDialog

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = PeopleMovementEditorDialog(
    None,
    ["A", "B", "Ward Bay", "Zone X"],
    ["A -> Door", "Door -> B"],
    seed={
        "id": "PUBLIC-VISITING",
        "enabled": True,
        "group_type": "public",
        "timeframe_preset": "visiting",
        "timeframe_name": "Visiting period",
        "start_time": "14:00",
        "end_time": "20:00",
        "days_active": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "profile_shape": "ramp_up_down",
        "minimum_people_per_interval": 2,
        "people_per_trip": 12,
        "interval_minutes": 15.0,
        "fit_profile_to_timeframe": False,
        "ramp_up_minutes": 90.0,
        "ramp_down_minutes": 90.0,
        "corridor_edges": ["A -> Door", "Door -> B"],
    },
)
dialog.resize(1024, 768)
dialog.show()
for index, slug in enumerate(("profile", "route", "flow", "interaction")):
    dialog.tabs.setCurrentIndex(index)
    for _ in range(6):
        app.processEvents()
    dialog.grab().save(str(OUT / f"people-movement-{slug}.png"))
print({
    "screen": (dialog.screen().availableGeometry().width(), dialog.screen().availableGeometry().height()),
    "dialog": (dialog.width(), dialog.height()),
    "minimum_hint": (dialog.minimumSizeHint().width(), dialog.minimumSizeHint().height()),
})
dialog.close()
