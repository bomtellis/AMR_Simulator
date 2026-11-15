"""Paint a staged selection without replacing the scene or its drawing underlays."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen, QPolygonF


def paint_selection_preview(editor, painter, store, names, anchor, label):
    def position(x, y):
        return QPointF(editor.canvas.mapFromScene(editor.world_to_scene(x, y)))
    points = store.all_points()
    painter.save()
    painter.setPen(QPen(QColor(editor._map_colours['accent']), 2, Qt.DashLine))
    painter.setBrush(Qt.NoBrush)
    for edge in store.data['corridors']['edges']:
        a, b = edge['from'], edge['to']
        if not names.intersection((a,b)) or a not in points or b not in points:
            continue
        if any(int(points[name]['floor']) != editor.floor_spin.value() for name in (a,b)):
            continue
        painter.drawLine(position(points[a]['x'], points[a]['y']), position(points[b]['x'], points[b]['y']))
    for name in names:
        p = points[name]
        painter.drawEllipse(position(p['x'], p['y']), 5, 5)
        location = store.get_location(name)
        if location is not None:
            outlines = [store.get_location_bounding_box_points(name)]
            outlines.extend(store.inventory_space_points_absolute(name, space)
                            for space in location.get('inventory_spaces', []))
            for outline in outlines:
                if outline:
                    painter.drawPolygon(QPolygonF([position(p['x'], p['y']) for p in outline]))
    pivot = position(*anchor)
    painter.drawLine(pivot+QPointF(-8,0), pivot+QPointF(8,0))
    painter.drawLine(pivot+QPointF(0,-8), pivot+QPointF(0,8))
    painter.drawText(pivot+QPointF(10,-10), label)
    painter.restore()
