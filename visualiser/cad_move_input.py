"""Inline numerical translation of the active-floor selection."""
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton
from visualiser.cad_drawing_input import CoordinateEdit, parse_coordinate


class CadMoveInput(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
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
        label = QLabel('Move by (m)', self)
        label.setBuddy(self.offset)
        layout.addWidget(label, 0, 0)
        layout.addWidget(self.offset, 0, 1)
        layout.addWidget(self.apply_button, 0, 2)
        layout.addWidget(cancel, 0, 3)
        layout.addWidget(self.preview, 1, 0, 1, 4)
        layout.setColumnStretch(1, 1)
        self.offset.textChanged.connect(self.refresh_preview)
        self.offset.returnPressed.connect(self.apply)
        self.offset.escapePressed.connect(self.hide)
        cancel.clicked.connect(self.hide)
        self.apply_button.clicked.connect(self.apply)
        self.hide()

    def displacement(self):
        value = parse_coordinate(self.offset.text(), (0, 0))
        if value is None or value == (0, 0):
            raise ValueError('Enter a non-zero displacement.')
        return value

    def refresh_preview(self, *_):
        try:
            dx, dy = self.displacement()
            points = self.editor.selection_move_points()
            if not points:
                raise ValueError('Select points or corridors on the active floor.')
            from visualiser.model_layers import locked_points
            if set(points) & locked_points(self.editor.store.data):
                raise ValueError('Unlock the selected objects and attached corridors before moving.')
            names = ', '.join(sorted(points)[:4])
            if len(points) > 4:
                names += ', …'
            self.preview.setText(f'{len(points)} points ({names}): X {dx:+.9g} m, Y {dy:+.9g} m. One undo step.')
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.preview.setText(str(exc))
            self.apply_button.setEnabled(False)

    def apply(self):
        try:
            dx, dy = self.displacement()
            if self.editor.move_selected_by(dx, dy):
                self.offset.clear()
                self.hide()
        except ValueError as exc:
            self.preview.setText(str(exc))

