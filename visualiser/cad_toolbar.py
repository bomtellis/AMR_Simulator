"""Compact drawing commands sharing the editor's existing state and actions."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QLabel, QToolBar


class CadToolBar(QToolBar):
    def __init__(self, editor):
        super().__init__('Drawing commands', editor)
        self.editor = editor
        self.setObjectName('cadDrawingToolbar')
        self.setAccessibleName('CAD drawing commands')
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.mode_actions = {}
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        for title, mode, explanation in (
                ('Select', 'select_move', 'Select or move graph objects. Selection highlights; use Properties to edit.'),
                ('Corridor', 'corridor_draw', 'Draw connected corridor segments. Snap to existing points and edges.'),
                ('Node', 'corridor_node', 'Place a corridor node or insert a node into an existing corridor.'),
                ('Location', 'location', 'Place a named simulation location.')):
            action = self.command(title, lambda checked=False, value=mode: editor._set_edit_mode(value), explanation,
                                  checkable=True)
            self.mode_group.addAction(action)
            self.mode_actions[mode] = action
        self.addSeparator()
        self.addAction(editor.undo_action)
        self.addAction(editor.redo_action)
        self.command('Fit', editor.fit_view, 'Fit the current floor drawing into the available canvas.')
        self.addSeparator()
        label = QLabel('Floor ')
        label.setBuddy(editor.floor_spin)
        self.addWidget(label)
        editor.floor_spin.setAccessibleName('Current floor')
        editor.floor_spin.setToolTip('Current drawing floor. This is the same floor selection used by the project tree.')
        self.addWidget(editor.floor_spin)
        self.snap_action = self.command('Snap', lambda checked: editor.snap_check.setChecked(checked),
            'Toggle the existing one-metre drawing grid snap. Also available under More tools → Edit.',
            checkable=True)
        self.snap_action.setChecked(editor.snap_check.isChecked())
        editor.snap_check.toggled.connect(self.snap_action.setChecked)
        self.addSeparator()
        self.properties_action = self.command('Properties', editor.workspace.set_properties_visible,
            'Show or hide properties for the selection. Hiding keeps unapplied drafts and recovery data.', checkable=True)
        self.check_action = self.command('Check', editor.show_project_checks,
            'Open project checks to validate inputs and review findings. Checks run only when requested.')
        self.project_action = self.command('Project tree', editor.workspace.set_project_tree_visible,
            'Show or hide project stages, floors and objects.', checkable=True)
        self.more_action = self.command('More tools', editor.workspace.set_ribbon_visible,
            'Show the full tool tabs: files, drawing settings, display, simulation and assets.', checkable=True)
        self.focus_action = self.command('Focus canvas', editor.workspace.set_canvas_focus,
            'Hide supporting panels. Toggle again to restore their previous visibility and sizes.', checkable=True)
        editor.mode_combo.currentIndexChanged.connect(self.sync_mode)
        self.sync_mode()

    def command(self, title, callback, explanation, *, checkable=False):
        action = QAction(title, self)
        action.setCheckable(checkable)
        action.setToolTip(explanation)
        action.setStatusTip(explanation)
        action.triggered.connect(callback)
        self.addAction(action)
        return action

    def sync_mode(self, *_):
        mode = self.editor.mode_combo.currentData()
        # Other tools remain selectable from More tools without falsely showing
        # Select as active. QActionGroup permits explicit clearing of its member.
        for key, action in self.mode_actions.items():
            action.setChecked(key == mode)

    def sync_panels(self):
        workspace = self.editor.workspace
        self.properties_action.setChecked(not workspace.properties.isHidden())
        self.project_action.setChecked(not workspace.sidebar.isHidden())
        self.more_action.setChecked(not self.editor.ribbon_tabs.isHidden())
        self.focus_action.setChecked(workspace._canvas_focus)
        layout = workspace.stage == 'layout'
        for action in (*self.mode_actions.values(), self.more_action):
            action.setEnabled(layout)
        self.focus_action.setEnabled(layout or workspace._canvas_focus)
        self.properties_action.setEnabled(workspace.stage in ('layout', 'configuration'))
