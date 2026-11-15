"""Optional floor and drawing setup before creating a new project."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from models import JsonStore
from pdf_underlay import PdfUnderlayDialog, normalise_pdf_underlay, render_pdf_page
from ui_theme import polish_dialog


class NewProjectDialog(QDialog):
    SKIPPED = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('New project setup')
        self.resize(760, 480)
        self.drawings = {}
        layout = QVBoxLayout(self)
        intro = QLabel('Choose the number of floors and optionally assign a DXF or PDF '
                       'background to each. You can configure the rest of the project '
                       'with the existing dialogs, or skip this setup entirely.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.floor_count = QSpinBox()
        self.floor_count.setRange(1, 100)
        self.floor_count.setValue(1)
        self.floor_count.setAccessibleName('Number of floors')
        form.addRow('Number of floors', self.floor_count)
        self.floor_height = QDoubleSpinBox()
        self.floor_height.setRange(0.1, 100.0)
        self.floor_height.setDecimals(2)
        self.floor_height.setSuffix(' m')
        self.floor_height.setValue(JsonStore().data['building']['floor_height_m'])
        form.addRow('Floor height', self.floor_height)
        layout.addLayout(form)
        note = QLabel('Floors are numbered from 0. Drawing assignments are optional.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Floor', 'Drawing', 'Actions'])
        self.table.setAccessibleName('Project floors and drawing assignments')
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.create_button = self.buttons.addButton('Create project', QDialogButtonBox.AcceptRole)
        self.create_button.setProperty('primary', True)
        self.create_button.setDefault(True)
        self.skip_button = self.buttons.addButton('Skip setup', QDialogButtonBox.ActionRole)
        self.skip_button.setToolTip('Start an empty project and use the existing dialogs.')
        self.skip_button.clicked.connect(lambda: self.done(self.SKIPPED))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.floor_count.valueChanged.connect(self.refresh_floors)
        self.refresh_floors()
        polish_dialog(self)

    def refresh_floors(self, *_):
        self.table.setRowCount(self.floor_count.value())
        for floor in range(self.floor_count.value()):
            self.table.setItem(floor, 0, QTableWidgetItem(f'Floor {floor}'))
            mapping = self.drawings.get(floor)
            drawing = QTableWidgetItem(Path(mapping['filepath']).name if mapping else 'No drawing')
            if mapping:
                drawing.setToolTip(mapping['filepath'])
            self.table.setItem(floor, 1, drawing)
            actions = QWidget()
            row = QHBoxLayout(actions)
            row.setContentsMargins(4, 2, 4, 2)
            for title, callback, enabled in (
                ('Choose…', self.choose_drawing, True),
                ('PDF settings…', self.edit_pdf, bool(mapping and mapping['kind'] == 'pdf')),
                ('Clear', self.clear_drawing, bool(mapping)),
            ):
                button = QPushButton(title)
                button.setAutoDefault(False)
                button.setAccessibleName(f'{title} for floor {floor}')
                button.setEnabled(enabled)
                button.clicked.connect(lambda _checked=False, f=floor, handler=callback: handler(f))
                row.addWidget(button)
            self.table.setCellWidget(floor, 2, actions)
            self.table.setRowHeight(floor, max(38, actions.sizeHint().height()))

    def choose_drawing(self, floor):
        existing = self.drawings.get(floor, {})
        initial = str(Path(existing['filepath']).parent) if existing else ''
        path, _ = QFileDialog.getOpenFileName(
            self, f'Choose drawing for floor {floor}', initial,
            'Floor drawings (*.dxf *.pdf);;DXF files (*.dxf);;PDF files (*.pdf)')
        if not path:
            return
        kind = Path(path).suffix.lower().lstrip('.')
        if kind not in {'dxf', 'pdf'}:
            QMessageBox.warning(self, 'Unsupported drawing', 'Choose a DXF or PDF file.')
            return
        if kind == 'pdf':
            mapping = self.pdf_mapping(floor, {'floor': floor, 'filepath': path})
            if mapping is None:
                return
        else:
            mapping = {'floor': floor, 'filepath': path}
        self.drawings[floor] = {**mapping, 'kind': kind}
        self.refresh_floors()

    def pdf_mapping(self, floor, mapping):
        try:
            _pixmap, page_count = render_pdf_page(mapping['filepath'])
        except Exception as exc:
            QMessageBox.critical(self, 'Could not import PDF',
                                 f"{Path(mapping['filepath']).name} could not be rendered.\n\n{exc}")
            return None
        dialog = PdfUnderlayDialog(self, mapping, page_count=page_count)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.mapping(floor, mapping['filepath'])

    def edit_pdf(self, floor):
        mapping = self.pdf_mapping(floor, self.drawings[floor])
        if mapping is not None:
            self.drawings[floor] = {**mapping, 'kind': 'pdf'}
            self.refresh_floors()

    def clear_drawing(self, floor):
        self.drawings.pop(floor, None)
        self.refresh_floors()

    def configuration(self):
        config = JsonStore().data
        config['simulation'].update(mode='simple', motion_model='legacy')
        config['building']['floor_count'] = self.floor_count.value()
        config['building']['floor_height_m'] = self.floor_height.value()
        for floor in range(self.floor_count.value()):
            mapping = self.drawings.get(floor)
            if mapping is None:
                continue
            if mapping['kind'] == 'dxf':
                config['floor_dxf_files'].append({'floor': floor, 'filepath': mapping['filepath']})
            else:
                config['floor_pdf_underlays'].append(normalise_pdf_underlay(deepcopy(mapping)))
        return config
