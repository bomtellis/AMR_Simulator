"""Render nonfunctional Mass collection editor layouts for design review."""
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    widget = QLabel(text)
    widget.setWordWrap(wrap)
    return widget


def field(value):
    return QLineEdit(value)


def combo(*values, selected=0):
    widget = QComboBox()
    widget.addItems(values)
    widget.setCurrentIndex(selected)
    return widget


def spin(value, suffix, maximum, decimals=0):
    widget = QDoubleSpinBox() if decimals else QSpinBox()
    widget.setRange(0.1 if decimals and suffix == " min" else 0, maximum)
    if decimals:
        widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setSuffix(suffix)
    return widget


def group(title, rows):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, control in rows:
        form.addRow(title, control)
    return box


def payloads():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("General waste bin, Clinical waste bin", True))
    row = QHBoxLayout()
    row.addWidget(QPushButton("Select…"))
    row.addWidget(QPushButton("Clear"))
    row.addStretch(1)
    layout.addLayout(row)
    return widget


def days():
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for index, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        check = QCheckBox(name)
        check.setChecked(index < 5)
        layout.addWidget(check)
    layout.addStretch(1)
    return widget


def schedule():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("07:00, 15:00, 22:00"))
    row = QHBoxLayout()
    row.addWidget(QPushButton("Edit times…"))
    row.addWidget(QPushButton("Clear"))
    row.addStretch(1)
    layout.addLayout(row)
    return widget


def basics():
    enabled = QCheckBox("Enabled")
    enabled.setChecked(True)
    return group("Collection identity and scope", [
        ("ID", field("MASS-COLLECTION-1")),
        ("Enabled", enabled),
        ("Bin store location", combo("", "Waste Store A", "Waste Store B", "Ward Bay", selected=1)),
        ("Payload types", payloads()),
    ])


def timing():
    return group("Schedule", [
        ("Days active", days()),
        ("Scheduled collection times", schedule()),
    ])


def triggers():
    return group("Capacity triggers", [
        ("Capacity trigger", spin(80.0, " %", 100.0, 1)),
        ("Full-bin trigger", spin(12, " bin(s)", 1_000_000)),
        ("Capacity check interval", spin(15.0, " min", 100_000.0, 1)),
    ])


def handling():
    replace = QCheckBox("Replace collected used/full bins with empty equivalents")
    replace.setChecked(True)
    notes = QPlainTextEdit("Check the bin store after the morning round.")
    notes.setFixedHeight(80)
    return group("Exchange and notes", [
        ("Exchange", replace),
        ("Notes", notes),
    ])


HELP = (
    "At each visit the simulator removes all used/full matching payload instances from the store "
    "and creates the same number of empty replacement instances. Capacity triggers use the number "
    "of configured inventory spaces at the selected location, unless a trigger count is entered."
)


def scroll(content):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setMinimumSize(0, 0)
    area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
    area.setWidget(content)
    return area


def top(root, option):
    root.addWidget(label(f"MASS COLLECTION / BIN ROTATION  ·  Design option {option}"))
    root.addWidget(label(
        "Configure a repeatable collection or bin-rotation event, including timing, locations and payload handling.", True))


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("MASS-COLLECTION-1 · Waste Store A · weekdays"), 1)
    row.addWidget(QPushButton("Cancel"))
    save = QPushButton("Save")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def page(*items):
    content = QWidget()
    layout = QVBoxLayout(content)
    for item in items:
        layout.addWidget(item)
    layout.addStretch(1)
    return scroll(content)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Mass collection — Option A: focused tabs")
    root = QVBoxLayout(dialog)
    top(root, "A")
    tabs = QTabWidget()
    tabs.addTab(page(basics()), "Collection")
    tabs.addTab(page(timing(), triggers()), "Timing and triggers")
    tabs.addTab(page(handling(), group("How the collection works", [("", label(HELP, True))])), "Handling and notes")
    root.addWidget(tabs, 1)
    footer(root)
    tabs.setCurrentIndex(1)
    return dialog, tabs


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("Mass collection — Option B: grouped page")
    root = QVBoxLayout(dialog)
    top(root, "B")
    content = QWidget()
    outer = QVBoxLayout(content)
    if width >= 900:
        columns = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()
        left.addWidget(basics())
        left.addWidget(handling())
        left.addStretch(1)
        right.addWidget(timing())
        right.addWidget(triggers())
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns)
    else:
        for item in (basics(), timing(), triggers(), handling()):
            outer.addWidget(item)
    outer.addWidget(group("How the collection works", [("", label(HELP, True))]))
    outer.addStretch(1)
    root.addWidget(scroll(content), 1)
    footer(root)
    return dialog


app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
    QWidget { font-size: 10pt; color: #213044; }
    QDialog { background: #f7f9fc; }
    QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9; border-radius: 5px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
    QTabWidget::pane { border: 1px solid #b9c9d9; }
    QTabBar::tab { padding: 8px 12px; }
""")
for width, height in ((760, 620), (1024, 768), (1600, 900)):
    dialog, tabs = option_a()
    dialog.resize(width, height)
    dialog.show()
    for index, slug in enumerate(("collection", "timing", "handling")):
        tabs.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"mass-collection-A-{slug}-{width}.png"))
    dialog.close()
    dialog = option_b(width)
    dialog.resize(width, height)
    dialog.show()
    for _ in range(5):
        app.processEvents()
    dialog.grab().save(str(OUT / f"mass-collection-B-{width}.png"))
    dialog.close()
