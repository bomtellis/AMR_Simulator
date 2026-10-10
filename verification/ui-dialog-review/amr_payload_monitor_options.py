"""Nonfunctional AMR payload monitor layouts in the established review style."""
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

HEADINGS = ("AMR", "Payloads onboard", "Count", "Slots", "Task(s)",
            "Status", "Segment", "From", "To", "Floor", "Updated")
ROWS = [
    ("AMR-01", "Bay A: Linen trolley (TASK-0101), Bay B: Sealed clinical supplies (TASK-0102)",
     "2", "2/3", "TASK-0101, TASK-0102", "in transit", "corridor",
     "North surgical ward staging bay", "Central stores loading area", "2", "2026-10-04 11:40:32"),
    ("AMR-02", "-", "0", "0/2", "TASK-0201", "loading", "pickup",
     "East theatre prep", "East theatre prep", "2", "2026-10-04 11:41:05"),
    ("AMR-03", "Flexible slot: Equipment crate (TASK-0301)",
     "1", "1/1", "TASK-0301", "in lift", "lift_loaded",
     "Ground floor reception", "North surgical ward staging bay", "1", "2026-10-04 11:39:48"),
]


def label(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def header(root, option):
    root.addWidget(label(f"AMR PAYLOAD MONITOR  ·  Design option {option}"))
    root.addWidget(label("Time: 2026-10-04 11:42:18  ·  AMRs: 3  ·  Payloads onboard: 3"))


def footer(root):
    line = QHBoxLayout()
    line.addStretch(1)
    line.addWidget(QPushButton("Close"))
    root.addLayout(line)


def comparison_table():
    widget = QTableWidget(len(ROWS), len(HEADINGS))
    widget.setHorizontalHeaderLabels(HEADINGS)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((120, 260, 70, 90, 190, 130, 130, 150, 150, 70, 160)):
        widget.setColumnWidth(index, width)
    for row_index, row in enumerate(ROWS):
        for column_index, value in enumerate(row):
            widget.setItem(row_index, column_index, QTableWidgetItem(value))
    widget.selectRow(0)
    return widget


def selected_detail(width):
    box = QGroupBox("Selected AMR · AMR-01")
    root = QVBoxLayout(box)
    root.addWidget(label(f"Payloads onboard: {ROWS[0][1]}"))
    grid = QGridLayout()
    pairs = 2 if width < 1100 else 3
    for index, column in enumerate(range(2, len(HEADINGS))):
        row_index = index // pairs
        col_index = (index % pairs) * 2
        grid.addWidget(label(HEADINGS[column]), row_index, col_index)
        grid.addWidget(label(ROWS[0][column]), row_index, col_index + 1)
    for col in range(1, pairs * 2, 2):
        grid.setColumnStretch(col, 1)
    root.addLayout(grid)
    return box


def option_a(width):
    dialog = QDialog()
    dialog.setWindowTitle("AMR Payload Monitor — Option A: full comparison table")
    root = QVBoxLayout(dialog)
    header(root, "A")
    root.addWidget(comparison_table(), 1)
    root.addWidget(selected_detail(width))
    footer(root)
    return dialog


def amr_card(row):
    box = QGroupBox(row[0])
    root = QVBoxLayout(box)
    root.addWidget(label(f"Payloads onboard: {row[1]}"))
    grid = QGridLayout()
    for index, column in enumerate(range(2, len(HEADINGS))):
        grid.addWidget(label(HEADINGS[column]), index, 0)
        grid.addWidget(label(row[column]), index, 1)
    grid.setColumnStretch(1, 1)
    root.addLayout(grid)
    return box


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("AMR Payload Monitor — Option B: responsive AMR cards")
    root = QVBoxLayout(dialog)
    header(root, "B")
    body = QWidget()
    grid = QGridLayout(body)
    columns = 1 if width < 1100 else (2 if width < 1500 else 3)
    for index, row in enumerate(ROWS):
        grid.addWidget(amr_card(row), index // columns, index % columns)
    grid.setRowStretch((len(ROWS) + columns - 1) // columns, 1)
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(body)
    root.addWidget(area, 1)
    footer(root)
    return dialog


for width, height in ((900, 540), (1320, 520), (1600, 720)):
    for key, dialog in (("A", option_a(width)), ("B", option_b(width))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"amr-payload-monitor-{key}-{width}.png"))
        dialog.close()
