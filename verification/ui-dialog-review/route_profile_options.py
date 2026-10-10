"""Render nonfunctional layouts for the active RouteProfilesEditorV2."""
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QTabWidget, QVBoxLayout, QWidget, QDialog)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    widget = QLabel(text)
    widget.setWordWrap(wrap)
    return widget


def top(root, option):
    root.addWidget(label(f"ROUTE PROFILES  ·  Design option {option}"))
    root.addWidget(label(
        "Profiles define the allowed routes: include a shared section in each profile that may use it. "
        "Empty lists mean unrestricted; edge pairs are directional. Task allowances extend profile allowances. "
        "Profiles apply after pickup. Empty approach, charging and idle-return journeys are unrestricted "
        "by profiles. Set a return profile explicitly when a return must follow a particular route.", True))


def profile_list():
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.addWidget(label("Profiles"))
    profiles = QListWidget()
    profiles.addItems(("default", "Service route", "Public route"))
    profiles.setCurrentRow(1)
    layout.addWidget(profiles, 1)
    row = QHBoxLayout()
    row.addWidget(QPushButton("Add"))
    row.addWidget(QPushButton("Delete"))
    row.addStretch(1)
    layout.addLayout(row)
    return panel


def choice_row(summary, *buttons):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label(summary, True), 1)
    for name in buttons:
        layout.addWidget(QPushButton(name))
    return widget


def access():
    group = QGroupBox("Profile access")
    form = QFormLayout(group)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.addRow("Profile name", QLineEdit("Service route"))
    form.addRow("Allowed lifts", choice_row("Lift 1", "Pick"))
    form.addRow("Allowed nodes", choice_row("A, Door, B", "Pick", "Graphical…"))
    return group


EDGE_JSON = '[\n  ["A", "Door"],\n  ["Door", "B"]\n]'


def edges():
    group = QGroupBox("Directional allowed edges · JSON array pairs")
    layout = QVBoxLayout(group)
    editor = QPlainTextEdit(EDGE_JSON)
    editor.setLineWrapMode(QPlainTextEdit.NoWrap)
    layout.addWidget(editor, 1)
    row = QHBoxLayout()
    row.addWidget(QPushButton("Generate from selected nodes"))
    row.addWidget(QPushButton("Clear edges"))
    row.addStretch(1)
    layout.addLayout(row)
    return group


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("Editing Service route · Apply edits to this profile before switching profiles", True), 1)
    row.addWidget(QPushButton("Apply Changes"))
    save = QPushButton("Save All")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Route Profiles — Option A: focused tabs")
    root = QVBoxLayout(dialog)
    top(root, "A")
    body = QHBoxLayout()
    body.addWidget(profile_list(), 1)
    tabs = QTabWidget()
    access_page = QWidget()
    access_layout = QVBoxLayout(access_page)
    access_layout.addWidget(access())
    access_layout.addStretch(1)
    tabs.addTab(access_page, "Profile access")
    edge_page = QWidget()
    edge_layout = QVBoxLayout(edge_page)
    edge_layout.addWidget(edges(), 1)
    tabs.addTab(edge_page, "Allowed edges")
    tabs.setCurrentIndex(1)
    body.addWidget(tabs, 3)
    root.addLayout(body, 1)
    footer(root)
    return dialog, tabs


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Route Profiles — Option B: grouped editor")
    root = QVBoxLayout(dialog)
    top(root, "B")
    body = QHBoxLayout()
    body.addWidget(profile_list(), 1)
    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.addWidget(access())
    right_layout.addWidget(edges(), 1)
    body.addWidget(right, 3)
    root.addLayout(body, 1)
    footer(root)
    return dialog


app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
    QWidget { font-size: 10pt; color: #213044; }
    QDialog { background: #f7f9fc; }
    QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9; border-radius: 5px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QPushButton, QLineEdit { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
    QTabWidget::pane { border: 1px solid #b9c9d9; }
    QTabBar::tab { padding: 8px 12px; }
    QListWidget::item { padding: 8px 4px; }
""")
for width, height in ((1024, 768), (1200, 720), (1600, 900)):
    dialog, tabs = option_a()
    dialog.resize(width, height)
    dialog.show()
    for index, slug in enumerate(("access", "edges")):
        tabs.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"route-profiles-A-{slug}-{width}.png"))
    dialog.close()
    dialog = option_b()
    dialog.resize(width, height)
    dialog.show()
    for _ in range(5):
        app.processEvents()
    dialog.grab().save(str(OUT / f"route-profiles-B-{width}.png"))
    dialog.close()
