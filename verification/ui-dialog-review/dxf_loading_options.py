"""Nonfunctional DXF-loading progress layouts in the established review style."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QVBoxLayout,
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


def label(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def progress():
    bar = QProgressBar()
    bar.setRange(0, 4)
    bar.setValue(2)
    return bar


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Loading DXFs — Option A: compact progress")
    root = QVBoxLayout(dialog)
    root.addWidget(label("LOADING DXF DRAWINGS  ·  Design option A"))
    box = QGroupBox("Drawing files")
    body = QVBoxLayout(box)
    body.addWidget(label("Loading 2 remaining DXF file(s)..."))
    body.addWidget(progress())
    body.addWidget(label("2 / 4 processed  ·  1 failed"))
    root.addWidget(box)
    root.addWidget(label("This window closes when all files have been processed."))
    return dialog


def metric(name, value):
    box = QGroupBox(name)
    body = QVBoxLayout(box)
    body.addWidget(label(value))
    return box


def option_b(width):
    dialog = QDialog()
    dialog.setWindowTitle("Loading DXFs — Option B: batch overview")
    root = QVBoxLayout(dialog)
    root.addWidget(label("LOADING DXF DRAWINGS  ·  Design option B"))
    root.addWidget(label("Loading 2 remaining DXF file(s)..."))
    root.addWidget(progress())
    grid = QGridLayout()
    cols = 2 if width < 600 else 3
    for index, (name, value) in enumerate((
        ("Processed", "2 / 4"),
        ("Remaining", "2"),
        ("Failed", "1"),
    )):
        grid.addWidget(metric(name, value), index // cols, index % cols)
    root.addLayout(grid)
    root.addWidget(label("This window closes when all files have been processed."))
    return dialog


for width in (420, 720):
    for key, dialog in (("A", option_a()), ("B", option_b(width))):
        dialog.resize(width, 230 if key == "A" else (290 if width < 600 else 210))
        dialog.show()
        for _ in range(6):
            app.processEvents()
        print(key, width, (dialog.width(), dialog.height()))
        dialog.grab().save(str(OUT / f"dxf-loading-{key}-{width}.png"))
        dialog.close()
