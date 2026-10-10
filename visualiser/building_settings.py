"""Post-setup floor editing with consistent physical lift speeds."""
from copy import deepcopy
import math

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout, QSpinBox,
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
                candidates=([item] if key=='floor' else item if key=='served_floors' and isinstance(item,list)
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
        layout = QVBoxLayout(self)
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
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(440, 240)
        polish_dialog(self)

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
        except ValueError as error:
            QMessageBox.warning(self, 'Building settings', str(error))
            return
        super().accept()
