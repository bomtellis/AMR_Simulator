"""Scrollable focused forms retaining the existing field widgets and callbacks."""
from PySide6.QtWidgets import QFormLayout, QFrame, QScrollArea, QTabWidget, QVBoxLayout, QWidget


def scroll_page(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidget(widget)
    return scroll


class FocusedForms(QTabWidget):
    """Small QFormLayout-compatible facade for grouping existing form rows.

    labelForField remains available to conditional row-visibility callbacks.
    Each tab scrolls independently, leaving the dialog's action footer fixed.
    """
    def __init__(self, titles, sections, parent=None):
        super().__init__(parent)
        self.setAccessibleName('Settings sections')
        self.sections = sections
        self.forms = {}
        for title in titles:
            page = QWidget()
            layout = QVBoxLayout(page)
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            layout.addLayout(form)
            layout.addStretch(1)
            self.forms[title] = form
            self.addTab(scroll_page(page), title.replace('&', '&&'))

    def addRow(self, label, field):
        title = self.sections[label]
        self.forms[title].addRow(label, field)

    def labelForField(self, field):
        for form in self.forms.values():
            label = form.labelForField(field)
            if label is not None:
                return label
        return None

    def setFieldGrowthPolicy(self, policy):
        for form in self.forms.values():
            form.setFieldGrowthPolicy(policy)

    def add_help(self, widget):
        self.forms['Notes & help'].addRow(widget)
