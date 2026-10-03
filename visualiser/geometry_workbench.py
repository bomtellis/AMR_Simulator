"""Runnable CAD/geometry workflow prototype: python -m visualiser.geometry_workbench.

Separate studies keep unfinished traffic integration out of production runs.
The drawing uses the same analytic motion objects as distance/time/clearance.
"""
import argparse
import copy
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen, QPolygonF, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QTextBrowser, QToolBar,
    QVBoxLayout, QWidget)

from amr_trajectories import Pose, TrajectoryError, check_clearance, footprint
from amr_project_runs import write_json
from amr_geometric_routing import simulation_project_from_study
from amr_reference_inputs import DEFAULT_REFERENCE_POINT, reference_point_options
from amr_reference_trajectories import plan_reference_trajectory

SCALE = 60
EXAMPLE = {'schema_version': 1, 'kind': 'amr_geometry_study',
           'points': [[0,0], [6,0], [6,6]],
           'obstacles': [[2,-3,2.3,-.55], [2,.55,2.3,3]],
           'parameters': {'minimum_radius_m': 2, 'speed_m_per_sec': 1,
                          'pivot_allowed': False, 'pivot_speed_deg_per_sec': 45,
                          'robot_length_m': 1.2, 'robot_width_m': .8,
                          'payload_length_m': 1.6, 'payload_width_m': .9, 'clearance_m': .05}}


def study_trajectory(points, parameters):
    return plan_reference_trajectory(points,
        **{key: parameters[key] for key in ('minimum_radius_m', 'speed_m_per_sec', 'pivot_allowed', 'pivot_speed_deg_per_sec')},
        **reference_point_options(parameters))


def validate_study(data):
    if not isinstance(data, dict) or data.get('kind') != 'amr_geometry_study' or data.get('schema_version') != 1:
        raise ValueError('Select a version 1 geometry study, not a simulation project.')
    p = data['parameters']
    try:
        study_trajectory(data['points'], p)
    except TrajectoryError as exc:
        if exc.reason != 'infeasible_route':
            raise
    for prefix in ('robot', 'payload'):
        footprint(Pose(0,0,0), p[prefix+'_length_m'], p[prefix+'_width_m'], p['clearance_m'])
    reference = study_trajectory([(0,0),(1,0)], p)
    check_clearance(reference, length_m=1, width_m=1, obstacles=data['obstacles'], clearance_m=p['clearance_m'])
    result = {k:copy.deepcopy(data[k]) for k in ('schema_version','kind','points','obstacles','parameters')}
    for key in EXAMPLE['parameters']:
        if key != 'pivot_allowed':
            result['parameters'][key] = float(result['parameters'][key])
    result['points'] = [list(map(float, point)) for point in result['points']]
    result['obstacles'] = [list(map(float, box)) for box in result['obstacles']]
    return result


def screen(point):
    return QPointF(point[0]*SCALE, -point[1]*SCALE)


class StudyEdit(QUndoCommand):
    def __init__(self, window, after, label):
        super().__init__(label)
        self.window, self.before, self.after = window, copy.deepcopy(window.study), copy.deepcopy(after)

    def undo(self):
        self.window.set_study(self.before)

    def redo(self):
        self.window.set_study(self.after)


class Canvas(QGraphicsView):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QColor('#f8fafc'))
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def model_point(self, pos, modifiers=Qt.NoModifier):
        point = self.mapToScene(pos)
        x, y = point.x()/SCALE, -point.y()/SCALE
        if self.owner.snap.isChecked():
            x,y = round(x*4)/4, round(y*4)/4
        if modifiers & Qt.ShiftModifier and self.owner.pending:
            a,b = self.owner.pending[-1]
            if abs(x-a) >= abs(y-b):
                y = b
            else:
                x = a
        return [x,y]

    def mouseMoveEvent(self, event):
        x,y = self.model_point(event.position().toPoint(), event.modifiers())
        self.owner.coordinates.setText(f'X {x:.2f} m    Y {y:.2f} m')
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.owner.mode != 'inspect':
            self.owner.add_point(self.model_point(event.position().toPoint(), event.modifiers()))
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        scale = self.transform().m11()
        factor = 1.2 if event.angleDelta().y() > 0 else 1/1.2
        if .05 <= scale*factor <= 20:
            self.scale(factor, factor)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.owner.finish_drawing()
        elif event.key() == Qt.Key_Escape:
            self.owner.cancel_drawing()
        else:
            super().keyPressEvent(event)


class GeometryWorkbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AMR geometric workbench — workflow prototype')
        self.resize(1280, 820)
        self.study = copy.deepcopy(EXAMPLE)
        self.mode, self.pending, self.trajectory, self.clearance_result = 'inspect', [], None, None
        self.planning_result = None
        self.undo_stack = QUndoStack(self)
        self.canvas = Canvas(self)
        self.setCentralWidget(self.canvas)
        toolbar = QToolBar('Drawing and inspection', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, callback in [('Example', self.load_example), ('Draw route', lambda: self.begin_drawing('route')),
                                ('Draw obstacle', lambda: self.begin_drawing('obstacle')), ('Finish', self.finish_drawing),
                                ('Cancel', self.cancel_drawing), ('Fit', self.fit), ('Open study', self.open_study),
                                ('Save study', self.save_study), ('Export simulation', self.export_simulation)]:
            toolbar.addAction(label, callback)
        undo = self.undo_stack.createUndoAction(self, 'Undo')
        undo.setShortcut('Ctrl+Z')
        redo = self.undo_stack.createRedoAction(self, 'Redo')
        redo.setShortcut('Ctrl+Y')
        toolbar.addActions([undo, redo])
        self.snap = QCheckBox('Snap 0.25 m')
        self.snap.setChecked(True)
        toolbar.addWidget(self.snap)
        self.position_input = QLineEdit()
        self.position_input.setMaximumWidth(130)
        self.position_input.setPlaceholderText('X, Y metres')
        self.position_input.setAccessibleName('Add route or obstacle point using X and Y coordinates in metres')
        self.position_input.returnPressed.connect(self.add_typed_point)
        toolbar.addWidget(self.position_input)
        self.controls = {}
        self.properties = QDockWidget('Robot, load and manoeuvres', self)
        self.properties.setObjectName('geometry-properties')
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for key, label, unit, minimum in [
                ('minimum_radius_m', 'Minimum radius', ' m', .001),
                ('speed_m_per_sec', 'Travel speed', ' m/s', .001),
                ('pivot_speed_deg_per_sec', 'Pivot speed', ' °/s', .001),
                ('robot_length_m', 'Robot length', ' m', .001), ('robot_width_m', 'Robot width', ' m', .001),
                ('payload_length_m', 'Load length', ' m', .001), ('payload_width_m', 'Load width', ' m', .001),
                ('clearance_m', 'Extra clearance', ' m', 0)]:
            control = QDoubleSpinBox()
            control.setDecimals(3)
            control.setRange(minimum, 10000)
            control.setSuffix(unit)
            control.setValue(self.study['parameters'][key])
            self.controls[key] = control
            form.addRow(label, control)
            control.editingFinished.connect(self.apply_parameters)
        self.pivots = QCheckBox('Permit stationary pivots when a turn cannot fit')
        self.pivots.toggled.connect(self.apply_parameters)
        form.addRow(self.pivots)
        self.reference_controls = {}
        reference = self.study['parameters'].get('reference_point', DEFAULT_REFERENCE_POINT)
        for key, label in (('longitudinal_mm', 'Reference offset: forwards +'), ('lateral_mm', 'Reference offset: left +')):
            control = QDoubleSpinBox()
            control.setDecimals(3)
            control.setRange(-1000000, 1000000)
            control.setSuffix(' mm')
            control.setValue(reference[key])
            control.setAccessibleName(label + ' in millimetres')
            control.editingFinished.connect(self.apply_parameters)
            self.reference_controls[key] = control
            form.addRow(label, control)
        self.pivot_axis = QComboBox()
        self.pivot_axis.addItem('Body centre', 'body_centre')
        self.pivot_axis.addItem('Turning reference point', 'reference_point')
        self.pivot_axis.setCurrentIndex(self.pivot_axis.findData(reference['pivot_axis']))
        self.pivot_axis.currentIndexChanged.connect(self.apply_parameters)
        form.addRow('Pivot about', self.pivot_axis)
        form.addRow(QLabel('Radius and travel speed refer to the marked reference point.\nOffsets use the robot body frame; the load remains centred.'))
        note = QLabel('Load and robot share a centred rectangular envelope.\nDrawn rectangles are explicit obstacles.\nExport simulation creates a separate geometric project.\nThis study previews forward paths and permitted pivots.')
        note.setWordWrap(True)
        form.addRow(note)
        self.properties.setWidget(form_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties)
        self.properties.hide()
        toolbar.addAction(self.properties.toggleViewAction())
        self.guide = QDockWidget('Try the reference', self)
        self.guide.setObjectName('geometry-guide')
        help_text = QTextBrowser()
        help_text.setHtml('''<h3>Geometry reference</h3><p>This is a planning prototype, not a simulation result.</p>
          <ol><li>Inspect the blue route: 4 m straight + a 2 m radius quarter turn + 4 m straight.
          Expected length <b>8 + π = 11.141593 m</b>; at 1 m/s, the same number of seconds.</li>
          <li>Open Robot, load and manoeuvres. Set load width to 1.01 m: with 0.05 m clearance
          on each side, the 1.10 m opening is too narrow. Restore 0.90 m.</li>
          <li>Choose Draw route. Enter 0,0 then 1,0 then 1,1 in the coordinate box (Enter after
          each). Click Finish: a 2 m radius cannot fit. Enable stationary pivots: the path is
          2 m plus a 90° pivot; at 1 m/s and 45°/s this takes 4 seconds.</li>
          <li>Draw obstacle uses two opposite corners. Undo/redo restores each completed operation.
          Save study retains inputs and inspectable trajectory/check results.</li>
          <li>Export simulation creates a new JSON project for the main editor or simulator. It has one
          delivery, the same motion parameters, explicit physical floor bounds and 2-second pickup/dropoff.
          The reference finishes at <b>15.141593 s</b>. Open Project Checks and acknowledge the geometric
          model scope before a managed run. Results use recorded curves and pivots.</li></ol>
          <p><b>Gestures:</b> wheel zoom; drag to pan in inspection mode; Shift constrains a new
          drawing point horizontally/vertically; Enter finishes; Escape cancels an unfinished drawing.</p>
          <p>Dashed grey is the requested polyline. Blue is the radius-constrained path. Orange
          circles mark pivots. Red means collision; unresolved/limited checks never mean clear.
          Exact boundary contact is allowed; use extra clearance to require separation.</p>''')
        self.guide.setWidget(help_text)
        self.addDockWidget(Qt.RightDockWidgetArea, self.guide)
        self.guide.hide()
        toolbar.addAction(self.guide.toggleViewAction())
        self.coordinates = QLabel('X 0.00 m    Y 0.00 m')
        self.statusBar().addPermanentWidget(self.coordinates)
        self._display_parameters = self.control_parameters()
        self._display_reference = self.control_reference()
        self.rebuild()

    def set_study(self, study):
        self.study = copy.deepcopy(study)
        for key, control in self.controls.items():
            control.blockSignals(True)
            control.setValue(self.study['parameters'][key])
            control.blockSignals(False)
        self.pivots.blockSignals(True)
        self.pivots.setChecked(self.study['parameters']['pivot_allowed'])
        self.pivots.blockSignals(False)
        reference = self.study['parameters'].get('reference_point', DEFAULT_REFERENCE_POINT)
        for key, control in self.reference_controls.items():
            control.blockSignals(True)
            control.setValue(reference[key])
            control.blockSignals(False)
        self.pivot_axis.blockSignals(True)
        self.pivot_axis.setCurrentIndex(self.pivot_axis.findData(reference['pivot_axis']))
        self.pivot_axis.blockSignals(False)
        self._display_parameters = self.control_parameters()
        self._display_reference = self.control_reference()
        self.rebuild()

    def control_parameters(self):
        return {**{k:c.value() for k,c in self.controls.items()}, 'pivot_allowed': self.pivots.isChecked()}

    def control_reference(self):
        return {**{key: control.value() for key, control in self.reference_controls.items()},
                'pivot_axis': self.pivot_axis.currentData()}

    def apply_parameters(self):
        after = copy.deepcopy(self.study)
        for key, value in self.control_parameters().items():
            if value != self._display_parameters[key]:
                after['parameters'][key] = value
        for key, value in self.control_reference().items():
            if value != self._display_reference[key]:
                after['parameters'].setdefault('reference_point', copy.deepcopy(DEFAULT_REFERENCE_POINT))[key] = value
        if after != self.study:
            self.undo_stack.push(StudyEdit(self, after, 'Change manoeuvre parameters'))

    def load_example(self):
        self.cancel_drawing()
        self.undo_stack.push(StudyEdit(self, EXAMPLE, 'Load reference'))
        self.fit()

    def begin_drawing(self, mode):
        self.mode, self.pending = mode, []
        self.canvas.setDragMode(QGraphicsView.NoDrag)
        self.canvas.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(f'Draw {mode}: click or type coordinates; Enter finishes, Escape cancels.')
        self.canvas.setFocus()

    def add_typed_point(self):
        try:
            point = [float(x.strip()) for x in self.position_input.text().split(',')]
            if len(point) != 2 or not all(math.isfinite(x) for x in point):
                raise ValueError
        except ValueError:
            self.statusBar().showMessage('Enter two finite coordinates, for example 6, 4 (metres).')
            return
        if self.mode == 'inspect':
            self.begin_drawing('route')
        self.add_point(point)
        self.position_input.clear()

    def add_point(self, point):
        if self.pending and point == self.pending[-1]:
            return
        self.pending.append(point)
        if self.mode == 'obstacle' and len(self.pending) == 2:
            self.finish_drawing()
        else:
            self.rebuild()

    def finish_drawing(self):
        if self.mode == 'inspect':
            return
        if len(self.pending) < 2:
            self.statusBar().showMessage('At least two points are needed; Escape cancels.')
            return
        after = copy.deepcopy(self.study)
        label = 'Draw route'
        if self.mode == 'route':
            after['points'] = copy.deepcopy(self.pending)
        else:
            a,b = self.pending
            if a[0] == b[0] or a[1] == b[1]:
                self.statusBar().showMessage('An obstacle needs nonzero width and height; Escape cancels.')
                return
            after['obstacles'].append([min(a[0],b[0]), min(a[1],b[1]), max(a[0],b[0]), max(a[1],b[1])])
            label = 'Draw obstacle'
        self.cancel_drawing()
        self.undo_stack.push(StudyEdit(self, after, label))

    def cancel_drawing(self):
        self.mode, self.pending = 'inspect', []
        self.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
        self.canvas.unsetCursor()
        self.rebuild()

    def rebuild(self):
        scene = self.canvas.scene()
        scene.clear()
        p = self.study['parameters']
        for a,b,c,d in self.study['obstacles']:
            scene.addRect(QRectF(screen((a,d)), screen((c,b))), QPen(QColor('#596777'), 1), QColor('#d7dfe7'))
        points = self.pending if self.mode == 'route' and self.pending else self.study['points']
        for a,b in zip(points, points[1:]):
            scene.addLine(screen(a).x(), screen(a).y(), screen(b).x(), screen(b).y(), QPen(QColor('#687583'), 1.5, Qt.DashLine))
        for i, point in enumerate(points):
            pos = screen(point)
            scene.addEllipse(pos.x()-4,pos.y()-4,8,8,QPen(QColor('#20344b')),QColor('#ffffff'))
            label = scene.addText(f'P{i+1}  ({point[0]:g}, {point[1]:g}) m')
            label.setDefaultTextColor(QColor('#20344b'))
            label.setPos(pos + QPointF(8,8))
        self.trajectory, self.clearance_result = None, None
        try:
            trajectory = study_trajectory(points, p)
            length, width = max(p['robot_length_m'], p['payload_length_m']), max(p['robot_width_m'],p['payload_width_m'])
            result = check_clearance(trajectory, length_m=length, width_m=width, clearance_m=p['clearance_m'], obstacles=self.study['obstacles'])
            self.trajectory, self.clearance_result = trajectory, result
            self.planning_result = {'status': 'planned'}
            colour = QColor('#006a9c' if result['status'] == 'clear' else '#aa302d')
            poses = trajectory.poses(step_m=.1)
            path = QPainterPath(screen((poses[0].x, poses[0].y)))
            for pose in poses[1:]:
                path.lineTo(screen((pose.x, pose.y)))
            scene.addPath(path, QPen(colour, 3))
            for pose in poses[::max(1,len(poses)//20)]:
                polygon = QPolygonF([screen(point) for point in footprint(pose, length, width, p['clearance_m'])])
                scene.addPolygon(polygon, QPen(QColor('#829dab'), .8), QColor(63,132,163,12))
                offsets = reference_point_options(p)
                dx, dy = offsets['reference_longitudinal_mm']/1000, offsets['reference_lateral_mm']/1000
                marker = screen((pose.x+dx*math.cos(pose.heading)-dy*math.sin(pose.heading),
                                 pose.y+dx*math.sin(pose.heading)+dy*math.cos(pose.heading)))
                scene.addLine(marker.x()-3, marker.y(), marker.x()+3, marker.y(), QPen(QColor('#573577'), 1))
                scene.addLine(marker.x(), marker.y()-3, marker.x(), marker.y()+3, QPen(QColor('#573577'), 1))
            for motion in trajectory.motions:
                if motion.kind == 'arc':
                    centre = screen(motion.centre)
                    reference_start = motion.reference_pose_at(0)
                    start = screen((reference_start.x,reference_start.y))
                    scene.addLine(centre.x(),centre.y(),start.x(),start.y(),QPen(QColor('#006a9c'),1,Qt.DotLine))
                    label = scene.addText(f'R {motion.radius_m:g} m')
                    label.setDefaultTextColor(QColor('#006a9c'))
                    label.setPos(centre)
                elif motion.kind == 'pivot':
                    axis = (motion.reference_pose_at(0) if motion.reference and
                            motion.reference['pivot_axis'] == 'reference_point' else motion.start)
                    pos = screen((axis.x,axis.y))
                    scene.addEllipse(pos.x()-12,pos.y()-12,24,24,QPen(QColor('#9b5a00'),3))
                    label = scene.addText(f'Pivot {abs(math.degrees(motion.sweep_rad)):g}° / {motion.duration_sec:g} s')
                    label.setPos(pos + QPointF(16,-30))
            distance_label = (f'{trajectory.length_m:.6f} m reference translation / '
                              f'{sum(m.body_length_m for m in trajectory.motions):.6f} m body travel'
                              if any(m.reference for m in trajectory.motions) else f'{trajectory.length_m:.6f} m')
            self.statusBar().showMessage(f'GEOMETRY STUDY • {result["status"].replace("_"," ")} • {distance_label} • {trajectory.duration_sec:.6f} s • not a simulation run')
        except TrajectoryError as exc:
            self.planning_result = {'status': exc.reason, 'message': str(exc)}
            self.statusBar().showMessage(str(exc))
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-70,-70,70,70))

    def fit(self):
        self.canvas.fitInView(self.canvas.sceneRect(), Qt.KeepAspectRatio)

    def export_data(self):
        return {**copy.deepcopy(self.study), 'scope': 'Geometry study only; no traffic is simulated here. Export simulation creates a separate runnable project.',
                'trajectory': self.trajectory.to_dict() if self.trajectory else None,
                'planning_result': self.planning_result,
                'clearance_result': self.clearance_result}

    def save_study(self):
        if self.mode != 'inspect':
            self.statusBar().showMessage('Finish or cancel the current drawing before saving.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save geometry study', 'geometry-study.json', 'Geometry study (*.json)')
        if path:
            try:
                write_json(path, self.export_data())
            except OSError as exc:
                QMessageBox.warning(self, 'Could not save study', str(exc))

    def open_study(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open geometry study', '', 'Geometry study (*.json)')
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            after = validate_study(data)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Could not open study', str(exc))
            return
        self.cancel_drawing()
        self.undo_stack.push(StudyEdit(self, after, 'Open geometry study'))
        self.fit()

    def export_simulation(self):
        if self.mode != 'inspect':
            self.statusBar().showMessage('Finish or cancel the current drawing before exporting.')
            return
        try:
            project = simulation_project_from_study(self.study)
        except (ValueError,KeyError,TypeError) as exc:
            QMessageBox.warning(self,'Could not export project',str(exc))
            return
        path,_ = QFileDialog.getSaveFileName(self,'Export geometric simulation project','geometric-project.json','JSON project (*.json)')
        if path:
            try:
                write_json(path,project)
            except OSError as exc:
                QMessageBox.warning(self,'Could not export project',str(exc))
                return
            self.statusBar().showMessage('Exported a separate geometric project. Import it in the main application, check and run; the study is unchanged.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshot')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    window = GeometryWorkbench()
    window.show()
    app.processEvents()
    window.fit()
    app.processEvents()
    if args.screenshot:
        window.grab().save(args.screenshot)
        return
    app.exec()


if __name__ == '__main__':
    main()
