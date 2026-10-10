"""Two-exercise, nonmodal walkthrough for the delivered project workbench."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)


EXERCISES = (
    {
        'title': 'Small connected map',
        'steps': (
            ('Open the practice map',
             'Choose Open exercise project below, or File → Open project / JSON and select docs/quick-start/small-map.json from the application folder.',
             'Layout shows A, B and C, with only A–B connected. Configuration contains two robot types, R1 and R2, and task T1. C is intentionally disconnected.',
             'layout'),
            ('Connect the last corridor',
             'In Layout choose Corridor. Click B, then C, using endpoint snapping. Press blank Enter to finish the drawing command.',
             'The graph has A–B and B–C. The new section is one undoable edit. Escape before the second point cancels the uncommitted segment.',
             'layout'),
            ('Save the project',
             'Choose File → Save project as and save small-map.amrproj in a folder you can find again.',
             'The title shows the .amrproj file. Reopen it later to confirm the B–C connection and both robot types.',
             'layout'),
            ('Run Project checks',
             'Open Check and choose Run checks. Review the findings; use Go to affected settings for any issue.',
             'The unreachable-task warning from the starting map is gone. This fixture has no check errors or warnings after B–C is connected; informational model-scope notes remain.',
             'checks'),
            ('Save a simulation run',
             'Open Simulate and choose Save, check and simulate. Review the checks dialog and start the run.',
             'A completed run appears in the project’s run list and is saved in its external results folder. The reference input has one completed task, zero failed and zero pending.',
             'simulate'),
            ('Inspect the result',
             'Select that run and choose Investigate selected run. Search for task T1 and open its supporting events; Playback selected run shows the recorded path.',
             'Review shows T1 as completed, with its task timeline and linked event rows. The saved run uses frozen inputs even if the editable project changes later.',
             'review'),
            ('Export a report',
             'Return to Simulate, select the run and choose Report selected run. In Report select sections and choose Generate report.',
             'The report is saved under that run’s reports folder. Open generated PDF views it; the run’s CSV evidence remains alongside the saved run.',
             'report'),
        ),
    },
    {
        'title': 'Supplied LTN project',
        'steps': (
            ('Open LTN',
             'Choose Open exercise project below, or File → Open project / JSON and select the supplied LTN project.',
             'Layout shows the hospital graph and its floors. If you opened JSON, save it as .amrproj before running so the inputs and available drawings are captured.',
             'layout'),
            ('Choose a bounded run window',
             'In Configuration → Simulation settings choose Simple and set the end of the supplied 1 January 2026 start day to 11:00. Keep other inputs unchanged, then save the project.',
             'The configured window is 05:00–11:00 on 1 January 2026. This bounded exercise avoids waiting for the full multi-day LTN run.',
             'configuration'),
            ('Review checks and layout risk',
             'Open Check, choose Run checks, and search for LOCAL_BAY_ENTRY_OVERLAP. Select a finding and choose Go to affected settings. Review all warnings before acknowledging them.',
             'Project checks navigate to affected drop-off locations, including D29, D32, D33, D35, D38, D39 and D41 in the supplied input. These are bay-bound risks, not proof that every task fails.',
             'checks'),
            ('Save the bounded run',
             'Open Simulate and choose Save, check and simulate. Confirm the checked inputs and start the run; do not edit the project while it runs.',
             'The run appears in the saved run list when the process finishes. Its configuration, checks and event log are frozen in the external results folder.',
             'simulate'),
            ('Investigate outcomes',
             'Select the saved run and choose Investigate selected run. Filter by outcome or task, then follow its task, journey, payload and lift records.',
             'Review distinguishes completed, failed and pending-at-stop work. A six-hour run of the supplied portable LTN archive recorded 206 completed, zero failed and zero pending; edited inputs or other software revisions may differ.',
             'review'),
            ('Export the LTN report',
             'Return to Simulate, choose Report selected run, select report sections and choose Generate report.',
             'A PDF and supporting run CSV records are available under the selected run’s external folder. Report uses the frozen run, not current editable inputs.',
             'report'),
        ),
    },
)


REFERENCE = (
    ('Compact settings', 'Task generation keeps categories on the left and department/group actions above focused settings tabs. Department settings use Details, Hours & waste, and Task locations & zones; Save there, then Save in the Departments list. Simulation settings keep four tabs; Run period groups Mode, Demand window, and Release and deferral. Show mode details reveals the complete findings. New projects and the small-map exercise use Simple mode.'),
    ('Project checks', 'Run checks after editing. Errors need correction; acknowledge only warnings you have reviewed. Go to affected settings navigates current findings. An edit makes the prior review stale.'),
    ('Demand preview', 'Configuration → Demand preview lets you choose dates and filters, inspect generated tasks and the weekly timetable, and read zero-work explanations before running.'),
    ('Snaps and selection', 'The Layout toolbar selects grid and object snaps. Left-to-right windows enclose objects; right-to-left windows touch them. Shift or Ctrl changes a selection. Selection does not open Properties automatically.'),
    ('Undo and layers', 'Use Undo/Redo for graph edits. View → Model layers controls assignment, visibility, locks and drawing style. Route permissions are separate. View → DXF layers changes imported underlay visibility only.'),
    ('Run investigation', 'Simulate lists revision-bound runs. Investigate selected run filters tasks and links timelines to event evidence. Select a task, then use the timeline choice to follow its recorded payload, journey or lift identity across the run. Pending at stop is a recorded snapshot, not a failed task. Timelines page 500 events at a time; Export selected evidence includes every page of the chosen task, related identity, metric or lift check. Logs above 250,000 events or 300 MiB are rejected without truncation.'),
    ('Report export', 'Select a completed run in Simulate, choose Report selected run, select sections, then Generate report. Open generated PDF and find supporting CSV records under the run’s external folder.'),
)


def application_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


class QuickStartDialog(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setWindowTitle('Guided walkthrough')
        self.setModal(False)
        self.resize(800, 560)
        layout = QVBoxLayout(self)
        intro = QLabel('Follow an exercise or the checked building course while keeping this window open. '
                       'Each step states an action and the expected application state.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        exercise_page = QWidget()
        exercise_layout = QVBoxLayout(exercise_page)
        self.exercise = QComboBox()
        self.exercise.setAccessibleName('Walkthrough exercise')
        for item in EXERCISES:
            self.exercise.addItem(item['title'])
        exercise_layout.addWidget(self.exercise)
        middle = QHBoxLayout()
        self.steps = QListWidget()
        self.steps.setAccessibleName('Walkthrough steps')
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Walkthrough action and expected state')
        middle.addWidget(self.steps, 1)
        middle.addWidget(self.details, 2)
        exercise_layout.addLayout(middle, 1)
        buttons = QHBoxLayout()
        self.previous = QPushButton('Previous step')
        self.next = QPushButton('Next step')
        self.open_stage = QPushButton('Open workspace')
        self.previous.clicked.connect(lambda: self.steps.setCurrentRow(self.steps.currentRow() - 1))
        self.next.clicked.connect(lambda: self.steps.setCurrentRow(self.steps.currentRow() + 1))
        self.open_stage.clicked.connect(self.go_to_workspace)
        for button in (self.previous, self.next, self.open_stage):
            buttons.addWidget(button)
        exercise_layout.addLayout(buttons)
        tabs.addTab(exercise_page, 'Exercises')
        reference_page = QPlainTextEdit()
        reference_page.setReadOnly(True)
        reference_page.setAccessibleName('Quick reference for project controls')
        reference_page.setPlainText('\n\n'.join(f'{title}\n{body}' for title, body in REFERENCE))
        tabs.addTab(reference_page, 'Controls reference')
        from building_tutorial_panel import BuildingCourse
        self.building_course = BuildingCourse(editor, self)
        tabs.addTab(self.building_course, 'Building course')
        self.tabs = tabs
        self.open_example = QPushButton('Open exercise project')
        self.open_example.clicked.connect(self.show_example)
        layout.addWidget(self.open_example)
        self.open_guide = QPushButton('Open illustrated guide')
        self.open_guide.clicked.connect(self.show_guide)
        tabs.currentChanged.connect(lambda i:(self.open_example.setVisible(i!=2),self.open_guide.setVisible(i!=2)))
        layout.addWidget(self.open_guide)
        self.exercise.currentIndexChanged.connect(self.populate_steps)
        self.steps.currentRowChanged.connect(self.show_step)
        self.populate_steps()

    def populate_steps(self, *_):
        self.steps.clear()
        for title, *_rest in EXERCISES[self.exercise.currentIndex()]['steps']:
            self.steps.addItem(title)
        self.steps.setCurrentRow(0)

    def show_step(self, row):
        steps = EXERCISES[self.exercise.currentIndex()]['steps']
        if row < 0 or row >= len(steps):
            self.details.clear()
            self.open_stage.setEnabled(False)
            return
        title, action, expected, stage = steps[row]
        self.details.setPlainText(f'{title}\n\nDo this\n{action}\n\nExpected state\n{expected}')
        self.previous.setEnabled(row > 0)
        self.next.setEnabled(row + 1 < len(steps))
        self.open_stage.setEnabled(bool(stage))
        self.open_stage.setText('Open ' + stage.title())

    def go_to_workspace(self):
        row = self.steps.currentRow()
        steps = EXERCISES[self.exercise.currentIndex()]['steps']
        if 0 <= row < len(steps):
            try:
                self.editor.workspace.activate(steps[row][3])
            except Exception as exc:
                QMessageBox.warning(self, 'Workspace could not open', str(exc))

    def show_guide(self):
        guide = application_root() / 'docs' / 'quick-start' / 'AMR-Simulator-Quick-Start.pdf'
        if not guide.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide))):
            QMessageBox.warning(self, 'Guide could not open',
                                f'The illustrated quick-start PDF could not be opened at:\n{guide}')

    def show_example(self):
        root = application_root()
        if self.exercise.currentIndex() == 0:
            candidates = [root / 'docs' / 'quick-start' / 'small-map.json']
        else:
            candidates = [root / 'examples' / 'ltn.amrproj', root / 'ltn.amrproj', root / 'ltn.json']
        path = next((item for item in candidates if item.is_file()), None)
        if path is None:
            QMessageBox.warning(self, 'Exercise project missing',
                                f'The {self.exercise.currentText()} example was not found beside the application.')
            return
        self.editor.load_json_file(str(path))
