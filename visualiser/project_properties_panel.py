"""Contextual layout fields with an explicit, atomic apply and bulk preview."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton, QScrollArea
from layout_properties import records, specs, fingerprint, apply_properties
from configuration_properties import SECTIONS, REQUIRED, choices
from property_choices import PropertyChoices


class ProjectPropertiesPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.target = None
        self.expected = None
        self.fields = {}
        self.initial = {}
        self.labels = {}
        self.pending = False
        self.loading = False
        root = QVBoxLayout(self)
        self.title = QLabel('Layout properties')
        self.title.setWordWrap(True)
        root.addWidget(self.title)
        self.note = QLabel('Select an object in the tree or layout.')
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        self.spaces_summary = QLabel()
        self.spaces_summary.setWordWrap(True)
        self.spaces_summary.setAccessibleName('Location inventory space summary')
        self.spaces_button = QPushButton('Create / edit spaces…')
        self.spaces_button.setAccessibleName('Create or edit location inventory spaces')
        self.spaces_button.setToolTip('Create AMR parking and charging bays or payload spaces for this location. Alternative: right-click the location → Inventory spaces.')
        self.spaces_button.clicked.connect(self.edit_spaces)
        root.addWidget(self.spaces_summary)
        root.addWidget(self.spaces_button)
        self.spaces_summary.hide(); self.spaces_button.hide()
        self.content = QWidget()
        self.form = QFormLayout(self.content)
        self.form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)
        self.preview = QLabel('')
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton('Apply changes')
        self.apply_button.clicked.connect(self.apply)
        self.discard_button = QPushButton('Discard draft')
        self.discard_button.clicked.connect(self.discard)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.discard_button)
        root.addLayout(buttons)
        self.setMinimumWidth(260)
        self.setMaximumWidth(410)

    def selection(self):
        editor = self.editor
        if getattr(editor, 'workspace', None) is not None and editor.workspace.stage == 'configuration':
            return editor.workspace.selected_configuration
        names = set(editor.selected_point_names)
        if editor.selected_point_name:
            names.add(editor.selected_point_name)
        if names and not editor.selected_edge_keys:
            return 'points', tuple(sorted(names))
        if editor.selected_edge_keys and not names:
            edges = editor.store.data.get('corridors', {}).get('edges', [])
            chosen = tuple(i for i, e in enumerate(edges) if tuple(sorted((e['from'], e['to']))) in editor.selected_edge_keys)
            explicit = getattr(editor.workspace, 'selected_edge_record', None)
            return 'edges', (explicit,) if explicit in chosen else chosen
        return None

    def refresh(self):
        if self.loading:
            return
        target = self.selection()
        current = fingerprint(self.editor.store.data)
        if self.pending:
            self.sync_spaces_control()
            if current != self.expected:
                self.note.setText('The project changed. Discard this draft and reload before applying.')
            elif target != self.target:
                self.note.setText('Draft retained for the object(s) below. Apply or discard it to edit the new selection.')
            return
        if target == self.target and current == self.expected:
            self.sync_spaces_control()
            return
        self.loading = True
        try:
            self.target, self.expected = target, current
            self.fields, self.initial, self.labels = {}, {}, {}
            while self.form.rowCount():
                self.form.removeRow(0)
            self.title.setText('Layout properties')
            self.preview.clear()
            self.apply_button.setEnabled(False)
            self.discard_button.setEnabled(False)
            if target is None:
                self.note.setText('Select one object, corridor records, or matching nodes for a bulk edit.')
                return
            rows = records(self.editor.store.data, target)
            if target[0] in SECTIONS:
                section_title, identity = SECTIONS[target[0]]
                labels = [f"{section_title}: {rows[0][1].get(identity) if identity else target[1][0]}"]
            else:
                labels = list(target[1]) if target[0] == 'points' else [f"{r['from']} → {r['to']} (record {i + 1})" for i, (_, r) in zip(target[1], rows)]
            self.title.setText('\n'.join(str(s) for s in labels[:3]) +
                               (f'\n… and {len(labels) - 3} more objects' if len(labels) > 3 else ''))
            self.title.setToolTip('\n'.join(str(s) for s in labels))
            self.note.setText('Names and floors are read-only here. Blank optional values use the existing defaults. Only changed fields will be applied.')
            if target[0] == 'route_profiles':
                self.note.setText('Empty lists mean unrestricted. Edges are directional. Include shared sections in every permitted profile. Task allowances extend these lists; return profiles are explicit. Empty approach, charging and idle-return journeys are unrestricted by profiles.')
            elif target[0] in SECTIONS:
                self.note.setText('Identity and unshown settings are preserved. Only changed fields apply. Use the existing full editor for nested slots, schedules and other options.')
            for key, label, kind in specs(self.editor.store.data, target):
                # An explicit JSON null is not the same as an absent override
                # (for example null wash duration means zero, absent means 300).
                values = [(key in r, r.get(key)) for _, r in rows]
                mixed = any(value != values[0] for value in values[1:])
                present, value = values[0]
                if kind in {'nodes', 'edges', 'lifts', 'orientations'}:
                    widget = PropertyChoices(self.editor.store.data, kind, value)
                    widget.changed.connect(self.changed)
                elif kind in {'bool', 'people', 'location', 'payload', 'profile'}:
                    widget = QComboBox()
                    if mixed:
                        widget.addItem('Mixed — leave unchanged', '__mixed__')
                    widget.addItem('Use default / unset', None)
                    if key in REQUIRED.get(target[0], set()):
                        widget.setItemText(widget.count() - 1, 'Choose a value')
                        widget.model().item(widget.count() - 1).setEnabled(False)
                    options = [('Yes', True), ('No', False)] if kind == 'bool' else (
                        [('No routine occupancy', 'none'), ('Staff', 'staff'), ('Public', 'public'), ('Staff and public', 'both')]
                        if kind == 'people' else choices(self.editor.store.data, kind))
                    for text, data in options:
                        widget.addItem(text, data)
                    if present and value is None and not mixed:
                        widget.addItem('Existing null — unchanged', '__null__')
                        index = widget.count() - 1
                    else:
                        index = 0 if mixed else widget.findData(value)
                    if index < 0:
                        widget.addItem((str(value) if value != '' else 'Blank') + ' (existing value)', value)
                        index = widget.count() - 1
                    widget.setCurrentIndex(index)
                    widget.currentIndexChanged.connect(self.changed)
                else:
                    widget = QLineEdit('' if mixed or not present else ('null' if value is None else str(value)))
                    placeholder = ('Unlimited (default)' if key == 'max_concurrency' else
                                   '300 seconds (default)' if key == 'wash_cycle_duration_sec' else
                                   'Use default / geometric length')
                    widget.setPlaceholderText('Mixed — leave unchanged' if mixed else ('Required' if kind == 'coordinate' else placeholder))
                    widget.textChanged.connect(self.changed)
                widget.setAccessibleName(label)
                self.fields[key] = widget
                self.labels[key] = label
                self.initial[key] = self.value(widget)
                if kind in {'positive', 'nonnegative', 'integer', 'percent'}:
                    line = QHBoxLayout()
                    line.addWidget(widget)
                    default_button = QPushButton('Default')
                    default_button.setToolTip('Remove this explicit override from all selected records.')
                    if key in REQUIRED.get(target[0], set()):
                        default_button.setEnabled(False)
                        default_button.setToolTip('This property requires an explicit value.')
                    default_button.clicked.connect(lambda _checked=False, field=widget: field.setText('default'))
                    line.addWidget(default_button)
                    self.form.addRow(label, line)
                else:
                    self.form.addRow(label, widget)
                building = self.editor.store.data.get('building', {})
                hints = {'width_m': f"Unset: building corridor width ({building.get('default_corridor_width_m', 2.4)} m). Door restrictions may be narrower.",
                         'door_clear_width_m': f"Unset: building door opening ({building.get('default_door_clear_width_m', .9)} m). Applies only when the node is a door.",
                         'distance_m': 'Unset: endpoint geometry. Zero is an explicit zero-length override; it does not mean automatic.',
                         'bidirectional': 'Unset: two-way travel. This changes this record only; a separate reverse record may still permit returning.',
                         'max_concurrency': 'Maximum AMRs served here at the same time, including wash cycles. 1 serves one AMR at a time. Unset: effectively unlimited service capacity.',
                         'wash_cycle_duration_sec': 'Unset: 300 seconds in the simulator. Zero explicitly disables the wash delay.',
                         'wash_location': 'Unset: wash at the task drop-off after delivery. The drop-off wash rule wins if both endpoints require washing.',
                         'has_door': 'Unset: no door restriction.', 'wash_cycle_required': 'Unset: no required wash cycle.'}
                widget.setToolTip((label + '. Default removes the explicit value; simulator defaults then apply.') if target[0] in SECTIONS else hints.get(key, label))
            profiles = self.editor.store.data.get('route_profiles', {})
            if profiles:
                hint = QLabel('Clean / dirty / shared access is defined by Route profiles in Configuration. Changing people occupancy does not change those profiles.')
                hint.setWordWrap(True)
                self.form.addRow(hint)
        except (ValueError, KeyError, TypeError) as exc:
            self.note.setText(str(exc))
        finally:
            self.loading = False
            self.sync_spaces_control()

    def sync_spaces_control(self):
        location = None
        if self.target and self.target[0] == 'points' and len(self.target[1]) == 1:
            try:
                rows = records(self.editor.store.data, self.target)
                if rows[0][0] == 'location': location = rows[0][1]
            except (ValueError, KeyError, TypeError): pass
        visible = location is not None
        self.spaces_button.setVisible(visible); self.spaces_summary.setVisible(visible)
        self.spaces_button.setEnabled(visible and not self.pending and not self.editor.project_editing_locked())
        if location is not None:
            from amr_inventory_inputs import inventory_space_is_amr
            spaces = location.get('inventory_spaces', []) or []
            bays = [space for space in spaces if inventory_space_is_amr(space)]
            chargers = sum(bool(space.get('has_charger')) for space in bays)
            self.spaces_summary.setText(f'{len(spaces)} spaces · {len(bays)} AMR bays · {chargers} chargers' if spaces else
                                       'No spaces yet. Create AMR bays or payload spaces here.')
            if self.pending:
                self.spaces_summary.setText(self.spaces_summary.text()+'\nApply or discard the property draft before editing spaces.')

    def edit_spaces(self):
        self.sync_spaces_control()
        if self.spaces_button.isEnabled():
            self.editor.edit_location_spaces(self.target[1][0])

    @staticmethod
    def value(widget):
        if isinstance(widget, PropertyChoices):
            return widget.value()
        return widget.currentData() if isinstance(widget, QComboBox) else widget.text().strip()

    def changes(self):
        result = {}
        for key, widget in self.fields.items():
            value = self.value(widget)
            if value != self.initial[key] and value != '__mixed__':
                result[key] = None if value == '' or (isinstance(value, str) and value.lower() == 'default' and isinstance(widget, QLineEdit) and key not in {'x', 'y'}) else value
        return result

    def changed(self, *_):
        if self.loading:
            return
        changes = self.changes()
        self.pending = bool(changes)
        self.sync_spaces_control()
        self.apply_button.setEnabled(self.pending)
        self.discard_button.setEnabled(self.pending)
        def describe(value):
            if isinstance(value, list):
                return f'{len(value)} selected' if value else 'empty list'
            return str(value) if value is not None else 'default'
        lines = [f"{self.labels[key]}: {describe(self.initial[key])} → {describe(value)}" for key, value in changes.items()]
        self.preview.setText(f'{len(self.target[1])} object(s) will change.\n' + '\n'.join(lines) if changes else '')
        self.editor._update_unsaved_indicator()
        if not self.pending:
            self.expected = None
            self.refresh()

    def apply(self):
        if not self.pending:
            return True
        if self.editor.project_editing_locked():
            self.note.setText('Project editing is locked while simulation runs. Stop the run or wait for it to finish.')
            return False
        if self.editor._history_busy():
            self.note.setText('Finish the active editor or drag before applying these properties.')
            return False
        try:
            updated = apply_properties(self.editor.store.data, self.target, self.changes(), self.expected)
            self.pending = False
            self.editor.apply_layout_properties(updated)
            self.expected = None
            self.refresh()
            self.editor._update_unsaved_indicator()
            return True
        except (ValueError, KeyError, TypeError) as exc:
            self.note.setText(str(exc))
            if self.target[0] in SECTIONS:
                self.editor.workspace.configuration()
            else:
                self.editor.workspace.show_page('layout', self.editor.canvas)
            return False

    def recovery_config(self):
        if self.pending:
            return apply_properties(self.editor.store.data, self.target, self.changes(), self.expected)
        return self.editor.store.data

    def discard(self):
        self.pending = False
        self.expected = None
        self.refresh()
        self.editor._update_unsaved_indicator()

    def reset(self):
        self.pending = False
        self.target = None
        self.expected = None
