"""Export recorded lift movements without rerunning or changing a model."""
import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from amr_run_evidence import config_hash, file_hash

COLUMNS = ('Start Seconds', 'Origin Number', 'Destination Number', 'Load weight',
           '% loading factor', 'Transfer times', 'Car not in service', 'concatenated')


def number(value, name):
    try:
        result = Decimal(str(value))
        if isinstance(value, bool) or not result.is_finite() or result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'Missing or invalid {name}; repeat the run with complete lift evidence.') from None


def seconds(value):
    return format(number(value, 'transfer time').quantize(Decimal('.001'), rounding=ROUND_HALF_UP), 'f').rstrip('0').rstrip('.') or '0'


def movement_rows(events, config, lift_id, include_reposition=False):
    """Pure conversion, shared by tests and the verified export boundary."""
    if not any(row.get('id') == lift_id for row in config.get('lifts', [])):
        raise ValueError(f'Unknown lift {lift_id!r} in this run’s saved configuration.')
    return grouped_movement_rows(events, config, include_reposition, [lift_id])[lift_id]


def grouped_movement_rows(events, config, include_reposition=False, lift_ids=None):
    """Read evidence once, retaining each lift's existing import schema."""
    records = _grouped_movement_records(events, config, include_reposition, lift_ids)
    return {identity: [record[2] for record in values] for identity, values in records.items()}


