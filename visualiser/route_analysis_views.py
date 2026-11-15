"""Read-only charts and recorded route geometry, using the application's palette."""
import math

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGraphicsScene, QGraphicsView, QGraphicsItem, QTableWidget,
    QTableWidgetItem, QHeaderView)

from amr_route_analysis import MOVE_TYPES
from visualiser.graph_navigation import zoom_at_cursor
from visualiser.dxf_scene import DXFScene


def fmt(value):
    if value is None:
        return 'Unknown'
    if isinstance(value, float):
        return f'{value:,.3f}'.rstrip('0').rstrip('.')
    return str(value)


class AnalysisView(QGraphicsView):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setAccessibleName(name)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setMinimumHeight(180)

    def wheelEvent(self, event):
        if .005 < self.transform().m11() < 500 or event.angleDelta().y() * (1 if self.transform().m11() < .005 else -1) > 0:
            zoom_at_cursor(self, event)
        event.accept()

    def fit(self):
        bounds = self.scene().itemsBoundingRect()
        if not bounds.isEmpty():
            self.scene().setSceneRect(bounds.adjusted(-8, -8, 8, 8))
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
            maximum = getattr(self, 'max_scale', None)
            if maximum and self.transform().m11() > maximum:
                self.resetTransform()
                self.scale(maximum, maximum)


def toolbar(view):
    bar = QHBoxLayout()
    for name, callback in [('Fit', view.fit), ('Zoom in', lambda: view.scale(1.25, 1.25)),
                           ('Zoom out', lambda: view.scale(.8, .8))]:
        button = QPushButton(name)
        button.clicked.connect(callback)
        bar.addWidget(button)
    bar.addStretch()
    return bar


def text(scene, value, x, y, palette, *, fixed=False):
    item = scene.addSimpleText(str(value))
    item.setBrush(palette.text())
    item.setPos(x, y)
    if fixed:
        item.setFlag(QGraphicsItem.ItemIgnoresTransformations)
    return item


def pen(color, width=1):
    result = QPen(color)
    result.setWidthF(width)
    result.setCosmetic(True)
    return result


