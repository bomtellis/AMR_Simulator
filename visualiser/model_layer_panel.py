"""Optional project-layer panel: definitions, selection assignment and locks."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox
from visualiser.dxf_layers import LayerDock
from visualiser.model_layers import definitions


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
        self.visible = QCheckBox('Visible',self.body)
        self.locked = QCheckBox('Locked against editing',self.body)
        layout.addWidget(self.visible)
        layout.addWidget(self.locked)
        self.assign_button = QPushButton('Assign selected objects',self.body)
        layout.addWidget(self.assign_button)
        row = QHBoxLayout()
        self.name = QLineEdit(self.body)
        self.name.setPlaceholderText('New layer name')
        self.name.setAccessibleName('New model layer name')
        row.addWidget(self.name)
        add = QPushButton('Add layer',self.body)
        row.addWidget(add)
        layout.addLayout(row)
        self.note = QLabel(self.body)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        explanation = QLabel('Layers control display and editing only. Clean/dirty/shared access stays in route profiles. New objects start on Default; assign them here. Undo restores layer edits too.',self.body)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addStretch(1)
        self.dock.setWidget(self.body)
        editor.addDockWidget(Qt.RightDockWidgetArea,self.dock)
        self.dock.hide()
        self.choice.currentIndexChanged.connect(self.refresh)
        self.visible.toggled.connect(self.apply_options)
        self.locked.toggled.connect(self.apply_options)
        self.assign_button.clicked.connect(self.assign)
        add.clicked.connect(self.add)
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
            self.visible.setChecked(options['visible'])
            self.locked.setChecked(options['locked'])
            count = len(self.editor.selected_point_names) + len(self.editor.selected_edge_keys)
            self.note.setText(f'{count} selected points/corridors. Assign changes their layer; unlock their current layer first if needed.')
            self.assign_button.setEnabled(count > 0)
        finally:
            self.loading = False
        self.sync_workspace()

    def apply_options(self, *_):
        if not self.loading:
            self.editor.update_model_layer(self.choice.currentText(),visible=self.visible.isChecked(),locked=self.locked.isChecked())
            self.refresh()

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
