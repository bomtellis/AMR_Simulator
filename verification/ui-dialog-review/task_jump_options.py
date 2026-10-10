"""Nonfunctional Tasks by AMR jump layouts in the established review style."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
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
QTreeWidget::item { padding: 5px 2px; }
""")


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def info_box(title="Selected task · TASK-0101"):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.addRow("AMR", label("AMR-01"))
    form.addRow("Payload", label("Linen trolley"))
    form.addRow("Origin", label("Central stores dispatch"))
    form.addRow("Destination", label("North surgical ward staging bay"))
    form.addRow("Duration", label("00:16:30"))
    form.addRow("Datetime", label("2026-10-04 08:48:00"))
    return box


def full_tree():
    tree = QTreeWidget()
    tree.setColumnCount(6)
    tree.setHeaderLabels(("Task ID / Segment", "Payload", "Origin", "Destination",
                          "Duration", "Datetime"))
    tree.setAlternatingRowColors(True)
    tree.header().setSectionResizeMode(QHeaderView.Interactive)
    for index, width in enumerate((220, 115, 185, 230, 85, 170)):
        tree.setColumnWidth(index, width)
    for amr_id, task_data in (
        ("AMR-01", [
            ("TASK-0101", "Linen trolley", "Central stores dispatch",
             "North surgical ward staging bay", "00:16:30", "2026-10-04 08:48:00"),
            ("TASK-0102", "Supply box", "Central stores dispatch",
             "Day treatment reception", "00:11:45", "2026-10-04 09:06:00"),
        ]),
        ("AMR-02", [
            ("TASK-0201", "Linen trolley", "Central stores dispatch",
             "North surgical ward staging bay", "00:16:30", "2026-10-04 10:08:00"),
            ("TASK-0202", "Supply box", "Central stores dispatch",
             "Day treatment reception", "00:11:45", "2026-10-04 10:26:00"),
        ]),
    ):
        amr = QTreeWidgetItem([amr_id])
        for task in task_data:
            item = QTreeWidgetItem(list(task))
            if task[0] == "TASK-0101":
                item.addChild(QTreeWidgetItem([
                    "Pickup and travel", "", "Central stores dispatch",
                    "Main lift lobby", "00:06:20", "2026-10-04 08:48:00",
                ]))
                item.addChild(QTreeWidgetItem([
                    "Delivery", "", "Main lift lobby",
                    "North surgical ward staging bay", "00:10:10",
                    "2026-10-04 08:54:00",
                ]))
                item.setExpanded(True)
            amr.addChild(item)
        tree.addTopLevelItem(amr)
        amr.setExpanded(True)
    tree.setCurrentItem(tree.topLevelItem(0).child(0))
    return tree


def navigator():
    tree = QTreeWidget()
    tree.setHeaderLabels(("AMR / Task / Segment",))
    tree.header().setStretchLastSection(True)
    for amr_id, task_ids in (("AMR-01", ["TASK-0101", "TASK-0102"]),
                             ("AMR-02", ["TASK-0201", "TASK-0202"])):
        amr = QTreeWidgetItem([amr_id])
        for task_id in task_ids:
            task = QTreeWidgetItem([task_id])
            if task_id == "TASK-0101":
                task.addChild(QTreeWidgetItem(["Pickup and travel"]))
                task.addChild(QTreeWidgetItem(["Delivery"]))
                task.setExpanded(True)
            amr.addChild(task)
        tree.addTopLevelItem(amr)
        amr.setExpanded(True)
    tree.setCurrentItem(tree.topLevelItem(0).child(0))
    return tree


def footer(root):
    root.addWidget(label("Double-click a task or segment to jump to its start time. Column headers cycle through ascending, descending and original order."))


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Tasks by AMR — Option A: full sortable tree")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASKS BY AMR  ·  Design option A"))
    root.addWidget(full_tree(), 1)
    root.addWidget(info_box())
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Tasks by AMR — Option B: navigator and details")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASKS BY AMR  ·  Design option B"))
    sort_line = QHBoxLayout()
    sort_line.addWidget(label("Sort by"))
    sort_choice = QComboBox()
    sort_choice.addItems(("Task ID / Segment", "Payload",
                          "Origin", "Destination", "Duration", "Datetime"))
    sort_line.addWidget(sort_choice)
    sort_line.addWidget(label("Order"))
    direction = QComboBox()
    direction.addItems(("Original", "Ascending", "Descending"))
    sort_line.addWidget(direction)
    sort_line.addStretch(1)
    root.addLayout(sort_line)
    body = QHBoxLayout()
    body.addWidget(navigator(), 1)
    details = QWidget()
    detail_layout = QVBoxLayout(details)
    detail_layout.setContentsMargins(0, 0, 0, 0)
    detail_layout.addWidget(info_box())
    segments = QGroupBox("Segments")
    segments_layout = QVBoxLayout(segments)
    segments_layout.addWidget(label("Pickup and travel · Central stores dispatch → Main lift lobby · 00:06:20 · 08:48:00"))
    segments_layout.addWidget(label("Delivery · Main lift lobby → North surgical ward staging bay · 00:10:10 · 08:54:00"))
    detail_layout.addWidget(segments)
    detail_layout.addStretch(1)
    body.addWidget(details, 2)
    root.addLayout(body, 1)
    root.addWidget(label("Double-click a task or segment to jump to its start time."))
    return dialog


for width, height in ((700, 520), (980, 620), (1400, 800)):
    for key, dialog in (("A", option_a()), ("B", option_b())):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        for tree in dialog.findChildren(QTreeWidget):
            if tree.topLevelItemCount():
                tree.topLevelItem(0).setExpanded(True)
                tree.topLevelItem(0).child(0).setExpanded(True)
        app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"task-jump-{key}-{width}.png"))
        dialog.close()
