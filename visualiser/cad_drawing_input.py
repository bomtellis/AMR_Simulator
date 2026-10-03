"""Compact CAD coordinate entry. World coordinates are metres; angles are degrees."""
import math

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


def parse_coordinate(text, anchor=None):
    """Return an absolute world point, or None for a blank finish command.

    Accept x,y; @dx,dy; @length<angle. Relative forms require an existing
    route endpoint. No grid, tolerance or engineering values are inferred.
    """
    text = text.strip()
    if not text:
        return None
    relative = text.startswith('@')
    expression = text[1:] if relative else text
    if relative and anchor is None:
        raise ValueError('Place a start point before using relative coordinates.')
    polar = '<' in expression
    if polar and not relative:
        raise ValueError('Polar entry uses @length<angle, measured from the route end.')
    parts = expression.split('<' if polar else ',')
    if len(parts) != 2 or any(not part.strip() for part in parts):
        raise ValueError('Enter X,Y, @dx,dy or @length<angle (metres and degrees).')
    try:
        first, second = (float(part) for part in parts)
    except ValueError:
        raise ValueError('Both coordinate values must be finite numbers.') from None
    if not all(math.isfinite(value) for value in (first, second)):
        raise ValueError('Both coordinate values must be finite numbers.')
    if polar:
        if first <= 0:
            raise ValueError('Polar length must be greater than zero metres.')
        angle = math.radians(second)
        first, second = first * math.cos(angle), first * math.sin(angle)
    if relative:
        first, second = first + anchor[0], second + anchor[1]
    if not all(math.isfinite(value) for value in (first, second)):
        raise ValueError('The resulting point must have finite coordinates.')
    return first, second


class CoordinateEdit(QLineEdit):
    escapePressed = Signal()

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escapePressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CadDrawingInput(QWidget):
    """Inline draft entry: this widget never commits or mutates project data."""
    submitted = Signal()
    cancelled = Signal()
    draftChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        label = QLabel('Next point (m)', self)
        self.coordinate_edit = CoordinateEdit(self)
        self.coordinate_edit.setPlaceholderText('X,Y  |  @dx,dy  |  @length<angle')
        self.coordinate_edit.setAccessibleName('Corridor coordinate entry in metres')
        self.coordinate_edit.setToolTip('Absolute X,Y; relative @dx,dy; polar @length<angle. '
            'Angles: 0° east, 90° north. Enter places a point; blank Enter finishes; Escape cancels the draft. '
            'Typed points bypass the grid. Object snapping remains active; review the actual endpoint before Enter.')
        self.coordinate_edit.setMinimumWidth(240)
        label.setBuddy(self.coordinate_edit)
        self.feedback_label = QLabel(self)
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setAccessibleName('Drawing coordinates, snapping and input errors')
        layout.addWidget(label)
        layout.addWidget(self.coordinate_edit, 1)
        layout.addWidget(self.feedback_label, 2)
        self.coordinate_edit.returnPressed.connect(self.submitted)
        self.coordinate_edit.escapePressed.connect(self.cancelled)
        self.coordinate_edit.textChanged.connect(self.draftChanged)

    def feedback(self, message, *, error=False):
        # Text carries the distinction, independent of theme or colour perception.
        self.feedback_label.setText(('Input error: ' if error else '') + message)
