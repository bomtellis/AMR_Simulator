"""Nonfunctional Edit Multiple Tasks layouts in the established review style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
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
QPushButton#primary { background: #005ea8; color: white; font-weight: 600;
                      padding: 4px 14px; }
""")

FIELDS = [
    ("Release date and time", "2026-10-04 08:30:00", True),
    ("Target allowance", "900 s", False),
    ("Priority", "10", True),
    ("Labels (comma-separated)", "stores, morning-round", False),
    ("Route profile", "Service route", False),
]


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def input_for(title, value, enabled):
    if title == "Route profile":
        widget = QComboBox()
        widget.addItem(value)
    else:
        widget = QLineEdit(value)
    widget.setEnabled(enabled)
    return widget


def row_group(title, fields):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setVerticalSpacing(12)
    for field_title, value, checked in fields:
        toggle = QCheckBox(field_title)
        toggle.setChecked(checked)
        editor = input_for(field_title, value, checked)
        toggle.toggled.connect(editor.setEnabled)
        form.addRow(toggle, editor)
    return box


def card(title, value, checked):
    box = QGroupBox()
    root = QVBoxLayout(box)
    toggle = QCheckBox("Update " + title.lower())
    toggle.setChecked(checked)
    editor = input_for(title, value, checked)
    toggle.toggled.connect(editor.setEnabled)
    root.addWidget(toggle)
    root.addWidget(editor)
    return box


def footer(root):
    line = QHBoxLayout()
    line.addWidget(label("2 fields selected for update · other values stay unchanged"), 1)
    line.addWidget(QPushButton("Cancel"))
    apply = QPushButton("Apply updates")
    apply.setObjectName("primary")
    line.addWidget(apply)
    root.addLayout(line)


def scroll(body):
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(body)
    return area


def header(root, option):
    root.addWidget(label(f"EDIT MULTIPLE TASKS  ·  Design option {option}"))
    root.addWidget(label(
        "Apply the chosen values to all selected tasks. Fields left unchecked keep "
        "their existing values. Select at least one field."
    ))


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Edit Multiple Tasks — Option A: grouped rows")
    root = QVBoxLayout(dialog)
    header(root, "A")
    body = QWidget()
    column = QVBoxLayout(body)
    column.addWidget(row_group("Timing and priority", FIELDS[:3]))
    column.addWidget(row_group("Labels and route", FIELDS[3:]))
    column.addStretch(1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


def option_b(wide):
    dialog = QDialog()
    dialog.setWindowTitle("Edit Multiple Tasks — Option B: field cards")
    root = QVBoxLayout(dialog)
    header(root, "B")
    body = QWidget()
    grid = QGridLayout(body)
    columns = 2 if wide else 1
    for index, (title, value, checked) in enumerate(FIELDS):
        grid.addWidget(card(title, value, checked), index // columns, index % columns)
    grid.setRowStretch((len(FIELDS) + columns - 1) // columns, 1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


for width, height in ((560, 400), (760, 520), (1024, 768)):
    for key, dialog in (("A", option_a()), ("B", option_b(width >= 760))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"edit-multiple-tasks-{key}-{width}.png"))
        dialog.close()
