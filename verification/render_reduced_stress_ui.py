"""Render the real project's history and reduced-data setup without running a study."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'visualiser'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app import AMRGraphEditor
from models import JsonStore
from scenario_stress_panel import ScenarioStressDialog
from amr_project import Project
from amr_project_runs import read_json

app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
app.setFont(QFont('Segoe UI', 10))
state = read_json(ROOT / 'ltn.stress.json')
editor = AMRGraphEditor()
editor.project = Project.open(state['source_project'])
editor.current_json_path = state['source_project']
editor.store = JsonStore(state['config'])
dialog = ScenarioStressDialog(editor)
editor.scenario_stress_dialog = dialog
dialog.set_settings({**state['settings'], 'data_mode': 'reduced'})
dialog.show()
app.processEvents()
dialog.setMaximumSize(1600, 1200)
dialog.resize(1240, 1040)
app.processEvents()
dialog.grab().save(str(ROOT / 'verification' / 'reduced-stress-setup.png'))
dialog.tabs.setCurrentIndex(3)
app.processEvents()
dialog.grab().save(str(ROOT / 'verification' / 'reduced-stress-history.png'))
print(f'{dialog.history.rowCount()} previous studies displayed')
dialog.close()
with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
    editor.close()
