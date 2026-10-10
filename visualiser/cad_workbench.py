"""A2 workflow navigation and honest current-project status around the CAD view."""
from dataclasses import replace

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QStyle, QStyleOptionButton, QStylePainter, QToolBar, QWidget)


class PropertiesTab(QPushButton):
    """A narrow, keyboard-accessible vertical tab using native button semantics."""
    def __init__(self, parent=None):
        super().__init__('Properties', parent)
        self.setObjectName('cadPropertiesTab')
        self.setAccessibleName('Show or hide selection properties')
        self.setToolTip('Open selection properties. Closing this panel keeps any unapplied draft.')
        self.setCheckable(True)

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(size.height(), size.width())

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _event):
        painter = QStylePainter(self)
        painter.translate(self.width(), 0)
        painter.rotate(90)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect.setWidth(self.height())
        option.rect.setHeight(self.width())
        painter.drawControl(QStyle.CE_PushButton, option)


class CadWorkbench(QObject):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self._checks_panel = None
        self.workflow = QToolBar('Project workflow', editor)
        self.workflow.setObjectName('cadWorkflowToolbar')
        self.workflow.setAccessibleName('Project workflow stages')
        self.workflow.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.workflow.setIconSize(QSize(22, 22))
        self.workflow.setMovable(False)
        self.workflow.setFloatable(False)
        self.save_action = self.action('Save', editor.save_json, 'save', 'Save the current project.', QKeySequence.Save)
        self.workflow.addAction(self.save_action)
        editor.undo_action.setProperty('cadIcon', 'undo')
        editor.redo_action.setProperty('cadIcon', 'redo')
        self.workflow.addAction(editor.undo_action)
        self.workflow.addAction(editor.redo_action)
        for action, title in ((editor.undo_action, 'Undo'), (editor.redo_action, 'Redo')):
            button = self.workflow.widgetForAction(action)
            def compact_history(action=action, button=button, title=title):
                button.setText(title)
                button.setToolTip(action.text() + '\n' + action.toolTip())
            action.changed.connect(compact_history)
            compact_history()
        self.workflow.addSeparator()
        self.stages = {}
        self.stage_group = QActionGroup(self)
        self.stage_group.setExclusive(True)
        from project_workspace import STAGES
        for key, title in STAGES:
            action = self.action(title, lambda checked=False, stage=key: editor.workspace.activate(stage), key,
                                 f'Open the {title.lower()} workspace.')
            action.setCheckable(True)
            self.stage_group.addAction(action)
            self.workflow.addAction(action)
            self.stages[key] = action
        self.workflow.addSeparator()
        self.text_size = QComboBox()
        self.text_size.setAccessibleName('Interface text size')
        self.text_size.setToolTip('Change interface text size. Saved as a personal preference, not project data.')
        for size in range(8, 25):
            self.text_size.addItem(f'{size} pt', size)
        self.theme = QComboBox()
        self.theme.setAccessibleName('Interface colour theme')
        self.theme.setToolTip('Choose an accessible application theme. Personal appearance does not change simulation inputs.')
        from appearance import PRESETS
        self.theme.addItems(list(PRESETS))
        self.workflow.addWidget(QLabel('Text '))
        self.workflow.addWidget(self.text_size)
        self.workflow.addWidget(QLabel('Theme '))
        self.workflow.addWidget(self.theme)
        self.help_action = self.action('Help', self.drawing_help, 'help', 'Show the implemented drawing controls and workflow.')
        self.workflow.addAction(self.help_action)
        self.appearance_action = self.action('Appearance…', editor.show_appearance, 'configuration',
                                            'Adjust text sizes, colours and other personal display preferences.')
        self._menus()
        self.checks_strip = QWidget(editor.workspace)
        self.checks_strip.setObjectName('cadChecksStrip')
        strip = QHBoxLayout(self.checks_strip)
        strip.setContentsMargins(10, 4, 10, 4)
        self.checks_label = QLabel('Project checks · Not checked')
        self.checks_label.setWordWrap(True)
        self.checks_label.setAccessibleName('Current project check status')
        strip.addWidget(self.checks_label, 1)
        self.open_checks = QPushButton('Open checks')
        self.open_checks.setProperty('cadIcon', 'checks')
        self.open_checks.setToolTip('Open checks for the current project. Drawing and selection do not run checks automatically.')
        self.open_checks.clicked.connect(editor.show_project_checks)
        strip.addWidget(self.open_checks)
        editor.workspace.central_layout.addWidget(self.checks_strip)
        self.text_size.currentIndexChanged.connect(self.change_text_size)
        self.theme.currentTextChanged.connect(self.change_theme)
        editor.appearance.changed.connect(self.appearance_changed)
        from route_view_toolbar import RouteViewToolbar
        editor.route_view_toolbar=RouteViewToolbar(editor)
        self.appearance_changed(editor.appearance.value)
        self.refresh()
        editor.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.editor and event.type() == QEvent.Resize:
            self.refresh_density()
        return super().eventFilter(watched, event)

    def refresh_density(self):
        compact = self.editor.width() < 1400 and self.editor.appearance.value.font_size >= 16
        self.editor.workspace.central_layout.setContentsMargins(4,2 if compact else 4,4,2 if compact else 4)
        toolbar = self.editor.cad_toolbar
        for action in toolbar.mode_actions.values():
            button = toolbar.widgetForAction(action)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextUnderIcon)
            button.setAccessibleName(action.text())
        toolbar.widgetForAction(toolbar.route_views_action).setToolButtonStyle(Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextUnderIcon)
        self.checks_strip.setVisible(self.editor.workspace.stage == 'layout' and
            not self.editor.workspace._canvas_focus and not compact)

    def action(self, text, callback, icon, tooltip, shortcut=None):
        action = QAction(text, self.editor)
        action.setProperty('cadIcon', icon)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        return action

    def _menus(self):
        editor = self.editor
        self.file_menu = editor.menuBar().addMenu('&File')
        self.new_action = self.action('New project', editor.new_project, 'project',
                                     'Start a new project after reviewing unsaved changes.', QKeySequence.New)
        self.file_menu.addAction(self.new_action)
        self.open_action = self.action('Open project / JSON…', editor.open_json, 'project',
                                      'Open a saved project or import a JSON configuration.', QKeySequence.Open)
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.save_action)
        self.save_as_action = self.action('Save project as…', lambda: editor.save_project(save_as=True), 'save',
                                         'Save a new project file.', QKeySequence.SaveAs)
        self.file_menu.addAction(self.save_as_action)
        self.file_menu.addAction(self.action('Export JSON…', editor.export_project_json, 'project',
                                            'Export the current project configuration as JSON.'))
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action('Recover unsaved work…', editor.recover_unsaved_work, 'project',
                                            'Review available recovery snapshots.'))
        self.file_menu.addAction(self.action('Close window', editor.close, 'project', 'Close after reviewing unsaved work.'))
        self.layout_menu = editor.menuBar().addMenu('&Layout')
        self.add_node_action = self.action('Add node / transition',lambda: editor._set_edit_mode('corridor_node'), 'transition',
            'Place a node on the current floor, or insert one into an existing corridor in Layout.')
        self.layout_menu.addAction(self.add_node_action)
        self.add_edge_action = self.action('Add edge between nodes',lambda: editor._set_edit_mode('edge'), 'edge',
            'In Layout, click two existing nodes to connect them on the same floor. Escape finishes.')
        self.layout_menu.addAction(self.add_edge_action)
        self.layout_menu.addAction(editor.cad_toolbar.mode_actions['corridor_draw'])
        self.layout_menu.addSeparator()
        def route_profiles():
            editor.workspace.activate('layout');editor.manage_route_profiles()
        self.route_profiles_action = self.action('Route profiles…',route_profiles,'edge',
            'Create flow profiles and select their permitted nodes and edges on the Layout drawing.')
        self.layout_menu.addAction(self.route_profiles_action)
        self.layout_menu.addAction(editor.cad_toolbar.route_views_action)
        self.edit_menu = editor.menuBar().addMenu('&Edit')
        self.edit_menu.addActions([editor.undo_action, editor.redo_action])
        self.edit_menu.addSeparator()
        self.delete_action = self.action('Delete selected', editor.delete_selected, 'select',
                                         'Delete selected graph objects as one undoable operation.', QKeySequence.Delete)
        self.delete_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        editor.canvas.addAction(self.delete_action)
        self.edit_menu.addAction(self.delete_action)
        self.move_action = self.action('Move selected by…', editor.show_selection_move, 'select',
                                      'Enter an exact displacement for the active-floor selection.', QKeySequence('Ctrl+M'))
        self.move_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        editor.canvas.addAction(self.move_action)
        self.edit_menu.addAction(self.move_action)
        self.rotate_action = self.action('Rotate selected…', editor.show_selection_rotation, 'select',
            'Rotate active-floor points, boundaries and bays. Enter centre/angle, or Pick rotation: centre, reference direction, target direction.')
        self.edit_menu.addAction(self.rotate_action)
        self.copy_action = self.action('Copy selected by…', editor.show_selection_copy, 'select',
            'Copy locations and corridor nodes with new names, internal connections and matching route-profile membership.')
        self.edit_menu.addAction(self.copy_action)
        self.endpoint_action = self.action('Trim / extend corridor…', editor.show_corridor_endpoint, 'select',
            'Move a free corridor endpoint to a boundary corridor, previewing the joined graph before applying.')
        self.edit_menu.addAction(self.endpoint_action)
        self.edit_menu.addAction(editor.cad_toolbar.properties_action)
        self.edit_menu.addAction(self.action('Clear selection', editor.clear_topology_selection, 'select',
                                            'Clear graph selections without editing objects.'))
        self.view_menu = editor.menuBar().addMenu('&View')
        self.view_menu.addAction(editor.cad_toolbar.fit_action)
        self.fit_selection_action = self.action('Zoom to selection', editor.fit_selection, 'fit',
            'Fit selected points, corridor endpoints and location boundaries on the current floor. Drawing underlays are excluded.')
        self.view_menu.addAction(self.fit_selection_action)
        self.view_menu.addAction(self.action('Model layers…', editor.show_model_layers, 'layout',
            'Create project layers, assign selected objects, hide them or lock them against editing. Route permissions remain separate.'))
        self.view_menu.addAction(self.action('DXF layers…', editor.show_dxf_layers, 'layout',
            'Search, show, hide or isolate imported DXF layers without changing model geometry or route access.'))
        self.view_menu.addAction(editor.cad_toolbar.project_action)
        self.view_menu.addAction(editor.cad_toolbar.properties_action)
        self.view_menu.addAction(editor.cad_toolbar.focus_action)
        self.view_menu.addAction(editor.cad_toolbar.more_action)
        self.view_menu.addSeparator()
        labels_menu = self.view_menu.addMenu('Object names')
        self.object_label_actions = {}
        self.object_label_group = QActionGroup(self)
        for title, index in [('All names', 0), ('Locations, departments, lifts and doors', 1), ('Selected objects only', 2), ('Hide names', -1)]:
            action = labels_menu.addAction(title)
            action.setCheckable(True)
            self.object_label_group.addAction(action)
            action.triggered.connect(lambda checked=False, value=index: self.set_object_label_mode(value))
            self.object_label_actions[index] = action
        editor.object_label_mode.currentIndexChanged.connect(self.sync_object_labels)
        editor.show_labels_check.toggled.connect(self.sync_object_labels)
        self.sync_object_labels()
        self.legend_action = self.action('Map key', self.change_legend, 'layout',
                                         'Show or hide the compact map key.')
        self.legend_action.setCheckable(True)
        self.legend_action.setChecked(editor.appearance.value.show_legend)
        self.view_menu.addAction(self.legend_action)
        self.view_menu.addAction(editor.cad_toolbar.grid_action)
        self.view_menu.addAction(self.appearance_action)
        self.help_menu = editor.menuBar().addMenu('&Help')
        self.walkthrough_action = self.action('Guided walkthrough…', self.show_quick_start, 'help',
                                              'Follow the small-map or supplied LTN exercise in the application.')
        self.help_menu.addAction(self.walkthrough_action)
        self.help_menu.addAction(self.action('Building flow tutorial…', self.show_building_course, 'help',
            'Build three floors, compare scenarios and plan lift locations.'))
        self.restart_bubble_action = self.action('Restart tutorial bubble', self.restart_tutorial_bubble, 'help',
            'Reopen the tutorial bubble at the current step, keeping your project and progress.')
        self.help_menu.addAction(self.restart_bubble_action)
        self.help_menu.addAction(self.help_action)
        self.help_menu.addAction(self.action('Model scope and checks', editor.show_project_checks, 'checks',
                                            'Review supported features, limitations and current project findings.'))

    def set_object_label_mode(self, index):
        if index >= 0:
            self.editor.object_label_mode.setCurrentIndex(index)
        self.editor.show_labels_check.setChecked(index >= 0)

    def sync_object_labels(self, *_):
        active = self.editor.object_label_mode.currentIndex() if self.editor.show_labels_check.isChecked() else -1
        for index, action in self.object_label_actions.items():
            action.setChecked(index == active)

    def drawing_help(self):
        QMessageBox.information(self.editor, 'Drawing controls',
            'Start in Layout. Use Select to highlight objects; open Properties to edit them.\n\n'
            'With the canvas focused, press Delete or right-click and choose Delete selected. '
            'Confirm once for the selection; Undo restores it. Delete in a text field edits text only.\n\n'
            'Corridor draws connected segments. Type X,Y, @dx,dy or @length<angle in metres and degrees. '
            'Enter places a point; blank Enter finishes. Escape cancels the current drawing draft. '
            'Undo and Redo use the shared project history.\n\n'
            'Department places a department marker or edits one by clicking it. Its drop-down opens Manage departments. '
            'Use the bottom-right Object snap toggles to combine End, Mid, Perp and Cross. Near is a fallback; '
            'turn Object snap off to suspend snapping while retaining your chosen targets.\n\n'
            'Edge connects existing graph points: click the start, then the end. Escape cancels the chain. '
            'More tools → Edit → Drawing behaviour controls bidirectional edges and chain creation. '
            'Right-click empty space cancels; right-click two points removes their edge.\n\n'
            'Door places a graph door restriction using the configured clear width. Select it and open Properties to edit the width; '
            'this does not draw physical walls or openings.\n\n'
            'Use the project tree or upper workflow bar to configure, check, simulate and investigate saved runs. '
            'View → DXF layers opens searchable underlay visibility controls; they do not change routes or physical geometry. '
            'More tools contains the full editor commands. Theme and text size are personal preferences.')

    def show_quick_start(self):
        if not hasattr(self, 'quick_start_dialog'):
            from quick_start import QuickStartDialog
            self.quick_start_dialog = QuickStartDialog(self.editor)
        self.quick_start_dialog.show()
        self.quick_start_dialog.raise_()
        self.quick_start_dialog.activateWindow()

    def show_building_course(self):
        if not hasattr(self, 'quick_start_dialog'):
            from quick_start import QuickStartDialog
            self.quick_start_dialog = QuickStartDialog(self.editor)
        self.quick_start_dialog.building_course.show_card()

    def restart_tutorial_bubble(self):
        if not hasattr(self, 'quick_start_dialog'):
            from quick_start import QuickStartDialog
            self.quick_start_dialog = QuickStartDialog(self.editor)
        self.quick_start_dialog.building_course.restart_bubble()

    def change_text_size(self, _index):
        value = self.text_size.currentData()
        if value is not None and value != self.editor.appearance.value.font_size:
            self._apply_appearance(replace(self.editor.appearance.value, font_size=value))

    def change_legend(self, visible):
        self._apply_appearance(replace(self.editor.appearance.value, show_legend=visible))

    def change_theme(self, theme):
        if theme and theme != self.editor.appearance.value.theme:
            from appearance import with_theme
            self._apply_appearance(with_theme(self.editor.appearance.value, theme))

    def _apply_appearance(self, value):
        try:
            self.editor.appearance.apply(value)
        except (ValueError, OSError) as exc:
            self.appearance_changed(self.editor.appearance.value)
            QMessageBox.warning(self.editor, 'Appearance was not changed', str(exc))

    def appearance_changed(self, value):
        self.legend_action.setChecked(value.show_legend)
        for control in (self.text_size, self.theme):
            control.blockSignals(True)
        try:
            self.text_size.setCurrentIndex(self.text_size.findData(value.font_size))
            self.theme.setCurrentText(value.theme)
        finally:
            for control in (self.text_size, self.theme):
                control.blockSignals(False)
        from cad_visual_style import apply_workbench_style
        apply_workbench_style(self.editor)
        self.refresh_density()

    def refresh(self):
        stage = self.editor.workspace.stage
        if hasattr(self.editor,'route_view_toolbar'):self.editor.route_view_toolbar.sync()
        active = {'demand': 'checks', 'playback': 'review', 'appearance': 'project', 'route_display': 'layout'}.get(stage, stage)
        for key, action in self.stages.items():
            action.setChecked(key == active)
        self.refresh_density()
        self.refresh_checks()

    def refresh_checks(self):
        panel = getattr(self.editor, 'checks_panel', None)
        if panel is not None and panel is not self._checks_panel:
            panel.readiness_changed.connect(self.refresh_checks)
            self._checks_panel = panel
        report = getattr(panel, 'report', None)
        if report is None:
            text = 'Project checks · Not checked'
        elif not panel.current():
            text = 'Project checks · Stale — run checks again'
        else:
            errors = sum(f.severity == 'error' for f in report.findings)
            warnings = sum(f.severity == 'warning' for f in report.findings)
            text = f'Project checks · Current · {errors} errors · {warnings} warnings'
        self.checks_label.setText(text)
        self.checks_label.setToolTip(text + '. Open checks to review findings and warning acknowledgements.')
        self.stages['checks'].setToolTip(text + '. Open checks to review findings and warning acknowledgements.')
