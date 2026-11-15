"""Create an explicit example selection from existing evidence; no simulations run."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'visualiser'))
from amr_project_runs import read_json
from amr_project_report import generate


def selection():
    paths = [ROOT / 'Lift stress.stress.json', ROOT / 'ltn.stress.json']
    states = [read_json(path) for path in paths]
    chosen = []
    for index, (path, state) in enumerate(zip(paths, states)):
        trials = [r for r in state['results'].values() if r['kind'] != 'baseline']
        records = trials[:1]
        if index == 0:
            failing = next((r for r in trials if not r['metrics']['passed']), None)
            if failing and failing not in records:
                records.append(failing)
        chosen.append(dict(study_path=str(path), study_root=state['root'], trial_ids=[r['id'] for r in records]))
    return states, chosen


if __name__ == '__main__':
    states, chosen = selection()
    if '--ui' in sys.argv:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontDatabase
        from app import AMRGraphEditor
        from models import JsonStore
        from stress_report_selection import StressReportSelectionDialog
        from amr_project import Project
        app = QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        app.setFont(QFont('Segoe UI', 10))
        editor = AMRGraphEditor()
        editor.project = Project.open(states[0]['source_project'])
        editor.current_json_path = states[0]['source_project']
        editor.store = JsonStore(states[0]['config'])
        dialog = StressReportSelectionDialog(editor, chosen)
        dialog.show()
        dialog.resize(1200, 800)
        app.processEvents()
        dialog.grab().save(str(ROOT / 'verification' / 'stress-report-selection.png'))
        dialog.close()
        with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
            editor.close()
    else:
        target = ROOT / 'output' / 'pdf' / 'stress-test-selection-example'
        print(generate(states[0]['results']['baseline']['directory'], target, ['stress_tests'],
                       report_title='Stress-test selection example', stress_selection=chosen))
