"""Independent object snap toggles in the bottom-right drawing status bar."""
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget


class CadSnapControls(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setObjectName('cadSnapControls')
        self.setAccessibleName('Object snap targets')
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(3)
        self.master = QToolButton(self)
        self.master.setText('Object snap')
        self.master.setAccessibleName('Enable object snapping')
        self.master.setToolTip('Enable object snapping using any combination of the adjacent targets. Disabling keeps your chosen targets.')
        self.master.setCheckable(True)
        self.master.setChecked(editor.object_snap_check.isChecked())
        self.master.toggled.connect(editor.object_snap_check.setChecked)
        editor.object_snap_check.toggled.connect(self.master.setChecked)
        editor.object_snap_check.toggled.connect(self.sync_enabled)
        row.addWidget(self.master)
        self.buttons = {}
        for mode, title, tooltip in (
            ('nearest', 'Near', 'Nearest point or corridor edge; used when no enabled specific target is nearby.'),
            ('endpoints', 'End', 'Endpoints and graph points on the current floor.'),
            ('midpoints', 'Mid', 'Corridor midpoints.'),
            ('perpendicular', 'Perp', 'Perpendicular projection from the current route end or transform anchor onto a finite corridor.'),
            ('intersections', 'Cross', 'Corridor intersections. Drawing connects the crossing as one junction; transform picking only uses it as a reference.'),
        ):
            button = QToolButton(self)
            button.setText(title)
            button.setCheckable(True)
            button.setAccessibleName(f'{mode.capitalize()} object snap')
            button.setToolTip(tooltip + ' Can be enabled together with other targets.')
            button.toggled.connect(self.targets_changed)
            row.addWidget(button)
            self.buttons[mode] = button
        self.custom_index = editor.object_snap_mode.count()
        editor.object_snap_mode.addItem('Combined targets', ())
        editor.object_snap_mode.currentIndexChanged.connect(self.preset_changed)
        self.preset_changed()

    def preset_changed(self, *_):
        from corridor_editing import object_snap_modes
        modes = object_snap_modes(self.editor.object_snap_mode.currentData())
        for mode, button in self.buttons.items():
            button.blockSignals(True)
            button.setChecked(mode in modes)
            button.blockSignals(False)
        self.sync_enabled()

    def targets_changed(self, *_):
        combo = self.editor.object_snap_mode
        modes = tuple(mode for mode, button in self.buttons.items() if button.isChecked())
        combo.blockSignals(True)
        if len(modes) == 1:
            combo.setCurrentIndex(combo.findData(modes[0]))
        else:
            combo.setItemData(self.custom_index, modes)
            combo.setItemText(self.custom_index, 'Combined targets' if modes else 'No attraction targets')
            combo.setCurrentIndex(self.custom_index)
        combo.blockSignals(False)
        self.editor.on_snap_settings_changed()

    def sync_enabled(self, *_):
        for button in self.buttons.values():
            button.setEnabled(self.editor.object_snap_check.isChecked())

    def sync_workspace(self):
        self.setVisible(self.editor.workspace.stage == 'layout')
        self.setEnabled(not self.editor.project_editing_locked())
