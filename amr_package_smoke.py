"""Installed-package run and report check; invoked by the hidden launcher flag."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        guide = root / 'docs' / 'quick-start' / 'AMR-Simulator-Quick-Start.pdf'
        small_map = root / 'docs' / 'quick-start' / 'small-map.json'
        if not (guide.is_file() and guide.read_bytes().startswith(b'%PDF-') and small_map.is_file()):
            raise ValueError('Installed guide or exercise input is missing.')
        if not getattr(sys, 'frozen', False):
            sys.path.insert(0, str(root / 'visualiser'))
        from app import AMRGraphEditor  # Loads the delivered Qt workbench modules.
        from quick_start import EXERCISES, application_root
        if len(EXERCISES) != 2 or application_root() != root:
            raise ValueError('Installed walkthrough could not resolve its two exercises.')

        from amr_project import Project
        from amr_project_runs import PreparedRun, read_json
        from amr_project_report import report_sections
        from amr_run_evidence import software_snapshot
        from visualiser.project_checks import check_project

        source = software_snapshot()
        if not source['files'] or 'amr_project_report.py' not in source['files'] or 'visualiser/quick_start.py' not in source['files']:
            raise ValueError('The installed application source fingerprint is incomplete.')
        config = json.loads(small_map.read_text(encoding='utf-8'))
        config['corridors']['edges'].append({'from': 'B', 'to': 'C', 'width_m': 2})
        project = Project()
        project.save(output / 'small-map.amrproj', config, base_dir=small_map.parent)
        prepared = PreparedRun(project, output / 'results')
        checks = check_project(prepared.config)
        checks.acknowledge_warnings()
        prepared.commit(checks)
        if getattr(sys, 'frozen', False):
            command = [str(root / 'AMRSimulatorWorker.exe')]
        else:
            command = [sys.executable, str(root / 'amr_app.py')]
        finished = subprocess.run(command + ['--run-project', str(prepared.directory)],
                                  cwd=output, text=True, capture_output=True, timeout=120)
        if finished.returncode:
            raise ValueError(f'Installed run worker failed: {finished.stdout}\n{finished.stderr}')
        manifest = read_json(prepared.directory / 'run_manifest.json')
        evidence = read_json(prepared.directory / 'simulation_steps.csv.run.json')
        if (manifest['status'] != 'complete' or manifest['completed_tasks'] != 1
                or manifest['failed_tasks'] != 0 or evidence['summary'].get('pending_task_ids')):
            raise ValueError('The installed small-map run did not complete as expected.')
        sections = [report_sections()[0][0]]
        pdf = output / 'report' / 'report.pdf'
        finished = subprocess.run(command + ['--generate-report', str(prepared.directory), str(pdf.parent),
                                             '--sections', ','.join(sections)],
                                  cwd=output, text=True, capture_output=True, timeout=120)
        if finished.returncode:
            raise ValueError(f'Installed report worker failed: {finished.stdout}\n{finished.stderr}')
        if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
            raise ValueError('The installed report export did not produce a PDF.')
        gui = small_map_gui(project.path, prepared.directory, output)
        result = {'status': 'passed', 'project': str(project.path), 'run': str(prepared.directory),
                  'report': str(pdf), 'completed': 1, 'failed': 0,
                  'software_sha256': source['sha256'], 'gui': gui,
                  'excluded': 'LTN tests and workloads'}
        (output / 'smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return 0
    except Exception:
        (output / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        return 1


def small_map_gui(project, directory, output):
    """Open the real installed workbench, compact settings, Review and Report."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from app import AMRGraphEditor
    from dialogs import SimulationSettingsDialog
    from amr_results_investigation import load_investigation
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    editor = AMRGraphEditor()
    before = {name: (Path(directory) / name).read_bytes() for name in ('config.json', 'simulation_steps.csv')}
    project_before = Path(project).read_bytes()
    try:
        if not editor.load_json_file(str(project), load_drawings=False):
            raise ValueError('The installed GUI could not reopen the practice project.')
        editor.resize(1280, 800)
        editor.show()
        app.processEvents()
        editor.grab().save(str(output / 'installed-layout.png'))
        settings = SimulationSettingsDialog(editor, full_config=editor.store.data)
        try:
            if settings.mode_combo.currentData() != 'simple' or settings.delivery_tabs.count() != 4:
                raise ValueError('The installed Simple settings do not match the delivered layout.')
            settings.show()
            app.processEvents()
            settings.grab().save(str(output / 'installed-simulation-settings.png'))
            settings.reject()
        finally:
            settings.deleteLater()
        editor.workbench.show_quick_start()
        walkthrough = editor.workbench.quick_start_dialog
        walkthrough.exercise.setCurrentIndex(0)
        walkthrough.close()
        editor.show_results_investigation()
        investigation = load_investigation(directory)
        if not investigation['tasks'] or any(not row['matches'] for row in investigation['reconciliation']):
            raise ValueError('The installed task outcomes do not reconcile with event evidence.')
        editor.results_panel.accept_result(investigation)
        editor.results_panel.tasks.selectRow(0)
        app.processEvents()
        editor.grab().save(str(output / 'installed-review.png'))
        editor.show_project_playback(directory)
        deadline = time.monotonic() + 45
        while editor.playback_panel.jobs:
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError('The installed playback did not finish loading.')
            time.sleep(.02)
        if editor.playback_panel.viewer is None:
            raise ValueError(editor.playback_panel.summary.text())
        app.processEvents()
        editor.grab().save(str(output / 'installed-playback.png'))
        editor.show_project_report(directory)
        app.processEvents()
        editor.grab().save(str(output / 'installed-report.png'))
    finally:
        editor.close()
        editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    if project_before != Path(project).read_bytes() or any(
            contents != (Path(directory) / name).read_bytes() for name, contents in before.items()):
        raise ValueError('Read-only installed GUI review modified saved project or run inputs.')
    return dict(project_reopened=True, compact_simple_settings=True, walkthrough=True,
        reconciled_investigation=True, playback=True, report_workspace=True, inputs_unchanged=True)


