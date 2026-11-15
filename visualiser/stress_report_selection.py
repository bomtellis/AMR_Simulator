"""Explicit trial checkboxes across saved stress studies for the final PDF."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QFileDialog, QDialogButtonBox, QHeaderView)

from amr_project_runs import read_json
from amr_scenario_study import validate_study_document
from amr_stress_history import discover_studies


class StressReportSelectionDialog(QDialog):
    def __init__(self, editor, selection=(), known=(), parent=None):
        super().__init__(parent or editor)
        self.editor = editor
        self.known = list(known) + [item['study_path'] for item in selection]
        self.setWindowTitle('Select stress tests for PDF')
        self.resize(1040, 640)
        layout = QVBoxLayout(self)
        note = QLabel('Tick individual trials, or tick a study to include all its saved trials. '
                      'You can select trials from multiple studies. Each study’s normal-operation baseline is included automatically. '
                      'Results are verified when you generate the PDF.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(['Study / trial', 'Saved outcome', 'Affected assets', 'Added delay (s)'])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 3):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tree.setColumnWidth(2, 330)
        self.tree.itemChanged.connect(self.update_count)
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton('Add study files…')
        self.add_button.clicked.connect(self.add_files)
        self.all_button = QPushButton('Select all trials')
        self.all_button.clicked.connect(lambda: self.check_all(Qt.Checked))
        self.clear_button = QPushButton('Clear selection')
        self.clear_button.clicked.connect(lambda: self.check_all(Qt.Unchecked))
        for button in (self.add_button, self.all_button, self.clear_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.count = QLabel()
        layout.addWidget(self.count)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.populate(selection)

    def populate(self, selection):
        selected = {(str(Path(item['study_path']).resolve()), item['study_root'], identity)
                    for item in selection for identity in item['trial_ids']}
        project = self.editor.project
        source = getattr(project, 'path', None) or self.editor.current_json_path
        saved = self.editor.store.scenario_testing().get('stress_test', {}).get('study_path')
        entries = discover_studies(source, project_id=getattr(project, 'project_id', None),
            known=[*self.known, saved], results_root=project.results_root() if project and project.path else None)
        self.tree.blockSignals(True)
        self.tree.clear()
        for entry in entries:
            path = entry['path']
            parent = QTreeWidgetItem([path.name, entry['status'], '', ''])
            parent.setToolTip(0, str(path))
            self.tree.addTopLevelItem(parent)
            try:
                state = read_json(path)
                validate_study_document(state)
                if state['status'] == 'running' or 'baseline' not in state['results']:
                    raise ValueError('Stop or finish the study and save its baseline before reporting.')
                parent.setData(0, Qt.UserRole, dict(study_path=str(path), study_root=state['root']))
                parent.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                records = [r for r in state['results'].values() if r['kind'] != 'baseline'] or [state['results']['baseline']]
                for record in records:
                    m = record['metrics']
                    assets = '; '.join(event['resource_type'] + ': ' + ', '.join(event['resource_ids'])
                                       for event in record['events']) or 'Normal operation'
                    child = QTreeWidgetItem([record['name'], 'Pass' if m['passed'] else 'Does not pass',
                        assets, f"{m['added_delay_sec']:.3f}"])
                    child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    child.setData(0, Qt.UserRole, record['id'])
                    child.setToolTip(0, record['directory'])
                    child.setToolTip(2, '\n'.join(
                        f"{event['resource_type']}: {', '.join(event['resource_ids'])}\n"
                        f"{event.get('start_datetime', event.get('start_time', ''))} to "
                        f"{event.get('end_datetime', event.get('end_time', ''))}; "
                        f"availability {event['availability_percent']:g}%, speed {100 * event['speed_factor']:g}%"
                        for event in record['events']) or 'Normal operation')
                    parent.addChild(child)
                    child.setCheckState(0, Qt.Checked if (str(path), state['root'], record['id']) in selected else Qt.Unchecked)
                parent.setExpanded(True)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                parent.setText(1, 'Unavailable')
                parent.setToolTip(1, str(exc))
                parent.setFlags(Qt.ItemIsEnabled)
        self.tree.blockSignals(False)
        self.update_count()

    def selection(self):
        result = []
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            identities = [parent.child(i).data(0, Qt.UserRole) for i in range(parent.childCount())
                          if parent.child(i).checkState(0) == Qt.Checked]
            if identities:
                result.append(dict(**parent.data(0, Qt.UserRole), trial_ids=identities))
        return result

    def update_count(self, *_):
        selection = self.selection()
        self.count.setText(f"{sum(len(s['trial_ids']) for s in selection)} trials selected from {len(selection)} studies.")

    def check_all(self, state):
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            if parent.childCount():
                parent.setCheckState(0, state)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add stress studies', '', 'Stress studies (*.stress.json);;JSON (*.json)')
        if paths:
            selected = self.selection()
            self.known.extend(paths)
            self.populate(selected)
