"""Capture the shared MultiSelectPicker with grouped, long location names."""
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QDialogButtonBox

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from advanced_dialogs import MultiSelectPicker

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])

floor_one = ["North surgical ward staging bay", "Central stores dispatch",
             "Imaging reception and handover", "Main lift lobby",
             "Outpatient day treatment bay", "West corridor door"]
floor_two = ["South surgical ward staging bay", "Sterile supplies store",
             "Day treatment waiting area", "West lift lobby",
             "Rehabilitation supply bay", "East corridor door"]
options = floor_one + floor_two
floor_map = {name: "Floor 1" for name in floor_one}
floor_map.update({name: "Floor 2" for name in floor_two})
selected = [floor_one[0], floor_one[2], floor_two[0], floor_two[4]]

dialog = MultiSelectPicker(None, "Select task locations", options,
                           selected=selected, group_resolver=floor_map.get)
for width, height in ((420, 500), (520, 620), (820, 720)):
    dialog.resize(width, height)
    dialog.show()
    for _ in range(6):
        app.processEvents()
    buttons = dialog.findChild(QDialogButtonBox)
    print((width, height), "actual", (dialog.width(), dialog.height()),
          "buttons", (buttons.y(), buttons.height()), "dpr", dialog.devicePixelRatioF())
    dialog.grab().save(str(OUT / f"multi-select-{width}.png"))
dialog.resize(520, 620)
dialog.filter_edit.setText("ward")
dialog.show()
for _ in range(6):
    app.processEvents()
dialog.grab().save(str(OUT / "multi-select-filtered.png"))
dialog.close()
