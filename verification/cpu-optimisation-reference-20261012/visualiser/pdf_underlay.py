"""Floor-scoped, scale-aware PDF underlays for the topology editor."""

import math
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


PAPER_SIZES_MM = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
}


def normalise_pdf_underlay(entry):
    """Return a stable PDF-underlay mapping in metres and millimetres."""
    raw = entry if isinstance(entry, dict) else {}
    width = max(1.0, float(raw.get("paper_width_mm", 841.0)))
    height = max(1.0, float(raw.get("paper_height_mm", 1189.0)))
    return {
        "floor": int(raw.get("floor", 0) or 0),
        "filepath": str(raw.get("filepath", "") or ""),
        "page": max(1, int(raw.get("page", 1) or 1)),
        "paper_width_mm": width,
        "paper_height_mm": height,
        "scale_denominator": max(
            0.001, float(raw.get("scale_denominator", 100.0))
        ),
        "x_m": float(raw.get("x_m", 0.0) or 0.0),
        "y_m": float(raw.get("y_m", 0.0) or 0.0),
        "rotation_deg": float(raw.get("rotation_deg", 0.0) or 0.0),
        "opacity": min(1.0, max(0.05, float(raw.get("opacity", 0.55) or 0.55))),
    }


def underlay_world_size(entry):
    """Return the plotted PDF paper width/height in DXF world metres."""
    item = normalise_pdf_underlay(entry)
    multiplier = item["scale_denominator"] / 1000.0
    return (
        item["paper_width_mm"] * multiplier,
        item["paper_height_mm"] * multiplier,
    )


def underlay_world_bounds(entry):
    """Return an axis-aligned world bbox, accounting for rotation."""
    item = normalise_pdf_underlay(entry)
    width, height = underlay_world_size(item)
    angle = math.radians(item["rotation_deg"])
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    corners = []
    for dx, dy in ((0.0, 0.0), (width, 0.0), (width, height), (0.0, height)):
        corners.append(
            (
                item["x_m"] + (dx * cos_a) - (dy * sin_a),
                item["y_m"] + (dx * sin_a) + (dy * cos_a),
            )
        )
    return (
        min(point[0] for point in corners),
        min(point[1] for point in corners),
        max(point[0] for point in corners),
        max(point[1] for point in corners),
    )


