"""Explicit permission edits for existing robot movement settings."""
from copy import deepcopy

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QLabel, QPushButton, QVBoxLayout, QWidget)

from amr_movement_inputs import (migrate_movement_inputs, movement_preset,
                                  resolve_movement_inputs)


class MovementCapabilities(QWidget):
    def __init__(self, movement, parent=None):
        super().__init__(parent)
        self.original = deepcopy(movement)
        self.controls, self.presets, self.apply_buttons = {}, {}, {}
        self.initial = {}
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        if movement is None:
            self.summary.setText('No detailed movement settings are configured. '
                'Import explicit empty and loaded engineering parameters before editing capabilities. '
                'No speeds, accelerations or radii are inferred here.')
            layout.addStretch(1)
            return
        try:
            resolved = resolve_movement_inputs(movement)
        except ValueError as exc:
            self.summary.setText(f'Existing detailed settings need correction: {exc}\n'
                'They are preserved when saving other robot details.')
            layout.addStretch(1)
            return
        self.summary.setText('Presets change pivot and lateral permissions for one load state. '
            'Reverse permission is independent. Numerical settings and the other state are preserved. '
            'Applying a preset does not establish that a physical robot supports these movements.\n'
            'Saving a changed permission writes explicit version 2 permissions for both states; '
            'previously omitted reverse permissions retain their existing enabled behaviour.')
        effective = resolved['movement']
        for state in ('empty', 'loaded'):
            box = QGroupBox(state.title())
            form = QFormLayout(box)
            preset = QComboBox()
            preset.addItem('Choose a capability preset', None)
            for label, key in (('Steering', 'steering'), ('Pivoting', 'pivoting'),
                               ('Omnidirectional', 'omnidirectional')):
                preset.addItem(label, key)
            button = QPushButton('Apply preset to this state')
            button.clicked.connect(lambda checked=False, state=state: self.apply_preset(state))
            form.addRow('Preset', preset)
            form.addRow(button)
            self.presets[state], self.apply_buttons[state] = preset, button
            self.controls[state] = {}
            for key, label in (('reverse_allowed', 'Allow reversing'),
                               ('pivot_allowed', 'Allow stationary pivots'),
                               ('lateral_allowed', 'Allow lateral translation')):
                control = QCheckBox(label)
                control.setChecked(effective[state][key])
                self.controls[state][key] = control
                self.initial[state, key] = control.isChecked()
                form.addRow(control)
            layout.addWidget(box)
        note = QLabel('Curved steering can remain permitted when stationary pivots are disabled. '
            'Available route searches and physical clearance still constrain every manoeuvre.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def apply_preset(self, state):
        name = self.presets[state].currentData()
        if name is None:
            return
        for key, value in movement_preset(name).items():
            self.controls[state][key].setChecked(value)

    def changed_movement(self):
        changes = {(state, key): control.isChecked()
                   for state, controls in self.controls.items()
                   for key, control in controls.items()
                   if control.isChecked() != self.initial[state, key]}
        if not changes:
            return None
        result = migrate_movement_inputs(self.original)['movement']
        for (state, key), value in changes.items():
            result[state][key] = value
        # Enabling a capability can require an explicit speed that an older
        # disabled state omitted. Reject that edit instead of inventing a value.
        resolve_movement_inputs(result)
        return result
