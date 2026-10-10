"""Render nonfunctional People movement profile layouts for design review."""
from pathlib import Path
import sys

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTabWidget,
    QTimeEdit, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "visualiser")]
from dialogs import DayOfWeekSelector, PeopleProfilePreview

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)


def label(text, wrap=False):
    widget = QLabel(text)
    widget.setWordWrap(wrap)
    return widget


def combo(*items, selected=0):
    widget = QComboBox()
    widget.addItems(items)
    widget.setCurrentIndex(selected)
    return widget


def field(text, value):
    widget = QLineEdit(value)
    widget.setPlaceholderText(text)
    return widget


def amount(value, suffix, decimals=0):
    widget = QDoubleSpinBox() if decimals else QSpinBox()
    widget.setRange(0, 100000)
    if decimals:
        widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setSuffix(suffix)
    return widget


def time(value):
    from PySide6.QtCore import QTime
    widget = QTimeEdit()
    widget.setDisplayFormat("HH:mm")
    widget.setTime(QTime.fromString(value, "HH:mm"))
    return widget


def group(title, rows):
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, control in rows:
        form.addRow(title, control)
    return box


def scroll(content):
    wrapper = QScrollArea()
    wrapper.setWidgetResizable(True)
    wrapper.setFrameShape(QScrollArea.NoFrame)
    wrapper.setWidget(content)
    return wrapper


def top(root, option):
    root.addWidget(label(f"PEOPLE MOVEMENT PROFILE  ·  Design option {option}"))
    root.addWidget(label(
        "Define when and where people use the graph. The profile can remain constant, ramp up, ramp down, "
        "or follow a busy-period shape within a named timeframe. The preview shows the people represented "
        "by each movement interval.", True))


def footer(root):
    row = QHBoxLayout()
    row.addWidget(label("PUBLIC-VISITING · Public only · Visiting period"), 1)
    row.addWidget(QPushButton("Cancel"))
    save = QPushButton("Save profile")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def identity():
    enabled = QCheckBox("Use this profile in simulations")
    enabled.setChecked(True)
    return group("Profile identity", [
        ("Profile name", field("For example, PUBLIC-VISITING", "PUBLIC-VISITING")),
        ("People using the route", combo("Staff only", "Public only", "Mixed staff and public", selected=1)),
        ("Status", enabled),
    ])


def timeframe():
    days = DayOfWeekSelector(selected=("mon", "tue", "wed", "thu", "fri", "sat", "sun"))
    return group("Daily timeframe", [
        ("Preset", combo("Custom timeframe", "Full day", "Early shift", "Day shift", "Late shift", "Night shift", "Typical visiting period", "Midday meal-service period", selected=6)),
        ("Timeframe description", field("For example, morning arrival peak", "Visiting period")),
        ("Starts", time("14:00")),
        ("Ends", time("20:00")),
        ("Active days", days),
    ])


def profile_page(option):
    page = QWidget()
    outer = QVBoxLayout(page)
    if option == "B":
        content = QWidget()
        layout = QHBoxLayout(content)
        outer.addWidget(content)
    else:
        layout = outer
    layout.addWidget(identity())
    layout.addWidget(timeframe())
    if option == "A":
        layout.addStretch(1)
    else:
        layout.setStretch(0, 2)
        layout.setStretch(1, 3)
        outer.addStretch(1)
    return page


def corridor_actions():
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label("Selected: A → Door; Door → B", True))
    row = QHBoxLayout()
    row.addWidget(QPushButton("Select corridor assets…"))
    row.addWidget(QPushButton("Clear selection"))
    row.addStretch(1)
    layout.addLayout(row)
    return widget


def route_page(option):
    page = QWidget()
    layout = QVBoxLayout(page)
    start = combo("Select a start location…", "A", "B", "Ward Bay", "Zone X")
    end = combo("Select an end location…", "A", "B", "Ward Bay", "Zone X")
    start.setEnabled(False)
    end.setEnabled(False)
    layout.addWidget(group("How the profile is applied", [
        ("Application method", combo("Route people between two locations", "Apply the profile directly to selected corridors", selected=1)),
        ("Start location", start),
        ("End location", end),
        ("Corridor assets", corridor_actions()),
    ]))
    layout.addWidget(label(
        "Location routing calculates the path through the graph. Direct corridor assignment is better "
        "for observed occupancy, public routes, waiting areas, and scenario studies.", True))
    if option == "B":
        layout.addWidget(label("When direct corridor assignment is selected, the start and end location controls are disabled.", True))
    layout.addStretch(1)
    return page


