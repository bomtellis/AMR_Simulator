"""Run the saved LTN fleet sweep and generate its verified PDF report."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amr_project import Project
from amr_project_runs import read_json, write_json
from amr_run_evidence import file_hash
from amr_scenario_study import amr_speed_sweep_settings, create_study, evaluate
from amr_project_report import generate

STUDY = ROOT / 'LTN AMR speed sweep 2026-10-14.stress.json'
OUTPUT = ROOT / 'output/pdf/ltn-amr-speed-sweep-2026-10-14'
PROGRESS = ROOT / 'verification/ltn-amr-speed-sweep-progress.json'
last_write = last_print = 0.0
last_phase = None


def feedback(event):
    global last_write, last_print, last_phase
    now = time.monotonic()
    phase = event.get('phase')
    changed = phase != last_phase
    if changed or now - last_write >= 10 or event.get('type') == 'complete':
        write_json(PROGRESS, dict(updated=time.strftime('%Y-%m-%d %H:%M:%S'), **event))
        last_write = now
    if changed or now - last_print >= 60 or event.get('type') == 'complete':
        print(json.dumps(event), flush=True)
        last_print = now
    last_phase = phase


def main():
    source = ROOT / 'ltn.amrproj'
    if not STUDY.exists() or '--restart' in sys.argv:
        project = Project.open(source)
        config = project.materialize(ROOT / 'tmp/amr-speed-sweep-source')
        provenance = dict(source=str(source), sha256=file_hash(source),
                          project_id=project.project_id, revision=project.revisions[-1],
                          simulation=config['simulation'])
        write_json(ROOT / 'verification/ltn-amr-speed-sweep-source.json', provenance)
        settings = amr_speed_sweep_settings(config, dict(data_mode='reduced', workers=8, ram_limit_gib=24.0, reserve_ram_gib=8.0))
        create_study(config, STUDY, settings, project=project, overwrite=STUDY.exists())
    state = evaluate(STUDY, feedback=feedback)
    if state['status'] != 'complete':
        raise RuntimeError('Sweep did not complete: ' + state['status'])
    summary = dict(summary=state['speed_sweep'], study=str(STUDY), root=state['root'], results=[])
    for identity, record in state['results'].items():
        metrics = {k: v for k, v in record['metrics'].items() if k not in ('obligations', 'unmet')}
        summary['results'].append(dict(id=identity, name=record['name'], directory=record['directory'], metrics=metrics))
    provenance = read_json(ROOT / 'verification/ltn-amr-speed-sweep-source.json')
    summary['source_archive_unchanged'] = file_hash(source) == provenance['sha256']
    write_json(ROOT / 'verification/ltn-amr-speed-sweep-results.json', summary)
    print(json.dumps(summary), flush=True)
    if OUTPUT.exists():
        if read_json(OUTPUT / 'report_manifest.json').get('status') != 'complete':
            raise RuntimeError('Existing report output is incomplete: ' + str(OUTPUT))
    else:
        feedback(dict(type='phase', phase='Verifying sweep evidence and generating PDF'))
        generate(state['results']['baseline']['directory'], OUTPUT, ['stress_tests'],
                 report_title='LTN AMR speed sweep', stress_selection=[dict(
                     study_path=str(STUDY), study_root=state['root'],
                     trial_ids=[key for key in state['results'] if key != 'baseline'])])
    feedback(dict(type='complete', phase='Sweep and verified PDF complete', pdf=str(OUTPUT / 'report.pdf')))


if __name__ == '__main__':
    main()
