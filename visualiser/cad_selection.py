"""CAD selection queries in viewport pixels over visible topology geometry."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor, QBrush
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsPolygonItem


HIT_TOLERANCE_PX = 6.0
DRAG_THRESHOLD_PX = 4.0


def rectangle_hits(paths, start, end):
    """Left-to-right encloses full geometry; right-to-left touches geometry.

    Inputs are viewport paths, so zoom and the world's inverted Y axis cannot
    change the interaction convention. Labels are deliberately not geometry.
    """
    rect = QRectF(start, end).normalized().adjusted(-1e-7, -1e-7, 1e-7, 1e-7)
    window = QPainterPath()
    window.addRect(rect)
    crossing = end.x() < start.x()
    return {key for key, path in paths.items()
            if (window.intersects(path) if crossing else path.subtracted(window).isEmpty())
            and not path.isEmpty()}


def point_hit(paths, point, tolerance_px=HIT_TOLERANCE_PX):
    """Prefer topology points over edges within a constant pixel halo."""
    halo = QPainterPath()
    halo.addEllipse(point, tolerance_px, tolerance_px)
    candidates = [(key, path) for key, path in paths.items()
                  if path.contains(point) or path.intersects(halo)]
    if not candidates:
        return None
    def order(row):
        key, path = row
        centre = path.boundingRect().center()
        return (0 if key[0] == 'point' else 1, 0 if path.contains(point) else 1,
                (centre.x()-point.x())**2+(centre.y()-point.y())**2, repr(key))
    return min(candidates, key=order)[0]


def _rendered_path(item, view):
    path = QPainterPath()
    if isinstance(item, QGraphicsLineItem):
        path.moveTo(item.line().p1())
        path.lineTo(item.line().p2())
    elif isinstance(item, QGraphicsEllipseItem):
        path.addEllipse(item.rect())
    elif isinstance(item, QGraphicsRectItem):
        path.addRect(item.rect())
    elif isinstance(item, QGraphicsPolygonItem):
        path.addPolygon(item.polygon())
        path.closeSubpath()
    else:
        return path
    transform = item.deviceTransform(view.viewportTransform())
    pen = item.pen()
    visible_pen = pen.style() != Qt.NoPen and pen.color().alpha() > 0
    if visible_pen and not pen.isCosmetic() and pen.widthF() > 0:
        stroke = QPainterPathStroker()
        stroke.setWidth(pen.widthF())
        path = path.united(stroke.createStroke(path))
    path = transform.map(path)
    if visible_pen and (pen.isCosmetic() or pen.widthF() == 0):
        stroke = QPainterPathStroker()
        stroke.setWidth(max(1., pen.widthF()))
        path = path.united(stroke.createStroke(path))
    return path


def editor_paths(editor):
    """Collect only rendered graph objects on the current floor.

    Group each location's visible boundary with its marker. A window must enclose
    the whole rendered object; crossing any part selects it. DXF/PDF underlays,
    labels and temporary handles never enter the candidates.
    """
    result = {}
    points = editor.store.points_for_floor(editor.floor_spin.value())
    for item, (kind, identity) in tuple(editor._item_lookup.items()):
        if not item.isVisible():
            continue
        if kind in ('point', 'location_bounding_box') and identity in points:
            key = ('point', identity)
        elif kind == 'edge' and identity.get('from') in points and identity.get('to') in points:
            key = ('edge', editor._physical_edge_key(identity['from'], identity['to']))
        else:
            continue
        shape = _rendered_path(item, editor.canvas)
        if not shape.isEmpty():
            result[key] = result[key].united(shape) if key in result else shape
    return result


def paint_rectangle(painter, start, end):
    crossing = end.x() < start.x()
    rect = QRectF(start, end).normalized()
    colour = QColor('#34d399' if crossing else '#60a5fa')
    pen = QPen(colour, 1)
    pen.setStyle(Qt.DashLine if crossing else Qt.SolidLine)
    painter.setPen(pen)
    painter.setBrush(QBrush(QColor(colour.red(), colour.green(), colour.blue(), 30)))
    painter.drawRect(rect)
    label = 'Crossing: touches' if crossing else 'Window: fully enclosed'
    label_rect = QRectF(rect.left(), max(0., rect.top()-25), 190, 23)
    painter.fillRect(label_rect, QColor('#18212d'))
    painter.setPen(QColor('#ffffff'))
    painter.drawText(label_rect.adjusted(5, 0, -2, 0), Qt.AlignVCenter, label)