def run_ltn(output):
    """Exercise the supplied LTN archive with the installed run and report worker."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    def mark(stage):
        (output / 'ltn-progress.txt').write_text(stage + '\n', encoding='utf-8')
    try:
        mark('checking bundled files')
        temp_root = output / 'temp'
        temp_root.mkdir(exist_ok=True)
        tempfile.tempdir = str(temp_root)
        root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        ltn = root / 'examples' / 'ltn.amrproj'
        if not getattr(sys, 'frozen', False):
            ltn = root / 'ltn.amrproj'
        guide = root / 'docs' / 'quick-start' / 'AMR-Simulator-Quick-Start.pdf'
        if not ltn.is_file() or not guide.is_file() or not guide.read_bytes().startswith(b'%PDF-'):
            raise ValueError('The LTN exercise or illustrated guide is missing.')
        if not getattr(sys, 'frozen', False):
            sys.path.insert(0, str(root / 'visualiser'))

        from PySide6.QtWidgets import QApplication
        from app import AMRGraphEditor
        from quick_start import QuickStartDialog, EXERCISES
        from amr_project import Project
        from amr_project_runs import PreparedRun, read_json
        from amr_project_report import report_sections
        from amr_results_investigation import load_investigation
        from visualiser.project_checks import check_project

        mark('creating Qt workbench')
        app = QApplication.instance() or QApplication([])
        editor = AMRGraphEditor()
        try:
            mark('opening LTN drawings')
            if not editor.load_json_file(str(ltn), load_drawings=True):
                raise ValueError('The installed workbench could not open the LTN project and drawings.')
            mark('waiting for LTN drawings')
            expected_floors = set(editor._all_mapped_floors())
            deadline = time.monotonic() + 120
            while expected_floors - set(editor._dxf_cache):
                app.processEvents()
                if editor._loading_batch_failed:
                    raise ValueError(f'Installed DXF load failed on floors {sorted(editor._loading_batch_failed)}.')
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'Installed DXF load did not finish: {sorted(expected_floors - set(editor._dxf_cache))}.')
                time.sleep(0.05)
            if not expected_floors:
                raise ValueError('The supplied LTN project has no DXF drawing floors.')
            mark('opening walkthrough')
            editor.workbench.show_quick_start()
            dialog = editor.workbench.quick_start_dialog
            dialog.exercise.setCurrentIndex(1)
            if (not isinstance(dialog, QuickStartDialog) or len(EXERCISES) != 2
                    or dialog.steps.count() != len(EXERCISES[1]['steps'])):
                raise ValueError('The installed LTN walkthrough did not open.')
            for index, (_title, _action, _expected, stage) in enumerate(EXERCISES[1]['steps']):
                dialog.steps.setCurrentRow(index)
                if stage not in editor.workbench.stages:
                    raise ValueError(f'The walkthrough refers to a missing workspace: {stage}')
            dialog.close()
        finally:
            mark('closing Qt workbench')
            editor.close()
            app.processEvents()

        mark('preparing bounded project')
        source = Project.open(ltn)
        config = source.configuration()
        if config['simulation']['start_datetime'] != '2026-01-01T05:00:00':
            raise ValueError('The supplied LTN start differs from the guide.')
        config['simulation']['end_datetime'] = '2026-01-01T11:00:00'
        source.save(output / 'ltn-bounded.amrproj', config, label='Six-hour guide exercise')
        prepared = PreparedRun(source, output / 'results')
        checks = check_project(prepared.config)
        overlap = {f.object_name for f in checks.findings if f.code == 'LOCAL_BAY_ENTRY_OVERLAP'}
        if not any('D29' in str(item) for item in overlap):
            raise ValueError('The installed project checks omitted the LTN bay-entry warning.')
        checks.acknowledge_warnings()
        prepared.commit(checks)
        mark('running bounded LTN')
        if getattr(sys, 'frozen', False):
            command = [str(root / 'AMRSimulatorWorker.exe')]
        else:
            command = [sys.executable, str(root / 'amr_app.py')]
        finished = subprocess.run(command + ['--run-project', str(prepared.directory)],
                                  cwd=output, text=True, capture_output=True)
        if finished.returncode:
            raise ValueError(f'Installed LTN run worker failed: {finished.stdout}\n{finished.stderr}')
        manifest = read_json(prepared.directory / 'run_manifest.json')
        evidence = read_json(prepared.directory / 'simulation_steps.csv.run.json')
        investigation = load_investigation(prepared.directory)
        if manifest['status'] != 'complete' or not investigation['tasks']:
            raise ValueError('The installed LTN run did not produce inspectable task outcomes.')
        if any(not item['matches'] for item in investigation['reconciliation']):
            raise ValueError('The installed LTN outcome counts do not reconcile with events.')
        mark('following investigation identities')
        from results_investigation_panel import ResultsInvestigationPanel
        panel = ResultsInvestigationPanel()
        related_task = ''
        try:
            panel.accept_result(investigation)
            for index, task in enumerate(panel.task_rows):
                panel.tasks.selectRow(index)
                if {kind for kind, _identity in panel.related_choices} >= {'task', 'payload', 'journey', 'lift'}:
                    related_task = task['task_id']
                    break
            if not related_task:
                raise ValueError('The installed investigation cannot follow LTN task identities.')
            for index, (kind, identity) in enumerate(panel.related_choices):
                if kind == 'task':
                    continue
                field = {'payload': 'payload_instance_id', 'journey': 'journey_id', 'lift': 'lift_id'}[kind]
                panel.follow.setCurrentIndex(index)
                expected_ids = {event['id'] for event in investigation['events'] if event[field] == identity}
                if (not expected_ids or {event['id'] for event in panel.event_rows} != expected_ids
                        or panel.selected_evidence[0] != kind):
                    raise ValueError(f'Installed {kind} investigation lost matching LTN evidence.')
        finally:
            panel.close()
            app.processEvents()
        mark('generating report')
        sections = [report_sections()[0][0]]
        pdf = output / 'report' / 'report.pdf'
        finished = subprocess.run(command + ['--generate-report', str(prepared.directory), str(pdf.parent),
                                             '--sections', ','.join(sections)],
                                  cwd=output, text=True, capture_output=True)
        if finished.returncode:
            raise ValueError(f'Installed LTN report worker failed: {finished.stdout}\n{finished.stderr}')
        if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
            raise ValueError('The installed LTN report did not produce a PDF.')
        result = {'status': 'passed', 'source_project': str(ltn), 'bounded_project': str(source.path),
                  'run': str(prepared.directory), 'report': str(pdf),
                  'completed': manifest['completed_tasks'], 'failed': manifest['failed_tasks'],
                  'pending': len(evidence['summary'].get('pending_task_ids', [])),
                  'events': len(investigation['events']), 'tasks': len(investigation['tasks']),
                  'related_timeline_task': related_task,
                  'loaded_dxf_floors': sorted(expected_floors),
                  'warning_locations': sorted(map(str, overlap)),
                  'reconciliation': investigation['reconciliation']}
        (output / 'ltn-smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        mark('passed')
        return 0
    except Exception:
        (output / 'ltn-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        return 1
