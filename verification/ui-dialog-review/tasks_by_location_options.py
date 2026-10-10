"""Nonfunctional tasks-by-location/department layouts in the review style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
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
QTreeWidget::item { padding: 5px 2px; }
""")

ROWS = [
    ("TASK-0101", "Linen trolley", "2026-10-04 08:30:00", "2026-10-04 08:47:00", "North surgical ward staging bay", "North surgical ward", "Ward porter A", "1", "00:17:00", "Complete", "Manual"),
    ("TASK-0102", "Supply box", "2026-10-04 09:30:00", "2026-10-04 09:47:00", "Day treatment reception", "Day treatment centre", "Ward porter B", "1", "00:17:00", "Complete", "Generated"),
    ("TASK-0201", "Sterile kit", "2026-10-04 10:30:00", "2026-10-04 10:47:00", "North surgical ward staging bay", "North surgical ward", "Ward porter A", "1", "00:17:00", "In progress", "Generated"),
    ("TASK-0202", "Empty trolley", "2026-10-04 11:30:00", "2026-10-04 11:47:00", "Central stores dispatch", "Imaging", "Unassigned", "1", "00:17:00", "Waiting", "Generated"),
]
HEADINGS = ("Task", "Payload", "Start time", "End time", "Finish location",
            "Department", "Staff", "People", "Duration", "Status", "Source")


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def toolbar(root):
    line = QHBoxLayout()
    line.addWidget(label("Group by"))
    group = QComboBox()
    group.addItems(("Department", "Location"))
    line.addWidget(group)
    line.addWidget(label("Filter"))
    edit = QLineEdit()
    edit.setPlaceholderText("Task, payload, department, start or finish location")
    line.addWidget(edit, 1)
    root.addLayout(line)
    root.addWidget(label("Groups: 3  |  Full tasks: 4  |  Double-click a row to jump to its start time."))


def tree(full):
    widget = QTreeWidget()
    keys = HEADINGS if full else ("Task", "Payload", "Start time", "Status")
    widget.setColumnCount(len(keys))
    widget.setHeaderLabels(keys)
    widget.setAlternatingRowColors(True)
    widget.header().setSectionResizeMode(QHeaderView.Interactive)
    widths = (170, 135, 170, 170, 195, 170, 150, 70, 100, 110, 100) if full else (200, 140, 100, 110)
    for index, width in enumerate(widths):
        widget.setColumnWidth(index, width)
    for department, indexes in (("Day treatment centre", [1]), ("Imaging", [3]),
                                ("North surgical ward", [0, 2])):
        parent = QTreeWidgetItem([department])
        widget.addTopLevelItem(parent)
        for index in indexes:
            row = ROWS[index]
            values = row if full else (row[0], row[1], row[2][11:16], row[9])
            parent.addChild(QTreeWidgetItem(list(values)))
        parent.setExpanded(True)
    widget.setCurrentItem(widget.topLevelItem(2).child(0))
    return widget


def detail():
    box = QGroupBox("Selected full task · TASK-0101")
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, value in (
        ("Payload", "Linen trolley"),
        ("Start → end", "2026-10-04 08:30:00 → 2026-10-04 08:47:00"),
        ("Start location", "Central stores dispatch"),
        ("Finish location", "North surgical ward staging bay"),
        ("Department", "North surgical ward"),
        ("Staff / people", "Ward porter A / 1"),
        ("Duration / status", "00:17:00 / Complete"),
        ("Source", "Manual"),
        ("Details", "TASK-0101: Central stores dispatch to North surgical ward staging bay; complete"),
    ):
        form.addRow(title, label(value))
    return box


def footer(root):
    line = QHBoxLayout()
    line.addStretch(1)
    line.addWidget(QPushButton("Close"))
    root.addLayout(line)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Tasks by location / department — Option A")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASKS BY LOCATION / DEPARTMENT  ·  Design option A"))
    toolbar(root)
    root.addWidget(tree(True), 1)
    root.addWidget(detail())
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Tasks by location / department — Option B")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASKS BY LOCATION / DEPARTMENT  ·  Design option B"))
    toolbar(root)
    body = QHBoxLayout()
    body.addWidget(tree(False), 3)
    body.addWidget(detail(), 2)
    root.addLayout(body, 1)
    footer(root)
    return dialog


for width, height in ((1024, 768), (1420, 720), (1600, 900)):
    for key, dialog in (("A", option_a()), ("B", option_b())):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"tasks-by-location-{key}-{width}.png"))
        dialog.close()
