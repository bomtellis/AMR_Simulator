"""Render nonfunctional shared-location wizard layouts for design review."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    widget = QLabel(text)
    widget.setWordWrap(wrap)
    return widget


def group(title, rows):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, control in rows:
        form.addRow(title, control)
    return box


def shared_locations():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("Shared Store"))
    row = QHBoxLayout()
    row.addWidget(QPushButton("Select shared location…"))
    row.addWidget(QPushButton("Clear"))
    row.addStretch(1)
    layout.addLayout(row)
    return widget


def options():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for text in ("Replace existing assignments for this category", "Only enabled departments"):
        check = QCheckBox(text)
        check.setChecked(True)
        layout.addWidget(check)
    return widget


def assignment():
    return group("Assignment", [
        ("Task category", combo()),
        ("Shared location(s)", shared_locations()),
        ("Options", options()),
    ])


def combo():
    widget = QComboBox()
    widget.addItems(("Stores", "Waste"))
    return widget


def selection_tools():
    box = QGroupBox("Select departments")
    grid = QGridLayout(box)
    for index, text in enumerate(("Select all", "Select none", "Select current floor",
                                  "Select departments already using category")):
        grid.addWidget(QPushButton(text), index // 2, index % 2)
    return box


def department_table():
    tree = QTreeWidget()
    tree.setColumnCount(6)
    tree.setHeaderLabels(("Use", "ID", "Name", "Floor", "Enabled", "Current category locations"))
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(False)
    tree.setMinimumHeight(150)
    sample = (
        ("D-01", "Emergency", "0", "Yes", "Stores A", True),
        ("D-02", "Imaging", "0", "Yes", "Stores A", True),
        ("D-05", "Outpatients", "0", "No", "", False),
        ("D-03", "Ward North", "1", "Yes", "", True),
        ("D-04", "Ward South", "1", "Yes", "Stores B", False),
        ("D-06", "Theatre", "2", "Yes", "", False),
    )
    for code, name, floor, enabled, locations, selected in sample:
        item = QTreeWidgetItem(("", code, name, floor, enabled, locations))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if selected else Qt.Unchecked)
        tree.addTopLevelItem(item)
    for index, width in enumerate((55, 75, 150, 70, 80)):
        tree.header().setSectionResizeMode(index, QHeaderView.Interactive)
        tree.setColumnWidth(index, width)
    tree.header().setSectionResizeMode(5, QHeaderView.Stretch)
    return tree


INTRO = (
    "Assign the same pickup / drop-off location to several departments for a task generation category. "
    "This is useful where multiple departments share one store, bin, collection point or common drop-off location."
)


def top(root, option):
    root.addWidget(label(f"TASK CATEGORY SHARED LOCATION  ·  Design option {option}"))
    root.addWidget(label(INTRO, True))


def footer(root, step=None):
    row = QHBoxLayout()
    row.addWidget(label("Ready to assign 1 shared location to 3 departments."), 1)
    row.addWidget(QPushButton("Cancel"))
    if step == 1:
        action = QPushButton("Next: departments")
        action.setObjectName("primary")
        row.addWidget(action)
    else:
        if step == 2:
            row.addWidget(QPushButton("Back"))
        action = QPushButton("Save assignment")
        action.setObjectName("primary")
        row.addWidget(action)
    root.addLayout(row)


def option_a(step):
    dialog = QDialog()
    dialog.setWindowTitle("Shared location — Option A: guided wizard")
    root = QVBoxLayout(dialog)
    top(root, "A")
    root.addWidget(label("1  Assignment     ›     2  Departments"))
    if step == 1:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(assignment())
        layout.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setWidget(content)
        root.addWidget(area, 1)
    else:
        root.addWidget(label("Stores  ·  Shared Store  ·  Replace existing assignments  ·  Only enabled departments"))
        root.addWidget(selection_tools())
        root.addWidget(department_table(), 1)
    footer(root, step)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Shared location — Option B: grouped single page")
    root = QVBoxLayout(dialog)
    top(root, "B")
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.addWidget(assignment())
    layout.addWidget(selection_tools())
    layout.addWidget(department_table(), 1)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setMinimumSize(0, 0)
    area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
    area.setWidget(content)
    root.addWidget(area, 1)
    footer(root)
    return dialog


app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
    QWidget { font-size: 10pt; color: #213044; }
    QDialog { background: #f7f9fc; }
    QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9; border-radius: 5px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QPushButton, QComboBox { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
    QTreeWidget { background: white; }
    QTreeWidget::item { min-height: 24px; }
""")
for width, height in ((920, 620), (1024, 768), (1600, 900)):
    for step in (1, 2):
        dialog = option_a(step)
        dialog.resize(width, height)
        dialog.show()
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"shared-location-A-step{step}-{width}.png"))
        dialog.close()
    dialog = option_b()
    dialog.resize(width, height)
    dialog.show()
    for _ in range(5):
        app.processEvents()
    dialog.grab().save(str(OUT / f"shared-location-B-{width}.png"))
    dialog.close()
