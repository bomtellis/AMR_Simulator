"""Render two nonfunctional Corridor settings layouts for design review."""
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    widget = QLabel(text)
    widget.setWordWrap(wrap)
    return widget


def button(text):
    return QPushButton(text)


def combo(*items):
    widget = QComboBox()
    widget.addItems(items)
    return widget


def width_control():
    widget = QDoubleSpinBox()
    widget.setRange(0.0, 100.0)
    widget.setDecimals(3)
    widget.setSpecialValueText("Leave unchanged")
    widget.setSuffix(" m")
    return widget


def profile_control():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("Leave unchanged"))
    actions = QHBoxLayout()
    actions.addWidget(button("Choose…"))
    actions.addWidget(button("Clear profiles"))
    layout.addLayout(actions)
    return widget


def box(title, rows):
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for name, widget in rows:
        form.addRow(name, widget)
    return group


def top(root, option):
    root.addWidget(label(f"CORRIDORS, DOORS AND PEOPLE USE  ·  Design option {option}"))
    root.addWidget(label(
        "Select one or more rows, choose only the values that need changing, then apply them. "
        "The effective width is the narrowest of the corridor and any door opening at either endpoint.", True))


def footer(root, selected):
    row = QHBoxLayout()
    status = label(selected)
    row.addWidget(status, 1)
    row.addWidget(button("Cancel"))
    save = button("Save changes")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)
    return status


def edit_panel():
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.addWidget(box("Selected corridors · change only specified values", [
        ("Traffic direction", combo("Leave unchanged", "Two-way / bidirectional", "One-way")),
        ("Nominal clear width", width_control()),
        ("People classification", combo("Leave unchanged", "None / unrestricted", "Staff", "Public", "Mixed staff and public")),
        ("Assigned people profiles", profile_control()),
    ]))
    layout.addWidget(button("Apply to 2 selected corridors"))
    layout.addWidget(label(
        "A two-way corridor can form two AMR lanes only when the AMR and its carried payload "
        "fit within one half of the effective width. People profiles add timed pedestrian use.", True))
    layout.addStretch(1)
    return panel


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Corridors and doors — Option A: selection + inspector")
    root = QVBoxLayout(dialog)
    top(root, "A")
    tabs = QTabWidget()
    root.addWidget(tabs, 1)
    page = QWidget()
    page_layout = QHBoxLayout(page)
    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.addWidget(QLineEdit("Filter corridors by node, use or profile…"))
    left_layout.addWidget(button("Select corridor assets on map…"))
    left_layout.addWidget(label("Corridors · Ctrl/Shift-click to select more"))
    routes = QListWidget()
    routes.addItems(["✓ A → Door    ·    two-way    ·    effective 0.800 m",
                     "✓ Door → B    ·    two-way    ·    effective 0.800 m"])
    routes.setCurrentRow(0)
    left_layout.addWidget(routes, 1)
    left_layout.addWidget(label("Selected route: A → Door · two-way · corridor width 3.000 m · effective width 0.800 m · people use None / unrestricted · profiles None", True))
    page_layout.addWidget(left, 3)
    page_layout.addWidget(edit_panel(), 2)
    tabs.addTab(page, "Corridors")
    tabs.addTab(doors_a(), "Door openings")
    status = footer(root, "2 corridors selected · Apply updates the draft; Save commits it")
    tabs.currentChanged.connect(lambda index: status.setText(
        ("1 corridor node selected" if index else "2 corridors selected")
        + " · Apply updates the draft; Save commits it"))
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Corridors and doors — Option B: table + edit drawer")
    root = QVBoxLayout(dialog)
    top(root, "B")
    tabs = QTabWidget()
    root.addWidget(tabs, 1)
    page = QWidget()
    page_layout = QVBoxLayout(page)
    filter_row = QHBoxLayout()
    filter_row.addWidget(QLineEdit("Filter by node, people use or profile…"), 1)
    filter_row.addWidget(button("Select on map…"))
    page_layout.addLayout(filter_row)
    page_layout.addWidget(label("2 selected · Ctrl/Shift-click adds rows to a bulk edit."))
    table = QTableWidget(2, 7)
    table.setHorizontalHeaderLabels(["From", "To", "Traffic", "Corridor width", "Effective width", "People use", "People profiles"])
    for row, values in enumerate((("A", "Door", "Two-way", "3.000 m", "0.800 m", "None / unrestricted", "None"),
                                  ("Door", "B", "Two-way", "3.000 m", "0.800 m", "None / unrestricted", "None"))):
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.selectRow(0)
    page_layout.addWidget(table, 1)
    drawer = QGroupBox("Edit selected corridors")
    drawer_layout = QVBoxLayout(drawer)
    first = QHBoxLayout()
    first.addWidget(label("Traffic direction"))
    first.addWidget(combo("Leave unchanged", "Two-way / bidirectional", "One-way"), 1)
    first.addWidget(label("Nominal width"))
    first.addWidget(width_control(), 1)
    drawer_layout.addLayout(first)
    second = QHBoxLayout()
    second.addWidget(label("People use"))
    second.addWidget(combo("Leave unchanged", "None / unrestricted", "Staff", "Public", "Mixed staff and public"), 1)
    second.addWidget(label("Profiles: Leave unchanged"))
    drawer_layout.addLayout(second)
    actions = QHBoxLayout()
    actions.addStretch(1)
    actions.addWidget(button("Choose…"))
    actions.addWidget(button("Clear profiles"))
    actions.addWidget(button("Apply to 2 selected"))
    drawer_layout.addLayout(actions)
    page_layout.addWidget(drawer)
    page_layout.addWidget(label(
        "A two-way corridor can form two AMR lanes only when the AMR and its carried payload "
        "fit within one half of the effective width. People profiles add timed pedestrian use.", True))
    tabs.addTab(page, "Corridors")
    tabs.addTab(doors_b(), "Door openings")
    status = footer(root, "2 corridors selected · Apply updates the draft; Save commits it")
    tabs.currentChanged.connect(lambda index: status.setText(
        ("1 corridor node selected" if index else "2 corridors selected")
        + " · Apply updates the draft; Save commits it"))
    return dialog


