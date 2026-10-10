"""Nonfunctional active inventory-payload layouts in the review style."""
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

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

HEADINGS = ("Inventory space", "Current payload", "Waste stream", "Container group",
            "Task", "AMR", "Status", "Updated", "Source")
ROWS = [
    ("North bay 01", "Sealed clinical waste bin", "Clinical waste", "Ward clinical bins",
     "TASK-0101", "AMR-01", "Occupied", "2026-10-04 11:39:02", "Simulation CSV"),
    ("North bay 02", "Linen trolley", "-", "-", "TASK-0102", "AMR-03",
     "Occupied", "2026-10-04 11:41:15", "Simulation CSV"),
    ("Flexible overflow area", "-", "-", "-", "-", "-", "Empty", "-", "Layout JSON"),
    ("Unassigned overflow 1", "Replacement container", "General waste", "Ward general bins",
     "TASK-0304", "AMR-05", "Capacity overflow", "2026-10-04 11:42:18",
     "Simulation CSV (capacity overflow)"),
]
DETAILS = (
    "Payload: Sealed clinical waste bin\n"
    "Details: Size 0.80 x 0.60 x 1.20 m | Weight 28.0 kg\n"
    "Waste volume filled: 0.240 / 0.500 m³ (48%)\n"
    "Fill rate: 0.032 m³/day\n"
    "Waste stream: Clinical waste\n"
    "Container group: Ward clinical bins\n"
    "Instance: BIN-009\n"
    "Task: TASK-0101\n"
    "Status: Occupied\n"
    "Source: Simulation CSV"
)


def label(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def header(root, option):
    root.addWidget(label(f"INVENTORY PAYLOADS  ·  Design option {option}"))
    root.addWidget(label("Location: North surgical ward staging bay  ·  Time: 2026-10-04 11:42:18  ·  Spaces: 4"))


def footer(root):
    line = QHBoxLayout()
    line.addStretch(1)
    line.addWidget(QPushButton("Close"))
    root.addLayout(line)


def details_text(height):
    widget = QPlainTextEdit()
    widget.setPlainText(DETAILS)
    widget.setReadOnly(True)
    widget.setMaximumHeight(height)
    return widget


def table():
    widget = QTableWidget(len(ROWS), len(HEADINGS))
    widget.setHorizontalHeaderLabels(HEADINGS)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((180, 170, 120, 160, 100, 100, 130, 160, 150)):
        widget.setColumnWidth(index, width)
    for row_index, row in enumerate(ROWS):
        for column_index, value in enumerate(row):
            widget.setItem(row_index, column_index, QTableWidgetItem(value))
    widget.selectRow(0)
    return widget


def selected_details(compact):
    box = QGroupBox("Selected inventory space · North bay 01")
    root = QVBoxLayout(box)
    if compact:
        root.addWidget(label("Sealed clinical waste bin  ·  Occupied  ·  TASK-0101  ·  AMR-01"))
        root.addWidget(label("Clinical waste  ·  Ward clinical bins  ·  Updated: 2026-10-04 11:39:02  ·  Source: Simulation CSV"))
    else:
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        for index in range(1, len(HEADINGS)):
            form.addRow(HEADINGS[index], label(ROWS[0][index]))
        root.addLayout(form)
    root.addWidget(label("Payload details (current row tooltip)"))
    root.addWidget(details_text(110) if compact else label(DETAILS))
    return box


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Inventory payloads — Option A: table and selected detail")
    root = QVBoxLayout(dialog)
    header(root, "A")
    root.addWidget(table(), 1)
    root.addWidget(selected_details(True))
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Inventory payloads — Option B: space list and full detail")
    root = QVBoxLayout(dialog)
    header(root, "B")
    split = QHBoxLayout()
    choices = QListWidget()
    choices.setMinimumWidth(250)
    choices.setMaximumWidth(360)
    for row in ROWS:
        item = QListWidgetItem(f"{row[0]}  ·  {row[6]}\n{row[1]}")
        item.setSizeHint(QSize(300, 54))
        choices.addItem(item)
    choices.setCurrentRow(0)
    split.addWidget(choices, 2)

    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.addWidget(selected_details(False))
    body_layout.addStretch(1)
    area.setWidget(body)
    split.addWidget(area, 3)
    root.addLayout(split, 1)
    footer(root)
    return dialog


for width, height in ((900, 520), (1420, 520), (1600, 800)):
    for key, dialog in (("A", option_a()), ("B", option_b())):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"inventory-payloads-{key}-{width}.png"))
        dialog.close()
