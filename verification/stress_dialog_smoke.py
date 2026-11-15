"""Small visible dialog for checking the native overwrite picker without user data."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'visualiser'))
os.environ.pop('QT_QPA_PLATFORM', None)
from PySide6.QtWidgets import QApplication
from app import AMRGraphEditor
from models import JsonStore
from scenario_stress_panel import ScenarioStressDialog
from tests.test_scenario_study import config
from amr_scenario_study import create_study, default_settings

os.environ['QT_QPA_PLATFORM'] = 'windows'
app = QApplication([])
editor = AMRGraphEditor()
editor.store = JsonStore(config())
directory = ROOT / 'tmp' / 'stress-dialog-native-audit'
directory.mkdir(exist_ok=True)
editor.current_json_path = str(directory / 'native-overwrite.json')
dialog = ScenarioStressDialog(editor)
editor.scenario_stress_dialog = dialog
dialog.setWindowTitle('Stress dialog audit - disposable example')
settings = {**default_settings(editor.store.data), 'assets': [['amr', 'R']], 'trial_budget': 1}
dialog.set_settings(settings)
path = directory / 'native-overwrite.stress.json'
if not path.exists():
    create_study(editor.store.data, path, settings)
editor.setWindowTitle('Stress dialog audit - isolated editor')
editor.show()
dialog.show()
raise SystemExit(app.exec())
