"""Nonfunctional Lift Monitor layouts in the established review style."""
from pathlib import Path
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from amr_sim_visualiser_pyside6 import LiftShaftWidget

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
QWidget { font-size: 10pt; color: #213044; }
QDialog { background: #f7f9fc; }
QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9;
            border-radius: 5px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton, QLineEdit { min-height: 28px; }
QPushButton#primary { background: #005ea8; color: white; font-weight: 600;
                      padding: 4px 14px; }
""")

STATES = [
    {"lift_id": "North service lift", "served_floors": [0, 1, 2, 3, 4],
     "current_floor": 2.4, "occupant": "AMR-01", "waiting_amrs": ["AMR-04", "AMR-07"]},
    {"lift_id": "Theatre goods lift", "served_floors": [1, 2, 3],
     "current_floor": 1, "occupant": None, "waiting_amrs": []},
    {"lift_id": "South logistics lift", "served_floors": [0, 1, 2, 3, 4],
     "current_floor": 3, "occupant": "AMR-03", "waiting_amrs": ["AMR-09"]},
    {"lift_id": "East transfer lift", "served_floors": [0, 1, 2],
     "current_floor": 0.5, "occupant": None, "waiting_amrs": ["AMR-12", "AMR-15"]},
]


def label(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def shaft(state):
    widget = LiftShaftWidget()
    widget.set_lift_state(state)
    return widget


def waiting_list(state):
    widget = QListWidget()
    widget.addItems(state["waiting_amrs"] or ["-"])
    widget.setMinimumHeight(95)
    return widget


def header(root, option):
    root.addWidget(label(f"LIFT MONITOR  ·  Design option {option}"))
    root.addWidget(label("Live lift positions  ·  4 lifts"))


def footer(root):
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    buttons.addWidget(QPushButton("Close"))
    root.addLayout(buttons)


def lift_card(state):
    box = QGroupBox(state["lift_id"])
    row = QHBoxLayout(box)
    row.addWidget(shaft(state))
    details = QVBoxLayout()
    details.addWidget(label("Served floors: " + ", ".join(f"F{floor}" for floor in state["served_floors"])))
    details.addWidget(label(f"Current position: F{state['current_floor']:.2f}"))
    details.addWidget(label("Occupant: " + (state["occupant"] or "-")))
    details.addWidget(label("Waiting AMRs"))
    details.addWidget(waiting_list(state), 1)
    row.addLayout(details, 1)
    return box


def option_a(width):
    dialog = QDialog()
    dialog.setWindowTitle("Lift Monitor — Option A: responsive lift panels")
    root = QVBoxLayout(dialog)
    header(root, "A")
    body = QWidget()
    grid = QGridLayout(body)
    columns = 2 if width < 1200 else 4
    for index, state in enumerate(STATES):
        grid.addWidget(lift_card(state), index // columns, index % columns)
    grid.setRowStretch((len(STATES) + columns - 1) // columns, 1)
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(body)
    root.addWidget(area, 1)
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Lift Monitor — Option B: lift list and detail")
    root = QVBoxLayout(dialog)
    header(root, "B")
    row = QHBoxLayout()
    lift_list = QListWidget()
    lift_list.setMinimumWidth(200)
    lift_list.setMaximumWidth(250)
    for state in STATES:
        item = QListWidgetItem(
            f"{state['lift_id']}\nF{state['current_floor']:.2f}  ·  "
            f"{state['occupant'] or '-'}  ·  {len(state['waiting_amrs'])} waiting"
        )
        item.setSizeHint(QSize(220, 55))
        lift_list.addItem(item)
    lift_list.setCurrentRow(0)
    row.addWidget(lift_list)

    box = QGroupBox("North service lift")
    detail = QHBoxLayout(box)
    detail.addWidget(shaft(STATES[0]), alignment=Qt.AlignTop)
    info = QVBoxLayout()
    info.addWidget(label("Served floors: F0, F1, F2, F3, F4"))
    info.addWidget(label("Current position: F2.40"))
    info.addWidget(label("Occupant: AMR-01"))
    info.addWidget(label("Waiting AMRs"))
    waiting = waiting_list(STATES[0])
    waiting.setMaximumHeight(160)
    info.addWidget(waiting)
    info.addStretch(1)
    detail.addLayout(info, 1)
    row.addWidget(box, 1)
    root.addLayout(row, 1)
    footer(root)
    return dialog


for width, height in ((700, 520), (980, 520), (1400, 700)):
    for key, dialog in (("A", option_a(width)), ("B", option_b())):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"lift-monitor-{key}-{width}.png"))
        dialog.close()
