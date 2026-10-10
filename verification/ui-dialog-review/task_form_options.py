"""Nonfunctional manual Task dialog layouts in the review's established style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
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


def label(text):
    item = QLabel(text)
    item.setWordWrap(True)
    return item


def choice(text):
    widget = QComboBox()
    widget.addItem(text)
    return widget


def location(text):
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(text)
    edit.setReadOnly(True)
    row.addWidget(edit, 1)
    row.addWidget(QPushButton("Select…"))
    return widget


def group(title, rows, description=""):
    box = QGroupBox(title)
    root = QVBoxLayout(box)
    if description:
        root.addWidget(label(description))
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(8)
    for name, widget in rows:
        form.addRow(name, widget)
    root.addLayout(form)
    return box


def journey():
    return group("Task and journey", [
        ("ID", QLineEdit("RECOVER-017")),
        ("Pickup", location("Ward North staging bay")),
        ("Dropoff", location("Central sterile stores")),
        ("Payload", choice("Linen trolley")),
        ("Route profile", choice("Service route")),
    ], "Select graph locations rather than typing names to avoid invalid references.")


def timing():
    return group("Release and priority", [
        ("Release date and time", QLineEdit("2026-10-04 08:30:00")),
        ("Target allowance", QLineEdit("900 s")),
        ("Priority", QLineEdit("10")),
        ("Labels (comma-separated)", QLineEdit("recovery, ward-north")),
    ])


def recovery():
    box = QGroupBox("Staged container recovery")
    root = QVBoxLayout(box)
    checked = QCheckBox("Recover a container staged after a failed return")
    checked.setChecked(True)
    root.addWidget(checked)
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.addRow("Container ID", QLineEdit("TROLLEY-0042"))
    root.addLayout(form)
    root.addWidget(label(
        "Use the exact container ID and pickup location from run evidence. "
        "The new run must reach that staged recovery state. Normal route, robot "
        "and storage checks apply; unconfirmed arrivals cannot be recovered."
    ))
    return box


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("Manual task · one physical payload"), 1)
    row.addWidget(QPushButton("Cancel"))
    save = QPushButton("Save")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def scroll(widget):
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Task — Option A: grouped form")
    root = QVBoxLayout(dialog)
    root.addWidget(label("MANUAL TASK  ·  Design option A"))
    body = QWidget()
    column = QVBoxLayout(body)
    column.setSpacing(10)
    column.addWidget(journey())
    column.addWidget(timing())
    column.addWidget(recovery())
    column.addStretch(1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


def option_b(wide):
    dialog = QDialog()
    dialog.setWindowTitle("Task — Option B: responsive split view")
    root = QVBoxLayout(dialog)
    root.addWidget(label("MANUAL TASK  ·  Design option B"))
    body = QWidget()
    if wide:
        panels = QHBoxLayout(body)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(journey())
        left_layout.addStretch(1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(timing())
        right_layout.addWidget(recovery())
        right_layout.addStretch(1)
        panels.addWidget(left, 1)
        panels.addWidget(right, 1)
    else:
        column = QVBoxLayout(body)
        column.addWidget(journey())
        column.addWidget(timing())
        column.addWidget(recovery())
        column.addStretch(1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


for width, height in ((700, 600), (1024, 768), (1600, 900)):
    for key, dialog in (("A", option_a()), ("B", option_b(width >= 1024))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"task-form-{key}-{width}.png"))
        dialog.close()
