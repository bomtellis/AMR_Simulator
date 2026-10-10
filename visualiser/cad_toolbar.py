"""Compact drawing commands sharing the editor's existing state and actions."""
from dataclasses import replace
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QLabel, QMenu, QToolBar, QToolButton


class CadToolBar(QToolBar):
    def __init__(self, editor):
        super().__init__('Drawing commands', editor)
        self.editor = editor
        self.setObjectName('cadDrawingToolbar')
        self.setAccessibleName('CAD drawing commands')
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(24, 24))
        self.mode_actions = {}
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        for title, mode, explanation in (
                ('Select', 'select_move', 'Select graph objects; Shift changes selection. Drag a selected point or corridor to move the group. Escape cancels. Use Properties to edit.'),
                ('Corridor', 'corridor_draw', 'Draw connected corridor segments. Snap to existing points and edges.'),
                ('Edge', 'edge', 'Draw an edge between existing graph points: click the start, then the end. Escape cancels the chain. Set direction and chaining under More tools → Edit → Drawing behaviour.'),
                ('Transition', 'corridor_node', 'Place a shared transition or junction node on the current floor, or insert a node into an existing corridor. Use Corridor to connect its lanes.'),
                ('Location', 'location', 'Place a named simulation location.'),
                ('Department', 'department', 'Place a department on the current floor, or click a department marker to edit it. Configure its workflows and associated locations.'),
                ('Door', 'door', 'Place a door restriction on a corridor. Existing nodes and clear widths are retained; links split when placed between nodes.'),
                ('Lift', 'lift', 'Connect floors using a lift. Place or edit its access point, then configure served floors and stops in the lift editor.')):
            action = self.command(title, lambda checked=False, value=mode: editor._set_edit_mode(value), explanation,
                                  checkable=True)
            self.mode_group.addAction(action)
            action.setProperty('cadIcon', {'select_move': 'select', 'corridor_draw': 'corridor',
                                         'corridor_node': 'transition'}.get(mode, mode))
            self.mode_actions[mode] = action
        self.departments_action = QAction('Manage departments…', self)
        self.departments_action.setToolTip('Add, edit or remove departments and their workflow locations.')
        self.departments_action.triggered.connect(lambda: editor.manage_departments())
        self.departments_action.setProperty('cadIcon', 'department')
        department_button = self.widgetForAction(self.mode_actions['department'])
        self.departments_menu = QMenu(department_button)
        self.departments_menu.addAction(self.departments_action)
        department_button.setMenu(self.departments_menu)
        department_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.addSeparator()
        self.route_views_action=self.command('Routes',lambda checked: editor.route_view_toolbar.set_expanded(checked),
            'Show route profile views and colours for permitted and blocked graph directions.',checkable=True)
        self.route_views_action.setProperty('cadIcon','edge')
        self.fit_action = self.command('Fit', editor.fit_view, 'Fit the current floor drawing into the available canvas.')
        self.fit_action.setProperty('cadIcon', 'fit')
        self.addSeparator()
        label = QLabel('Floor ')
        label.setBuddy(editor.floor_spin)
        self.addWidget(label)
        editor.floor_spin.setAccessibleName('Current floor')
        editor.floor_spin.setToolTip('Current drawing floor. This is the same floor selection used by the project tree.')
        self.addWidget(editor.floor_spin)
        self.snap_action = self.command('Grid snap', lambda checked: editor.snap_check.setChecked(checked),
            'Toggle placement grid snapping. Set spacing under More tools → Edit → Drawing behaviour.',
            checkable=True)
        self.snap_action.setChecked(editor.snap_check.isChecked())
        editor.snap_check.toggled.connect(self.snap_action.setChecked)
        self.object_snap_action = self.command('Object snap', lambda checked: editor.object_snap_check.setChecked(checked),
            editor.object_snap_check.toolTip(), checkable=True)
        self.object_snap_action.setChecked(editor.object_snap_check.isChecked())
        editor.object_snap_check.toggled.connect(self.object_snap_action.setChecked)
        # Object snap targets live together in the bottom-right status bar.
        self.removeAction(self.object_snap_action)

        self.grid_action = self.command('Grid', self.change_grid,
            'Show or hide the adaptive metre grid. This is a display setting; Snap is independent.', checkable=True)
        self.grid_action.setChecked(editor.appearance.value.show_grid)
        editor.appearance.changed.connect(self.sync_appearance)
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
        for action, name in ((self.properties_action, 'properties'), (self.check_action, 'checks'),
                             (self.project_action, 'tree'), (self.more_action, 'more'), (self.focus_action, 'focus')):
            action.setProperty('cadIcon', name)
        # The stage bar, right-side tab and View menu expose these commands;
        # keep the drawing row reserved for frequent drawing tools.
        for action in (self.properties_action, self.check_action, self.project_action):
            self.removeAction(action)
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

    def change_grid(self, checked):
        self.editor.workbench._apply_appearance(replace(self.editor.appearance.value, show_grid=checked))

    def sync_appearance(self, value):
        self.grid_action.setChecked(value.show_grid)

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
        self.setVisible(layout)
        for action in (*self.mode_actions.values(), self.departments_action, self.more_action):
            action.setEnabled(layout and not self.editor.project_editing_locked())
        if getattr(self.editor,'route_profile_select_edges',False):
            for mode,action in self.mode_actions.items():
                if mode!='select_move':action.setEnabled(False)
            self.departments_action.setEnabled(False)
            self.more_action.setEnabled(False)
        self.focus_action.setEnabled(layout or workspace._canvas_focus)
        self.properties_action.setEnabled(workspace.stage in ('layout', 'configuration'))
