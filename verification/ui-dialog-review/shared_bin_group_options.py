"""Render nonfunctional shared-bin-group wizard layouts for design review."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

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


def streams():
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("All assigned waste streams"), 1)
    layout.addWidget(QPushButton("Select streams…"))
    layout.addWidget(QPushButton("All"))
    return widget


def options():
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for index, (text, checked) in enumerate((
        ("Only enabled departments", True),
        ("Only selected departments", False),
        ("Overwrite existing shared bin groups", False),
    )):
        check = QCheckBox(text)
        check.setChecked(checked)
        layout.addWidget(check, index // 2, index % 2)
    layout.addWidget(label("Minimum departments per group"), 2, 0)
    layout.addWidget(QLineEdit("2"), 2, 1)
    return widget


def setup():
    category = QComboBox()
    category.addItems(("Waste", "Stores"))
    return group("Group source and rules", [
        ("Source task category", category),
        ("Waste streams to update", streams()),
        ("Shared bin group prefix", QLineEdit("SHARED-BIN")),
        ("Options", options()),
    ])


def actions():
    box = QGroupBox("Preview actions")
    grid = QGridLayout(box)
    for index, text in enumerate(("Refresh preview", "Select all groups", "Select none",
                                  "Select current floor groups")):
        grid.addWidget(QPushButton(text), index // 2, index % 2)
    return box


INTRO = (
    "Find departments that already share the same assigned task-category location, then write a matching "
    "shared bin group for each assigned waste stream. Different waste streams receive different "
    "physical-bin group IDs. This does not change the existing category location assignments."
)


def top(root, option):
    root.addWidget(label(f"AUTO SHARED BIN GROUPS  ·  Design option {option}"))
    root.addWidget(label(INTRO, True))


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label(
        "Selected 2 shared-location groups · 5 departments · 9 waste stream updates · 1 existing group skipped.", True), 1)
    row.addWidget(QPushButton("Cancel"))
    save = QPushButton("Save groups")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def summary_table():
    table = QTableWidget(2, 4)
    table.setHorizontalHeaderLabels(("Use", "Shared location", "Updates", "Skipped"))
    for row, values in enumerate((
        ("", "Shared Bin Store A", "5", "1"),
        ("", "Shared Bin Store B", "4", "0"),
    )):
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 0:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
            table.setItem(row, col, item)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    for col in (2, 3):
        table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.selectRow(0)
    return table


def detail_panel():
    box = QGroupBox("Shared Bin Store A · group details")
    layout = QVBoxLayout(box)
    layout.addWidget(label("Departments: Emergency, Imaging, Ward North · Floors: 0, 1", True))
    layout.addWidget(label("Generated shared bin group IDs (one per waste stream):", True))
    ids = QPlainTextEdit(
        "Clinical waste\nSHARED-BIN-SHARED-BIN-STORE-A-CLINICAL-WASTE\n\n"
        "General waste\nSHARED-BIN-SHARED-BIN-STORE-A-GENERAL-WASTE"
    )
    ids.setReadOnly(True)
    ids.setMinimumHeight(135)
    layout.addWidget(ids, 1)
    layout.addWidget(label("5 stream updates · 1 existing group skipped", True))
    return box


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Shared bin groups — Option A: table and detail panel")
    root = QVBoxLayout(dialog)
    top(root, "A")
    root.addWidget(setup())
    root.addWidget(actions())
    lower = QHBoxLayout()
    lower.addWidget(summary_table(), 2)
    lower.addWidget(detail_panel(), 3)
    root.addLayout(lower, 1)
    footer(root)
    return dialog


GROUPS = (
    ("Shared Bin Store A", "Emergency, Imaging, Ward North", "0, 1", 5, 1,
     "SHARED-BIN-SHARED-BIN-STORE-A-CLINICAL-WASTE",
     "SHARED-BIN-SHARED-BIN-STORE-A-GENERAL-WASTE"),
    ("Shared Bin Store B", "Ward South, Theatre", "1", 4, 0,
     "SHARED-BIN-SHARED-BIN-STORE-B-CLINICAL-WASTE",
     "SHARED-BIN-SHARED-BIN-STORE-B-GENERAL-WASTE"),
)


def group_card(data):
    location, departments, floors, updates, skipped, clinical, general = data
    box = QGroupBox(location)
    layout = QVBoxLayout(box)
    use = QCheckBox("Use this shared-location group")
    use.setChecked(True)
    layout.addWidget(use)
    layout.addWidget(label(f"Departments: {departments} · Floors: {floors}", True))
    layout.addWidget(label("Generated group IDs:", True))
    layout.addWidget(label(f"Clinical waste: {clinical}", True))
    layout.addWidget(label(f"General waste: {general}", True))
    layout.addWidget(label(f"{updates} stream updates · {skipped} existing groups skipped", True))
    return box


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Shared bin groups — Option B: full group cards")
    root = QVBoxLayout(dialog)
    top(root, "B")
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.addWidget(setup())
    layout.addWidget(actions())
    for data in GROUPS:
        layout.addWidget(group_card(data))
    layout.addStretch(1)
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
    QPushButton, QComboBox, QLineEdit { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
""")
for name, factory in (("A", option_a), ("B", option_b)):
    for width, height in ((1040, 680), (1024, 768), (1600, 900)):
        dialog = factory()
        dialog.resize(width, height)
        dialog.show()
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"shared-bin-groups-{name}-{width}.png"))
        dialog.close()
