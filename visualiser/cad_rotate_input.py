"""Inline rotation parameters and affected-selection preview."""
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit, parse_coordinate
from visualiser.selection_rotation import finite, rotate_selection


class CadRotateInput(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.preview_store = None
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
        self.preview = QLabel(self)
        self.preview.setWordWrap(True)
        centre_label, angle_label = QLabel('Centre (m)', self), QLabel('Angle (°)', self)
        centre_label.setBuddy(self.centre)
        angle_label.setBuddy(self.angle)
        for column, widget in enumerate((centre_label, self.centre, angle_label,
                                         self.angle, self.apply_button, cancel)):
            layout.addWidget(widget, 0, column)
        layout.addWidget(self.preview, 1, 0, 1, 6)
        layout.setColumnStretch(1, 1)
        for entry in (self.centre, self.angle):
            entry.textChanged.connect(self.refresh_preview)
            entry.returnPressed.connect(self.apply)
            entry.escapePressed.connect(self.hide)
        cancel.clicked.connect(self.hide)
        self.apply_button.clicked.connect(self.apply)
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

    def hideEvent(self, event):
        super().hideEvent(event)
        self.preview_store = None
        self.editor.canvas.viewport().update()

    def paint_preview(self, painter):
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
