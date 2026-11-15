"""Offscreen visual check of the built-in fleet speed sweep controls."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'visualiser'))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from app import AMRGraphEditor
from models import JsonStore
from scenario_stress_panel import ScenarioStressDialog

if __name__ == '__main__':
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI', 10))
    editor = AMRGraphEditor()
    state = json.loads((ROOT / 'Lift stress.stress.json').read_text(encoding='utf-8'))
    editor.store = JsonStore(state['config'])
    dialog = ScenarioStressDialog(editor)
    dialog.test_mode.setCurrentIndex(1)
    dialog.show()
    dialog.resize(1080, 760)
    app.processEvents()
    dialog.grab().save(str(ROOT / 'verification' / 'amr-speed-sweep-setup.png'))
    dialog.close()
    with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
        editor.close()
