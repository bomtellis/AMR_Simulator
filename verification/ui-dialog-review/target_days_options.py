"""Nonfunctional target-days calendar layouts in the established review style."""
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
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
QPushButton { min-height: 28px; }
QPushButton#primary { background: #005ea8; color: white; font-weight: 600;
                      padding: 4px 14px; }
QListWidget::item { padding: 7px 4px; }
""")

SELECTED = [(5, "Mon 5 Oct"), (7, "Wed 7 Oct"), (9, "Fri 9 Oct"),
            (12, "Mon 12 Oct"), (14, "Wed 14 Oct")]


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def calendar():
    widget = QCalendarWidget()
    widget.setNavigationBarVisible(False)
    widget.setGridVisible(True)
    widget.setFirstDayOfWeek(Qt.Monday)
    widget.setCurrentPage(2026, 10)
    widget.setSelectedDate(QDate(2026, 10, 5))
    selected_format = QTextCharFormat()
    selected_format.setBackground(QBrush(QColor("#cde7f6")))
    selected_format.setForeground(QBrush(QColor("#173b62")))
    selected_format.setFontWeight(700)
    for day, _ in SELECTED:
        widget.setDateTextFormat(QDate(2026, 10, day), selected_format)
    return widget


def toolbar(root, compact):
    nav = QHBoxLayout()
    nav.addWidget(QPushButton("◀"))
    nav.addWidget(QPushButton("Today"))
    nav.addWidget(QPushButton("▶"))
    month = QLabel("October 2026")
    month.setStyleSheet("font-weight: 600;")
    nav.addWidget(month)
    nav.addStretch(1)
    if not compact:
        nav.addWidget(QPushButton("Clear all"))
        nav.addWidget(QPushButton("Select displayed month"))
    root.addLayout(nav)
    if compact:
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(QPushButton("Clear all"))
        actions.addWidget(QPushButton("Select displayed month"))
        root.addLayout(actions)


def selection_list():
    box = QGroupBox("Selected dates · 5")
    root = QVBoxLayout(box)
    root.addWidget(label("Selected days remain in the set when you change month."))
    listing = QListWidget()
    listing.addItems(text for _, text in SELECTED)
    root.addWidget(listing, 1)
    return box


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("5 days selected"), 1)
    row.addWidget(QPushButton("Cancel"))
    apply = QPushButton("Apply selection")
    apply.setObjectName("primary")
    row.addWidget(apply)
    root.addLayout(row)


def header(root, option):
    root.addWidget(label(f"TARGET DAYS  ·  Design option {option}"))
    root.addWidget(label(
        "Select individual dates, a whole displayed month, or hold Shift while "
        "clicking to select a continuous date range."
    ))


def option_a(width):
    dialog = QDialog()
    dialog.setWindowTitle("Select target days — Option A: selection beside calendar")
    root = QVBoxLayout(dialog)
    header(root, "A")
    toolbar(root, width < 760)
    body = QHBoxLayout()
    body.addWidget(calendar(), 3)
    body.addWidget(selection_list(), 1)
    root.addLayout(body, 1)
    footer(root)
    return dialog


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("Select target days — Option B: full-width calendar")
    root = QVBoxLayout(dialog)
    header(root, "B")
    toolbar(root, width < 760)
    root.addWidget(calendar(), 1)
    box = QGroupBox("Selected dates · 5")
    line = QHBoxLayout(box)
    line.addWidget(label(", ".join(text for _, text in SELECTED)))
    root.addWidget(box)
    footer(root)
    return dialog


for width, height in ((620, 500), (820, 560), (1024, 768), (1600, 900)):
    for key, dialog in (("A", option_a(width)), ("B", option_b(width))):
        dialog.resize(width, height)
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, (width, height), (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"target-days-{key}-{width}.png"))
        dialog.close()
