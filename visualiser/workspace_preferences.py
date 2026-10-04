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
    sizes = raw.get('panel_sizes', {})
    widths = raw.get('property_widths', {})
    if not isinstance(sizes, dict) or not isinstance(widths, dict):
        raise ValueError('Invalid workspace panel sizes.')
    for stage, values in sizes.items():
        if stage not in ('layout','configuration') or not isinstance(values,list) or len(values) != 3:
            raise ValueError('Invalid workspace panel sizes.')
        if any(type(v) is not int or not 0 <= v <= 20000 for v in values) or values[1] <= 0:
            raise ValueError('Invalid workspace panel sizes.')
    for stage, width in widths.items():
        if stage not in ('layout','configuration') or type(width) is not int or not 80 <= width <= 20000:
            raise ValueError('Invalid workspace property width.')
    return dict({key: raw[key] for key in ('version', *BOOL_FIELDS, 'name_mode')},
                panel_sizes=sizes,property_widths=widths)


class WorkspacePreferences:
    def __init__(self, editor, settings):
        self.editor = editor
        self.settings = settings
        self.loading = True
        self.last_saved = None
        self.warning = ''
        self.panel_sizes = {}
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
                    self.panel_sizes = value['panel_sizes']
                    workspace._stage_sizes.update(self.panel_sizes)
                    workspace._property_widths.update(value['property_widths'])
                    editor.object_label_mode.setCurrentIndex(editor.object_label_mode.findData(value['name_mode']))
                    editor.show_labels_check.setChecked(value['show_names'])
                    workspace._sync_panels()
                    if value['layout_properties']:
                        workspace._expand_properties()
                    if 'layout' in self.panel_sizes:
                        workspace.splitter.setSizes(self.panel_sizes['layout'])
                        if value['layout_properties'] and self.panel_sizes['layout'][2] == 0:
                            workspace._expand_properties()
                    self.last_saved = self.snapshot()
                except (TypeError, ValueError):
                    self.warning = 'Saved workspace preferences could not be read. Defaults are in use; changing a view preference replaces them.'
                    editor.set_status(self.warning)
        self.last_saved = self.snapshot()
        self.loading = False
        editor.object_label_mode.currentIndexChanged.connect(self.save)
        editor.show_labels_check.toggled.connect(self.save)
        editor.workspace.splitter.splitterMoved.connect(self.capture_sizes)

    def capture_sizes(self, *_):
        workspace = self.editor.workspace
        if self.loading or workspace._canvas_focus or workspace.stage not in ('layout','configuration'):
            return
        sizes = workspace.splitter.sizes()
        if sizes[1] <= 0:
            return
        self.panel_sizes[workspace.stage] = sizes
        workspace._stage_sizes[workspace.stage] = sizes
        if not workspace.properties.isHidden() and sizes[2] >= 80:
            workspace._property_widths[workspace.stage] = sizes[2]
        self.save()

    def snapshot(self):
        workspace = self.editor.workspace
        return json.dumps(dict(version=1,project_tree=workspace._project_tree_open,
            layout_properties=workspace._layout_properties_open,
            configuration_properties=workspace._configuration_properties_open,
            more_tools=workspace._ribbon_open,show_names=self.editor.show_labels_check.isChecked(),
            name_mode=self.editor.object_label_mode.currentData(),panel_sizes=self.panel_sizes,
            property_widths=workspace._property_widths),sort_keys=True)

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