class RouteMap(QWidget):
    """A saved run's graph and drawing; overlay only the selected recorded leg."""
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.run = self.leg = None
        layout = QVBoxLayout(self)
        self.heading = QLabel(f'Run {label} — select a journey in AMR routes')
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Floor'))
        self.floor = QComboBox()
        self.floor.setAccessibleName(f'Run {label} route floor')
        self.floor.currentIndexChanged.connect(self.redraw)
        controls.addWidget(self.floor)
        controls.addStretch()
        layout.addLayout(controls)
        self.view = AnalysisView(f'Run {label} recorded route floor plan')
        tools = toolbar(self.view)
        fit_route = QPushButton('Fit route')
        fit_route.clicked.connect(self.fit_route)
        tools.insertWidget(0, fit_route)
        layout.addLayout(tools)
        layout.addWidget(self.view, 1)
        self.sequence = AnalysisView(f'Run {label} floor and lift sequence')
        self.sequence.max_scale = 1.15
        self.sequence.setMinimumHeight(100)
        self.sequence.setMaximumHeight(165)
        layout.addWidget(self.sequence)
        self.notes = QLabel('Recorded geometry only. Select each run’s journey independently.')
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        self.label = label

    def set_leg(self, run, leg):
        self.run, self.leg = run, leg
        prior = self.floor.currentData()
        floors = sorted(leg.floors) if leg else []
        self.floor.blockSignals(True)
        self.floor.clear()
        for floor in floors:
            self.floor.addItem(f'Floor {fmt(floor)}', floor)
        index = self.floor.findData(prior)
        if index >= 0:
            self.floor.setCurrentIndex(index)
        self.floor.blockSignals(False)
        if leg:
            self.heading.setText(f'Run {self.label} · {leg.origin} → {leg.destination}\n'
                                 f'{leg.amr} · {leg.purpose} · {fmt(leg.time)}–{fmt(leg.end)} s')
        else:
            self.heading.setText(f'Run {self.label} — select a journey in AMR routes')
        self.redraw()

    def redraw(self):
        scene = self.view.scene()
        scene.clear()
        self.sequence.scene().clear()
        if not self.run or not self.leg:
            return
        floor = self.floor.currentData()
        palette = self.palette()
        accent = palette.highlight().color()
        saved = self.run.drawings.get(floor)
        if saved:
            DXFScene.from_content(saved.get('path'), saved.get('entities'), saved.get('bounds')).populate_graphics_scene(scene)
        pdf = self.run.pdf_drawings.get(floor)
        if pdf:
            from visualiser.pdf_underlay import MovablePdfUnderlayItem
            scene.addItem(MovablePdfUnderlayItem(QPixmap.fromImage(pdf[0]), pdf[1], movable=False))
        points = self.run.points
        for edge in self.run.config.get('corridors', {}).get('edges', []):
            a, b = points.get(edge.get('from')), points.get(edge.get('to'))
            if a and b and a.get('floor') == floor == b.get('floor'):
                scene.addLine(a['x'], -a['y'], b['x'], -b['y'], pen(palette.mid().color()))
        gaps = 0
        for index, s in enumerate(self.leg.segments):
            if s.kind.startswith('wait') and s.start[2] == floor and None not in s.start[:2]:
                item = text(scene, f'◷ {fmt(s.duration)} s', s.start[0], -s.start[1], palette, fixed=True)
                item.setToolTip(f'{s.kind}: {s.id}')
                continue
            if s.kind not in MOVE_TYPES:
                continue
            if s.kind == 'lift_transfer':
                for connector in ('entry_edge', 'exit_edge'):
                    edge = s.detail.get(connector) or {}
                    a, b = points.get(edge.get('from')), points.get(edge.get('to'))
                    if a and b and a.get('floor') == floor == b.get('floor'):
                        item = scene.addLine(a['x'], -a['y'], b['x'], -b['y'], pen(accent, 3))
                        item.setZValue(10)
                        item.setToolTip(f'{connector}: {edge["from"]} → {edge["to"]}\n{s.id}')
                for location, suffix in ((s.start, 'board'), (s.finish, 'exit')):
                    if location[2] == floor and None not in location[:2]:
                        text(scene, f'{s.lift} · {suffix}', location[0], -location[1], palette, fixed=True)
                continue
            if s.start[2] != floor:
                continue
            coords = self._recorded_points(s)
            if len(coords) < 2:
                gaps += 1
                continue
            path = QPainterPath(QPointF(*coords[0]))
            for point in coords[1:]:
                path.lineTo(*point)
            item = scene.addPath(path, pen(accent, 3))
            item.setZValue(10)
            item.setToolTip(f'{s.origin} → {s.destination}\n{s.id}\n{fmt(s.distance)} m · {fmt(s.duration)} s')
            a, b = coords[-2:]
            angle = math.atan2(b[1]-a[1], b[0]-a[0])
            length = min(1., max(.1, math.dist(a, b) / 4))
            arrow = QPolygonF([QPointF(*b), QPointF(b[0]-length*math.cos(angle-.45), b[1]-length*math.sin(angle-.45)),
                              QPointF(b[0]-length*math.cos(angle+.45), b[1]-length*math.sin(angle+.45))])
            scene.addPolygon(arrow, pen(accent), QBrush(accent)).setZValue(11)
        moves = [s for s in self.leg.segments if s.kind in MOVE_TYPES]
        for point, label in ((moves[0].start, 'Start'), (moves[-1].finish, 'Finish')):
            if point[2] == floor and None not in point[:2]:
                text(scene, label, point[0], -point[1], palette, fixed=True).setZValue(12)
        self.fit_route()
        self._sequence(moves)
        self.notes.setText(f'{self.leg.evidence} · {self.leg.compliance}\n{self.leg.reason}\n'
                           f'{fmt(self.leg.distance)} m · lift waiting {fmt(self.leg.wait)} s. '
                           + (f'{gaps} geometry gap(s); no replacement path calculated.' if gaps else 'Arrows follow recorded segments.')
                           + (' Saved topology shown; no bound floor drawing available.' if not saved and not pdf else ''))

    def fit_route(self):
        if not self.leg:
            return
        floor = self.floor.currentData()
        points = [p for s in self.leg.segments if s.kind in MOVE_TYPES
                  for p in (s.start, s.finish) if p[2] == floor and None not in p[:2]]
        if points:
            x, y = [p[0] for p in points], [-p[1] for p in points]
            bounds = QRectF(min(x)-8, min(y)-8, max(16,max(x)-min(x)+16), max(16,max(y)-min(y)+16))
            self.view.fitInView(bounds, Qt.KeepAspectRatio)
        else:
            self.view.fit()

    @staticmethod
    def _recorded_points(segment):
        if segment.trajectory:
            try:
                from amr_trajectories import trajectory_from_dict
                trajectory = trajectory_from_dict(segment.trajectory)
                points = []
                for motion in trajectory.motions:
                    steps = 24 if motion.kind == 'arc' else 1
                    for n in range(steps + 1):
                        pose = motion.pose_at(n / steps)
                        points.append((pose.x, -pose.y))
                return points
            except (ValueError, TypeError, KeyError, AttributeError):
                return []
        if None in (*segment.start[:2], *segment.finish[:2]):
            return []
        return [(segment.start[0], -segment.start[1]), (segment.finish[0], -segment.finish[1])]

    def _sequence(self, movements):
        scene = self.sequence.scene()
        palette = self.palette()
        stops = [(movements[0].start[2], self.leg.origin)]
        for s in movements:
            if s.kind == 'lift_transfer':
                stops.append((s.finish[2], f'{s.lift} exit'))
        if stops[-1] != (movements[-1].finish[2], self.leg.destination):
            stops.append((movements[-1].finish[2], self.leg.destination))
        required = self.run.config.get('building', {}).get('force_via_floor')
        enabled = self.run.config.get('building', {}).get('force_via_floor_enabled') is True
        for i, (floor, name) in enumerate(stops):
            x = i * 150
            if i:
                scene.addLine(x-35, 24, x-5, 24, pen(palette.highlight().color(), 2))
                text(scene, '→', x-24, 12, palette)
            marker = ' · required' if enabled and floor == required else ''
            text(scene, f'F{fmt(floor)}{marker}', x, 0, palette)
            text(scene, name, x, 25, palette)
        self.sequence.fit()


