"""Nonfunctional location inventory-spaces layouts in the review style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget,
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
QPushButton { min-height: 28px; }
""")

HEADINGS = ("Inventory space", "Length m", "Width m", "Height m", "Flexible",
            "Occupied", "Payload", "Task", "Reserved by", "Points")
ROWS = [
    ("North bay 01", "2.2", "1.4", "1.8", "No", "Yes", "Linen trolley", "TASK-0101", "-", "N-101"),
    ("North bay 02", "2.2", "1.4", "1.8", "No", "No", "-", "-", "TASK-0201", "N-102"),
    ("Flexible overflow area", "3.5", "2.0", "2.4", "Yes", "Yes", "Supply box", "TASK-0102", "-", "N-103, N-104"),
]


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def header(root, option):
    root.addWidget(label(f"INVENTORY SPACES  ·  Design option {option}"))
    root.addWidget(label("Location: North surgical ward staging bay  ·  Inventory spaces: 3"))


def footer(root):
    line = QHBoxLayout()
    line.addStretch(1)
    line.addWidget(QPushButton("Close"))
    root.addLayout(line)


def table():
    widget = QTableWidget(len(ROWS), len(HEADINGS))
    widget.setHorizontalHeaderLabels(HEADINGS)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((180, 90, 90, 90, 80, 90, 160, 120, 120, 90)):
        widget.setColumnWidth(index, width)
    for row_index, row in enumerate(ROWS):
        for column_index, value in enumerate(row):
            widget.setItem(row_index, column_index, QTableWidgetItem(value))
    widget.selectRow(0)
    return widget


def detail(row, title):
    box = QGroupBox(title)
    grid = QGridLayout(box)
    details = [
        ("Dimensions (m)", f"{row[1]} × {row[2]} × {row[3]}"),
        ("Flexible", row[4]), ("Occupied", row[5]),
        ("Payload", row[6]), ("Task", row[7]),
        ("Reserved by", row[8]), ("Points", row[9]),
    ]
    for index, (name, value) in enumerate(details):
        target_row = index // 2
        start_col = (index % 2) * 2
        grid.addWidget(label(name), target_row, start_col)
        grid.addWidget(label(value), target_row, start_col + 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)
    return box


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Inventory spaces — Option A: table and detail")
    root = QVBoxLayout(dialog)
    header(root, "A")
    root.addWidget(table(), 1)
    root.addWidget(detail(ROWS[0], "Selected inventory space · North bay 01"))
    footer(root)
    return dialog


def space_card(row):
    box = QGroupBox(row[0])
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.addRow("Dimensions (m)", label(f"{row[1]} × {row[2]} × {row[3]}"))
    form.addRow("Flexible", label(row[4]))
    form.addRow("Occupied", label(row[5]))
    form.addRow("Payload", label(row[6]))
    form.addRow("Task", label(row[7]))
    form.addRow("Reserved by", label(row[8]))
    form.addRow("Points", label(row[9]))
    return box


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("Inventory spaces — Option B: responsive cards")
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


for width, height in ((800, 500), (1080, 460), (1440, 720)):
    for key, dialog in (("A", option_a()), ("B", option_b(width))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"inventory-spaces-{key}-{width}.png"))
        dialog.close()
