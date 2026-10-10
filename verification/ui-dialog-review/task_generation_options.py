"""Render two nonfunctional Task generation layout options for design review."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, *, wrap=False):
    item = QLabel(text)
    item.setWordWrap(wrap)
    return item


def button(text):
    return QPushButton(text)


def field(text=""):
    item = QLineEdit(text)
    return item


def combo(items, selected=0):
    item = QComboBox()
    item.addItems(items)
    item.setCurrentIndex(selected)
    return item


def form_group(title, rows):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for name, control in rows:
        form.addRow(name, control)
    return box


def footer(layout, context):
    row = QHBoxLayout()
    row.addWidget(label(context), 1)
    row.addWidget(button("Export configuration…"))
    row.addWidget(button("Cancel"))
    save = button("Save")
    save.setObjectName("primary")
    row.addWidget(save)
    layout.addLayout(row)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Task generation — Option A: selection + focused tabs")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASK GENERATION  ·  Design option A", wrap=True))
    root.addWidget(label("Select a category and department, then edit one related group at a time. All existing settings remain available.", wrap=True))
    staff = QHBoxLayout()
    staff.addWidget(label("Automatic generation  ☑     Staff: 09:00–17:00 · Mon–Fri · 4 on / 4 off", wrap=True), 1)
    staff.addWidget(button("Global staff…"))
    root.addLayout(staff)
    body = QHBoxLayout()
    root.addLayout(body, 1)
    selection = QGroupBox("Choose scope")
    selection.setMinimumWidth(240)
    selection.setMaximumWidth(280)
    left = QVBoxLayout(selection)
    left.addWidget(label("Categories"))
    categories = QListWidget()
    categories.addItems(["Catering", "Linen", "Pharmacy", "SSD", "Stores", "Waste"])
    categories.setCurrentRow(0)
    left.addWidget(categories, 1)
    cat_buttons = QHBoxLayout()
    cat_buttons.addWidget(button("Add"))
    cat_buttons.addWidget(button("Delete"))
    left.addLayout(cat_buttons)
    left.addWidget(label("Department override"))
    left.addWidget(combo(["All departments", "Ward A", "Ward B"]))
    left.addWidget(button("Manage department groups…"))
    body.addWidget(selection)
    tabs = QTabWidget()
    body.addWidget(tabs, 1)
    pages = [
        ("Basics", [
            form_group("Category", [("Enabled", QCheckBox("Generate tasks")),
                                    ("Display name", field("Catering")),
                                    ("Generation mode", combo(["Scheduled", "Threshold", "Continuous", "Sporadic", "Hybrid"])),
                                    ("Priority", field("40"))]),
            form_group("At a glance", [("Pickup", label("Department location")),
                                        ("Drop-off", label("Select destination locations")),
                                        ("Return", label("Generate return / exchange task"))]),
        ]),
        ("Locations & routing", [
            form_group("Source and destination", [("Pickup/source location", combo(["Choose location…", "Stores", "Ward A"])),
                                                  ("Department role", QCheckBox("Use department location as drop-off")),
                                                  ("Drop-off destinations", button("Select destinations…"))]),
            form_group("Payload and route", [("Payload", combo(["Choose payload…", "Box"])),
                                              ("Route profile", combo(["Unrestricted", "Clean", "Dirty"]))]),
        ]),
        ("Schedule & staff", [
            form_group("Timing", [("Schedule times", field("09:00, 13:00")),
                                   ("Timeframe", button("Set active days and hours…"))]),
            form_group("Staff", [("Staff handling", QCheckBox("Requires staff")),
                                  ("Working hours", button("Edit hours…"))]),
        ]),
        ("Returns & stock", [
            form_group("Return task", [("Generate return", QCheckBox("Generate return / exchange task")),
                                       ("Return payload", combo(["Choose payload…", "Box"])),
                                       ("Return delay (minutes)", field("0"))]),
            form_group("Stock", [("Tracked exchange", QCheckBox("Generate tracked item exchange tasks"))]),
        ]),
        ("Notes & help", [
            form_group("Stored guidance", [("Schedule", label("HH:MM values; staff-assisted timeframe releases use applicable working hours.", wrap=True)),
                                            ("Compatibility", label("The first drop-off is also saved as dropoff_location.", wrap=True)),
                                            ("Groups", label("Each configured department group creates an additional run.", wrap=True)),
                                            ("Waste", label("Stream-specific volume stays in Departments → Manage waste streams.", wrap=True))]),
        ]),
    ]
    for title, groups in pages:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        for group in groups:
            page_layout.addWidget(group)
        page_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        tabs.addTab(scroll, title)
    footer(root, "Catering  /  All departments  /  Scheduled")
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Task generation — Option B: full-width sections")
    root = QVBoxLayout(dialog)
    root.addWidget(label("TASK GENERATION  ·  Design option B", wrap=True))
    root.addWidget(label("Choose a category and department above one full-width form. Scroll through the sections; no setting is hidden by a tab.", wrap=True))
    scope = QGroupBox("Editing scope")
    scope_row = QHBoxLayout(scope)
    scope_row.addWidget(label("Category"))
    scope_row.addWidget(combo(["Catering", "Linen", "Pharmacy", "SSD", "Stores", "Waste"]), 1)
    scope_row.addWidget(button("Add / delete…"))
    scope_row.addWidget(label("Department"))
    scope_row.addWidget(combo(["All departments", "Ward A", "Ward B"]), 1)
    scope_row.addWidget(button("Groups…"))
    root.addWidget(scope)
    body = QWidget()
    sections = QVBoxLayout(body)
    sections.addWidget(form_group("1 · Basics", [("Generate tasks", QCheckBox("Enabled")),
                                                  ("Display name", field("Catering")),
                                                  ("Mode", combo(["Scheduled", "Threshold", "Continuous", "Sporadic", "Hybrid"])),
                                                  ("Priority", field("40"))]))
    sections.addWidget(form_group("2 · Locations, payload and route", [
        ("Department location role", QCheckBox("Use as drop-off")),
        ("Pickup/source", combo(["Choose location…", "Stores", "Ward A"])),
        ("Drop-off destinations", button("Select destinations…")),
        ("Payload", combo(["Choose payload…", "Box"])),
        ("Route profile", combo(["Unrestricted", "Clean", "Dirty"]))]))
    sections.addWidget(form_group("3 · Timing and staff", [
        ("Schedule times", field("09:00, 13:00")),
        ("Working hours", button("Edit hours…")),
        ("Global staff", button("Global staff configuration…"))]))
    sections.addWidget(form_group("4 · Returns and stock", [
        ("Return task", QCheckBox("Generate return / exchange task")),
        ("Return payload", combo(["Choose payload…", "Box"])),
        ("Return delay (minutes)", field("0")),
        ("Tracked exchange", QCheckBox("Generate tracked item exchange tasks"))]))
    sections.addWidget(form_group("Reference and assumptions", [
        ("Schedule", label("HH:MM values; staff-assisted timeframe releases use applicable working hours.", wrap=True)),
        ("Compatibility", label("The first drop-off is also saved as dropoff_location.", wrap=True)),
        ("Groups", label("Each configured department group creates an additional run.", wrap=True)),
        ("Waste", label("Stream-specific volume stays in Departments → Manage waste streams.", wrap=True))]))
    sections.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(body)
    root.addWidget(scroll, 1)
    footer(root, "Catering  /  All departments  /  Scheduled")
    return dialog


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
        dialog.grab().save(str(OUT / f"task-generation-{name}-{width}.png"))
    dialog.close()
