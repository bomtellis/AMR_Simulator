"""Generate external reports from a completed run's verified, frozen inputs."""
import argparse
import json
from pathlib import Path
import sys

from amr_project_runs import OUTPUTS, read_json, write_json, validate_run_inputs, timestamp
from amr_run_evidence import file_hash, config_hash


def report_software():
    root = Path(__file__).resolve().parent
    paths = [Path(__file__), root / 'amr_project_runs.py', root / 'amr_run_evidence.py', *sorted((root / 'report').glob('*.py'))]
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in paths}
    return dict(files=files, sha256=config_hash(files))


def verified_inputs(directory, *, drawings=False):
    directory = Path(directory).resolve()
    manifest, config = validate_run_inputs(directory, verify_drawings=drawings)
    if manifest['status'] != 'complete':
        raise ValueError('Reports require a completed project run. Investigate incomplete runs separately.')
    csv = directory / OUTPUTS['steps_csv']
    evidence = read_json(str(csv) + '.run.json')
    if (evidence.get('project_binding') != manifest['project_binding'] or
            evidence.get('config_sha256') != manifest['config_object_sha256'] or
            config_hash(evidence.get('frozen_inputs')) != manifest['config_object_sha256'] or
            evidence.get('software', {}).get('sha256') != manifest['software']['sha256'] or
            evidence.get('log_sha256') != file_hash(csv) or evidence.get('run_status') != 'finished' or
            evidence.get('log_kind') != 'full' or not evidence.get('logging_enabled') or evidence.get('reduced_logging')):
        raise ValueError('The report requires complete event evidence matching this run and its frozen configuration.')
    return manifest, config, csv, evidence['log_sha256']


def report_sections():
    folder = str(Path(__file__).resolve().parent / 'report')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    from amr_report_pdf_report import REPORT_SECTIONS
    return REPORT_SECTIONS


def generate(directory, output, sections, *, drawings=False):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    manifest, config, csv, log_hash = verified_inputs(directory, drawings=drawings)
    source_hashes = {name: file_hash(directory / name) for name in
                     ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json', OUTPUTS['steps_csv'] + '.run.json')}
    allowed = dict(report_sections())
    if not sections or any(s not in allowed for s in sections) or len(set(sections)) != len(sections):
        raise ValueError('Select at least one distinct supported report section.')
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(status='running', created_at=timestamp(), project_binding=manifest['project_binding'],
                    source_config_sha256=manifest['config_object_sha256'], source_log_sha256=log_hash,
                    simulation_software=manifest['software'], report_software=report_software(),
                    source_files=source_hashes, sections=sections, include_drawings=drawings)
    write_json(output / 'report_manifest.json', metadata)
    try:
        # Relocate drawings into this run without rewriting its immutable inputs.
        from amr_project import drawing_entries
        for entry, _suffix in drawing_entries(config):
            entry['filepath'] = str(directory / 'drawings' / Path(entry['filepath']).name)
        write_json(output / 'report_configuration.json', config)
        from amr_report_main import generate_report_from_paths
        generate_report_from_paths(csv, output / 'report.pdf', config_json=output / 'report_configuration.json',
                                   include_drawings=drawings, heatmap_workers=1, report_sections=sections)
        verified_inputs(directory, drawings=drawings)
        if (file_hash(csv) != log_hash or report_software() != metadata['report_software'] or
                any(file_hash(directory / name) != checksum for name, checksum in source_hashes.items())):
            raise ValueError('Inputs or report software changed during generation. This report is incomplete.')
        metadata.update(status='complete', completed_at=timestamp(), pdf_sha256=file_hash(output / 'report.pdf'))
    except Exception as exc:
        metadata.update(status='failed', completed_at=timestamp(), error=str(exc))
        raise
    finally:
        write_json(output / 'report_manifest.json', metadata)
    return output / 'report.pdf'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--sections', required=True)
    parser.add_argument('--drawings', action='store_true')
    args = parser.parse_args()
    print(generate(args.run, args.output, args.sections.split(','), drawings=args.drawings), flush=True)


if __name__ == '__main__':
    main()
