"""Transactional editing and local clipboard support for configured schedules."""
from copy import deepcopy
import json

from PySide6.QtCore import Qt, QMimeData, QByteArray
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QVBoxLayout,
    QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QMessageBox, QLabel,
    QAbstractItemView)
from ui_theme import polish_dialog

MIME = 'application/x-amr-configured-group+json'


def same_group_settings(payload, group_payload):
    """Bulk compatibility overrides differ only at the department's own endpoint."""
    payload, group_payload = deepcopy(payload), deepcopy(group_payload)
    for value in (payload, group_payload):
        value.setdefault('staff_movement_policy', 'batch_same_location')
        value.setdefault('staff_shift_pattern', 'none')
    if payload == group_payload:
        return True
    role = group_payload.get('department_location_role', 'dropoff')
    if payload.get('department_location_role', 'dropoff') != role:
        return False
    endpoint = 'pickup' if role == 'pickup' else 'dropoff'
    exclude = {endpoint + '_location', endpoint + '_locations'}
    return ({key: value for key, value in payload.items() if key not in exclude}
            == {key: value for key, value in group_payload.items() if key not in exclude})


def apply_group_edits(category, before, after, compatibility_payload):
    """Keep independent overrides; remove only obsolete group compatibility copies."""
    result = deepcopy(category)
    previous = {group['id']: group for group in before}
    updated = {group['id']: group for group in after}
    changed = {identity for identity in previous.keys() | updated.keys()
               if previous.get(identity) != updated.get(identity)}
    affected = {department for identity in changed
                for group in (previous.get(identity), updated.get(identity)) if group
                for department in group['departments']}
    overrides = result.setdefault('departments', {})
    for department in affected:
        old = [group for group in before if department in group['departments']]
        remaining = [group for group in after if department in group['departments']]
        edited = [group for group in remaining if group['id'] in changed]
        current = overrides.get(department)
        matches = isinstance(current, dict) and any(same_group_settings(current, group['payload']) for group in old)
        if edited:
            overrides[department] = deepcopy(compatibility_payload(edited[-1], department))
        elif remaining and matches:
            overrides[department] = deepcopy(compatibility_payload(remaining[-1], department))
        elif not remaining and matches:
            overrides.pop(department, None)
    result['department_groups'] = deepcopy(after)
    return result


class ConfiguredGroupEditorDialog(QDialog):
    """Every change stays in a deep-copied draft until Save is accepted."""
    def __init__(self, parent, groups, label_builder, edit_group, category_key):
        super().__init__(parent)
        self.setWindowTitle('Edit configured group')
        self.resize(900, 560)
        self.groups = deepcopy(groups)
        self._reserved_ids = set(groups)
        self.label_builder = label_builder
        self.edit_group_callback = edit_group
        self.category_key = category_key
        self.result_groups = None
        layout = QVBoxLayout(self)
        note = QLabel('Copy a group, then paste and adjust its schedule. Double-click a group to edit it. '
                      'Save applies all changes; Cancel discards them.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setAccessibleName('Configured schedule groups')
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.edit_selected())
        self.list_widget.currentItemChanged.connect(self._refresh_actions)
        layout.addWidget(self.list_widget, 1)
        actions = QHBoxLayout()
        for attribute, label, callback in (
                ('edit_button', 'Edit…', self.edit_selected),
                ('copy_button', 'Copy', self.copy_selected),
                ('paste_button', 'Paste…', self.paste_group),
                ('delete_button', 'Delete', self.delete_selected)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            setattr(self, attribute, button)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.copy_button.setToolTip('Copy the selected group (Ctrl+C in the list).')
        self.paste_button.setToolTip('Paste a copied group from this category as a new schedule (Ctrl+V in the list).')
        self.delete_button.setToolTip('Delete the selected group from this draft (Delete in the list).')
        self.shortcuts = []
        for sequence, callback in ((QKeySequence.Copy, self.copy_selected),
                                   (QKeySequence.Paste, self.paste_group),
                                   (QKeySequence.Delete, self.delete_selected)):
            shortcut = QShortcut(QKeySequence(sequence), self.list_widget)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._clipboard = QApplication.clipboard()
        self._clipboard.dataChanged.connect(self._refresh_actions)
        self._clipboard_connected = True
        self._refresh_list()
        polish_dialog(self)

    def _selected_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _refresh_list(self, selected=None):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for identity, group in self.groups.items():
            item = QListWidgetItem(self.label_builder(group))
            item.setData(Qt.UserRole, identity)
            self.list_widget.addItem(item)
            if identity == selected:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentRow() < 0 and self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self.list_widget.blockSignals(False)
        self._refresh_actions()

    def _clipboard_group(self):
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasFormat(MIME):
            return None
        raw = bytes(mime.data(MIME))
        if len(raw) > 4 * 1024 * 1024:
            return None
        try:
            value = json.loads(raw.decode('utf-8'))
            if (not isinstance(value, dict) or value.get('version') != 1
                    or value.get('category') != self.category_key):
                return None
            group = value.get('group')
            if (not isinstance(group, dict) or not isinstance(group.get('payload'), dict)
                    or not isinstance(group.get('departments'), list) or not group['departments']
                    or any(not isinstance(dept, str) or not dept.strip() for dept in group['departments'])):
                return None
            return deepcopy(group)
        except (UnicodeError, ValueError, TypeError):
            return None

    def _refresh_actions(self, *_args):
        selected = self._selected_id() in self.groups
        for button in (self.edit_button, self.copy_button, self.delete_button):
            button.setEnabled(selected)
        self.paste_button.setEnabled(self._clipboard_group() is not None)

    def copy_selected(self):
        identity = self._selected_id()
        if identity not in self.groups:
            return
        value = dict(version=1, category=self.category_key, group=deepcopy(self.groups[identity]))
        text = json.dumps(value, ensure_ascii=False)
        mime = QMimeData()
        mime.setData(MIME, QByteArray(text.encode('utf-8')))
        mime.setText(text)
        QApplication.clipboard().setMimeData(mime)

    def _edit(self, group):
        try:
            updated = self.edit_group_callback(deepcopy(group))
        except Exception as exc:
            QMessageBox.warning(self, 'Check configured group', str(exc))
            return False
        if updated is None:
            return False
        updated = deepcopy(updated)
        updated['id'] = group['id']
        self.groups[group['id']] = updated
        self._refresh_list(group['id'])
        return True

    def edit_selected(self):
        identity = self._selected_id()
        if identity in self.groups:
            self._edit(self.groups[identity])

    def paste_group(self):
        group = self._clipboard_group()
        if group is None:
            return
        counter = 1
        while f'GROUP-{counter}' in self._reserved_ids or f'GROUP-{counter}' == group.get('id'):
            counter += 1
        group['id'] = f'GROUP-{counter}'
        if self._edit(group):
            self._reserved_ids.add(group['id'])

    def delete_selected(self):
        identity = self._selected_id()
        if identity not in self.groups:
            return
        if QMessageBox.question(self, 'Delete configured group',
                'Delete the selected configured schedule? Save applies the deletion; Cancel discards it.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        row = self.list_widget.currentRow()
        self.groups.pop(identity)
        self._refresh_list()
        if self.list_widget.count():
            self.list_widget.setCurrentRow(min(row, self.list_widget.count() - 1))

    def accept(self):
        self.result_groups = deepcopy(list(self.groups.values()))
        super().accept()

    def done(self, result):
        if self._clipboard_connected:
            self._clipboard.dataChanged.disconnect(self._refresh_actions)
            self._clipboard_connected = False
        super().done(result)
