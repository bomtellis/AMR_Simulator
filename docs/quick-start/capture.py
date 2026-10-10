"""Capture the current workbench for the illustrated quick-start guide."""
import json
import os
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / 'images'


def main():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'visualiser'))
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from appearance import Appearance, controller
    from app import AMRGraphEditor
    from models import JsonStore
    from amr_recovery import RecoveryStore

    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for filename in ('segoeui.ttf', 'segoeuib.ttf'):
        font = Path('C:/Windows/Fonts') / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI', 10))
    appearance = controller(app)  # In-memory appearance settings during capture.
    appearance.apply(replace(Appearance(), show_legend=False))
    editor = AMRGraphEditor()
    editor._drawings_enabled = False
    editor._recovery_store = RecoveryStore(ROOT / 'tmp' / 'quick-start-recovery')
    editor.resize(1440, 900)
    editor.show()
    try:
        config = json.loads((ROOT / 'docs' / 'quick-start' / 'small-map.json').read_text(encoding='utf-8'))
        config['corridors']['edges'].append({'from': 'B', 'to': 'C', 'width_m': 2})
        editor.store = JsonStore(config)
        editor.refresh_canvas()
        editor.workspace.activate('layout')
        editor.fit_view()
        app.processEvents()
        editor.grab().save(str(OUTPUT / 'small-map-layout.png'))

        editor.validate_json()
        app.processEvents()
        editor.grab().save(str(OUTPUT / 'small-map-checks.png'))

        editor.workbench.show_quick_start()
        app.processEvents()
        editor.workbench.quick_start_dialog.grab().save(str(OUTPUT / 'guided-walkthrough.png'))
        editor.workbench.quick_start_dialog.close()

        ltn = json.loads((ROOT / 'ltn.json').read_text(encoding='utf-8'))
        editor.store = JsonStore(ltn)
        editor.floor_spin.setValue(3)
        editor.show_labels_check.setChecked(False)
        editor.refresh_canvas()
        editor.workspace.activate('layout')
        editor.fit_view()
        app.processEvents()
        editor.grab().save(str(OUTPUT / 'ltn-layout.png'))
        editor.validate_json()
        editor.checks_panel.search.setText('LOCAL_BAY_ENTRY_OVERLAP')
        app.processEvents()
        editor.grab().save(str(OUTPUT / 'ltn-checks.png'))
    finally:
        editor._confirm_unsaved_changes = lambda: True
        editor.close()


if __name__ == '__main__':
    main()
