"""Nonfunctional one-to-many Task layouts in the established review style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
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
QListWidget::item { padding: 7px 4px; }
""")

DESTINATIONS = ["North surgical ward", "Day treatment centre", "Imaging reception"]


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def choice(value):
    widget = QComboBox()
    widget.addItem(value)
    return widget


def group(title, rows):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    for name, widget in rows:
        form.addRow(name, widget)
    return box


def destination_picker():
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(label("3 selected: " + ", ".join(DESTINATIONS)), 1)
    row.addWidget(QPushButton("Select…"))
    return widget


def common_timing():
    return group("Shared timing and labels", [
        ("Release date and time", QLineEdit("2026-01-01 08:00:00")),
        ("Target allowance", QLineEdit("300 s")),
        ("Priority", QLineEdit("10")),
        ("Labels (comma-separated)", QLineEdit("stores, morning-round")),
    ])


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("3 destinations · 3 tasks will be created"), 1)
    row.addWidget(QPushButton("Cancel"))
    create = QPushButton("Create tasks")
    create.setObjectName("primary")
    row.addWidget(create)
    root.addLayout(row)


def scroll(widget):
    area = QScrollArea()
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def header(root, option):
    root.addWidget(label(f"ONE-TO-MANY TASKS  ·  Design option {option}"))
    root.addWidget(label(
        "Create one task per selected destination using the same pickup, payload, "
        "release time and route profile."
    ))


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("One-to-many tasks — Option A: grouped form")
    root = QVBoxLayout(dialog)
    header(root, "A")
    body = QWidget()
    column = QVBoxLayout(body)
    column.addWidget(group("Journey and destinations", [
        ("Base task ID", QLineEdit("BULK-021")),
        ("Pickup", choice("Central stores")),
        ("Dropoffs", destination_picker()),
        ("Payload", choice("Linen trolley")),
        ("Route profile", choice("Service route")),
    ]))
    column.addWidget(common_timing())
    column.addStretch(1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


def option_b(wide):
    dialog = QDialog()
    dialog.setWindowTitle("One-to-many tasks — Option B: destination panel")
    root = QVBoxLayout(dialog)
    header(root, "B")
    body = QWidget()
    if wide:
        layout = QHBoxLayout(body)
    else:
        layout = QVBoxLayout(body)
    destinations = QGroupBox("Destinations · 3 selected")
    dest_layout = QVBoxLayout(destinations)
    dest_layout.addWidget(label("One task will be created for each location."))
    listing = QListWidget()
    listing.addItems(DESTINATIONS)
    if not wide:
        listing.setMinimumHeight(160)
    dest_layout.addWidget(listing, 1)
    dest_layout.addWidget(QPushButton("Select dropoffs…"))
    if wide:
        layout.addWidget(destinations, 1)
    else:
        destinations.setMaximumHeight(300)
        layout.addWidget(destinations)
    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.addWidget(group("Shared task details", [
        ("Base task ID", QLineEdit("BULK-021")),
        ("Pickup", choice("Central stores")),
        ("Payload", choice("Linen trolley")),
        ("Route profile", choice("Service route")),
    ]))
    right_layout.addWidget(common_timing())
    right_layout.addStretch(1)
    layout.addWidget(right, 2 if wide else 1)
    root.addWidget(scroll(body), 1)
    footer(root)
    return dialog


for width, height in ((620, 500), (1024, 768), (1600, 900)):
    for key, dialog in (("A", option_a()), ("B", option_b(width >= 1024))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"one-to-many-{key}-{width}.png"))
        dialog.close()
