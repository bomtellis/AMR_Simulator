"""Persistent project navigation around the editor's shared state and panels."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem, QScrollArea, QLineEdit, QLayout)


STAGES = [('project', 'Project'), ('layout', 'Layout'), ('configuration', 'Configuration'),
          ('checks', 'Check'), ('simulate', 'Simulate'), ('review', 'Review'), ('report', 'Report')]
CONFIGURATION = [('Simulation settings', 'manage_simulation_settings'), ('Robots', 'manage_amrs'),
    ('Payloads', 'manage_payloads'), ('Lifts', 'manage_lifts'), ('Tasks', 'manage_tasks'),
    ('Demand generation', 'manage_task_generation'), ('Route profiles', 'manage_route_profiles'),
    ('Departments', 'manage_departments'), ('People movement', 'manage_people_movement'),
    ('Scenarios', 'manage_scenario_testing'), ('Corridor settings', 'manage_corridor_settings')]


class ProjectWorkspace(QWidget):
    def __init__(self, editor, canvas):
        super().__init__(editor)
        self.editor = editor
        self.pages = {'layout': canvas}
        self.stage = 'layout'
        self._floors = None
        self._objects = None
        self.selected_edge_record = None
        self.object_items = {}
        self.configuration_items = {}
        self._configuration_objects = None
        self.selected_configuration = None
        self._navigating = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        self.splitter = split
        self._property_layout = None
        root.addWidget(split)
        sidebar = QWidget()
        nav = QVBoxLayout(sidebar)
        nav.setSizeConstraint(QLayout.SetMinimumSize)
        self.project_label = QLabel('Unsaved project')
        self.project_label.setWordWrap(True)
        nav.addWidget(self.project_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find project objects…')
        self.search.setAccessibleName('Filter project objects')
        self.search.textChanged.connect(self.filter_objects)
        nav.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderLabel('Project workflow')
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Project workflow and floors')
        self.items = {}
        for key, title in STAGES:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, key)
            self.items[key] = item
            self.tree.addTopLevelItem(item)
        child = QTreeWidgetItem(['Appearance'])
        child.setData(0, Qt.UserRole, 'appearance')
        self.items['project'].addChild(child)
        self.items['project'].setExpanded(True)
        self.items['appearance'] = child
        child = QTreeWidgetItem(['Route identification'])
        child.setData(0, Qt.UserRole, 'route_display')
        self.items['project'].addChild(child)
        self.items['route_display'] = child
        child = QTreeWidgetItem(['Demand preview'])
        child.setData(0, Qt.UserRole, 'demand')
        self.items['checks'].addChild(child)
        self.items['demand'] = child
        child = QTreeWidgetItem(['Playback'])
        child.setData(0, Qt.UserRole, 'playback')
        self.items['review'].addChild(child)
        self.items['review'].setExpanded(True)
        self.items['playback'] = child
        nav.addWidget(self.tree, 1)
        buttons = QVBoxLayout()
        self.previous = QPushButton('Previous')
        self.next = QPushButton('Next')
        self.previous.clicked.connect(lambda: self.step(-1))
        self.next.clicked.connect(lambda: self.step(1))
        buttons.addWidget(self.previous)
        buttons.addWidget(self.next)
        nav.addLayout(buttons)
        split.addWidget(sidebar)
        self.stack = QStackedWidget()
        self.stack.addWidget(canvas)
        split.addWidget(self.stack)
        from project_properties_panel import ProjectPropertiesPanel
        self.properties = ProjectPropertiesPanel(editor)
        editor.properties_panel = self.properties
        split.addWidget(self.properties)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 960, 300])
        sidebar.setMinimumWidth(180)
        self.tree.currentItemChanged.connect(self.selected)
        self.show_page('layout', canvas)
        self.refresh()

    def selected(self, item, _previous):
        if item is None or self._navigating:
            return
        key = item.data(0, Qt.UserRole)
        if key is None:
            return
        if isinstance(key, tuple) and key[0] == 'config':
            self.select_configuration(key[1], key[2])
            return
        if isinstance(key, tuple) and key[0] in {'point', 'edge'}:
            self.select_object(key)
            return
        if isinstance(key, tuple) and key[0] == 'floor':
            self.editor.floor_spin.setValue(key[1])
            self.show_page('layout', self.editor.canvas)
            self.editor.fit_view()
            return
        self.activate(key)

    def activate(self, key):
        handlers = {'project': self.editor.show_project_revisions, 'layout': lambda: self.show_page('layout', self.editor.canvas),
            'configuration': self.configuration, 'checks': self.editor.validate_json, 'demand': self.editor.show_demand_preview,
            'simulate': self.editor.show_project_runs, 'review': self.editor.show_results_investigation,
            'report': self.editor.show_project_report, 'playback': self.editor.show_project_playback,
            'appearance': self.editor.show_appearance, 'route_display': self.editor.show_route_identification}
        handlers[key]()

    def show_page(self, key, widget):
        if key not in self.pages:
            self.pages[key] = widget
            self.stack.addWidget(widget)
        if self.stage == 'layout' and key != 'layout':
            self.editor._clear_corridor_drawing()
        if self.stage == 'playback' and key != 'playback':
            self.pages['playback'].pause()
        self.stage = key
        self.stack.setCurrentWidget(widget)
        self.editor.ribbon_tabs.setVisible(key == 'layout')
        properties_visible = key == 'layout' or (key == 'configuration' and (self.selected_configuration is not None or self.properties.pending))
        self.properties.setVisible(properties_visible)
        property_layout = (key, properties_visible)
        if property_layout != self._property_layout:
            self._property_layout = property_layout
            self.properties.setMaximumWidth(10000 if key == 'configuration' else 410)
            if properties_visible:
                self.splitter.setSizes([200, 280, 900] if key == 'configuration' else [200, 960, 300])
        self._navigating = True
        try:
            self.tree.setCurrentItem(self.items[key])
        finally:
            self._navigating = False
        index = [s[0] for s in STAGES].index({'demand': 'checks', 'playback': 'review', 'appearance': 'project', 'route_display': 'layout'}.get(key, key))
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < len(STAGES) - 1)
        self.refresh()

    def step(self, delta):
        if delta == 1 and self.stage == 'playback':
            self.editor.show_project_report(self.pages['playback'].directory)
            return
        runs = getattr(self.editor, 'project_runs_panel', None)
        if delta == 1 and runs is not None and runs.selected_path() is not None:
            if self.stage == 'simulate':
                runs.investigate()
                return
            if self.stage == 'review':
                runs.report()
                return
        keys = [s[0] for s in STAGES]
        index = keys.index({'demand': 'checks', 'playback': 'review', 'appearance': 'project', 'route_display': 'layout'}.get(self.stage, self.stage)) + delta
        if 0 <= index < len(keys):
            self.activate(keys[index])

    def refresh(self, dirty=None):
        path = self.editor.current_json_path
        project = self.editor.project
        title = Path(path).name if path else 'Unsaved project'
        revision = f"\nRevision {project.revisions[-1]['id'][:8]}" if project and project.revisions else ''
        if dirty is None:
            dirty = self.editor.has_unsaved_changes() if hasattr(self.editor, '_saved_state') else False
        self.project_label.setText(title + revision + ('\nUnsaved changes' if dirty else ''))
        self.project_label.setToolTip(str(path or 'Save a project to start revision history.'))
        points = self.editor.store.all_points()
        edges = self.editor.store.data.get('corridors', {}).get('edges', [])
        floors = tuple(sorted({int(p['floor']) for p in points.values()}))
        objects = (tuple(sorted((name, int(p['floor']), p['kind']) for name, p in points.items())),
                   tuple((e.get('from'), e.get('to'), e.get('bidirectional', True)) for e in edges))
        if objects != self._objects:
            self._objects = objects
            self._floors = floors
            self.tree.blockSignals(True)
            try:
                item = self.items['layout']
                expanded = {key for key, row in self.object_items.items() if row.isExpanded()}
                item.takeChildren()
                self.object_items = {}
                groups = {}
                for floor in floors:
                    child = QTreeWidgetItem([f'Floor {floor}'])
                    child.setData(0, Qt.UserRole, ('floor', floor))
                    item.addChild(child)
                    self.object_items[('floor', floor)] = child
                    for kind, label in [('location', 'Locations'), ('corridor_node', 'Corridor nodes / doors'),
                                        ('lift_node', 'Lift stops'), ('department', 'Departments'), ('edge', 'Corridors')]:
                        group = QTreeWidgetItem([label])
                        child.addChild(group)
                        groups[floor, kind] = group
                        self.object_items[('group', floor, kind)] = group
                for name, point in sorted(points.items()):
                    row = QTreeWidgetItem([name])
                    key = ('point', name)
                    row.setData(0, Qt.UserRole, key)
                    row.setToolTip(0, f"{point['kind'].replace('_', ' ')} | floor {point['floor']}")
                    groups[int(point['floor']), point['kind']].addChild(row)
                    self.object_items[key] = row
                unresolved = None
                for index, edge in enumerate(edges):
                    arrow = '↔' if edge.get('bidirectional', True) else '→'
                    row = QTreeWidgetItem([f"{edge.get('from')} {arrow} {edge.get('to')} [{index + 1}]"])
                    key = ('edge', index)
                    row.setData(0, Qt.UserRole, key)
                    start = points.get(edge.get('from'))
                    if start:
                        groups[int(start['floor']), 'edge'].addChild(row)
                    else:
                        if unresolved is None:
                            unresolved = QTreeWidgetItem(['Unresolved corridors'])
                            item.addChild(unresolved)
                        unresolved.addChild(row)
                    self.object_items[key] = row
                for key in expanded:
                    if key in self.object_items:
                        self.object_items[key].setExpanded(True)
                item.setExpanded(True)
            finally:
                self.tree.blockSignals(False)
        self.refresh_configuration_objects()
        self.properties.refresh()
        self.filter_objects()
        if self.stage == 'layout' and not self.properties.pending:
            target = self.properties.selection()
            if target and len(target[1]) == 1:
                key = ('point' if target[0] == 'points' else 'edge', target[1][0])
                row = self.object_items.get(key)
                if row is not None:
                    self.tree.blockSignals(True)
                    self.tree.setCurrentItem(row)
                    self.tree.blockSignals(False)
        elif self.stage == 'configuration' and self.selected_configuration is not None:
            section, keys = self.selected_configuration
            row = self.configuration_items.get(('config', section, keys[0]))
            if row is not None:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(row)
                self.tree.blockSignals(False)

    def refresh_configuration_objects(self):
        from configuration_properties import SECTIONS
        config = self.editor.store.data
        catalogue = []
        for section, (title, identity) in SECTIONS.items():
            source = config.get(section, {} if section == 'route_profiles' else [])
            entries = [(name, name) for name in source] if section == 'route_profiles' else [
                (index, str(row.get(identity, f'Unnamed record {index + 1}'))) for index, row in enumerate(source)]
            catalogue.append((section, title, tuple(entries)))
        signature = tuple(catalogue)
        if signature == self._configuration_objects:
            return
        self._configuration_objects = signature
        expanded = {key for key, item in self.configuration_items.items() if item.isExpanded()}
        self.tree.blockSignals(True)
        try:
            self.items['configuration'].takeChildren()
            self.configuration_items = {}
            for section, title, entries in catalogue:
                group = QTreeWidgetItem([f'{title} ({len(entries)})'])
                self.items['configuration'].addChild(group)
                self.configuration_items[('group', section)] = group
                for key, label in entries:
                    item = QTreeWidgetItem([label])
                    token = ('config', section, key)
                    item.setData(0, Qt.UserRole, token)
                    item.setToolTip(0, title + ': ' + label)
                    group.addChild(item)
                    self.configuration_items[token] = item
            for key in expanded:
                if key in self.configuration_items:
                    self.configuration_items[key].setExpanded(True)
        finally:
            self.tree.blockSignals(False)

    def select_configuration(self, section, key):
        self.selected_configuration = (section, (key,))
        self.configuration()

    def filter_objects(self, *_):
        if not hasattr(self, 'items'):
            return
        query = self.search.text().strip().casefold()
        def visit(item, parent_match=False):
            own_match = parent_match or not query or query in item.text(0).casefold()
            child_matches = [visit(item.child(i), own_match) for i in range(item.childCount())]
            visible = own_match or any(child_matches)
            item.setHidden(not visible)
            if query and any(child_matches):
                item.setExpanded(True)
            return visible
        for root in (self.items['layout'], self.items['configuration']):
            for index in range(root.childCount()):
                visit(root.child(index))

    def select_object(self, key):
        editor = self.editor
        points = editor.store.all_points()
        editor.selected_point_names.clear()
        editor.selected_point_name = None
        editor.selected_edge_keys.clear()
        self.selected_edge_record = None
        if key[0] == 'point':
            point = points.get(key[1])
            if point is None:
                return
            editor.selected_point_name = key[1]
            editor.selected_point_names = {key[1]}
            names = [key[1]]
        else:
            edges = editor.store.data.get('corridors', {}).get('edges', [])
            if not 0 <= key[1] < len(edges):
                return
            edge = edges[key[1]]
            names = [edge['from'], edge['to']]
            editor.selected_edge_keys = {tuple(sorted(names))}
            self.selected_edge_record = key[1]
        available = [points[name] for name in names if name in points]
        if available:
            editor.floor_spin.setValue(int(available[0]['floor']))
        self.show_page('layout', editor.canvas)
        editor.refresh_canvas()
        if available:
            editor.canvas.centerOn(sum(float(p['x']) for p in available) / len(available),
                                   -sum(float(p['y']) for p in available) / len(available))

    def configuration(self):
        if 'configuration' not in self.pages:
            content = QWidget()
            layout = QVBoxLayout(content)
            intro = QLabel('Select a robot, payload, lift, task or route profile under Configuration in the project tree to edit its properties here. Changes share the project undo history. The full editors below provide nested slots, schedules and other options. Preview demand and run checks before simulation.')
            intro.setWordWrap(True)
            layout.addWidget(intro)
            for title, method in CONFIGURATION:
                button = QPushButton(title)
                button.clicked.connect(getattr(self.editor, method))
                layout.addWidget(button)
            layout.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(content)
            self.show_page('configuration', scroll)
        else:
            self.show_page('configuration', self.pages['configuration'])
