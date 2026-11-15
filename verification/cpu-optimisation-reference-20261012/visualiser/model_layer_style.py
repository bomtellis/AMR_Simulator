"""Cosmetic line styling; routing overlays and selection retain their own pens."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QColor
from visualiser.model_layers import PATTERNS

PEN_PATTERNS = dict(zip(PATTERNS, (Qt.SolidLine, Qt.DashLine, Qt.DotLine, Qt.DashDotLine, Qt.DashDotDotLine)))


def styled_pen(original, options):
    pen = QPen(original)
    style = options.get('style')
    if style is not None:
        if style['colour'] is not None:
            pen.setColor(QColor(style['colour']))
        pen.setStyle(PEN_PATTERNS[style['pattern']])
        pen.setWidthF(style['width_px'])
        pen.setCosmetic(True)
    return pen
