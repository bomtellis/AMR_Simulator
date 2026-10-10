"""Nonfunctional layout concepts for BulkDepartmentTaskGenerationDialog."""
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

OUT = Path(__file__).resolve().parent / "revisions"
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])


def note(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    return widget


def field(value=""):
    return QLineEdit(str(value))


def combo(value, values=None):
    widget = QComboBox()
    widget.addItems(values or [value])
    widget.setCurrentText(value)
    return widget


def check(text, checked=False):
    widget = QCheckBox(text)
    widget.setChecked(checked)
    return widget


def picker(summary, disabled=False):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    label = note(summary)
    label.setEnabled(not disabled)
    layout.addWidget(label, 1)
    for title in ("Select…", "Clear"):
        button = QPushButton(title)
        button.setEnabled(not disabled)
        layout.addWidget(button)
    return row


def form_group(title, rows, description=""):
    box = QGroupBox(title)
    root = QVBoxLayout(box)
    if description:
        root.addWidget(note(description))
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(10)
    for title, widget in rows:
        form.addRow(title, widget)
    root.addLayout(form)
    return box


def scope():
    box = QGroupBox("Apply to departments · Stores")
    root = QVBoxLayout(box)
    line = QHBoxLayout()
    line.addWidget(note("2 selected: North surgical ward (D-01), Day treatment centre (D-02)"), 1)
    line.addWidget(QPushButton("Select departments…"))
    root.addLayout(line)
    root.addWidget(note("Only departments with a placed Stores category location can be selected."))
    roles = QHBoxLayout()
    roles.addWidget(check("Department location is pickup/source"))
    roles.addWidget(check("Department location is drop-off", True))
    roles.addStretch(1)
    root.addLayout(roles)
    return box


def basics():
    return form_group("Task basics", [
        ("Enabled", check("Generate tasks for this category", True)),
        ("Generation mode", combo("hybrid", ["scheduled", "threshold", "continuous", "sporadic", "hybrid", "scheduled_threshold", "scheduled_sporadic", "timeframe"])),
        ("Priority", field(100)),
        ("Payload", combo("Linen trolley", ["Linen trolley", "Empty trolley"])),
    ], "One configuration is applied to every selected department. Values can be changed individually afterwards.")


def locations():
    return form_group("Locations and route", [
        ("Pickup/source locations", picker("From each selected department’s placed Stores location", True)),
        ("Drop-off destinations", picker("Central stores", False)),
        ("Route profile", combo("Service route", ["default", "Service route"])),
    ], "The department location role above controls which endpoint comes from each department.")


def returns():
    return form_group("Returns and stock", [
        ("Tracked item exchange", check("Generate tracked item exchange tasks")),
        ("Exchange mode", combo("Selected when exchange is enabled")),
        ("Return task", check("Generate return / exchange task", True)),
        ("Return payload", combo("Empty trolley")),
        ("Return delay (minutes)", field(0)),
        ("Shared-zone release spacing", check("Release the next task after the preceding return clears the shared space")),
        ("Reusable return pool", check("Reuse returned payloads as a capped source pool", True)),
        ("Pool multiplier", field("2.0")),
        ("Pool hard cap (0 = auto)", field(0)),
    ])


def timing():
    return form_group("Days and volume · hybrid mode", [
        ("Days active", picker("Mon, Tue, Wed, Thu, Fri")),
        ("Fortnightly recurrence", check("Run every fortnight")),
        ("Frequency per day", field("1.0")),
        ("Volume per event m³", field("0.1")),
        ("Threshold volume m³", field("0.5")),
        ("Base daily volume m³", field("0.2")),
    ], "Mode-dependent values appear only when the selected generation mode uses them.")


def staff():
    return form_group("Staff handling", [
        ("Staff handling", check("Assign category staff for delivered payload handling", True)),
        ("Collection response delay (minutes)", field("0.0")),
        ("Handling time (minutes)", field("15.0")),
        ("Handoff timing", check("Movement-only handoff (no destination dwell)")),
        ("Initial staff count", field(1)),
        ("Staff resource name", field("Stores staff")),
        ("Out-of-hours fallback", check("Use fallback resource")),
        ("Fallback resource name", field("Porter")),
        ("Staff movement", picker("Configured movement policy")),
        ("Shift pattern", combo("Default")),
        ("Working hours by day", picker("Department working hours")),
    ])


def help_box(waste=False):
    box = QGroupBox("Notes and guidance")
    layout = QVBoxLayout(box)
    layout.addWidget(note("Waste stream generation is configured in Departments → Manage waste streams. In this dialog, Waste applies routing, destination, priority and return settings only."))
    layout.addWidget(note("The selected department must have a valid placed category location. The chosen location role determines which route endpoint is copied from each department."))
    layout.addWidget(QLabel("Notes"))
    layout.addWidget(QTextEdit(), 1)
    return box


def scroll(*widgets):
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(12)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(inner)
    area.setFrameShape(QScrollArea.NoFrame)
    return area


def header(root, option):
    root.addWidget(QLabel(f"BULK DEPARTMENT TASK GENERATION  ·  Design option {option}"))


def footer(root):
    line = QHBoxLayout()
    line.addWidget(note("Stores · 2 eligible departments selected"), 1)
    line.addWidget(QPushButton("Cancel"))
    apply = QPushButton("Apply to departments")
    apply.setObjectName("primary")
    line.addWidget(apply)
    root.addLayout(line)


def option_a():
    dialog = QDialog()
    dialog.setWindowTitle("Bulk department task generation — Option A")
    root = QVBoxLayout(dialog)
    root.setSpacing(10)
    header(root, "A · focused tabs")
    root.addWidget(scope())
    tabs = QTabWidget()
    tabs.addTab(scroll(basics()), "Basics")
    tabs.addTab(scroll(locations()), "Locations && routing")
    tabs.addTab(scroll(returns()), "Returns && stock")
    tabs.addTab(scroll(timing(), staff()), "Schedule && staff")
    tabs.addTab(scroll(help_box()), "Notes && help")
    root.addWidget(tabs, 1)
    footer(root)
    return dialog, tabs


def section_title(text):
    label = QLabel(text)
    label.setObjectName("section")
    return label


def option_b():
    dialog = QDialog()
    dialog.setWindowTitle("Bulk department task generation — Option B")
    root = QVBoxLayout(dialog)
    root.setSpacing(10)
    header(root, "B · continuous form")
    root.addWidget(note("One guided page for the selected category. Sections and conditional fields scroll together."))
    area = scroll(
        scope(), section_title("1 · Task basics"), basics(),
        section_title("2 · Locations and route"), locations(),
        section_title("3 · Returns and stock"), returns(),
        section_title("4 · Schedule and staff"), timing(), staff(),
        section_title("5 · Notes and guidance"), help_box(),
    )
    root.addWidget(area, 1)
    footer(root)
    return dialog, area


STYLE = """
QWidget { font-size: 10pt; color: #213044; }
QDialog { background: #f7f9fc; }
QGroupBox { margin-top: 10px; padding: 10px 8px 8px; border: 1px solid #b9c9d9;
            border-radius: 5px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton, QLineEdit { min-height: 28px; }
QPushButton#primary { background: #005ea8; color: white; font-weight: 600;
                      padding: 4px 14px; }
QTabWidget::pane { border: 1px solid #b9c9d9; }
QTabBar::tab { padding: 8px 12px; }
QLabel#section { font-weight: 600; margin-top: 6px; }
"""

for width, height in ((1024, 768), (1600, 900)):
    dialog, tabs = option_a()
    dialog.setStyleSheet(STYLE)
    dialog.resize(width, height)
    dialog.show()
    for index, tag in ((0, "basics"), (1, "locations"), (2, "returns"), (3, "schedule")):
        tabs.setCurrentIndex(index)
        for _ in range(5):
            app.processEvents()
        dialog.grab().save(str(OUT / f"bulk-department-A-{tag}-{width}.png"))
    print("A", (width, height), (dialog.width(), dialog.height()))
    dialog.close()

    dialog, area = option_b()
    dialog.setStyleSheet(STYLE)
    dialog.resize(width, height)
    dialog.show()
    for _ in range(5):
        app.processEvents()
    area.verticalScrollBar().setValue(0)
    app.processEvents()
    dialog.grab().save(str(OUT / f"bulk-department-B-top-{width}.png"))
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum() // 3)
    app.processEvents()
    dialog.grab().save(str(OUT / f"bulk-department-B-middle-{width}.png"))
    print("B", (width, height), (dialog.width(), dialog.height()))
    dialog.close()
