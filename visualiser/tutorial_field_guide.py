"""One transient value prompt beside the tutorial's active dialog field.

The prompt participates in the form layout, so it cannot cover an input or a
Save button. Removing it restores the original layout and leaves inputs alone.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QDialog, QFormLayout, QLabel, QScrollArea, QTabBar,QSizePolicy
from shiboken6 import isValid


class DialogFieldGuide:
    def __init__(self):
        self.label = None
        self.target = None
        self.layout = None

    def clear(self):
        if self.label is not None and isValid(self.label):
            if self.layout is not None and isValid(self.layout):
                if isinstance(self.layout, QFormLayout):
                    row = self.layout.takeRow(self.label)
                    if row.labelItem and row.labelItem.widget():
                        row.labelItem.widget().deleteLater()
                else:
                    self.layout.removeWidget(self.label)
            self.label.hide()
            self.label.deleteLater()
        self.label = self.target = self.layout = None

    def show(self, widget, text):
        window = widget.window()
        if not text or not isinstance(window, QDialog) or isinstance(widget, QTabBar):
            self.clear()
            return False
        if self.target is widget and self.label is not None and isValid(self.label):
            self.label.setText(text)
            return True
        self.clear()
        # Find the nearest field/container in a form or box layout. Table
        # viewports use their table; fields inside a composite row use that row.
        ancestor = widget
        chosen = None
        while ancestor is not None and ancestor is not window:
            for layout in window.findChildren(QFormLayout):
                row, role = layout.getWidgetPosition(ancestor)
                if row >= 0 and role != QFormLayout.LabelRole:
                    chosen = layout, row + 1
                    break
            if chosen:
                break
            for layout in window.findChildren(QBoxLayout):
                index = layout.indexOf(ancestor)
                if index >= 0:
                    chosen = layout, index + 1
                    break
            if chosen:
                break
            ancestor = ancestor.parentWidget()
        if chosen is None:
            return False
        layout, index = chosen
        label = QLabel(text, window)
        label.setObjectName('tutorialFieldValue')
        label.setAccessibleName('Required tutorial value')
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Maximum)
        if isinstance(layout,QBoxLayout) and layout.direction() in (QBoxLayout.LeftToRight,QBoxLayout.RightToLeft):
            label.setMinimumWidth(160)
        label.setFocusPolicy(Qt.NoFocus)
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        label.setStyleSheet('#tutorialFieldValue { color: #075985; background: #e0f2fe; '
                            'border-left: 3px solid #0077cc; padding: 5px 8px; }')
        if isinstance(layout, QFormLayout):
            layout.insertRow(index, '', label)
        else:
            layout.insertWidget(index, label)
        self.label, self.target, self.layout = label, widget, layout
        label.show()
        layout.activate()
        if window.layout():window.layout().activate()
        parent=label.parentWidget()
        while parent is not None:
            if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(label,0,12)
            parent=parent.parentWidget()
        return True
