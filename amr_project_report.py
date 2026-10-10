"""Generate external reports from a completed run's verified, frozen inputs."""
import argparse
import json
from pathlib import Path
import sys

from amr_project_runs import OUTPUTS, read_json, write_json, validate_run_inputs, timestamp
from amr_run_evidence import file_hash, config_hash
from amr_run_review import verified_inputs


def report_software():
    root = Path(__file__).resolve().parent
    paths = [Path(__file__), root / 'amr_project_runs.py', root / 'amr_run_evidence.py', root / 'amr_run_review.py', *sorted((root / 'report').glob('*.py'))]
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in paths}
    return dict(files=files, sha256=config_hash(files))


def report_sections():
    folder = str(Path(__file__).resolve().parent / 'report')
    if folder not in sys.path:
        sys.path.insert(0, folder)
    from amr_report_pdf_report import REPORT_SECTIONS
    return REPORT_SECTIONS


def generate(directory, output, sections, *, drawings=False, existing_pdf=None, insert_after_page=None, report_title=None,
             lift_cohorts_only=False):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    drawings = drawings and not lift_cohorts_only
    manifest, config, csv, log_hash = verified_inputs(directory, drawings=drawings)
    source_hashes = {name: file_hash(directory / name) for name in
                     ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json', OUTPUTS['steps_csv'] + '.run.json')}
    allowed = dict(report_sections())
    if not lift_cohorts_only and (not sections or any(s not in allowed for s in sections) or len(set(sections)) != len(sections)):
        raise ValueError('Select at least one distinct supported report section.')
    if lift_cohorts_only and (existing_pdf or insert_after_page is not None):
        raise ValueError('Lift CSV export cannot insert into a PDF.')
    insertion = None
    if existing_pdf:
        from amr_report_pdf_insert import validate_insertion
        existing_pdf = Path(existing_pdf).resolve()
        validate_insertion(existing_pdf, output / 'report.pdf', insert_after_page)
        insertion = dict(existing_pdf=str(existing_pdf), sha256=file_hash(existing_pdf),
                         insert_after_page=insert_after_page, numbering='Separate report supplement')
    elif insert_after_page is not None:
        raise ValueError('Choose an existing PDF when setting an insertion page.')
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(status='running', created_at=timestamp(), project_binding=manifest['project_binding'],
                    source_config_sha256=manifest['config_object_sha256'], source_log_sha256=log_hash,
                    simulation_software=manifest['software'], report_software=report_software(),
                    source_files=source_hashes, sections=[] if lift_cohorts_only else sections,
                    include_drawings=drawings, report_title=report_title,
                    kind='lift_cohorts_csv' if lift_cohorts_only else 'pdf')
    if insertion:
        metadata['insertion'] = insertion
    write_json(output / 'report_manifest.json', metadata)
    try:
        # Relocate drawings into this run without rewriting its immutable inputs.
        from amr_project import drawing_entries
        for entry, _suffix in drawing_entries(config):
            entry['filepath'] = str(directory / 'drawings' / Path(entry['filepath']).name)
        write_json(output / 'report_configuration.json', config)
        from amr_report_main import generate_report_from_paths, export_lift_cohorts_csv
        lift_csv = output / 'report_lift_cohorts.csv'
        if lift_cohorts_only:
            from amr_report_analysis import extract_lift_cohorts
            print('Exporting five-minute and hourly lift usage CSV...', flush=True)
            export_lift_cohorts_csv(extract_lift_cohorts(csv), lift_csv)
        else:
            generate_report_from_paths(csv, output / 'report.pdf', config_json=output / 'report_configuration.json',
                                   include_drawings=drawings, heatmap_workers=1, report_sections=sections,
                                   existing_pdf=existing_pdf, insert_after_page=insert_after_page, report_title=report_title,
                                   lift_cohorts_csv=lift_csv)
        verified_inputs(directory, drawings=drawings)
        if (file_hash(csv) != log_hash or report_software() != metadata['report_software'] or
                any(file_hash(directory / name) != checksum for name, checksum in source_hashes.items())):
            raise ValueError('Inputs or report software changed during generation. This report is incomplete.')
        if existing_pdf and file_hash(existing_pdf) != metadata['insertion']['sha256']:
            raise ValueError('The existing PDF changed during insertion. This report is incomplete.')
        metadata.update(status='complete', completed_at=timestamp(), lift_cohorts_sha256=file_hash(lift_csv))
        if not lift_cohorts_only:
            metadata['pdf_sha256'] = file_hash(output / 'report.pdf')
    except Exception as exc:
        metadata.update(status='failed', completed_at=timestamp(), error=str(exc))
        raise
    finally:
        write_json(output / 'report_manifest.json', metadata)
    return output / ('report_lift_cohorts.csv' if lift_cohorts_only else 'report.pdf')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--sections', default='')
    parser.add_argument('--lift-cohorts-only', action='store_true')
    parser.add_argument('--drawings', action='store_true')
    parser.add_argument('--existing-pdf', type=Path)
    parser.add_argument('--insert-after-page', type=int)
    parser.add_argument('--report-title')
    args = parser.parse_args(argv)
    print(generate(args.run, args.output, args.sections.split(','), drawings=args.drawings,
                   existing_pdf=args.existing_pdf, insert_after_page=args.insert_after_page, report_title=args.report_title,
                   lift_cohorts_only=args.lift_cohorts_only), flush=True)


if __name__ == '__main__':
    main()
