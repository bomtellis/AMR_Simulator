"""Nonfunctional maximum payload-space utilisation layouts for design review."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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

HEADINGS = (
    "Payload space", "Ever occupied", "Payload entries", "Occupied time",
    "Time utilised %", "First occupied", "Last released", "Occupied at peak",
)
ROWS = [
    ("North bay 01", "Yes", "6", "03:20:00", "33.3", "2026-10-04 08:18:00", "2026-10-04 16:12:00", "Yes"),
    ("North bay 02", "Yes", "3", "02:05:00", "20.8", "2026-10-04 09:31:00", "2026-10-04 15:04:00", "Yes"),
    ("Flexible overflow area", "No", "0", "00:00:00", "0.0", "-", "-", "No"),
]
METHOD = (
    "Maximum occupancy is reconstructed over the complete loaded simulation, "
    "not just the current playback time. Time utilisation is the percentage "
    "of the simulation horizon for which each payload space was occupied. "
    "Assignments use the recorded payload-space evidence where available; "
    "unassigned payloads are reconstructed from location events."
)


def label(value):
    result = QLabel(value)
    result.setWordWrap(True)
    return result


def header(root, option):
    root.addWidget(label(f"MAXIMUM PAYLOAD-SPACE UTILISATION  ·  Design option {option}"))
    root.addWidget(label("Location: North surgical ward staging bay"))

    metrics = QGroupBox("Peak occupancy")
    grid = QGridLayout(metrics)
    for index, (name, value) in enumerate((
        ("Maximum occupied", "2 / 3 payload spaces (66.7%)"),
        ("Peak time", "2026-10-04 11:42:18"),
        ("Overflow at peak", "1"),
        ("Simulation horizon", "2026-10-04 08:00–18:00"),
    )):
        grid.addWidget(label(name), index // 2, (index % 2) * 2)
        grid.addWidget(label(value), index // 2, (index % 2) * 2 + 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)
    root.addWidget(metrics)

    method = QGroupBox("How this is calculated")
    method_layout = QVBoxLayout(method)
    method_layout.addWidget(label(METHOD))
    root.addWidget(method)


def footer(root):
    line = QHBoxLayout()
    line.addStretch(1)
    line.addWidget(QPushButton("Close"))
    root.addLayout(line)


def table():
    widget = QTableWidget(len(ROWS), len(HEADINGS))
    widget.setHorizontalHeaderLabels(HEADINGS)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((190, 105, 105, 125, 115, 165, 165, 120)):
        widget.setColumnWidth(index, width)
    for row_index, row in enumerate(ROWS):
        for column_index, value in enumerate(row):
            widget.setItem(row_index, column_index, QTableWidgetItem(value))
    widget.selectRow(0)
    return widget


def selected_detail():
    box = QGroupBox("Selected payload space · North bay 01")
    grid = QGridLayout(box)
    for index, (name, value) in enumerate(zip(HEADINGS[1:], ROWS[0][1:])):
        grid.addWidget(label(name), index // 4, (index % 4) * 2)
        grid.addWidget(label(value), index // 4, (index % 4) * 2 + 1)
    for col in (1, 3, 5, 7):
        grid.setColumnStretch(col, 1)
    return box


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Maximum payload-space utilisation — Option A: comparison table")
    root = QVBoxLayout(dialog)
    header(root, "A")
    root.addWidget(table(), 1)
    root.addWidget(selected_detail())
    footer(root)
    return dialog


def space_card(row):
    box = QGroupBox(row[0])
    grid = QGridLayout(box)
    for index, (name, value) in enumerate(zip(HEADINGS[1:], row[1:])):
        grid.addWidget(label(name), index, 0)
        grid.addWidget(label(value), index, 1)
    grid.setColumnStretch(1, 1)
    return box


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("Maximum payload-space utilisation — Option B: full-detail cards")
    root = QVBoxLayout(dialog)
    header(root, "B")
    body = QWidget()
    grid = QGridLayout(body)
    columns = 1 if width < 1000 else (2 if width < 1400 else 3)
    for index, row in enumerate(ROWS):
        grid.addWidget(space_card(row), index // columns, index % columns)
    grid.setRowStretch((len(ROWS) + columns - 1) // columns, 1)
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(body)
    root.addWidget(area, 1)
    footer(root)
    return dialog


for width, height in ((900, 560), (1120, 500), (1440, 720)):
    for key, dialog in (("A", option_a()), ("B", option_b(width))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"payload-utilisation-{key}-{width}.png"))
        dialog.close()