def render_pdf_page(filepath, page_number=1, longest_edge_px=2200):
    """Render one PDF page to a pixmap using Qt's bundled PDF renderer."""
    path = str(Path(filepath))
    document = QPdfDocument()
    document.load(path)
    if document.pageCount() < 1:
        raise ValueError(f"{Path(path).name} has no renderable pages")
    page_index = max(0, min(int(page_number) - 1, document.pageCount() - 1))
    points = document.pagePointSize(page_index)
    if points.width() <= 0 or points.height() <= 0:
        raise ValueError(f"Could not determine page {page_index + 1} dimensions")
    longest = max(points.width(), points.height())
    factor = max(1.0, float(longest_edge_px) / longest)
    size = QSize(
        max(1, int(round(points.width() * factor))),
        max(1, int(round(points.height() * factor))),
    )
    rendered = document.render(page_index, size)
    if rendered.isNull():
        raise ValueError(f"Could not render page {page_index + 1}")
    image = QImage(size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.drawImage(0, 0, rendered)
    painter.end()
    return QPixmap.fromImage(image), document.pageCount()


class MovablePdfUnderlayItem(QGraphicsPixmapItem):
    """Pixmap anchored at its lower-left world point and optionally draggable."""

    def __init__(self, pixmap, entry, movable=False, moved_callback=None):
        super().__init__(pixmap)
        self.entry = normalise_pdf_underlay(entry)
        self.moved_callback = moved_callback
        width, height = underlay_world_size(self.entry)
        pixel_width = max(1.0, float(pixmap.width()))
        pixel_height = max(1.0, float(pixmap.height()))
        sx, sy = width / pixel_width, height / pixel_height
        angle = math.radians(self.entry["rotation_deg"])
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        # Map the PDF's lower-left paper corner to the supplied world point.
        # Scene Y is inverted relative to the metre-based DXF/world Y axis.
        self.setTransform(
            QTransform(
                cos_a * sx,
                -sin_a * sx,
                sin_a * sy,
                cos_a * sy,
                self.entry["x_m"] - (sin_a * height),
                -self.entry["y_m"] - (cos_a * height),
            )
        )
        self.setOpacity(self.entry["opacity"])
        self.setZValue(-100.0)
        self.setFlag(QGraphicsItem.ItemIsMovable, bool(movable))
        self.setFlag(QGraphicsItem.ItemIsSelectable, bool(movable))
        self.setCursor(Qt.OpenHandCursor if movable else Qt.ArrowCursor)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if (
            change == QGraphicsItem.ItemPositionHasChanged
            and self.moved_callback is not None
        ):
            position = self.pos()
            self.moved_callback(
                self.entry["x_m"] + float(position.x()),
                self.entry["y_m"] - float(position.y()),
            )
        return result


class PdfUnderlayDialog(QDialog):
    """Edit paper scale and the PDF lower-left alignment point."""

    def __init__(self, parent=None, entry=None, page_count=1):
        super().__init__(parent)
        value = normalise_pdf_underlay(entry)
        self.setWindowTitle("PDF underlay settings")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        note = QLabel(
            "The DXF/editor world uses metres. Paper dimensions and the plotted "
            "scale are converted to metres automatically. X and Y locate the "
            "lower-left paper corner."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        layout.addLayout(form)

        self.paper_size = QComboBox()
        self.paper_size.addItems(list(PAPER_SIZES_MM) + ["Custom"])
        self.orientation = QComboBox()
        self.orientation.addItems(["Portrait", "Landscape"])
        self.paper_width = self._number(1.0, 5000.0, value["paper_width_mm"], 1)
        self.paper_height = self._number(1.0, 5000.0, value["paper_height_mm"], 1)
        self.scale_denominator = self._number(
            0.001, 1000000.0, value["scale_denominator"], 3
        )
        self.page = QSpinBox()
        self.page.setRange(1, max(1, int(page_count)))
        self.page.setValue(min(value["page"], self.page.maximum()))
        self.x_m = self._number(-1000000.0, 1000000.0, value["x_m"], 3)
        self.y_m = self._number(-1000000.0, 1000000.0, value["y_m"], 3)
        self.rotation = self._number(-360.0, 360.0, value["rotation_deg"], 2)
        self.opacity = self._number(0.05, 1.0, value["opacity"], 2)
        self.opacity.setSingleStep(0.05)

        form.addRow("Page", self.page)
        form.addRow("Paper size", self.paper_size)
        form.addRow("Orientation", self.orientation)
        form.addRow("Paper width (mm)", self.paper_width)
        form.addRow("Paper height (mm)", self.paper_height)
        form.addRow("Drawing scale (1 :)", self.scale_denominator)
        form.addRow("Lower-left X (m)", self.x_m)
        form.addRow("Lower-left Y (m)", self.y_m)
        form.addRow("Rotation (degrees)", self.rotation)
        form.addRow("Opacity", self.opacity)

        self._select_matching_paper(value)
        self.paper_size.currentTextChanged.connect(self._paper_changed)
        self.orientation.currentTextChanged.connect(self._paper_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _number(minimum, maximum, value, decimals):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.setValue(value)
        return control

    def _select_matching_paper(self, value):
        width, height = value["paper_width_mm"], value["paper_height_mm"]
        for name, dimensions in PAPER_SIZES_MM.items():
            if all(
                abs(current - expected) < 0.2
                for current, expected in zip((width, height), dimensions)
            ):
                self.paper_size.setCurrentText(name)
                self.orientation.setCurrentText("Portrait")
                return
            if all(
                abs(current - expected) < 0.2
                for current, expected in zip((width, height), reversed(dimensions))
            ):
                self.paper_size.setCurrentText(name)
                self.orientation.setCurrentText("Landscape")
                return
        self.paper_size.setCurrentText("Custom")

    def _paper_changed(self, *_):
        dimensions = PAPER_SIZES_MM.get(self.paper_size.currentText())
        if not dimensions:
            return
        width, height = dimensions
        if self.orientation.currentText() == "Landscape":
            width, height = height, width
        self.paper_width.setValue(width)
        self.paper_height.setValue(height)

    def mapping(self, floor, filepath):
        return {
            "floor": int(floor),
            "filepath": str(filepath),
            "page": self.page.value(),
            "paper_width_mm": self.paper_width.value(),
            "paper_height_mm": self.paper_height.value(),
            "scale_denominator": self.scale_denominator.value(),
            "x_m": self.x_m.value(),
            "y_m": self.y_m.value(),
            "rotation_deg": self.rotation.value(),
            "opacity": self.opacity.value(),
        }