def flow_controls():
    fit = QCheckBox("Fit the ramp automatically to the full daily timeframe")
    return group("People flow", [
        ("Profile shape", combo("Constant throughout the timeframe", "Ramp up to the peak", "Ramp down from the peak", "Ramp up, remain busy, then ramp down", selected=3)),
        ("Quiet-period people per interval", amount(2, " people")),
        ("Peak people per interval", amount(12, " people")),
        ("Movement interval", amount(15.0, " min", 1)),
        ("Timeframe alignment", fit),
        ("Manual ramp-up duration", amount(90.0, " min", 1)),
        ("Manual ramp-down duration", amount(90.0, " min", 1)),
    ])


def flow_preview():
    box = QGroupBox("Profile preview")
    layout = QVBoxLayout(box)
    preview = PeopleProfilePreview()
    preview.set_profile(shape="ramp_up_down", minimum=2, peak=12,
                        ramp_up=90.0, ramp_down=90.0, start="14:00", end="20:00")
    layout.addWidget(preview)
    layout.addWidget(label(
        "Ramp up, remain busy, then ramp down. Groups enter every 15 minutes, "
        "ranging from 2 to 12 people per interval. Manual ramp durations are used.", True))
    return box


def flow_page(option):
    page = QWidget()
    outer = QVBoxLayout(page)
    if option == "B":
        content = QWidget()
        layout = QHBoxLayout(content)
        outer.addWidget(content)
    else:
        layout = outer
    layout.addWidget(flow_controls())
    layout.addWidget(flow_preview())
    if option == "A":
        layout.addStretch(1)
    else:
        layout.setStretch(0, 3)
        layout.setStretch(1, 2)
        outer.addStretch(1)
    return page


def interaction_page(option):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(group("Movement and AMR safety effect", [
        ("Average walking speed", amount(1.2, " m/s", 2)),
        ("AMR speed while sharing the route", amount(70.0, " %", 0)),
    ]))
    layout.addWidget(label(
        "For example, 70% means an AMR normally travelling at 1.0 m/s is limited to "
        "0.7 m/s while this profile is present. Higher people counts may reduce it further.", True))
    layout.addStretch(1)
    return page


PAGES = (("Profile and timeframe", profile_page),
         ("Route or corridor assets", route_page),
         ("Flow profile", flow_page),
         ("AMR interaction", interaction_page))


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("People movement profile — Option A: guided steps")
    root = QVBoxLayout(dialog)
    top(root, "A")
    middle = QHBoxLayout()
    steps = QListWidget()
    steps.addItems(["1  Profile and timeframe", "2  Route or corridor assets", "3  Flow profile", "4  AMR interaction"])
    steps.setFixedWidth(235)
    middle.addWidget(steps)
    stack = QStackedWidget()
    for _, factory in PAGES:
        stack.addWidget(scroll(factory("A")))
    steps.currentRowChanged.connect(stack.setCurrentIndex)
    steps.setCurrentRow(2)
    middle.addWidget(stack, 1)
    root.addLayout(middle, 1)
    footer(root)
    return dialog, steps


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("People movement profile — Option B: refined tabs")
    root = QVBoxLayout(dialog)
    top(root, "B")
    tabs = QTabWidget()
    for name, factory in PAGES:
        tabs.addTab(scroll(factory("B")), name)
    tabs.setCurrentIndex(2)
    root.addWidget(tabs, 1)
    footer(root)
    return dialog, tabs


app = QApplication.instance() or QApplication([])
app.setStyleSheet("""
    QWidget { font-size: 10pt; color: #213044; }
    QDialog { background: #f7f9fc; }
    QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9; border-radius: 5px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTimeEdit { min-height: 28px; }
    QPushButton#primary { background: #005ea8; color: white; font-weight: 600; padding: 4px 14px; }
    QTabWidget::pane { border: 1px solid #b9c9d9; }
    QTabBar::tab { padding: 8px 12px; }
    QListWidget::item { padding: 10px 6px; }
""")
for option, factory in (("A", option_a), ("B", option_b)):
    dialog, navigation = factory()
    for width, height in ((1024, 768), (1600, 900)):
        dialog.resize(width, height)
        dialog.show()
        for index, slug in enumerate(("profile", "route", "flow", "interaction")):
            navigation.setCurrentRow(index) if option == "A" else navigation.setCurrentIndex(index)
            for _ in range(5):
                app.processEvents()
            dialog.grab().save(str(OUT / f"people-movement-{option}-{slug}-{width}.png"))
    dialog.close()