def _grouped_movement_records(events, config, include_reposition=False, lift_ids=None):
    """Keep source rows attached to import fields for the detailed workbook."""
    lifts = {lift['id']: lift for lift in config.get('lifts', [])}
    selected = list(lifts) if lift_ids is None else lift_ids
    rows = {identity: [] for identity in selected}
    for order, event in enumerate(events):
        segment = str(event.get('segment_type') or event.get('event_type') or '').lower()
        segment = re.sub(r'^(?:multi_stop_)?segment_', '', segment)
        if segment not in ('lift_transfer', 'lift_reposition'):
            continue
        raw = event.get('details') or '{}'
        try:
            details = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(details, dict):
                details = {}
        except (ValueError, TypeError):
            details = {}
        lift_id = str(event.get('lift_id') or details.get('lift_id') or '')
        if lift_id not in rows:
            continue
        lift = lifts[lift_id]
        reposition = segment == 'lift_reposition'
        if reposition and not include_reposition:
            continue
        floors = []
        for which, field in (('from', 'start_floor'), ('to', 'end_floor')):
            floor = None
            for name in (details.get(which), event.get('start_node' if which == 'from' else 'end_node'),
                         event.get('from_location' if which == 'from' else 'to_location')):
                match = re.fullmatch(re.escape(lift_id) + r'-F(-?\d+)', str(name or ''))
                if match:
                    floor = int(match.group(1))
                    break
            if floor is None and not (reposition and details.get('amr_wait_node')):
                value = details.get(which + '_floor', event.get(field))
                try:
                    numeric = Decimal(str(value))
                    if not isinstance(value, bool) and numeric.is_finite() and numeric == int(numeric):
                        floor = int(numeric)
                except (InvalidOperation, ValueError, TypeError, OverflowError):
                    pass
            if floor is None:
                raise ValueError('Lift movement floor evidence is missing; repeat the run with complete lift evidence.')
            floors.append(str(floor + 1))
        start = number(event.get('sim_time_sec'), 'simulation start seconds')
        if reposition:
            entry = exit = '0'
        elif all(key in details for key in ('entry_start_sec', 'entry_time_sec', 'exit_time_sec')):
            start = number(details['entry_start_sec'], 'entry start')
            entry, exit = seconds(details['entry_time_sec']), seconds(details['exit_time_sec'])
        elif lift.get('transfer_timing_mode', 'fixed') == 'fixed' and 'boarding_time_sec' in lift and 'door_time_sec' in lift:
            # The legacy lift_transfer segment starts before its origin-door allowance.
            start += number(lift['door_time_sec'], 'saved door time')
            entry = exit = seconds(lift['boarding_time_sec'])
        else:
            raise ValueError('Entry/exit timing evidence is missing; repeat the run with complete lift evidence.')
        formatted_start = str(start.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        values = [formatted_start, *floors, '1500', '60', entry + ',' + exit, '2']
        rows[lift_id].append((start, order, dict(zip(COLUMNS, [*values, ','.join(values)])),
                             dict(event, lift_id=lift_id, segment_type=segment)))
    return {identity: sorted(values, key=lambda row: (row[0], row[1]))
            for identity, values in rows.items()}


def lift_trip_workbook_data(events, config, config_path):
    """Reuse the full movement report and existing third-party conversion.

    Every recorded movement is included, including empty reposition trips.
    Rows remain paired by source order even when boarding times reorder them.
    """
    import pandas as pd
    from report.amr_report_analysis import (build_lift_movement_detail, derive_lift_columns,
        load_amr_weights, load_payload_weights, parse_time_column)

    grouped = _grouped_movement_records(events, config, True)
    records = sorted((r for values in grouped.values() for r in values), key=lambda r: (r[0], r[1]))
    empty = build_lift_movement_detail(pd.DataFrame(), None)
    detail_columns = list(empty.columns)
    details_by_order = {}
    time_kind = 'seconds'
    if records:
        frame = pd.DataFrame([dict(r[3], export_order=r[1]) for r in records])
        frame, ctx = parse_time_column(frame)
        time_kind = 'datetime' if ctx.has_datetime else 'seconds'
        frame['_segment_text'] = frame['segment_type']
        frame = derive_lift_columns(frame, ctx.cols)
        duration = pd.to_numeric(frame.get(ctx.cols.get('duration'), pd.Series(index=frame.index, dtype=float)), errors='coerce')
        # Preserve incomplete older evidence as blank detail cells, not lost trips.
        frame['_duration_missing'] = duration.isna() | duration.lt(0)
        frame['lift_time_s'] = duration.where(~frame['_duration_missing'], 0)
        frame = frame.sort_values(ctx.time_col, kind='stable')
        detail = build_lift_movement_detail(frame, ctx, load_payload_weights(config_path), load_amr_weights(config_path))
        for (_, original), row in zip(frame.iterrows(), detail.to_dict('records')):
            start = original[ctx.time_col]
            row['start_time'] = start.isoformat() if ctx.has_datetime else float(start)
            finish = start + pd.Timedelta(seconds=original['lift_time_s']) if ctx.has_datetime else float(start) + original['lift_time_s']
            row['finish_time'] = finish.isoformat() if ctx.has_datetime else float(finish)
            if original['_duration_missing']:
                row.update(duration_s=None, finish_time=None)
            details_by_order[original['export_order']] = [
                None if value is None or pd.isna(value) else value for value in (row[c] for c in detail_columns)]
    rows = []
    for index, record in enumerate(records, 1):
        detail = details_by_order[record[1]]
        detail[0] = index
        values = [int(record[2][column]) if column != 'Transfer times' else record[2][column]
                  for column in COLUMNS[:-1]]
        rows.append([*detail, *values])
    return dict(headers=[*detail_columns, *COLUMNS], rows=rows, time_kind=time_kind,
                lifts=[dict(lift_id=identity, trips=len(values)) for identity, values in grouped.items()])


def export_lift_trips_xlsx(source, target, preview_directory=None):
    """Atomically publish one Excel table of all lifts and all recorded trips."""
    from report.amr_department_review import _spreadsheet_runtime

    source, target = Path(source).resolve(), Path(target).resolve()
    if target.suffix.lower() != '.xlsx':
        raise ValueError('Choose an Excel output filename ending in .xlsx.')
    config, events, checksum = verified_source(source)
    protected = {events, Path(str(events) + '.run.json')}
    if source.is_dir():
        protected.update(source / name for name in ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json'))
    if target in protected:
        raise ValueError('Choose an output filename separate from the saved run evidence.')
    if not config.get('lifts'):
        raise ValueError('This saved run has no configured lifts.')
    node, modules = _spreadsheet_runtime()
    sidecar = Path(str(events) + '.run.json')
    sidecar_hash = file_hash(sidecar)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.lift-trips-', dir=target.parent) as folder:
        folder = Path(folder)
        frozen = folder / 'config.json'
        frozen.write_text(json.dumps(config), encoding='utf-8')
        data = lift_trip_workbook_data(recorded_events(events), config, frozen)
        data['source'] = str(source)
        data['source_sha256'] = checksum
        payload = folder / 'trips.json'
        payload.write_text(json.dumps(data, allow_nan=False, ensure_ascii=False), encoding='utf-8')
        output = folder / 'lift-trips.xlsx'
        env = dict(os.environ, AMR_REPORT_NODE_MODULES=str(modules))
        command = [node, str(Path(__file__).with_name('amr_lift_trip_workbook.mjs')), str(payload), str(output)]
        if preview_directory:
            command.append(str(Path(preview_directory).resolve()))
        result = subprocess.run(command,
            env=env, capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not output.is_file():
            raise RuntimeError('Lift trip Excel export failed: ' + (result.stderr or result.stdout)[-3000:])
        if file_hash(events) != checksum or file_hash(sidecar) != sidecar_hash:
            raise ValueError('Saved evidence changed during export; no output was replaced.')
        if source.is_dir():
            _, checked_events, checked_hash = verified_source(source)
            if checked_events != events or checked_hash != checksum:
                raise ValueError('Saved run changed during export.')
        output.replace(target)
    return {row['lift_id']: row['trips'] for row in data['lifts']}


def verified_source(source):
    source = Path(source).resolve()
    if source.is_dir():
        from amr_run_review import verified_events
        _, config, path, checksum = verified_events(source)
        return config, path, checksum
    if source.suffix == '.sqlite':
        from amr_run_review import verified_standalone_events
        evidence, config, path, checksum = verified_standalone_events(source)
        if evidence.get('run_status') != 'finished':
            raise ValueError('Choose a completed run for the third-party lift export.')
        return config, path, checksum
    sidecar = Path(str(source) + '.run.json')
    if not sidecar.exists():
        raise ValueError('Saved run configuration evidence is missing; repeat the run with complete logging.')
    evidence = json.loads(sidecar.read_text(encoding='utf-8-sig'))
    config = evidence.get('frozen_inputs')
    checksum = file_hash(source)
    if (not isinstance(config, dict) or config_hash(config) != evidence.get('config_sha256')
            or checksum != evidence.get('log_sha256') or evidence.get('log_kind') != 'full'
            or evidence.get('logging_enabled') is not True or evidence.get('reduced_logging')
            or evidence.get('run_status') != 'finished'):
        raise ValueError('The CSV does not match complete saved-run evidence.')
    from amr_run_evidence import verified_simulation_mode, verify_legacy_computation
    verified_simulation_mode(evidence, config)
    verify_legacy_computation(evidence, config)
    return config, source, checksum


def recorded_events(path):
    if path.suffix == '.sqlite':
        from amr_event_store import EventStore
        store = EventStore(path, readonly=True)
        try:
            yield from store.iter_rows()
        finally:
            store.close()
    else:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            yield from csv.DictReader(stream)


def export_lift_csv(source, target, lift_id, include_reposition=False):
    source, target = Path(source).resolve(), Path(target).resolve()
    config, events, checksum = verified_source(source)
    protected = {events, Path(str(events) + '.run.json')}
    if source.is_dir():
        protected.update(source / name for name in ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json'))
    if target in protected:
        raise ValueError('Choose an output filename separate from the saved run evidence.')
    sidecar = Path(str(events) + '.run.json')
    sidecar_hash = file_hash(sidecar)
    rows = movement_rows(recorded_events(events), config, lift_id, include_reposition)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f'.{os.getpid()}.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        if file_hash(events) != checksum or file_hash(sidecar) != sidecar_hash:
            raise ValueError('Saved evidence changed during export; no output was replaced.')
        if source.is_dir():
            _, checked_events, checked_hash = verified_source(source)
            if checked_events != events or checked_hash != checksum:
                raise ValueError('Saved run changed during export.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return len(rows)


def export_all_lifts_csv(source, target_directory, include_reposition=False):
    """Publish a complete new directory of per-lift CSVs in one final rename."""
    source, target = Path(source).resolve(), Path(target_directory).resolve()
    if target.exists():
        raise ValueError('Choose a new output folder for the all-lifts export; existing folders are retained.')
    config, events, checksum = verified_source(source)
    if not config.get('lifts'):
        raise ValueError('This saved run has no configured lifts.')
    sidecar = Path(str(events) + '.run.json')
    sidecar_hash = file_hash(sidecar)
    grouped = grouped_movement_rows(recorded_events(events), config, include_reposition)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.third-party-lifts-', dir=target.parent) as folder:
        staged = Path(folder) / 'export'
        staged.mkdir()
        manifest = dict(schema_version=1, source_events_sha256=checksum,
                        include_reposition=bool(include_reposition), lifts=[])
        for index, (identity, rows) in enumerate(grouped.items(), 1):
            label = re.sub(r'[^A-Za-z0-9._-]+', '_', identity).strip('._')[:80] or 'lift'
            name = f'lift-{index:03d}-{label}.csv'
            with (staged / name).open('x', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
                stream.flush()
                os.fsync(stream.fileno())
            manifest['lifts'].append(dict(lift_id=identity, filename=name, movements=len(rows)))
        (staged / 'export-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        if file_hash(events) != checksum or file_hash(sidecar) != sidecar_hash:
            raise ValueError('Saved evidence changed during export; no export folder was published.')
        if source.is_dir():
            _, checked_events, checked_hash = verified_source(source)
            if checked_events != events or checked_hash != checksum:
                raise ValueError('Saved run changed during export.')
        # rename intentionally refuses replacement of an existing destination.
        staged.rename(target)
    return {identity: len(rows) for identity, rows in grouped.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Completed run folder, event CSV or compact event store')
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--third-party-lift-csv', type=Path)
    output.add_argument('--third-party-lifts-dir', type=Path, help='New folder containing one CSV per configured lift')
    output.add_argument('--third-party-lift-xlsx', type=Path, help='Excel table of all lifts and all trips with a concatenation formula')
    parser.add_argument('--lift-id')
    parser.add_argument('--include-lift-reposition', action='store_true')
    args = parser.parse_args(argv)
    if args.third_party_lift_xlsx:
        if args.lift_id:
            parser.error('--lift-id cannot be combined with --third-party-lift-xlsx')
        counts = export_lift_trips_xlsx(args.source, args.third_party_lift_xlsx)
        print(f'Exported {len(counts)} lifts ({sum(counts.values())} trips) to {args.third_party_lift_xlsx}', flush=True)
        return 0
    if args.third_party_lifts_dir:
        if args.lift_id:
            parser.error('--lift-id cannot be combined with --third-party-lifts-dir')
        counts = export_all_lifts_csv(args.source, args.third_party_lifts_dir, args.include_lift_reposition)
        print(f'Exported {len(counts)} lifts ({sum(counts.values())} movements) to {args.third_party_lifts_dir}', flush=True)
        return 0
    if not args.lift_id:
        parser.error('--third-party-lift-csv requires --lift-id')
    count = export_lift_csv(args.source, args.third_party_lift_csv, args.lift_id, args.include_lift_reposition)
    print(f'Exported {count} lift movements to {args.third_party_lift_csv}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
