"""Nonfunctional shared picker layouts, including a filtered state."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QScrollArea, QVBoxLayout, QWidget,
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

GROUPS = [
    ("Floor 1", [
        ("Central stores dispatch", False),
        ("Imaging reception and handover", True),
        ("Main lift lobby", False),
        ("North surgical ward staging bay", True),
        ("Outpatient day treatment bay", False),
        ("West corridor door", False),
    ]),
    ("Floor 2", [
        ("Day treatment waiting area", False),
        ("East corridor door", False),
        ("Rehabilitation supply bay", True),
        ("South surgical ward staging bay", True),
        ("Sterile supplies store", False),
        ("West lift lobby", False),
    ]),
]
SELECTED = ["Imaging reception and handover", "North surgical ward staging bay",
            "Rehabilitation supply bay", "South surgical ward staging bay"]


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def search(filtered):
    row = QHBoxLayout()
    edit = QLineEdit("ward" if filtered else "")
    edit.setPlaceholderText("Search available items…")
    row.addWidget(edit, 1)
    return row


def actions(root, compact, filtered):
    line = QHBoxLayout()
    line.addWidget(QPushButton("All"))
    line.addWidget(QPushButton("None"))
    if not compact:
        line.addWidget(QPushButton("Select visible"))
        line.addWidget(QPushButton("Clear visible"))
    line.addStretch(1)
    line.addWidget(label("4 selected · 2 visible" if filtered else "4 selected"))
    root.addLayout(line)
    if compact:
        visible = QHBoxLayout()
        visible.addWidget(QPushButton("Select visible"))
        visible.addWidget(QPushButton("Clear visible"))
        visible.addStretch(1)
        root.addLayout(visible)


def group(title, items):
    box = QGroupBox(f"{title} · {len(items)} matching" if len(items) == 1 else
                    f"{title} · {len(items)} items")
    root = QVBoxLayout(box)
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    buttons.addWidget(QPushButton("All"))
    buttons.addWidget(QPushButton("None"))
    root.addLayout(buttons)
    for name, checked in items:
        toggle = QCheckBox(name)
        toggle.setChecked(checked)
        root.addWidget(toggle)
    return box


def groups_area(filtered):
    body = QWidget()
    column = QVBoxLayout(body)
    for name, items in GROUPS:
        visible_items = [(text, checked) for text, checked in items
                         if not filtered or "ward" in text.lower()]
        if visible_items:
            column.addWidget(group(name, visible_items))
    column.addStretch(1)
    scroll = QScrollArea()
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setWidget(body)
    return scroll


def selected_panel():
    box = QGroupBox("Selected items · 4")
    root = QVBoxLayout(box)
    root.addWidget(label("The search filter does not clear hidden selections."))
    selected = QListWidget()
    selected.addItems(SELECTED)
    root.addWidget(selected, 1)
    return box


def footer(root):
    line = QHBoxLayout()
    line.addWidget(label("4 locations selected"), 1)
    line.addWidget(QPushButton("Cancel"))
    apply = QPushButton("Apply selection")
    apply.setObjectName("primary")
    line.addWidget(apply)
    root.addLayout(line)


def option_a(width, filtered):
    dialog = QDialog()
    dialog.setWindowTitle("Shared picker — Option A: grouped checklist")
    root = QVBoxLayout(dialog)
    root.addWidget(label("SELECT TASK LOCATIONS  ·  Design option A"))
    root.addWidget(label("Search available items, then select one or more entries. Use visible-selection controls after filtering large lists."))
    root.addLayout(search(filtered))
    actions(root, width < 580, filtered)
    root.addWidget(groups_area(filtered), 1)
    footer(root)
    return dialog


def option_b(width, filtered):
    dialog = QDialog()
    dialog.setWindowTitle("Shared picker — Option B: selected list")
    root = QVBoxLayout(dialog)
    root.addWidget(label("SELECT TASK LOCATIONS  ·  Design option B"))
    root.addWidget(label("Search available items, then select one or more entries. Use visible-selection controls after filtering large lists."))
    root.addLayout(search(filtered))
    actions(root, width < 580, filtered)
    if width >= 700:
        body = QHBoxLayout()
        body.addWidget(groups_area(filtered), 3)
        body.addWidget(selected_panel(), 2)
        root.addLayout(body, 1)
    else:
        root.addWidget(groups_area(filtered), 2)
        panel = selected_panel()
        panel.setMaximumHeight(150)
        root.addWidget(panel, 1)
    footer(root)
    return dialog


for width, height in ((520, 620), (820, 720)):
    for filtered in (False, True):
        state = "filtered" if filtered else "all"
        for key, dialog in (("A", option_a(width, filtered)),
                            ("B", option_b(width, filtered))):
            dialog.resize(width, height)
            dialog.show()
            for _ in range(6):
                app.processEvents()
            print(key, state, (width, height), (dialog.width(), dialog.height()))
            dialog.grab().save(str(OUT / f"multi-select-{key}-{state}-{width}.png"))
            dialog.close()
