"""Inline polygon drafting with exact coordinates and explicit completion."""
import math
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit, parse_coordinate


class BoundaryInput(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.coordinate = CoordinateEdit(self)
        self.coordinate.setPlaceholderText('X,Y | @dx,dy | @length<angle')
        self.coordinate.setAccessibleName('Boundary vertex coordinates in metres')
        self.coordinate.setToolTip('Absolute coordinates or displacement from the last vertex. '
            'Angles are counterclockwise from east. Typed vertices bypass snapping. '
            'Enter adds a vertex; blank Enter finishes; Escape cancels.')
        label = QLabel('Boundary (m)', self)
        label.setBuddy(self.coordinate)
        self.add_button = QPushButton('Add point', self)
        self.remove_button = QPushButton('Undo point', self)
        self.finish_button = QPushButton('Finish', self)
        self.finish_button.setToolTip('Save the added vertices as a closed polygon. Add any pending coordinate first.')
        self.cancel_button = QPushButton('Cancel', self)
        self.feedback = QLabel(self)
        self.feedback.setWordWrap(True)
        self.feedback.setAccessibleName('Boundary draft coordinates and input errors')
        for column, widget in enumerate((label, self.coordinate, self.add_button,
                                         self.remove_button, self.finish_button, self.cancel_button)):
            layout.addWidget(widget, 0, column)
        layout.addWidget(self.feedback, 1, 0, 1, 6)
        layout.setColumnStretch(1, 1)
        self.coordinate.textChanged.connect(self.refresh)
        self.coordinate.returnPressed.connect(self.submit)
        self.coordinate.escapePressed.connect(editor.cancel_cad_command)
        self.add_button.clicked.connect(self.submit)
        self.remove_button.clicked.connect(self.remove_last)
        self.finish_button.clicked.connect(self.finish)
        self.cancel_button.clicked.connect(editor.cancel_cad_command)
        self.hide()

    def check_draft(self):
        e = self.editor
        name = e.bounding_box_location_name
        if (not name or e.workspace.stage != 'layout' or e._current_edit_mode() != 'location_bbox'
                or e.project_editing_locked()):
            raise ValueError('Start a location boundary on the Layout workspace.')
        location = e.store.get_location(name)
        if (location != e._boundary_original or not location
                or int(location.get('floor', -1)) != e.floor_spin.value()):
            raise ValueError('Location changed; cancel and select it again.')
        if e.dragging_bounding_box_point_index is not None:
            raise ValueError('Release or cancel the corner drag before entering a point.')
        return e.bounding_box_points

    def target(self, points):
        anchor = (points[-1]['x'], points[-1]['y']) if points else None
        target = parse_coordinate(self.coordinate.text(), anchor)
        if target is not None and target == anchor:
            raise ValueError('The next vertex must differ from the last one.')
        return target

    def refresh(self, *_):
        self.add_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.finish_button.setEnabled(False)
        try:
            points = self.check_draft()
            self.remove_button.setEnabled(bool(points))
            self.finish_button.setEnabled(len(points) >= 3)
            target = self.target(points)
            message = f'{self.editor.bounding_box_location_name}: {len(points)} vertices. '
            if target is None:
                message += 'Click or type the next vertex. Finish closes the polygon; saved geometry changes only on Finish.'
            else:
                message += f'Next: X {target[0]:.9g}, Y {target[1]:.9g} m.'
                if points:
                    length = math.hypot(target[0]-points[-1]['x'], target[1]-points[-1]['y'])
                    message += f' Segment {length:.9g} m.'
                self.add_button.setEnabled(True)
            self.feedback.setText(message)
        except ValueError as exc:
            self.feedback.setText(str(exc))

    def submit(self):
        try:
            points = self.check_draft()
            target = self.target(points)
            if target is None:
                self.finish()
                return
            points.append(dict(x=target[0], y=target[1]))
            self.coordinate.clear()
            self.editor.refresh_canvas()
            self.coordinate.setFocus()
        except ValueError as exc:
            self.feedback.setText(str(exc))

    def remove_last(self):
        try:
            points = self.check_draft()
            if points:
                points.pop()
                self.editor.refresh_canvas()
        except ValueError as exc:
            self.feedback.setText(str(exc))

    def finish(self):
        try:
            self.check_draft()
            if not self.editor.finish_location_bounding_box_draw():
                self.feedback.setText(self.editor.status_label.text())
        except ValueError as exc:
            self.feedback.setText(str(exc))
