"""Shared cursor-centred navigation for graph views."""
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsView


def zoom_at_cursor(view, event):
    """Keep the wheel event's scene point fixed, even without native hover."""
    delta = event.angleDelta().y()
    if not delta or view.scene() is None:
        return False
    position = event.position()
    inverse, _ = view.viewportTransform().inverted()
    target = inverse.map(position)
    anchor = view.transformationAnchor()
    view.setTransformationAnchor(QGraphicsView.NoAnchor)
    try:
        factor = 1.1 if delta > 0 else 0.9
        view.scale(factor, factor)
        inverse, _ = view.viewportTransform().inverted()
        offset = target - inverse.map(position)
        visible = view.mapToScene(view.viewport().rect()).boundingRect().translated(offset)
        # Qt otherwise clamps the scrollbars or centres a small drawing,
        # preventing the requested cursor anchor near the scene boundaries.
        if not view.sceneRect().contains(visible):
            margin = visible.adjusted(-visible.width(), -visible.height(),
                                      visible.width(), visible.height())
            view.scene().setSceneRect(view.sceneRect().united(margin))
        inverse, _ = view.viewportTransform().inverted()
        centre = QPointF(view.viewport().width() / 2, view.viewport().height() / 2)
        view.centerOn(inverse.map(centre) + target - inverse.map(position))
    finally:
        view.setTransformationAnchor(anchor)
    view.viewport().update()
    return True
