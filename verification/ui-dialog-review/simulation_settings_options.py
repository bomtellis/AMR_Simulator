"""Render two nonfunctional Simulation settings layouts for design review."""
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    value = QLabel(text)
    value.setWordWrap(wrap)
    return value


def button(text):
    return QPushButton(text)


def entry(text):
    return QLineEdit(text)


def combo(*items):
    value = QComboBox()
    value.addItems(items)
    return value


def box(title, rows):
    value = QGroupBox(title)
    form = QFormLayout(value)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, control in rows:
        form.addRow(title, control)
    return value


def period_content():
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.addWidget(box("Mode", [
        ("Simulation mode", combo("Simple — graph-based simulation", "Detailed — geometric traffic")),
        ("Readiness", label("Ready · Run Project Checks before simulation.")),
        ("Mode details", button("Show mode changes and findings…")),
    ]))
    layout.addWidget(box("Demand window", [
        ("Starts", entry("05 Jan 2026 00:00:00")),
        ("End condition", QCheckBox("End generated demand at a fixed date and time")),
        ("Ends", entry("05 Jan 2026 00:10:00")),
    ]))
    layout.addWidget(box("Release and deferral", [
        ("Same-time task release spacing", entry("0.250 s")),
        ("Maximum task deferral", entry("Unlimited")),
        ("Legacy rate (metadata)", entry("120.000×")),
    ]))
    layout.addWidget(label("Released tasks and returns may finish after demand ends. Duration settings retain their current precedence.", True))
    layout.addStretch(1)
    return content


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("Changes to settings are saved with the project."), 1)
    row.addWidget(button("Cancel"))
    save = button("Save")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Simulation settings — Option A: section navigator")
    root = QVBoxLayout(dialog)
    root.addWidget(label("SIMULATION SETTINGS  ·  Design option A"))
    root.addWidget(label("Choose a section on the left. The active section uses the full remaining width; explanations stay with their settings.", True))
    summary = QHBoxLayout()
    summary.addWidget(label("Mode: Simple   ·   Demand: 05 Jan 00:00–00:10   ·   Project checks: run before simulation", True), 1)
    root.addLayout(summary)
    body = QHBoxLayout()
    root.addLayout(body, 1)
    sections = QListWidget()
    sections.addItems(["Run period", "Performance", "Charging", "Initial conditions"])
    sections.setCurrentRow(0)
    sections.setMinimumWidth(180)
    sections.setMaximumWidth(220)
    body.addWidget(sections)
    body.addWidget(scroll(period_content()), 1)
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Simulation settings — Option B: compact tabs")
    root = QVBoxLayout(dialog)
    root.addWidget(label("SIMULATION SETTINGS  ·  Design option B"))
    root.addWidget(label("Keep the current tabs, group related rows inside each tab, and collapse the large mode-readiness panel into a details control.", True))
    tabs = QTabWidget()
    tabs.addTab(scroll(period_content()), "Run period")
    for title, content in (
        ("Performance", ["Route preparation", "Scheduling workload limits"]),
        ("Charging", ["Opportunity charging"]),
        ("Initial conditions", ["Inventory and container state"]),
    ):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        for heading in content:
            page_layout.addWidget(box(heading, [("Current settings", label("All existing controls and guidance remain here."))]))
        page_layout.addStretch(1)
        tabs.addTab(scroll(page), title)
    root.addWidget(tabs, 1)
    footer(root)
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
        dialog.grab().save(str(OUT / f"simulation-settings-{name}-{width}.png"))
    dialog.close()
