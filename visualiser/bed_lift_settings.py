"""Native controls for bed-lift AMR access, shared by lift editing paths."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QFormLayout, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QPushButton, QHBoxLayout)
from amr_bed_lifts import window_intervals


class BedLiftSettings(QGroupBox):
    def __init__(self, lift, parent=None):
        super().__init__('Lift use and AMR access', parent)
        self.original = lift
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem('FM lift — preferred', 'fm')
        self.mode.addItem('Bed lift — AMR fallback', 'bed_fallback')
        self.mode.setAccessibleName('Lift use')
        self.mode.setCurrentIndex(max(0, self.mode.findData(lift.get('usage_mode', 'fm'))))
        form.addRow('Lift use', self.mode)
        layout.addLayout(form)
        self.note = QLabel('FM lifts are preferred. Bed lifts are considered only above the FM waiting '
            'limit in Building settings, or when no usable FM route exists. The whole lift booking '
            'must fit within an access window. Empty windows mean no AMR access. Bed journeys are not simulated.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.all_day = QCheckBox('Allow AMR fallback all day')
        windows = lift.get('amr_access_windows', [])
        self.all_day.setChecked(windows == [{'start': '00:00', 'end': '24:00'}])
        layout.addWidget(self.all_day)
        self.windows = QTableWidget(0, 2)
        self.windows.setHorizontalHeaderLabels(['Start (HH:MM)', 'End (HH:MM)'])
        self.windows.setAccessibleName('Daily AMR access windows')
        self.windows.setToolTip('Simulation clock times, repeated daily. End before start crosses midnight. 24:00 is an allowed end time.')
        self.windows.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.windows.setMaximumHeight(135)
        self.windows.setMinimumHeight(80)
        for window in windows:
            self.add_window(window)
        layout.addWidget(self.windows)
        row = QHBoxLayout()
        self.add_button = QPushButton('Add access window')
        self.remove_button = QPushButton('Remove selected window')
        self.add_button.clicked.connect(lambda: self.add_window())
        self.remove_button.clicked.connect(self.remove_window)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        row.addStretch()
        layout.addLayout(row)
        self.mode.currentIndexChanged.connect(self.update_enabled)
        self.all_day.toggled.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self, *_):
        bed = self.mode.currentData() == 'bed_fallback'
        self.all_day.setEnabled(bed)
        for widget in (self.windows, self.add_button, self.remove_button):
            widget.setEnabled(bed and not self.all_day.isChecked())

    def add_window(self, window=None):
        window = window or {'start': '09:00', 'end': '10:00'}
        row = self.windows.rowCount()
        self.windows.insertRow(row)
        for col, key in enumerate(('start', 'end')):
            self.windows.setItem(row, col, QTableWidgetItem(window[key]))

    def remove_window(self):
        if self.windows.currentRow() >= 0:
            self.windows.removeRow(self.windows.currentRow())

    def values(self):
        mode = self.mode.currentData()
        if self.all_day.isChecked():
            windows = [{'start': '00:00', 'end': '24:00'}]
        else:
            windows = [{key: (self.windows.item(row, col).text().strip() if self.windows.item(row, col) else '')
                        for col, key in enumerate(('start', 'end'))} for row in range(self.windows.rowCount())]
        window_intervals(windows)
        result = {}
        if mode != 'fm' or 'usage_mode' in self.original:
            result['usage_mode'] = mode
        if windows or mode == 'bed_fallback' or 'amr_access_windows' in self.original:
            result['amr_access_windows'] = windows
        return result
