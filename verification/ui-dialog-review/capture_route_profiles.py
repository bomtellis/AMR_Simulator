"""Capture the active RouteProfilesEditorV2 with representative values."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import RouteProfilesEditorV2

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
dialog = RouteProfilesEditorV2(
    None,
    {
        "default": {"allowed_lifts": [], "allowed_nodes": [], "allowed_edges": []},
        "Service route": {
            "allowed_lifts": ["Lift 1"],
            "allowed_nodes": ["A", "Door", "B"],
            "allowed_edges": [["A", "Door"], ["Door", "B"]],
        },
        "Public route": {
            "allowed_lifts": [], "allowed_nodes": ["A", "Door"],
            "allowed_edges": [["A", "Door"]],
        },
    },
    ["A", "Door", "B", "Ward Bay"],
    ["Lift 1", "Lift 2"],
    [{"from": "A", "to": "Door", "bidirectional": True},
     {"from": "Door", "to": "B", "bidirectional": False}],
    lambda _profiles: None,
    floor_map={"A": 0, "Door": 0, "B": 1, "Ward Bay": 1},
)
dialog.profile_list.setCurrentRow(1)
rows = []
for width, height in ((1200, 720), (1024, 768)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    rows.append({"requested": (width, height), "actual": (dialog.width(), dialog.height())})
    dialog.grab().save(str(OUT / f"route-profiles-{width}.png"))
print(rows)
dialog.close()
