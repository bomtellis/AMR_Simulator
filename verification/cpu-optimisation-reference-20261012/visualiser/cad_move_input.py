"""Inline numerical translation of the active-floor selection."""
from copy import deepcopy
import math
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit, parse_coordinate


class CadMoveInput(QWidget):
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
        self.offset = CoordinateEdit(self)
        self.offset.setAccessibleName('Move selection displacement in metres')
        self.offset.setPlaceholderText('dx,dy or @distance<angle')
        self.offset.setToolTip('Translation in metres; positive X east, positive Y north. Grid and direction constraints do not alter these values.')
        self.preview = QLabel(self)
        self.preview.setWordWrap(True)
        self.apply_button = QPushButton('Apply move', self)
        cancel = QPushButton('Cancel', self)
        self.pick_button = QPushButton('Pick destination', self)
        self.pick_button.setToolTip('Click a base point, then a destination. Uses the selected grid/object snap mode; perpendicular uses the base point. Reference picks never split corridors. Escape or right-click cancels.')
        label = QLabel('Move by (m)', self)
        label.setBuddy(self.offset)
        layout.addWidget(label, 0, 0)
        layout.addWidget(self.offset, 0, 1)
        layout.addWidget(self.apply_button, 0, 2)
        layout.addWidget(cancel, 0, 3)
        layout.addWidget(self.preview, 1, 0, 1, 3)
        layout.addWidget(self.pick_button, 1, 3)
        layout.setColumnStretch(1, 1)
        self.offset.textChanged.connect(self.refresh_preview)
        self.offset.returnPressed.connect(self.apply)
        self.offset.escapePressed.connect(self.hide)
        cancel.clicked.connect(self.hide)
        self.apply_button.clicked.connect(self.apply)
        self.pick_button.clicked.connect(self.begin_mouse)
        self.hide()

    def displacement(self):
        value = parse_coordinate(self.offset.text(), (0, 0))
        if value is None or value == (0, 0):
            raise ValueError('Enter a non-zero displacement.')
        return value

    def refresh_preview(self, *_):
        self.preview_store = None
        try:
            dx, dy = self.displacement()
            points = self.editor.selection_move_points()
            if not points:
                raise ValueError('Select points or corridors on the active floor.')
            from visualiser.model_layers import locked_points
            if set(points) & locked_points(self.editor.store.data):
                raise ValueError('Unlock the selected objects and attached corridors before moving.')
            self.preview_store = deepcopy(self.editor.store)
            for name, point in points.items():
                x,y = float(point['x'])+dx,float(point['y'])+dy
                if not all(math.isfinite(v) for v in (x,y)):
                    raise ValueError('The resulting coordinates must be finite.')
                self.preview_store.set_point_position(name,x,y,exact=True)
            self.preview_names = set(points)
            first = self.preview_store.all_points()[sorted(points)[0]]
            self.preview_anchor = (first['x'],first['y'])
            names = ', '.join(sorted(points)[:4])
            if len(points) > 4:
                names += ', …'
            self.preview.setText(f'{len(points)} points ({names}): X {dx:+.9g} m, Y {dy:+.9g} m. One undo step.')
            self.apply_button.setEnabled(not self.editor.project_editing_locked())
        except ValueError as exc:
            self.preview_store = None
            self.preview.setText(str(exc))
            self.apply_button.setEnabled(False)
        self.editor.canvas.viewport().update()

    def apply(self):
        try:
            dx, dy = self.displacement()
            if self.editor.move_selected_by(dx, dy):
                self.offset.clear()
                self.hide()
        except ValueError as exc:
            self.preview.setText(str(exc))

    def _clear_mouse(self):
        self.pending_pointer = None
        self.mouse_stage = None
        self.mouse_timer.stop()
        self.preview_store = None
        self.offset.setEnabled(True)
        self.editor.canvas.viewport().update()

    def hide(self):
        self._clear_mouse()
        super().hide()

    def hideEvent(self, event):
        self._clear_mouse()
        super().hideEvent(event)

    def paint_preview(self, painter):
        if not self.isHidden() and self.preview_store is not None:
            from visualiser.selection_preview import paint_selection_preview
            paint_selection_preview(self.editor,painter,self.preview_store,
                                    self.preview_names,self.preview_anchor,'Move preview')

    def begin_mouse(self):
        if not self.editor.selection_move_points() or self.editor.project_editing_locked():
            self.preview.setText('Select points or corridors first.')
            return
        if not self.editor._layout_points_editable(self.editor.selection_move_points()):
            self.preview.setText('Unlock the selected objects and attached corridors first.')
            return
        self.mouse_timer.stop()
        self.offset.clear()
        self.pending_pointer = None
        self.preview_store = None
        self.mouse_stage = 'base'
        self.offset.setEnabled(False)
        self.preview.setText('Click a base point. Escape or right-click cancels.')
        self.editor.set_status(self.preview.text())
        self.editor.canvas.setFocus()

    def pointer_moved(self, sx, sy):
        if self.mouse_stage == 'target' and not self.editor.project_editing_locked():
            self.pending_pointer = (sx,sy)
            if not self.mouse_timer.isActive():
                self.mouse_timer.start()

    def _update_mouse_preview(self):
        if self.mouse_stage != 'target':
            return
        if self.pending_pointer is not None:
            from visualiser.cad_transform_pick import pick_point
            sx,sy = self.pending_pointer
            self.pending_pointer = None
            try:
                self.mouse_target = pick_point(self.editor,sx,sy,anchor=self.mouse_base)
            except ValueError as error:
                self.mouse_timer.stop()
                self.mouse_target = None
                self.preview_store = None
                self.apply_button.setEnabled(False)
                self.preview.setText(str(error))
                self.editor.canvas.viewport().update()
                return
        if self.mouse_stage == 'target' and self.mouse_target is not None:
            dx = self.mouse_target[0]-self.mouse_base[0]
            dy = self.mouse_target[1]-self.mouse_base[1]
            text = f'{dx:.12g},{dy:.12g}'
            if self.offset.text() == text and self.preview_store is None:
                self.refresh_preview()
            else:
                self.offset.setText(text)

    def mouse_click(self, sx, sy):
        self.mouse_timer.stop()
        self.pending_pointer = None
        from visualiser.cad_transform_pick import pick_point
        try:
            point = pick_point(self.editor,sx,sy,anchor=self.mouse_base if self.mouse_stage == 'target' else None)
        except ValueError as error:
            self.preview_store = None
            self.apply_button.setEnabled(False)
            self.preview.setText(str(error))
            return
        if self.mouse_stage == 'base':
            self.mouse_base = point
            self.mouse_stage = 'target'
            self.mouse_target = None
            self.preview.setText('Move to preview; click the destination to apply. Escape cancels.')
            self.editor.set_status(self.preview.text())
        elif self.mouse_stage == 'target':
            self.mouse_timer.stop()
            self.mouse_target = point
            self._update_mouse_preview()
            if self.apply_button.isEnabled():
                self.apply()

