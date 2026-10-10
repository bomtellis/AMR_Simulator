"""Per-user DXF visibility, independent of simulation inputs and graph history."""
from collections import Counter
import json
import os
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QSignalBlocker
from PySide6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
                              QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton)

KEY = 'dxf-layer-visibility/v1'


class LayerDock(QDockWidget):
    def closeEvent(self, event):
        self.owner.open_requested = False
        super().closeEvent(event)


def read_preferences(raw):
    value = json.loads(raw)
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or not isinstance(value.get('hidden'), dict)):
        raise ValueError('Invalid DXF visibility preferences.')
    for path, names in value['hidden'].items():
        if (not isinstance(path, str) or not path or not isinstance(names, list)
                or any(not isinstance(name, str) or not name for name in names)):
            raise ValueError('Invalid drawing or layer names.')
    return {path:set(names) for path,names in value['hidden'].items()}


class DxfLayers:
    def __init__(self, editor, settings):
        self.editor, self.settings = editor, settings
        self.hidden, self.counts = {}, {}
        self.source, self.path, self.dock = None, '', None
        self.entities_source = None
        self.open_requested = False
        self.warning = ''
        if settings is not None and settings.value(KEY, ''):
            try:
                self.hidden = read_preferences(settings.value(KEY, ''))
            except (TypeError, ValueError):
                self.warning = 'Saved DXF layer choices could not be read; all layers start visible.'

    def refresh(self):
        e = self.editor
        floor = e.floor_spin.value()
        source = e._dxf_cache.get(floor) if e.loaded_dxf_floor == floor else None
        entities = source['entities'] if source else None
        if source is not self.source or entities is not self.entities_source:
            self.source = source
            self.entities_source = entities
            self.path = os.path.normcase(str(Path(source['path']).resolve())) if source else ''
            self.counts = Counter(str(row.get('layer') or '0') for row in source['entities']) if source else {}
            self.refresh_list()
        hidden = self.hidden.get(self.path, set())
        for item in getattr(e, '_rendered_dxf_items', []):
            item.setVisible(str(item.data(10) or '0') not in hidden)
        if self.dock is not None:
            self.note.setText(self.warning or (
                f'{Path(self.path).name}: {len(self.counts)} layers; {len(set(self.counts)&hidden)} hidden.'
                if self.path else 'Load a DXF for the current floor to list its layers.'))
        e.canvas.viewport().update()

    def save(self):
        if self.settings is None:
            return
        old = self.settings.value(KEY, None)
        value = json.dumps(dict(version=1,hidden={path:sorted(names) for path,names in self.hidden.items() if names}))
        self.settings.setValue(KEY, value)
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            if old is None:
                self.settings.remove(KEY)
            else:
                self.settings.setValue(KEY, old)
            self.settings.sync()
            self.warning = 'DXF visibility could not be saved. Session choices remain active.'
            self.editor.set_status(self.warning)
        else:
            self.warning = ''

    def set_visible(self, names, visible):
        names = set(names) & self.counts.keys()
        if not self.path or not names:
            return
        hidden = self.hidden.setdefault(self.path, set())
        if visible:
            hidden.difference_update(names)
        else:
            hidden.update(names)
        self.save()
        self.sync_checks()
        self.refresh()

    def sync_checks(self):
        if self.dock is None:
            return
        with QSignalBlocker(self.layers):
            for index in range(self.layers.count()):
                item = self.layers.item(index)
                item.setCheckState(Qt.Unchecked if item.data(Qt.UserRole) in self.hidden.get(self.path,set()) else Qt.Checked)

    def refresh_list(self):
        if self.dock is None:
            return
        current = self.layers.currentItem()
        selected = current.data(Qt.UserRole) if current else None
        with QSignalBlocker(self.layers):
            self.layers.clear()
            for name,count in sorted(self.counts.items(), key=lambda row:row[0].casefold()):
                item = QListWidgetItem(f'{name} ({count})',self.layers)
                item.setData(Qt.UserRole,name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked if name in self.hidden.get(self.path,set()) else Qt.Checked)
                if name == selected:
                    self.layers.setCurrentItem(item)
        self.filter()

    def filter(self, *_):
        query = self.search.text().casefold()
        for index in range(self.layers.count()):
            item = self.layers.item(index)
            item.setHidden(query not in item.data(Qt.UserRole).casefold())

    def isolate(self):
        item = self.layers.currentItem()
        if item is None:
            return
        self.hidden[self.path] = set(self.counts) - {item.data(Qt.UserRole)}
        self.save()
        self.sync_checks()
        self.refresh()

    def show(self):
        if self.dock is None:
            self.dock = LayerDock('DXF layers',self.editor)
            self.dock.owner = self
            self.dock.setObjectName('DxfLayerVisibility')
            body = QWidget(self.dock)
            layout = QVBoxLayout(body)
            self.note = QLabel(body)
            self.note.setWordWrap(True)
            layout.addWidget(self.note)
            master = QCheckBox('Show DXF underlay',body)
            master.setChecked(self.editor.show_dxf_check.isChecked())
            master.toggled.connect(self.editor.show_dxf_check.setChecked)
            self.editor.show_dxf_check.toggled.connect(master.setChecked)
            layout.addWidget(master)
            self.search = QLineEdit(body)
            self.search.setPlaceholderText('Find a DXF layer…')
            self.search.setAccessibleName('Find a DXF layer')
            layout.addWidget(self.search)
            self.layers = QListWidget(body)
            self.layers.setAccessibleName('DXF layers; checked layers are visible')
            layout.addWidget(self.layers,1)
            buttons = QHBoxLayout()
            for title, callback in (('Show all',lambda:self.set_visible(self.counts,True)),
                                    ('Hide all',lambda:self.set_visible(self.counts,False)),
                                    ('Isolate',self.isolate)):
                button = QPushButton(title,body)
                button.clicked.connect(callback)
                buttons.addWidget(button)
            layout.addLayout(buttons)
            explanation = QLabel('Underlay display only. Route permissions and simulation geometry are unchanged. Choices follow this drawing path on this computer.',body)
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
            self.dock.setWidget(body)
            self.editor.addDockWidget(Qt.RightDockWidgetArea,self.dock)
            self.search.textChanged.connect(self.filter)
            self.layers.itemChanged.connect(lambda item:self.set_visible([item.data(Qt.UserRole)],item.checkState()==Qt.Checked))
        self.refresh()
        self.refresh_list()
        self.open_requested = True
        self.sync_workspace()
        self.dock.raise_()
        self.search.setFocus()

    def sync_workspace(self):
        if self.dock is not None:
            workspace = self.editor.workspace
            self.dock.setVisible(self.open_requested and workspace.stage == 'layout' and not workspace._canvas_focus)
