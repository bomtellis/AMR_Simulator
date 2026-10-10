"""Searchable permission choices, including explicitly named graph edges."""
from copy import deepcopy
import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QComboBox, QLabel
from configuration_properties import choices


class PropertyChoices(QWidget):
    changed = Signal()

    def __init__(self, config, kind, selected, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.original = deepcopy(selected)
        self.touched = False
        self.keys = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter choices…')
        self.search.textChanged.connect(self.filter)
        root.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumHeight(105)
        self.list.setMaximumHeight(160)
        root.addWidget(self.list)
        self.count = QLabel()
        root.addWidget(self.count)
        options = choices(config, kind)
        values = selected if isinstance(selected, list) else []
        for label, value in options:
            self.add(label, value, value in values)
        for value in values:
            if self.key(value) not in self.keys:
                self.add(f'{value} (existing entry)', value, True)
        self.list.itemChanged.connect(self.edited)
        row = QHBoxLayout()
        all_button = QPushButton('Select shown')
        all_button.clicked.connect(lambda: self.set_shown(True))
        clear = QPushButton('Clear all')
        clear.clicked.connect(self.clear)
        row.addWidget(all_button)
        row.addWidget(clear)
        root.addLayout(row)
        if kind == 'edges':
            self.start = QComboBox()
            self.finish = QComboBox()
            for name, value in choices(config, 'nodes'):
                self.start.addItem(name, value)
                self.finish.addItem(name, value)
            edge_row = QHBoxLayout()
            edge_row.addWidget(self.start)
            edge_row.addWidget(QLabel('→'))
            edge_row.addWidget(self.finish)
            root.addLayout(edge_row)
            add = QPushButton('Add named edge permission')
            add.setToolTip('Adds a directional allowance between named nodes; it does not create a physical link.')
            add.clicked.connect(self.add_edge)
            root.addWidget(add)
        self.update_count()

    @staticmethod
    def key(value):
        return json.dumps(value, sort_keys=True)

    def add(self, label, value, checked):
        item = QListWidgetItem(label)
        item.setToolTip(label)
        item.setData(Qt.UserRole, deepcopy(value))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list.addItem(item)
        self.keys[self.key(value)] = item

    def value(self):
        if not self.touched:
            return deepcopy(self.original)
        # Preserve the original ordering of remaining entries.
        selected = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked]
        original = self.original if isinstance(self.original, list) else []
        result = [value for value in original if value in selected]
        result.extend(value for value in selected if value not in result)
        return result

    def update_count(self):
        value = self.value()
        count = len(value) if isinstance(value, list) else 0
        if self.kind == 'orientations' and value is None:
            self.count.setText('No explicit setting; simulator default applies')
        else:
            self.count.setText(f'{count} selected' if count else ('No orientations selected' if self.kind == 'orientations' else 'Unrestricted (empty list)'))

    def edited(self, *_):
        self.touched = True
        self.update_count()
        self.changed.emit()

    def filter(self, *_):
        text = self.search.text().strip().casefold()
        for index in range(self.list.count()):
            item = self.list.item(index)
            item.setHidden(text not in item.text().casefold())

    def set_shown(self, checked):
        self.list.blockSignals(True)
        for index in range(self.list.count()):
            item = self.list.item(index)
            if not item.isHidden():
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list.blockSignals(False)
        self.edited()

    def clear(self):
        self.list.blockSignals(True)
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(Qt.Unchecked)
        self.list.blockSignals(False)
        self.edited()

    def add_edge(self):
        a, b = self.start.currentData(), self.finish.currentData()
        if a is None or b is None or a == b:
            self.count.setText('Choose two distinct nodes.')
            return
        value = [a, b]
        key = self.key(value)
        if key not in self.keys:
            self.add(f'{a} → {b}', value, True)
        else:
            self.keys[key].setCheckState(Qt.Checked)
        self.edited()
        self.filter()