def doors_a():
    page = QWidget()
    layout = QHBoxLayout(page)
    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.addWidget(QLineEdit("Filter by corridor node or floor…"))
    left_layout.addWidget(button("Select corridor nodes on map…"))
    left_layout.addWidget(label("Corridor nodes · Ctrl/Shift-click to select more"))
    nodes = QListWidget()
    nodes.addItem("✓ Door · floor 0 · door opening · clear width 0.800 m")
    nodes.setCurrentRow(0)
    left_layout.addWidget(nodes, 1)
    left_layout.addWidget(label("Selected node: Door · floor 0 · door opening · clear width 0.800 m", True))
    layout.addWidget(left, 3)
    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.addWidget(box("Selected nodes · change only specified values", [
        ("Door classification", combo("Leave unchanged", "This node is a door opening", "This node is not a door")),
        ("Clear opening width", width_control()),
    ]))
    right_layout.addWidget(button("Apply to selected nodes"))
    right_layout.addWidget(label("Mark the graph node at the restrictive opening. Every connected corridor uses this width when it is narrower than the corridor.", True))
    right_layout.addStretch(1)
    layout.addWidget(right, 2)
    return page


def doors_b():
    page = QWidget()
    layout = QVBoxLayout(page)
    filter_row = QHBoxLayout()
    filter_row.addWidget(QLineEdit("Filter by corridor node or floor…"), 1)
    filter_row.addWidget(button("Select corridor nodes on map…"))
    layout.addLayout(filter_row)
    layout.addWidget(label("Select corridor nodes to mark or remove door restrictions."))
    table = QTableWidget(1, 4)
    table.setHorizontalHeaderLabels(["Corridor node", "Floor", "Door opening", "Clear opening width"])
    for col, value in enumerate(("Door", "0", "Door", "0.800 m")):
        table.setItem(0, col, QTableWidgetItem(value))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.selectRow(0)
    layout.addWidget(table, 1)
    edit = QGroupBox("Edit selected corridor nodes")
    row = QHBoxLayout(edit)
    row.addWidget(label("Door classification"))
    row.addWidget(combo("Leave unchanged", "This node is a door opening", "This node is not a door"), 1)
    row.addWidget(label("Clear opening width"))
    row.addWidget(width_control(), 1)
    row.addWidget(button("Apply to selected nodes"))
    layout.addWidget(edit)
    layout.addWidget(label("Mark the graph node at the restrictive opening. Every connected corridor uses this width when it is narrower than the corridor.", True))
    return page


app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
    QWidget { font-size: 10pt; color: #213044; }
    QDialog { background: #f7f9fc; }
    QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9; border-radius: 5px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QPushButton, QComboBox, QLineEdit, QListWidget { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
    QTabWidget::pane { border: 1px solid #b9c9d9; }
    QTabBar::tab { padding: 8px 12px; }
""")
for name, factory in (("A", option_a), ("B", option_b)):
    dialog = factory()
    for width, height in ((1024, 768), (1600, 900)):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"corridors-{name}-{width}.png"))
        dialog.findChild(QTabWidget).setCurrentIndex(1)
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"corridors-{name}-doors-{width}.png"))
        dialog.findChild(QTabWidget).setCurrentIndex(0)
    dialog.close()
