"""Repeatable Simple delivery QA and real-widget captures; no LTN workloads."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'test_compact_delivery_dialogs', 'test_project_setup', 'test_building_settings',
    'test_cad_workspace', 'test_cad_selection', 'test_cad_edge_tool',
    'test_cad_snap_controls', 'test_corridor_drawing', 'test_corridor_editing',
    'test_crossing_junction', 'test_edit_history', 'test_model_layers',
    'test_project_storage', 'test_recovery', 'test_project_workspace',
    'test_project_runs', 'test_project_playback', 'test_playback_timeline',
    'test_persistent_run_links', 'test_project_editing_lock', 'test_workbench_lifecycle',
    'test_project_checks', 'test_demand_preview',
    'test_generation_provenance', 'test_generation_contracts', 'test_department_location_contracts',
    'test_department_draft_transactions', 'test_generation_settings',
    'test_generation_input_validation', 'test_simulation_run_controls',
    'test_simulation_mode_dialog', 'test_simulation_mode_evidence', 'test_simulation_modes',
    'test_results_investigation', 'test_partial_run', 'test_report_structure',
    'test_report_kpis', 'test_quick_start', 'test_zoom_selection',
    'test_partial_project_runs', 'test_partial_playback',
)


def snapshot(output):
    from verification.run import source_manifest
    identity = source_manifest()
    with zipfile.ZipFile(output / 'source-snapshot.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, expected in identity['files'].items():
            data = (ROOT / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f'Source changed during snapshot: {name}')
            archive.writestr(name, data)
    (output / 'source.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
    return identity


def capture(output):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    sys.path.insert(0, str(ROOT / 'visualiser'))
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QTabWidget
    from app import AMRGraphEditor
    from dialogs import DepartmentEditorDialog, SimulationSettingsDialog, TaskGenerationSettingsDialog
    from tests.test_generation_reference import grouped_config
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    editor = AMRGraphEditor()
    editor._drawings_enabled = False
    config = grouped_config()
    factories = {
        'task-generation': lambda: TaskGenerationSettingsDialog(editor, config['task_generation'],
            ['A', 'B', 'Ward Bay', 'Zone X'], ['Box'], ['clean', 'dirty'], config['departments'], lambda _: None),
        'department': lambda: DepartmentEditorDialog(editor, ['A', 'B', 'Ward Bay', 'Zone X'],
            ['General', 'Clinical'], seed=config['departments'][0],
            task_generation_categories=[('stores', 'Stores', '-STORES'),
                ('catering', 'Catering', '-CAT'), ('waste', 'Waste', '-WASTE')]),
        'simulation-settings': lambda: SimulationSettingsDialog(editor, full_config=config),
    }
    rows = []
    for name, factory in factories.items():
        dialog = factory()
        for width, height in ((1024, 768), (1600, 900)):
            dialog.show()
            app.processEvents()
            # The offscreen platform's synthetic screen is only 800px wide.
            # Apply the requested logical window after the queued screen-fit pass.
            dialog.setMaximumSize(16777215, 16777215)
            dialog.resize(width, height)
            app.processEvents()
            tabs = getattr(dialog, 'delivery_tabs', None)
            indices = range(tabs.count()) if tabs else range(1)
            for index in indices:
                if tabs:
                    tabs.setCurrentIndex(index)
                app.processEvents()
                box = dialog.findChild(QDialogButtonBox)
                buttons = box.buttons() if box else []
                usable = bool(buttons) and all(button.isVisible() and
                    dialog.rect().contains(button.mapTo(dialog, button.rect().topLeft())) and
                    dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight())) for button in buttons)
                rows.append(dict(name=name, size=[dialog.width(), dialog.height()], tab=index,
                    footer_visible=usable, scale=os.environ.get('QT_SCALE_FACTOR', '1')))
                dialog.grab().save(str(output / f'{name}-{width}-tab{index}.png'))
        dialog.reject()
        dialog.deleteLater()
        app.processEvents()
    editor.resize(1024, 768)
    editor.show()
    app.processEvents()
    viewport = editor.canvas.viewport()
    rows.append(dict(name='workbench', canvas_fraction=viewport.width()*viewport.height()/
        (editor.width()*editor.height()), properties_collapsed=editor.workspace.properties.isHidden()))
    editor.grab().save(str(output / 'workbench-1024.png'))
    editor.close()
    (output / 'layout.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps(rows[-1]))
    if not all(row.get('footer_visible', True) for row in rows):
        raise RuntimeError('A dialog footer is clipped; inspect layout.json and captures.')


def qa(output):
    from verification.isolated import run_modules
    from verification.run import source_manifest
    identity = snapshot(output)
    missing = [name for name in MODULES if not (ROOT / 'tests' / f'{name}.py').is_file()]
    if missing:
        raise RuntimeError(f'Unknown QA modules: {missing}')
    started = time.perf_counter()
    result = run_modules(ROOT / 'tests', output, modules=MODULES)
    unchanged = identity['files'] == source_manifest()['files']
    payload = dict(successful=result.wasSuccessful() and unchanged, source_unchanged=unchanged,
        seconds=time.perf_counter()-started, modules=list(MODULES), cases=result.cases,
        excluded='LTN-specific tests, simulations, benchmarks and repairs')
    (output / 'qa.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({key: payload[key] for key in ('successful', 'source_unchanged', 'seconds')}))
    return 0 if payload['successful'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'capture', 'qa'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'temp'
    temporary.mkdir(exist_ok=True)
    os.environ['TMP'] = os.environ['TEMP'] = str(temporary)
    import tempfile
    tempfile.tempdir = str(temporary)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if args.action == 'qa':
        return qa(output)
    if args.action == 'snapshot':
        snapshot(output)
    else:
        capture(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
