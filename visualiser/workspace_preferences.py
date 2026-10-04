"""Per-user workspace visibility; deliberately separate from project inputs."""
import json
from PySide6.QtCore import QSettings


KEY = 'workspace/v1'
BOOL_FIELDS = ('project_tree', 'layout_properties', 'configuration_properties', 'more_tools', 'show_names')


def validate(raw):
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw.get('version') != 1:
        raise ValueError('Unrecognised workspace preference version.')
    if any(type(raw.get(key)) is not bool for key in BOOL_FIELDS):
        raise ValueError('Workspace visibility preferences must be booleans.')
    if raw.get('name_mode') not in ('all', 'key', 'selected'):
        raise ValueError('Unrecognised object-name preference.')
    return {key: raw[key] for key in ('version', *BOOL_FIELDS, 'name_mode')}


class WorkspacePreferences:
    def __init__(self, editor, settings):
        self.editor = editor
        self.settings = settings
        self.loading = True
        self.last_saved = None
        self.warning = ''
        if settings is not None:
            raw = settings.value(KEY, '')
            if raw:
                try:
                    value = validate(json.loads(raw))
                    workspace = editor.workspace
                    workspace._project_tree_open = value['project_tree']
                    workspace._layout_properties_open = value['layout_properties']
                    workspace._configuration_properties_open = value['configuration_properties']
                    workspace._ribbon_open = value['more_tools']
                    editor.object_label_mode.setCurrentIndex(editor.object_label_mode.findData(value['name_mode']))
                    editor.show_labels_check.setChecked(value['show_names'])
                    workspace._sync_panels()
                    if value['layout_properties']:
                        workspace._expand_properties()
                    self.last_saved = self.snapshot()
                except (TypeError, ValueError):
                    self.warning = 'Saved workspace preferences could not be read. Defaults are in use; changing a view preference replaces them.'
                    editor.set_status(self.warning)
        self.last_saved = self.snapshot()
        self.loading = False
        editor.object_label_mode.currentIndexChanged.connect(self.save)
        editor.show_labels_check.toggled.connect(self.save)

    def snapshot(self):
        workspace = self.editor.workspace
        return json.dumps(dict(version=1,project_tree=workspace._project_tree_open,
            layout_properties=workspace._layout_properties_open,
            configuration_properties=workspace._configuration_properties_open,
            more_tools=workspace._ribbon_open,show_names=self.editor.show_labels_check.isChecked(),
            name_mode=self.editor.object_label_mode.currentData()),sort_keys=True)

    def save(self, *_):
        if self.loading or self.settings is None:
            return
        value = self.snapshot()
        if value == self.last_saved:
            return
        old = self.settings.value(KEY, None)
        self.settings.setValue(KEY, value)
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            if old is None:
                self.settings.remove(KEY)
            else:
                self.settings.setValue(KEY, old)
            self.settings.sync()
            self.warning = 'Workspace preferences could not be saved. This view remains usable for the current session.'
            self.editor.set_status(self.warning)
            return
        self.last_saved = value
        self.warning = ''
