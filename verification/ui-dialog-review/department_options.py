"""Render two nonfunctional Department dialog options for design review."""
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


def group(title, rows):
    value = QGroupBox(title)
    form = QFormLayout(value)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for title, control in rows:
        form.addRow(title, control)
    return value


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def footer(root):
    root.addWidget(label("Save here, then Save in the Departments list to commit new locations and zones.", True))
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(button("Cancel"))
    save = button("Save department")
    save.setObjectName("primary")
    row.addWidget(save)
    root.addLayout(row)


def details_page():
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(group("Identity", [
        ("Department ID", entry("D")),
        ("Department name", entry("Department")),
        ("Floor", label("0 · read only")),
        ("Status", QCheckBox("Enabled")),
    ]))
    layout.addWidget(group("Activity", [
        ("Bed count", entry("0")),
        ("Patient turnover", entry("0.0")),
        ("Staff count", entry("0")),
    ]))
    layout.addWidget(group("Map position", [("X (m)", entry("0")), ("Y (m)", entry("0"))]))
    layout.addStretch(1)
    return page


def hours_page():
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(group("Working pattern", [
        ("Operating start", entry("00:00")),
        ("Operating end", entry("24:00")),
        ("Calculated hours", label("24.00 h")),
        ("Days active", label("☑ Mon   ☑ Tue   ☑ Wed   ☑ Thu   ☑ Fri   ☐ Sat   ☐ Sun")),
    ]))
    layout.addWidget(group("Waste streams", [
        ("Assigned streams", button("Select waste streams…")),
        ("Guidance", label("Waste generation mode, frequency, volume, threshold and scheduled times are configured in Departments → Manage waste streams.", True)),
    ]))
    layout.addStretch(1)
    return page


def category_detail():
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(group("Stores · service location", [
        ("Pickup / drop-off", label("None selected")),
        ("Choose locations", button("Select…")),
        ("New-location suffix", entry("-STORES")),
        ("Place on map", button("Place…")),
    ]))
    layout.addWidget(group("Stores · drop-off zone", [
        ("Current delivery", label("Direct delivery (no zone)")),
        ("Choose zone", button("Select…")),
    ]))
    layout.addWidget(group("Shared staged-delivery zone", [
        ("Assign across categories", button("Select or create…")),
        ("Guidance", label("A newly placed location or zone is provisional until both department saves are complete.", True)),
    ]))
    layout.addStretch(1)
    return page


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Department — Option A: focused tabs")
    root = QVBoxLayout(dialog)
    root.addWidget(label("DEPARTMENT  ·  Design option A"))
    root.addWidget(label("Edit identity, working pattern and category locations in separate tabs. The two-step save reminder stays visible.", True))
    tabs = QTabWidget()
    tabs.addTab(scroll(details_page()), "Details")
    tabs.addTab(scroll(hours_page()), "Hours & waste")
    locations = QWidget()
    locations_layout = QHBoxLayout(locations)
    categories = QListWidget()
    categories.addItems(["Stores", "Catering", "Waste"])
    categories.setCurrentRow(0)
    categories.setMaximumWidth(185)
    locations_layout.addWidget(categories)
    locations_layout.addWidget(scroll(category_detail()), 1)
    tabs.addTab(locations, "Task locations & zones")
    root.addWidget(tabs, 1)
    footer(root)
    return dialog


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Department — Option B: grouped continuous form")
    root = QVBoxLayout(dialog)
    root.addWidget(label("DEPARTMENT  ·  Design option B"))
    root.addWidget(label("Keep everything in one scrollable form, grouped by purpose. Category location rows open into cards when needed.", True))
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.addWidget(group("1 · Identity and activity", [
        ("Department ID", entry("D")),
        ("Department name", entry("Department")),
        ("Floor / status", label("Floor 0   ·   Enabled")),
        ("Beds / turnover / staff", label("0 beds   ·   0.0 turnover   ·   0 staff")),
        ("Activity fields", button("Expand bed, turnover and staff fields…")),
    ]))
    layout.addWidget(group("2 · Hours and waste", [
        ("Operating hours", label("00:00–24:00   ·   24.00 h")),
        ("Days active", label("Mon  Tue  Wed  Thu  Fri")),
        ("Working pattern", button("Expand hours and active days…")),
        ("Waste streams", button("Select waste streams…")),
    ]))
    layout.addWidget(group("3 · Task locations and zones", [
        ("Stores", button("Expand service location and zone…")),
        ("Catering", button("Expand service location and zone…")),
        ("Waste", button("Expand service location and zone…")),
        ("Shared drop-off zone", button("Select or create…")),
    ]))
    layout.addWidget(group("4 · Map position", [("X (m)", entry("0")), ("Y (m)", entry("0"))]))
    layout.addWidget(group("Guidance", [
        ("Waste", label("Configure waste stream volume and schedule in Departments → Manage waste streams.", True)),
        ("Placement", label("New locations and zones remain provisional until both department saves complete.", True)),
    ]))
    layout.addStretch(1)
    root.addWidget(scroll(body), 1)
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
        if name == "A":
            dialog.findChild(QTabWidget).setCurrentIndex(0)
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"department-{name}-{width}.png"))
        if name == "A" and width == 1024:
            dialog.findChild(QTabWidget).setCurrentIndex(2)
            for _ in range(3):
                app.processEvents()
            dialog.grab().save(str(OUT / "department-A-locations-1024.png"))
    dialog.close()