class LiftHeatmap(QTableWidget):
    selectedPair = Signal(object, object)

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setAccessibleName(f'Run {label} lift floor movements heatmap')
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cellClicked.connect(self.pick)
        self.floors = []
        self.setMinimumHeight(160)

    def set_movements(self, movements, *, floors=None, maximum=None, complete=True):
        from collections import Counter
        self.floors = floors if floors is not None else sorted({f for s in movements for f in (s.start[2], s.finish[2]) if f is not None})
        counts = Counter((s.start[2], s.finish[2]) for s in movements)
        self.setRowCount(len(self.floors))
        self.setColumnCount(len(self.floors))
        self.setHorizontalHeaderLabels([f'To F{fmt(f)}' for f in self.floors])
        self.setVerticalHeaderLabels([f'From F{fmt(f)}' for f in self.floors])
        maximum = maximum or max(counts.values(), default=1)
        base, accent = self.palette().base().color(), self.palette().highlight().color()
        for row, origin in enumerate(self.floors):
            for col, destination in enumerate(self.floors):
                count = counts[origin, destination]
                item = QTableWidgetItem(str(count) if count or complete else 'Unknown')
                item.setTextAlignment(Qt.AlignCenter)
                mix = .7 * count / maximum
                color = QColor(*(int(a*(1-mix)+b*mix) for a,b in zip(base.getRgb()[:3], accent.getRgb()[:3])))
                item.setBackground(color)
                item.setForeground(self.palette().text())
                item.setToolTip(f'{count} observed lift movements from F{fmt(origin)} to F{fmt(destination)}. '
                                'A and B use the same colour scale. Select to filter.'
                                + (' Missing evidence does not establish zero movements.' if not complete else ''))
                self.setItem(row, col, item)

    def pick(self, row, col):
        if row < len(self.floors) and col < len(self.floors):
            self.selectedPair.emit(self.floors[row], self.floors[col])


class LiftTimeline(QWidget):
    selectedLift = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.caption = QLabel('Lift activity · solid: transfer · hatched: empty repositioning. Select a bar to filter by lift.')
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.view = AnalysisView('A and B lift movement timeline')
        self.view.fit = self.fit_timeline
        layout.addLayout(toolbar(self.view))
        layout.addWidget(self.view)
        self.view.scene().selectionChanged.connect(self.pick)

    def fit_timeline(self):
        bounds = self.view.scene().itemsBoundingRect().adjusted(-8,-8,8,8)
        self.view.scene().setSceneRect(bounds)
        self.view.resetTransform()
        self.view.scale(max(.25,(self.view.viewport().width()-30)/max(1,bounds.width())),1)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().minimum())

    def set_result(self, result):
        from collections import defaultdict
        scene = self.view.scene()
        scene.blockSignals(True)
        scene.clear()
        rows = defaultdict(list)
        for label, side in zip(('A','B'), result['sides']):
            if side:
                for s in side['movements']:
                    rows[(label, s.lift)].append(s)
        start, end = result['sides'][0]['start'], result['sides'][0]['end']
        scale = 1000 / max(1, end-start)
        palette = self.palette()
        # At full-week scale merge same-pixel bars to bound graphics items.
        # Individual exact records remain available in the paged movement table.
        for row_index, ((label, lift), movements) in enumerate(sorted(rows.items(),key=lambda item:(item[0][1],item[0][0]))):
            y = row_index * 28
            text(scene, f'{label} · {lift}', 0, y, palette)
            bins = defaultdict(list)
            for s in movements:
                if s.time is not None and s.end is not None:
                    x = int((s.time-start)*scale)
                    finish = max(x+1, int((min(end, s.end)-start)*scale))
                    bins[(x, finish, s.kind)].append(s)
            for (x, finish, kind), events in bins.items():
                brush = QBrush(palette.highlight())
                if kind == 'lift_reposition':
                    brush.setStyle(Qt.Dense4Pattern)
                item = scene.addRect(145+x, y+3, max(1,finish-x), 16, pen(palette.highlight().color()), brush)
                item.setFlag(QGraphicsItem.ItemIsSelectable)
                item.setData(0, lift)
                first = events[0]
                item.setToolTip(f'{label} · {lift} · {kind}\n{fmt(first.time)}–{fmt(first.end)} s\n'
                                f'F{fmt(first.start[2])} → F{fmt(first.finish[2])}\n{len(events)} record(s) at this scale')
        for i in range(6):
            text(scene, f'{(start+(end-start)*i/5)/3600:.2f} h', 145+200*i, -25, palette)
        scene.blockSignals(False)
        self.view.fit()

    def pick(self):
        selected = self.view.scene().selectedItems()
        if selected and selected[0].data(0):
            self.selectedLift.emit(str(selected[0].data(0)))
