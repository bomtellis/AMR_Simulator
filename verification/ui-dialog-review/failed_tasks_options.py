"""Nonfunctional Failed Tasks layouts in the established review style."""
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QTableWidget,
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

HEADINGS = ("Failed at", "Task", "Payload", "Final destination",
            "AMR drop-off zone", "Pickup", "Department", "AMR", "Failure reason")
ROWS = [
    ("2026-10-04 12:06:51", "TASK-0402", "Waste bin", "Waste processing hub",
     "-", "West outpatient clinic", "OUT-W", "-",
     "No AMR was available within the configured dispatch window."),
    ("2026-10-04 11:42:18", "TASK-0309", "Sealed clinical supplies", "South diagnostics ward",
     "South diagnostics receiving", "Central stores loading area", "DIAG-S", "AMR-05",
     "Destination inventory space was fully occupied; delivery could not be completed before the task deadline."),
    ("2026-10-04 10:25:11", "TASK-0204", "Sterile equipment crate", "East theatre preparation",
     "Theatre goods drop-off", "Ground floor stores", "THEATRE", "AMR-03",
     "Required payload slot was unavailable on the assigned AMR."),
    ("2026-10-04 09:12:43", "TASK-0101", "Linen trolley", "North surgical ward staging bay",
     "Ward AMR drop-off", "Central linen collection", "SURG-N", "AMR-01",
     "No viable route to the final destination after the north service corridor was closed."),
]


def label(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def header(root, option):
    root.addWidget(label(f"FAILED TASKS  ·  Design option {option}"))
    root.addWidget(label("Failed tasks: 4  ·  Select a task to inspect its failure and view the destination."))
    line = QHBoxLayout()
    line.addWidget(label("Filter"))
    field = QLineEdit()
    field.setPlaceholderText("Task, payload, destination, drop-off zone, department or reason")
    line.addWidget(field, 1)
    root.addLayout(line)


def footer(root):
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    view = QPushButton("View at destination")
    view.setObjectName("primary")
    buttons.addWidget(view)
    buttons.addWidget(QPushButton("Close"))
    root.addLayout(buttons)


def full_table():
    widget = QTableWidget(len(ROWS), len(HEADINGS))
    widget.setHorizontalHeaderLabels(HEADINGS)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((185, 230, 160, 180, 180, 170, 105, 90, 430)):
        widget.setColumnWidth(index, width)
    for row_index, row in enumerate(ROWS):
        for column_index, value in enumerate(row):
            widget.setItem(row_index, column_index, QTableWidgetItem(value))
    widget.selectRow(1)
    return widget


def selected_detail():
    row = ROWS[1]
    box = QGroupBox("Selected failed task · TASK-0309")
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for index in (0, 2, 3, 4, 5, 6, 7, 8):
        form.addRow(HEADINGS[index], label(row[index]))
    return box


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Failed Tasks — Option A: full table and selected detail")
    root = QVBoxLayout(dialog)
    header(root, "A")
    root.addWidget(full_table(), 1)
    detail = selected_detail()
    detail.setMaximumHeight(230)
    root.addWidget(detail)
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Failed Tasks — Option B: task list and full detail")
    root = QVBoxLayout(dialog)
    header(root, "B")
    sort_line = QHBoxLayout()
    sort_line.addWidget(label("Sort by"))
    sort = QComboBox()
    sort.addItems(("Failed at", "Task", "Payload", "Final destination",
                   "AMR drop-off zone", "Pickup", "Department", "AMR", "Failure reason"))
    sort_line.addWidget(sort)
    direction = QComboBox()
    direction.addItems(("Descending", "Ascending"))
    sort_line.addWidget(direction)
    sort_line.addStretch(1)
    root.addLayout(sort_line)

    split = QHBoxLayout()
    choices = QListWidget()
    choices.setMinimumWidth(300)
    choices.setMaximumWidth(460)
    for row in ROWS:
        item = QListWidgetItem(f"{row[1]}  ·  {row[0]}\n{row[3]}")
        item.setSizeHint(QSize(340, 56))
        choices.addItem(item)
    choices.setCurrentRow(1)
    split.addWidget(choices, 2)

    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.addWidget(selected_detail())
    body_layout.addStretch(1)
    area.setWidget(body)
    split.addWidget(area, 3)
    root.addLayout(split, 1)
    footer(root)
    return dialog


for width, height in ((1000, 600), (1400, 700), (1600, 720)):
    for key, dialog in (("A", option_a()), ("B", option_b())):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"failed-tasks-{key}-{width}.png"))
        dialog.close()
