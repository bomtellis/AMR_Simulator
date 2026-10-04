"""Optional exact dimensions alongside two-corner footprint drawing."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit
from visualiser.location_drawing import dimensioned_rectangle


class RectangleInput(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4,2,4,2)
        self.dimensions = CoordinateEdit(self)
        self.dimensions.setPlaceholderText('width,height[,angle]')
        self.dimensions.setAccessibleName('Location rectangle dimensions and rotation')
        self.dimensions.setToolTip('Metres, then optional counterclockwise degrees from east. Centred on the location. Grid snapping is bypassed.')
        self.explanation = QLabel(self)
        self.explanation.setWordWrap(True)
        self.apply_button = QPushButton('Apply dimensions', self)
        cancel = QPushButton('Cancel', self)
        layout.addWidget(QLabel('Rectangle at location centre (m, °)', self))
        layout.addWidget(self.dimensions)
        layout.addWidget(self.explanation, 1)
        layout.addWidget(self.apply_button)
        layout.addWidget(cancel)
        self.dimensions.textChanged.connect(self.preview)
        self.dimensions.returnPressed.connect(self.apply)
        self.dimensions.escapePressed.connect(editor.cancel_cad_command)
        cancel.clicked.connect(editor.cancel_cad_command)
        self.apply_button.clicked.connect(self.apply)
        self.hide()

    def rectangle_geometry(self):
        draft = getattr(self.editor, '_rectangle_draft', None)
        if not draft:
            raise ValueError('Select a location before entering dimensions.')
        location = self.editor.store.get_location(draft['name'])
        if location != draft['original']:
            raise ValueError('Location changed; cancel and select it again.')
        return dimensioned_rectangle((location['x'],location['y']), self.dimensions.text())

    def preview(self, *_):
        draft = getattr(self.editor, '_rectangle_draft', None)
        if draft:
            draft.pop('numeric_points', None)
            if self.dimensions.text().strip():
                draft['first'] = draft['second'] = None
        self.apply_button.setEnabled(False)
        if not self.dimensions.text().strip():
            self.explanation.setText('Click two corners, or enter exact dimensions centred on the location.')
        else:
            try:
                points, width, height, angle = self.rectangle_geometry()
                draft['numeric_points'] = points
                self.explanation.setText(f'{width:g} × {height:g} m, {angle:g}°; replaces the boundary in one undo step.')
                self.apply_button.setEnabled(True)
            except ValueError as exc:
                self.explanation.setText(str(exc))
        self.editor.canvas.viewport().update()

    def apply(self):
        try:
            points, *_ = self.rectangle_geometry()
            self.editor.apply_location_rectangle(points)
        except ValueError as exc:
            self.explanation.setText(str(exc))
