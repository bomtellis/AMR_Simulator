"""Optional project-layer panel: definitions, selection assignment and locks."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QScrollArea, QDoubleSpinBox, QFormLayout
from visualiser.dxf_layers import LayerDock
from visualiser.model_layers import definitions, members, current_layer, DEFAULT, PATTERNS


class ModelLayerPanel:
    def __init__(self, editor):
        self.editor = editor
        self.open_requested = False
        self.loading = False
        self.dock = LayerDock('Model layers',editor)
        self.dock.owner = self
        self.dock.setObjectName('ModelLayers')
        self.body = QWidget(self.dock)
        layout = QVBoxLayout(self.body)
        layout.addWidget(QLabel('Project layer',self.body))
        self.choice = QComboBox(self.body)
        self.choice.setAccessibleName('Model layer')
        layout.addWidget(self.choice)
        self.current = QLabel(self.body)
        self.current.setWordWrap(True)
        layout.addWidget(self.current)
        self.use_current = QPushButton('Use for new drawing', self.body)
        layout.addWidget(self.use_current)
        self.visible = QCheckBox('Visible',self.body)
        self.locked = QCheckBox('Locked against editing',self.body)
        layout.addWidget(self.visible)
        layout.addWidget(self.locked)
        self.assign_button = QPushButton('Assign selected objects',self.body)
        layout.addWidget(self.assign_button)
        self.style_toggle = QPushButton('Line style…', self.body)
        self.style_toggle.setCheckable(True)
        layout.addWidget(self.style_toggle)
        self.style_body = QWidget(self.body)
        form = QFormLayout(self.style_body)
        self.colour = QLineEdit(self.style_body)
        self.colour.setPlaceholderText('Theme colour, or #RRGGBB')
        self.colour.setAccessibleName('Layer line colour')
        self.pattern = QComboBox(self.style_body)
        self.pattern.addItems(PATTERNS)
        self.pattern.setAccessibleName('Layer line pattern')
        self.width = QDoubleSpinBox(self.style_body)
        self.width.setRange(.5, 6)
        self.width.setSingleStep(.5)
        self.width.setSuffix(' px')
        self.width.setAccessibleName('Layer line width in screen pixels')
        form.addRow('Colour', self.colour)
        form.addRow('Pattern', self.pattern)
        form.addRow('Width', self.width)
        self.apply_style = QPushButton('Apply line style', self.style_body)
        self.reset_style = QPushButton('Restore theme style', self.style_body)
        form.addRow(self.apply_style)
        form.addRow(self.reset_style)
        hint = QLabel('Applies to corridors and location outlines. Blank colour follows the theme. '
                      'Custom colours stay fixed; choose a visible colour and a distinct pattern. '
                      'Selection and route-profile overlays keep their own styles.', self.style_body)
        hint.setWordWrap(True)
        form.addRow(hint)
        layout.addWidget(self.style_body)
        self.style_body.hide()
        self.style_toggle.toggled.connect(self.style_body.setVisible)
        self.apply_style.clicked.connect(self.save_style)
        self.reset_style.clicked.connect(lambda: self.editor.style_model_layer(self.choice.currentText(), None))
        row = QHBoxLayout()
        self.name = QLineEdit(self.body)
        self.name.setPlaceholderText('New layer name')
        self.name.setAccessibleName('New model layer name')
        row.addWidget(self.name)
        add = QPushButton('Add layer',self.body)
        row.addWidget(add)
        layout.addLayout(row)
        self.rename_button = QPushButton('Rename layer',self.body)
        self.rename_button.setToolTip('Rename the selected layer using the name entered above.')
        layout.addWidget(self.rename_button)
        layout.addWidget(QLabel('Move contents to',self.body))
        self.destination = QComboBox(self.body)
        self.destination.setAccessibleName('Destination for removed layer contents')
        layout.addWidget(self.destination)
        self.removal_preview = QLabel(self.body)
        self.removal_preview.setWordWrap(True)
        layout.addWidget(self.removal_preview)
        self.remove_button = QPushButton('Move contents and remove layer',self.body)
        layout.addWidget(self.remove_button)
        self.note = QLabel(self.body)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        explanation = QLabel('Layers control display and editing only. Clean/dirty/shared access stays in route profiles. New drawing uses the current layer; copies and split corridors retain their source layers. Undo restores layer edits too.',self.body)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addStretch(1)
        scroll = QScrollArea(self.dock)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)
        self.dock.setWidget(scroll)
        editor.addDockWidget(Qt.RightDockWidgetArea,self.dock)
        self.dock.hide()
        self.choice.currentIndexChanged.connect(self.refresh)
        self.visible.toggled.connect(self.apply_options)
        self.locked.toggled.connect(self.apply_options)
        self.assign_button.clicked.connect(self.assign)
        self.use_current.clicked.connect(lambda: self.editor.set_current_model_layer(self.choice.currentText()))
        add.clicked.connect(self.add)
        self.rename_button.clicked.connect(self.rename)
        self.remove_button.clicked.connect(self.remove)
        self.destination.currentTextChanged.connect(self.refresh_removal)
        self.name.returnPressed.connect(self.add)
        self.refresh()

    def refresh(self, *_):
        if self.loading:
            return
        self.loading = True
        try:
            layers = definitions(self.editor.store.data)
            current = self.choice.currentText()
            names = list(layers)
            if [self.choice.itemText(i) for i in range(self.choice.count())] != names:
                self.choice.clear()
                self.choice.addItems(names)
                if current in layers:
                    self.choice.setCurrentText(current)
            options = layers[self.choice.currentText()]
            style = options.get('style', dict(colour=None,pattern='Solid',width_px=1.5))
            self.colour.setText(style['colour'] or '')
            self.pattern.setCurrentText(style['pattern'])
            self.width.setValue(style['width_px'])
            self.current.setText(f'Current drawing layer: {current_layer(self.editor.store.data)}')
            self.use_current.setEnabled(options['visible'] and not options['locked'])
            destinations = [n for n in names if n != self.choice.currentText() and not layers[n]['locked']]
            destination = self.destination.currentText()
            self.destination.clear()
            self.destination.addItems(destinations)
            if destination in destinations:
                self.destination.setCurrentText(destination)
            editable = self.choice.currentText() != DEFAULT and not options['locked']
            self.rename_button.setEnabled(editable)
            self.remove_button.setEnabled(editable and bool(destinations))
            self.visible.setChecked(options['visible'])
            self.locked.setChecked(options['locked'])
            count = len(self.editor.selected_point_names) + len(self.editor.selected_edge_keys)
            self.note.setText(f'{count} selected points/corridors. Assign changes their layer; unlock their current layer first if needed.')
            self.assign_button.setEnabled(count > 0)
        finally:
            self.loading = False
        self.sync_workspace()
        self.refresh_removal()

    def refresh_removal(self, *_):
        if self.loading:
            return
        source, target = self.choice.currentText(), self.destination.currentText()
        if source == DEFAULT:
            self.removal_preview.setText('Default is retained and cannot be renamed or removed.')
            return
        count = len(members(self.editor.store.data,source))
        noun = 'record' if count == 1 else 'records'
        self.removal_preview.setText(f'{count} object {noun} will move from {source} to {target or "an unlocked layer"}. '
                                    'No objects are deleted. Destination visibility applies; Undo restores the original layer.')

    def rename(self):
        name = self.name.text().strip()
        if self.editor.reorganize_model_layer(self.choice.currentText(),name):
            self.choice.setCurrentText(name)
            self.name.clear()

    def remove(self):
        target = self.destination.currentText()
        if self.editor.reorganize_model_layer(self.choice.currentText(),target,remove=True):
            self.choice.setCurrentText(target)

    def apply_options(self, *_):
        if not self.loading:
            self.editor.update_model_layer(self.choice.currentText(),visible=self.visible.isChecked(),locked=self.locked.isChecked())
            self.refresh()

    def save_style(self):
        self.editor.style_model_layer(self.choice.currentText(), dict(
            colour=self.colour.text().strip() or None,
            pattern=self.pattern.currentText(),width_px=self.width.value()))

    def assign(self):
        self.editor.assign_model_layer(self.choice.currentText())
        self.refresh()

    def add(self):
        name = self.name.text().strip()
        if not name or name in definitions(self.editor.store.data):
            self.note.setText('Enter a new, nonblank layer name.')
            return
        if self.editor.update_model_layer(name):
            self.choice.setCurrentText(name)
            self.name.clear()

    def show(self):
        self.open_requested = True
        self.refresh()
        self.dock.raise_()
        self.editor.set_status('Model layers: select objects to assign, hide or lock their layer.')

    def sync_workspace(self):
        workspace = self.editor.workspace
        self.dock.setVisible(self.open_requested and workspace.stage == 'layout' and not workspace._canvas_focus)
        self.body.setEnabled(not self.editor.project_editing_locked())
