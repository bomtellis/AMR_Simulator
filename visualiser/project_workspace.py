"""Persistent project navigation around the editor's shared state and panels."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem, QScrollArea)


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
        self._navigating = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        root.addWidget(split)
        sidebar = QWidget()
        nav = QVBoxLayout(sidebar)
        self.project_label = QLabel('Unsaved project')
        self.project_label.setWordWrap(True)
        nav.addWidget(self.project_label)
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
        buttons = QHBoxLayout()
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
        split.setStretchFactor(1, 1)
        split.setSizes([220, 1250])
        sidebar.setMinimumWidth(180)
        self.tree.currentItemChanged.connect(self.selected)
        self.show_page('layout', canvas)
        self.refresh()

    def selected(self, item, _previous):
        if item is None or self._navigating:
            return
        key = item.data(0, Qt.UserRole)
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
            'report': self.editor.show_project_report, 'playback': self.editor.show_project_playback}
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
        self._navigating = True
        try:
            self.tree.setCurrentItem(self.items[key])
        finally:
            self._navigating = False
        index = [s[0] for s in STAGES].index({'demand': 'checks', 'playback': 'review'}.get(key, key))
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
        index = keys.index({'demand': 'checks', 'playback': 'review'}.get(self.stage, self.stage)) + delta
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
        floors = tuple(sorted({int(p['floor']) for p in self.editor.store.all_points().values()}))
        if floors != self._floors:
            self._floors = floors
            self.tree.blockSignals(True)
            try:
                item = self.items['layout']
                item.takeChildren()
                for floor in floors:
                    child = QTreeWidgetItem([f'Floor {floor}'])
                    child.setData(0, Qt.UserRole, ('floor', floor))
                    item.addChild(child)
                item.setExpanded(True)
            finally:
                self.tree.blockSignals(False)

    def configuration(self):
        if 'configuration' not in self.pages:
            content = QWidget()
            layout = QVBoxLayout(content)
            intro = QLabel('Configure the current project. Changes share the layout editor’s undo history. Preview demand and run checks before simulation.')
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
