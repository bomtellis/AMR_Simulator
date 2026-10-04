"""Inline rotation parameters and affected-selection preview."""
import math
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit, parse_coordinate
from visualiser.selection_rotation import finite, rotate_selection


class CadRotateInput(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.preview_store = None
        self.mouse_stage = None
        self.mouse_target = None
        self.pending_pointer = None
        self.mouse_timer = QTimer(self)
        self.mouse_timer.setSingleShot(True)
        self.mouse_timer.setInterval(33)
        self.mouse_timer.timeout.connect(self._update_mouse_preview)
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.centre = CoordinateEdit(self)
        self.centre.setAccessibleName('Rotation centre X,Y in metres')
        self.centre.setPlaceholderText('X,Y')
        self.centre.setToolTip('Absolute world coordinates in metres. Initially the centre of the selected point extents; edit to choose another pivot.')
        self.angle = CoordinateEdit(self)
        self.angle.setAccessibleName('Rotation angle in degrees counterclockwise')
        self.angle.setPlaceholderText('Degrees')
        self.angle.setMaximumWidth(130)
        self.angle.setToolTip('Counterclockwise degrees; negative values rotate clockwise. Typed values bypass snapping.')
        self.apply_button = QPushButton('Apply rotation', self)
        cancel = QPushButton('Cancel', self)
        self.pick_button = QPushButton('Pick rotation', self)
        self.pick_button.setToolTip('Click centre, reference direction, then target direction to apply. Uses the selected grid/object snap mode; perpendicular uses the centre. Reference picks never split corridors. Escape cancels.')
        self.preview = QLabel(self)
        self.preview.setWordWrap(True)
        centre_label, angle_label = QLabel('Centre (m)', self), QLabel('Angle (°)', self)
        centre_label.setBuddy(self.centre)
        angle_label.setBuddy(self.angle)
        for column, widget in enumerate((centre_label, self.centre, angle_label,
                                         self.angle, self.apply_button, cancel)):
            layout.addWidget(widget, 0, column)
        layout.addWidget(self.preview, 1, 0, 1, 5)
        layout.addWidget(self.pick_button, 1, 5)
        layout.setColumnStretch(1, 1)
        for entry in (self.centre, self.angle):
            entry.textChanged.connect(self.refresh_preview)
            entry.returnPressed.connect(self.apply)
            entry.escapePressed.connect(self.hide)
        cancel.clicked.connect(self.hide)
        self.apply_button.clicked.connect(self.apply)
        self.pick_button.clicked.connect(self.begin_mouse)
        self.hide()

    def parameters(self):
        centre = parse_coordinate(self.centre.text())
        if centre is None:
            raise ValueError('Enter an absolute rotation centre X,Y in metres.')
        angle = finite(self.angle.text())
        if angle % 360 == 0:
            raise ValueError('Enter a non-zero rotation, excluding full turns.')
        return centre, angle

    def refresh_preview(self, *_):
        self.preview_store = None
        self.apply_button.setEnabled(False)
        try:
            centre, angle = self.parameters()
            points = self.editor.selection_move_points()
            if not points:
                raise ValueError('Select points or corridors on the current floor.')
            self.preview_store = rotate_selection(self.editor.store, points, centre, angle)
            self.preview_names = set(points)
            self.preview_centre = centre
            names = ', '.join(sorted(points)[:4]) + (', …' if len(points) > 4 else '')
            self.preview.setText(f'{len(points)} points ({names}): {angle:g}° about ({centre[0]:g}, {centre[1]:g}) m; '
                'includes attached boundaries and bays. Recheck routes and initial robot poses. One undo step.')
            self.apply_button.setEnabled(not self.editor.project_editing_locked())
        except ValueError as exc:
            self.preview.setText(str(exc))
        self.editor.canvas.viewport().update()

    def _clear_mouse(self):
        self.pending_pointer = None
        self.preview_store = None
        self.mouse_stage = None
        self.mouse_timer.stop()
        self.centre.setEnabled(True)
        self.angle.setEnabled(True)
        self.editor.canvas.viewport().update()

    def hide(self):
        self._clear_mouse()
        super().hide()

    def hideEvent(self, event):
        self._clear_mouse()
        super().hideEvent(event)

    def paint_preview(self, painter):
        if not self.isHidden() and self.mouse_stage == 'target' and self.mouse_target is not None:
            centre = self.editor.canvas.mapFromScene(self.editor.world_to_scene(*self.mouse_centre))
            reference = self.editor.canvas.mapFromScene(self.editor.world_to_scene(*self.mouse_reference))
            target = self.editor.canvas.mapFromScene(self.editor.world_to_scene(*self.mouse_target))
            painter.save()
            painter.setPen(QPen(QColor(self.editor._map_colours['accent']), 1, Qt.DashLine))
            painter.drawLine(centre, reference)
            painter.drawLine(centre, target)
            painter.restore()
        if self.isHidden() or self.preview_store is None:
            return
        from visualiser.selection_preview import paint_selection_preview
        paint_selection_preview(self.editor, painter, self.preview_store,
                                self.preview_names, self.preview_centre, 'Rotation preview')

    def apply(self):
        try:
            centre, angle = self.parameters()
            if self.editor.rotate_selected(centre, angle):
                self.hide()
        except ValueError as exc:
            self.preview.setText(str(exc))

    def begin_mouse(self):
        if not self.editor.selection_move_points() or self.editor.project_editing_locked():
            self.preview.setText('Select points or corridors before picking a rotation.')
            return
        if not self.editor._layout_points_editable(self.editor.selection_move_points()):
            self.preview.setText('Unlock the selected objects and attached corridors before rotating.')
            return
        self.mouse_timer.stop()
        self.mouse_stage = 'centre'
        self.pending_pointer = None
        self.mouse_target = None
        self.preview_store = None
        self.angle.clear()
        self.centre.setEnabled(False)
        self.angle.setEnabled(False)
        self.preview.setText('Click the rotation centre. Escape or right-click cancels.')
        self.editor.set_status(self.preview.text())
        self.editor.canvas.setFocus()

    def _mouse_point(self, sx, sy):
        from visualiser.cad_transform_pick import pick_point
        return pick_point(self.editor,sx,sy,anchor=self.mouse_centre if self.mouse_stage != 'centre' else None)

    def pointer_moved(self, sx, sy):
        if self.mouse_stage == 'target' and not self.editor.project_editing_locked():
            self.pending_pointer = (sx,sy)
            if not self.mouse_timer.isActive():
                self.mouse_timer.start()

    def _update_mouse_preview(self):
        if self.mouse_stage != 'target':
            return
        if self.pending_pointer is not None:
            sx,sy = self.pending_pointer
            self.pending_pointer = None
            try:
                self.mouse_target = self._mouse_point(sx,sy)
            except ValueError as error:
                self.mouse_timer.stop()
                self.mouse_target = None
                self.preview_store = None
                self.apply_button.setEnabled(False)
                self.preview.setText(str(error))
                self.editor.canvas.viewport().update()
                return
        if self.mouse_stage != 'target' or self.mouse_target is None:
            return
        cx, cy = self.mouse_centre
        x, y = self.mouse_target
        if math.hypot(x-cx,y-cy) < 1e-9:
            self.angle.clear()
            return
        rx, ry = self.mouse_reference
        degrees = math.degrees(math.atan2(y-cy,x-cx)-math.atan2(ry-cy,rx-cx))
        degrees = (degrees+180) % 360-180
        text = f'{degrees:.12g}'
        if self.angle.text() == text and self.preview_store is None:
            self.refresh_preview()
        else:
            self.angle.setText(text)

    def mouse_click(self, sx, sy):
        self.mouse_timer.stop()
        self.pending_pointer = None
        try:
            point = self._mouse_point(sx,sy)
        except ValueError as error:
            self.preview_store = None
            self.apply_button.setEnabled(False)
            self.preview.setText(str(error))
            return
        if self.mouse_stage == 'centre':
            self.mouse_centre = point
            self.centre.setText(f'{point[0]:.12g},{point[1]:.12g}')
            self.mouse_stage = 'reference'
            self.preview.setText('Click a point along the reference direction from the centre.')
            self.editor.set_status(self.preview.text())
        elif self.mouse_stage == 'reference':
            if math.dist(point,self.mouse_centre) < 1e-9:
                self.preview.setText('Choose a reference point away from the centre.')
                return
            self.mouse_reference = point
            self.mouse_stage = 'target'
            self.preview.setText('Move to preview; click the target direction to apply. Escape cancels.')
            self.editor.set_status(self.preview.text())
        elif self.mouse_stage == 'target':
            self.mouse_timer.stop()
            self.mouse_target = point
            self._update_mouse_preview()
            if self.apply_button.isEnabled():
                self.apply()
