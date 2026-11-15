"""Post-setup floor editing with consistent physical lift speeds."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, Slot

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout, QSpinBox, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView,
    QComboBox, QListWidget, QListWidgetItem, QScrollArea, QWidget, QCheckBox,
)
from ui_theme import polish_dialog


def set_level_height(config, height):
    """Return an atomic edit, retaining effective m/s rather than stale metadata."""
    if isinstance(height, bool):
        raise ValueError('Level height must be a positive finite number in metres.')
    try:
        height = float(height)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Level height must be a positive finite number in metres.') from None
    if not math.isfinite(height) or height <= 0:
        raise ValueError('Level height must be a positive finite number in metres.')
    result = deepcopy(config)
    building = result.setdefault('building', {})
    old_height = building.get('floor_height_m', 4.0)
    if old_height == height:
        return result
    for lift in result.get('lifts', []):
        # An incomplete editor draft has no effective runtime speed to preserve.
        if 'speed_floors_per_sec' not in lift:
            continue
        try:
            old = float(old_height)
            speed = float(lift['speed_floors_per_sec'])
            physical_speed = old * speed
            converted = physical_speed / height
            valid = (not isinstance(old_height, bool)
                     and not isinstance(lift['speed_floors_per_sec'], bool)
                     and all(math.isfinite(x) and x > 0 for x in (old, speed, physical_speed, converted)))
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ValueError('Correct the existing level height and lift speeds before changing level height.')
        lift['speed_floors_per_sec'] = converted
        lift['speed_m_per_sec'] = physical_speed
    building['floor_height_m'] = height
    return result


def minimum_floor_count(config):
    """Keep every floor referenced by the project; changing count deletes nothing."""
    floors=[0]
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                candidates=([item] if key in ('floor', 'lift_transfer_floor', 'from_floor', 'via_floor', 'force_via_floor')
                            else item if key in ('served_floors', 'to_floors', 'destination_side_lift_floors') and isinstance(item,list)
                            else list(item) if key=='floor_locations' and isinstance(item,dict) else [])
                for floor in candidates:
                    try:
                        if not isinstance(floor,bool):floors.append(int(floor))
                    except (ValueError,TypeError,OverflowError):pass
                visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(config)
    return max(floors)+1


class BuildingSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle('Building settings')
        self.config = deepcopy(config)
        self.result = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        note = QLabel('Level height is the vertical distance between adjacent floors and '
                      'applies to every level. Lift speeds in metres per second are kept; '
                      'travel times and vertical distances use the new height.')
        note.setWordWrap(True)
        note.setObjectName('dialogIntro')
        form = QFormLayout()
        minimum=minimum_floor_count(config)
        self.floor_count=QSpinBox()
        self.floor_count.setAccessibleName('Number of floors')
        try:count=int(config.get('building',{}).get('floor_count',minimum))
        except (ValueError,TypeError,OverflowError):count=minimum
        self._configured_floor_count=count
        self.floor_count.setRange(minimum,max(100,minimum,count))
        self.floor_count.setValue(max(minimum,count))
        self._initial_floor_count=self.floor_count.value()
        self.floor_count.setToolTip(f'Floors are numbered from 0. At least {minimum} floors are required by existing objects or drawings.')
        form.addRow('Number of floors',self.floor_count)
        self.level_height = QDoubleSpinBox()
        self.level_height.setDecimals(6)
        self.level_height.setRange(0.000001, 1000000.0)
        self.level_height.setSuffix(' m')
        self.level_height.setAccessibleName('Level height in metres')
        self.level_height.setToolTip(note.text())
        try:
            initial = float(config.get('building', {}).get('floor_height_m', 4.0))
        except (TypeError, ValueError, OverflowError):
            initial = 4.0
        self.level_height.setValue(initial if math.isfinite(initial) and initial > 0 else 4.0)
        form.addRow('Level height', self.level_height)
        layout.addLayout(form)
        note.setText('Floors start at 0. Changing level height preserves lift speed in m/s.')
        layout.addWidget(note)
        policy_form = QFormLayout()
        self.bed_lift_wait = QDoubleSpinBox()
        self.bed_lift_wait.setRange(0, 1000000)
        self.bed_lift_wait.setDecimals(2)
        self.bed_lift_wait.setSuffix(' min')
        self.bed_lift_wait.setAccessibleName('FM waiting limit before bed-lift fallback')
        self.bed_lift_wait.setToolTip('Consider bed lifts only when total predicted lift waiting exceeds this limit and arrival is earlier. No usable FM route also permits fallback.')
        self.bed_lift_wait.setValue(config.get('building', {}).get('bed_lift_fallback_wait_sec', 300) / 60)
        self._initial_bed_lift_wait = self.bed_lift_wait.value()
        policy_form.addRow('FM waiting limit before bed-lift fallback', self.bed_lift_wait)
        self.force_via_enabled = QCheckBox('Force every AMR journey via a floor')
        self.force_via_enabled.setAccessibleName('Force every AMR journey via a floor')
        self.force_via_enabled.setToolTip('Includes same-floor journeys, empty approaches, returns, charging and parking. '
            'The AMR must stop and exit on the selected floor. Multiple lifts and floor revisits are allowed.')
        self.force_via_floor = QComboBox()
        self.force_via_floor.setAccessibleName('Required floor for every AMR journey')
        self.force_via_floor.setToolTip('Final arrival uses the reachable suitable lift stop nearest the destination '
            'by permitted corridor distance, even when extra lift connections are needed. Stationary actions stay local.')
        self._initial_force_enabled = config.get('building', {}).get('force_via_floor_enabled', False)
        self._initial_force_floor = config.get('building', {}).get('force_via_floor')
        self.force_via_enabled.setChecked(self._initial_force_enabled is True)
        self._force_enabled_edited = False
        self.force_via_enabled.toggled.connect(self._mark_force_enabled_edited)
        self.force_via_floor.setEnabled(self.force_via_enabled.isChecked())
        self.force_via_enabled.toggled.connect(self.force_via_floor.setEnabled)
        policy_form.addRow(self.force_via_enabled)
        policy_form.addRow('Required floor', self.force_via_floor)
        saved_preference = config.get('building', {}).get('forced_floor_lift_preference', {})
        preference = saved_preference if isinstance(saved_preference, dict) else {}
        self._initial_preference_floor = preference.get('from_floor')
        self.lift_preference_mode = QComboBox()
        self.lift_preference_mode.setAccessibleName('Forced-floor lift preference')
        self.lift_preference_mode.addItem('Off', 'off')
        self.lift_preference_mode.addItem('Prefer selected lifts with fallback', 'prefer')
        self.lift_preference_mode.addItem('Selected lifts only', 'required')
        self.lift_preference_mode.setCurrentIndex(max(0, self.lift_preference_mode.findData(preference.get('mode'))))
        self.lift_preference_mode.setToolTip('Applies to rides into or out of the required floor. '
                                            'Applied route profiles take precedence.')
        self.lift_preference_floor = QComboBox()
        self.lift_preference_floor.setAccessibleName('Departure floor for forced-floor lift preference')
        self.lift_preference_lifts = QListWidget()
        self.lift_preference_lifts.setAccessibleName('Selected lifts for forced-floor journeys')
        self.lift_preference_lifts.setMaximumHeight(110)
        self.lift_preference_lifts.setToolTip('Select lifts for the rides into and out of the required floor.')
        known_ids = {lift['id'] for lift in config.get('lifts', []) if isinstance(lift.get('id'), str)}
        saved_ids = preference.get('lift_ids', [])
        checked_ids = {lift_id for lift_id in saved_ids if isinstance(lift_id, str)} if isinstance(saved_ids, list) else set()
        for lift_id in sorted(known_ids | checked_ids):
            item = QListWidgetItem(lift_id if lift_id in known_ids else f'{lift_id} (missing)')
            item.setData(Qt.UserRole, lift_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if lift_id in checked_ids else Qt.Unchecked)
            self.lift_preference_lifts.addItem(item)
        policy_form.addRow('Lift preference', self.lift_preference_mode)
        policy_form.addRow('Departure floor', self.lift_preference_floor)
        policy_form.addRow('Selected lifts', self.lift_preference_lifts)
        self.transfer_floor = QComboBox()
        self.transfer_floor.setAccessibleName('Transfer floor when a connection is needed')
        self.transfer_floor.setToolTip('A suitable direct lift bypasses this floor, even if busy. Explicit mandatory waypoints still apply.')
        self.destination_floors = QListWidget()
        self.destination_floors.setAccessibleName('Destination-side lift selection boarding floors')
        self.destination_floors.setMaximumHeight(110)
        self.destination_floors.setToolTip('On checked boarding floors, choose the suitable lift closest to the endpoint by permitted destination-floor corridor distance, then wait if busy.')
        self._initial_transfer = config.get('building', {}).get('lift_transfer_floor')
        self._initial_destination_floors = config.get('building', {}).get('destination_side_lift_floors', [])
        self._refresh_policy_floors(initial=True)
        self._initial_preference_controls = self._lift_preference_controls()
        self.floor_count.valueChanged.connect(lambda: self._refresh_policy_floors())
        policy_form.addRow('Transfer floor when a connection is needed', self.transfer_floor)
        policy_form.addRow('Destination-side lift selection\nBoarding floors', self.destination_floors)
        self._update_lift_policy_controls()
        self.force_via_enabled.toggled.connect(self._update_lift_policy_controls)
        self.lift_preference_mode.currentIndexChanged.connect(self._update_lift_policy_controls)
        layout.addLayout(policy_form)
        waypoint_note = QLabel('Mandatory floor waypoints apply to all AMR journeys, including empty '
            'approach, charging and idle return. A journey must stop on the via floor before '
            'continuing; it may use the same lift or change lifts. Journeys ending on the via '
            'floor finish there. Route profiles still restrict every leg.')
        waypoint_note.setWordWrap(True)
        layout.addWidget(QLabel('Mandatory floor waypoints'))
        layout.addWidget(waypoint_note)
        self.waypoint_rules = QTableWidget(0, 3)
        self.waypoint_rules.setHorizontalHeaderLabels(['From floor', 'Destination floors', 'Via floor'])
        self.waypoint_rules.setAccessibleName('Mandatory floor waypoint rules')
        self.waypoint_rules.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.waypoint_rules.setMinimumHeight(130)
        self.waypoint_rules.setToolTip('Use whole floor numbers. Separate destination floors with commas, for example 1, 2, 3, 4, 5.')
        self._initial_waypoint_rules = deepcopy(config.get('building', {}).get('mandatory_floor_waypoints', []))
        for rule in self._initial_waypoint_rules:
            self.add_waypoint_rule(rule)
        layout.addWidget(self.waypoint_rules)
        row = QHBoxLayout()
        add = QPushButton('Add waypoint rule')
        add.clicked.connect(lambda: self.add_waypoint_rule())
        remove = QPushButton('Remove selected rule')
        remove.clicked.connect(lambda: self.remove_waypoint_rule())
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.resize(760, 700)
        polish_dialog(self)

    @Slot()
    def _update_lift_policy_controls(self):
        normal = not self.force_via_enabled.isChecked()
        self.transfer_floor.setEnabled(normal)
        self.destination_floors.setEnabled(normal)
        self.lift_preference_mode.setEnabled(not normal)
        active = not normal and self.lift_preference_mode.currentData() != 'off'
        self.lift_preference_floor.setEnabled(active)
        self.lift_preference_lifts.setEnabled(active)

    def _lift_preference_controls(self):
        items = [self.lift_preference_lifts.item(i) for i in range(self.lift_preference_lifts.count())]
        return dict(mode=self.lift_preference_mode.currentData(),
                    from_floor=self.lift_preference_floor.currentData(),
                    lift_ids=[item.data(Qt.UserRole) for item in items if item.checkState() == Qt.Checked])

    @Slot(bool)
    def _mark_force_enabled_edited(self, _checked):
        self._force_enabled_edited = True

    def _refresh_policy_floors(self, initial=False):
        forced = self._initial_force_floor if initial else self.force_via_floor.currentData()
        departure = self._initial_preference_floor if initial else self.lift_preference_floor.currentData()
        transfer = self._initial_transfer if initial else self.transfer_floor.currentData()
        checked = self._initial_destination_floors if initial else [
            self.destination_floors.item(i).data(Qt.UserRole) for i in range(self.destination_floors.count())
            if self.destination_floors.item(i).checkState() == Qt.Checked]
        floors = set(range(self.floor_count.value()))
        floors.update(row['floor'] for row in self.config.get('locations', []) if type(row.get('floor')) is int)
        floors.update(row['floor'] for row in self.config.get('corridors', {}).get('nodes', [])
                      if type(row.get('floor')) is int)
        for lift in self.config.get('lifts', []):
            floors.update(lift.get('served_floors', []))
        self.transfer_floor.clear()
        self.transfer_floor.addItem('No required transfer floor', None)
        self.force_via_floor.clear()
        self.lift_preference_floor.clear()
        self.lift_preference_floor.addItem('Select departure floor', None)
        self.destination_floors.clear()
        for floor in sorted(floors):
            self.force_via_floor.addItem(f'Level {floor}', floor)
            self.lift_preference_floor.addItem(f'Level {floor}', floor)
            self.transfer_floor.addItem(f'Level {floor}', floor)
            item = QListWidgetItem(f'Level {floor}')
            item.setData(Qt.UserRole, floor)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if floor in checked else Qt.Unchecked)
            self.destination_floors.addItem(item)
        self.transfer_floor.setCurrentIndex(max(0, self.transfer_floor.findData(transfer)))
        if forced is None:
            forced = 2 if 2 in floors else min(floors, default=None)
        self.force_via_floor.setCurrentIndex(self.force_via_floor.findData(forced))
        self.lift_preference_floor.setCurrentIndex(max(0, self.lift_preference_floor.findData(departure)))

    def add_waypoint_rule(self, rule=None):
        if rule is None:
            destinations = list(range(1, self.floor_count.value()))
            rule = dict(from_floor=0, to_floors=destinations, via_floor=2 if 2 in destinations else 1)
        row = self.waypoint_rules.rowCount()
        self.waypoint_rules.insertRow(row)
        for column, value in enumerate((rule['from_floor'], ', '.join(map(str, rule['to_floors'])), rule['via_floor'])):
            self.waypoint_rules.setItem(row, column, QTableWidgetItem(str(value)))

    def remove_waypoint_rule(self):
        row = self.waypoint_rules.currentRow()
        if row >= 0:
            self.waypoint_rules.removeRow(row)

    def accept(self):
        try:
            # Saving an unchanged field must preserve imported precision and metadata.
            initial = self.config.get('building', {}).get('floor_height_m', 4.0)
            if isinstance(initial, (int, float)) and math.isfinite(initial) and initial > 0 \
                    and self.level_height.value() == round(initial, self.level_height.decimals()):
                self.result = deepcopy(self.config)
            else:
                self.result = set_level_height(self.config, self.level_height.value())
            if (self.floor_count.value()!=self._initial_floor_count or
                'floor_count' in self.config.get('building',{}) and self.floor_count.value()!=self._configured_floor_count):
                self.result.setdefault('building',{})['floor_count']=self.floor_count.value()
            rules = []
            for row in range(self.waypoint_rules.rowCount()):
                values = [(self.waypoint_rules.item(row, column).text().strip()
                           if self.waypoint_rules.item(row, column) else '') for column in range(3)]
                try:
                    rule = dict(from_floor=int(values[0]),
                                to_floors=[int(v.strip()) for v in values[1].split(',')],
                                via_floor=int(values[2]))
                except ValueError:
                    raise ValueError(f'Waypoint rule {row + 1}: use whole floor numbers and comma-separated destination floors.') from None
                # Retain extra metadata on unchanged imported rules.
                if row < len(self._initial_waypoint_rules):
                    original = self._initial_waypoint_rules[row]
                    if all(original.get(key) == value for key, value in rule.items()):
                        rule = deepcopy(original)
                rules.append(rule)
            if rules != self._initial_waypoint_rules:
                self.result.setdefault('building', {})['mandatory_floor_waypoints'] = rules
            force_enabled = self.force_via_enabled.isChecked()
            forced_floor = self.force_via_floor.currentData()
            if self._force_enabled_edited:
                self.result.setdefault('building', {})['force_via_floor_enabled'] = force_enabled
            if (force_enabled and forced_floor != self._initial_force_floor
                    or self._initial_force_floor is not None and forced_floor != self._initial_force_floor):
                self.result.setdefault('building', {})['force_via_floor'] = forced_floor
            preference = self._lift_preference_controls()
            if preference != self._initial_preference_controls:
                self.result.setdefault('building', {})['forced_floor_lift_preference'] = preference
            transfer = self.transfer_floor.currentData()
            floors = [self.destination_floors.item(i).data(Qt.UserRole) for i in range(self.destination_floors.count())
                      if self.destination_floors.item(i).checkState() == Qt.Checked]
            if transfer != self._initial_transfer:
                if transfer is None:
                    self.result.setdefault('building', {}).pop('lift_transfer_floor', None)
                else:
                    self.result.setdefault('building', {})['lift_transfer_floor'] = transfer
            if floors != sorted(self._initial_destination_floors):
                self.result.setdefault('building', {})['destination_side_lift_floors'] = floors
            from amr_routing_inputs import waypoint_input_findings, lift_policy_input_findings
            if self.bed_lift_wait.value() != self._initial_bed_lift_wait:
                self.result.setdefault('building', {})['bed_lift_fallback_wait_sec'] = self.bed_lift_wait.value() * 60
            findings = list(waypoint_input_findings(self.result)) + list(lift_policy_input_findings(self.result))
            if findings:
                raise ValueError(findings[0][1])
        except ValueError as error:
            self.result = None
            QMessageBox.warning(self, 'Building settings', str(error))
            return
        super().accept()
