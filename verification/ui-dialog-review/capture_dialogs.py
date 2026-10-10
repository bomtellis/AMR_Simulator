"""Capture representative real dialogs and record their layout at this display scale."""
import json
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QScrollArea, QTabWidget

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from app import AMRGraphEditor
from dialogs import (CorridorSettingsDialog, DepartmentEditorDialog,
                     SimulationSettingsDialog, TaskGenerationSettingsDialog)
from tests.test_engineering_reference import reference_config
from tests.test_generation_reference import grouped_config


def capture(name, dialog, output):
    if name == "department":
        dialog.resize(1024, 768)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    box = dialog.findChild(QDialogButtonBox)
    scrolls = dialog.findChildren(QScrollArea)
    data = {
        "name": name,
        "screen": [dialog.screen().availableGeometry().width(), dialog.screen().availableGeometry().height()],
        "size": [dialog.width(), dialog.height()],
        "minimum_hint": [dialog.minimumSizeHint().width(), dialog.minimumSizeHint().height()],
        "button_visible": bool(box and box.isVisible() and dialog.rect().intersects(box.geometry())),
        "scrolls": len(scrolls),
        "wrapped": bool(dialog.property("amrScrollWrapped")),
    }
    dialog.grab().save(str(output / f"{name}.png"))
    if name == "corridors":
        tabs = dialog.findChild(QTabWidget)
        tabs.setCurrentIndex(1)
        for _ in range(3):
            app.processEvents()
        dialog.grab().save(str(output / "corridors-doors.png"))
    dialog.close()
    dialog.deleteLater()
    return data


app = QApplication.instance() or QApplication([])
editor = AMRGraphEditor()
editor._drawings_enabled = False
config = reference_config()
locations = [item["name"] for item in config.get("locations", [])]
payloads = [item["name"] for item in config.get("payloads", [])]
profiles = list(config.get("route_profiles", {}))
out = ROOT / "verification" / "ui-dialog-review" / "captures"
out.mkdir(exist_ok=True)
factories = {
    "task-generation": lambda: TaskGenerationSettingsDialog(
        editor, config.get("task_generation", {}), locations, payloads,
        profiles, config.get("departments", []), lambda _: None),
    "department": lambda: DepartmentEditorDialog(
        editor, ["A", "B", "Ward Bay", "Zone X"], ["General", "Clinical"],
        seed=grouped_config()["departments"][0],
        task_generation_categories=[("stores", "Stores", "-STORES"),
                                    ("catering", "Catering", "-CAT"),
                                    ("waste", "Waste", "-WASTE")]),
    "simulation-settings": lambda: SimulationSettingsDialog(editor, full_config=config),
    "corridors": lambda: CorridorSettingsDialog(
        editor, config["corridors"]["edges"], config["corridors"]["nodes"]),
}
rows = []
for name, factory in factories.items():
    try:
        rows.append(capture(name, factory(), out))
    except Exception as exc:
        rows.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
print(json.dumps(rows, indent=2))
editor.close()
