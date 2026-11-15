"""Shared daily, per-lift purpose counts for editable Excel charts and PDF."""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import math
import os
import re
import subprocess

INTERVALS = (5, 15, 30, 60)
ALL_DAYS = 'All days'
PURPOSES = {
    'catering': ('Catering', '#2F5597'),
    'linen': ('Linen', '#8064A2'),
    'pharmacy': ('Pharmacy', '#548235'),
    'waste': ('Waste', '#C55A11'),
    'stores': ('Stores', '#008C95'),
    'ssd': ('SSD', '#A38720'),
    'mixed': ('Mixed purposes', '#A64D79'),
    'empty_amr_travel': ('Empty AMR travel', '#78909C'),
    'unknown': ('Unclassified', '#A7A7A7'),
    'empty_lift_reposition': ('Empty lift repositioning', '#4E5966'),
}


def _text(value):
    return '' if value is None or str(value).strip().lower() in ('nan', 'none', '<na>') else str(value).strip()


def _natural(value):
    return [(0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r'(\d+)', value)]


def _datetime(value):
    value = _text(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        for pattern in ('%d/%m/%Y %H:%M:%S.%f', '%d/%m/%Y %H:%M:%S'):
            try:
                return datetime.strptime(value, pattern)
            except ValueError:
                pass
    return None


def _purpose(row):
    if _text(row.get('movement_type')).lower() == 'lift_reposition':
        return 'empty_lift_reposition'
    purpose = _text(row.get('service_category')).lower()
    if purpose and purpose != 'unknown':
        return purpose
    return 'empty_amr_travel' if row.get('activity_type') == 'empty_amr_travel' else 'unknown'


def build_chart_data(movements, config=None, interval_minutes=30):
    """Count each recorded physical movement once, at its movement start.

    A mixed load is one Mixed purposes movement, not one count per task. Empty
    repositioning is kept in the source so Excel can include/exclude it live.
    No simulation is run and no missing category is guessed from a payload.
    """
    if type(interval_minutes) is not int or interval_minutes not in INTERVALS:
        raise ValueError('Lift chart intervals must be 5, 15, 30 or 60 minutes.')
    config = config or {}
    simulation = config.get('simulation', {})
    epoch = _datetime(simulation.get('start_datetime'))
    configured_end = _datetime(simulation.get('end_datetime'))
    counts = Counter()
    lifts = {_text(row.get('id')) for row in config.get('lifts', []) if _text(row.get('id'))}
    calendar_days, relative_days = set(), set()
    kinds = set()
    purpose_ids = set()
    for row in movements.to_dict('records') if movements is not None else []:
        if row.get('movement_type') not in ('lift_transfer', 'lift_reposition'):
            continue
        identity = _text(row.get('lift_id')) or 'Unknown lift'
        lifts.add(identity)
        raw = row.get('start_time')
        stamp = _datetime(raw)
        if stamp is None:
            value = _text(raw).replace(',', '')
            try:
                seconds = float(value[:-1] if value.endswith('s') else value)
            except (TypeError, ValueError):
                raise ValueError(f'Lift {identity}: movement start time is missing or invalid.') from None
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError(f'Lift {identity}: movement start seconds must be finite and nonnegative.')
            try:
                stamp = epoch + timedelta(seconds=seconds) if epoch is not None else None
            except OverflowError:
                raise ValueError(f'Lift {identity}: movement start is outside the supported calendar range.') from None
        if stamp is not None:
            kinds.add('calendar')
            day = stamp.date().isoformat()
            calendar_days.add(stamp.date())
            minute = stamp.hour * 60 + stamp.minute
        else:
            kinds.add('relative')
            number = int(seconds // 86400) + 1
            day = f'Day {number}'
            relative_days.add(number)
            minute = int(seconds % 86400 // 60)
        purpose = _purpose(row)
        purpose_ids.add(purpose)
        bucket = minute // interval_minutes * interval_minutes
        counts[identity, day, bucket, purpose] += 1
    if len(kinds) > 1:
        raise ValueError('Calendar and elapsed movement times need a matching simulation start to be combined.')
    mode = 'calendar' if epoch is not None or 'calendar' in kinds else 'relative'
    if mode == 'calendar':
        if epoch is not None:
            calendar_days.add(epoch.date())
        if configured_end is not None and (epoch is None or configured_end > epoch):
            calendar_days.add((configured_end - timedelta(microseconds=1)).date())
        if calendar_days:
            first, last = min(calendar_days), max(calendar_days)
            if (last - first).days > 3660:
                raise ValueError('The lift chart observation exceeds ten years. Check saved movement timestamps.')
            days = [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
        else:
            days = []
    else:
        if max(relative_days,default=0) > 3661:
            raise ValueError('The lift chart observation exceeds ten years. Check saved movement timestamps.')
        days = [f'Day {i}' for i in range(1, max(relative_days, default=0)+1)]
    purposes = []
    palette = ['#4F6B92', '#907144', '#62806B', '#8B668B', '#4F7C85']
    for code in sorted(purpose_ids, key=lambda value: (list(PURPOSES).index(value) if value in PURPOSES else 8, value)):
        name, colour = PURPOSES.get(code, (code.replace('_', ' ').title(),
            palette[int(hashlib.sha256(code.encode()).hexdigest()[:8], 16) % len(palette)]))
        purposes.append(dict(id=code, label=name, colour=colour))
    return dict(schema_version=1, day_mode=mode, interval_minutes=interval_minutes,
        days=days, lifts=sorted(lifts, key=_natural), purposes=purposes,
        counts=[dict(lift_id=lift, day=day, minute=minute, purpose=purpose, count=count)
                for (lift, day, minute, purpose), count in sorted(counts.items())],
        movements=sum(counts.values()),
        note='Movements are counted at their start. All days combines '+
             ('clock-time bins' if mode == 'calendar' else 'time bins within each simulation day')+', without averaging. '
             'Outbound and return trips share their recorded service category. Mixed loads count once. '
             'Partial days follow the saved observation period. Unavailable purposes remain Unclassified.')


def selected_charts(data, day=None, include_reposition=True):
    day = None if day in (None, '', ALL_DAYS) else str(day).strip()
    if day is not None and day not in data['days']:
        raise ValueError(f'Chart day {day!r} is not in this run. Choose All days or one of the recorded observation days.')
    purposes = [p for p in data['purposes'] if include_reposition or p['id'] != 'empty_lift_reposition']
    slots = list(range(0, 1440, data['interval_minutes']))
    totals = Counter()
    for row in data['counts']:
        if day is None or row['day'] == day:
            totals[row['lift_id'], row['minute'], row['purpose']] += row['count']
    return [dict(lift_id=identity, day=day or ALL_DAYS,
        labels=[f'{m//60:02d}:{m%60:02d}' for m in slots],
        series=[dict(p, values=[totals[identity, m, p['id']] for m in slots]) for p in purposes],
        total=sum(totals[identity, m, p['id']] for m in slots for p in purposes)) for identity in data['lifts']]


def extract_chart_data(events, config=None, interval_minutes=30):
    """Read only movement rows; counting a trip does not require its duration."""
    import pandas as pd
    from amr_third_party_lift import recorded_events
    from report.amr_report_analysis import parse_time_column,derive_lift_columns,lift_activity_tags
    rows=[]
    for event in recorded_events(Path(events)):
        kind=_text(event.get('segment_type') or event.get('event_type')).lower()
        kind=re.sub(r'^(?:multi_stop_)?segment_','',kind)
        if kind in ('lift_transfer','lift_reposition'):
            rows.append(dict(event,chart_movement_type=kind))
    if not rows:
        return build_chart_data(None,config,interval_minutes)
    frame,ctx=parse_time_column(pd.DataFrame(rows))
    frame=derive_lift_columns(frame,ctx.cols)
    movements=[]
    for _,row in frame.iterrows():
        try:
            details=json.loads(_text(row.get('details')) or '{}')
            if not isinstance(details,dict):details={}
        except (ValueError,TypeError):
            details={}
        identity=_text(row['_lift_id']) or _text(details.get('lift_id'))
        if not identity:
            match=re.fullmatch(r'(.+)-F-?\d+',_text(details.get('from')))
            identity=match[1] if match else 'Unknown lift'
        kind=row['chart_movement_type']
        movements.append(dict(lift_id=identity,movement_type=kind,start_time=row[ctx.time_col],
            **lift_activity_tags(row,ctx,details,kind=='lift_reposition')))
    return build_chart_data(pd.DataFrame(movements),config,interval_minutes)


def export_lift_charts_xlsx(source, target, *, interval_minutes=30, day=None,
                            include_reposition=True, preview_directory=None):
    """Verified saved evidence -> editable workbook, published in one rename."""
    from amr_third_party_lift import verified_source
    from amr_run_evidence import file_hash
    from report.amr_department_review import _spreadsheet_runtime
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.suffix.lower() != '.xlsx':
        raise ValueError('Choose an Excel workbook filename ending in .xlsx.')
    config, events, checksum = verified_source(source)
    protected = {source, events, Path(str(events)+'.run.json')}
    if source.is_dir():
        protected.update(source/name for name in ('run_manifest.json','config.json','project_configuration.json','project_checks.json'))
    if target in protected:
        raise ValueError('Choose an output separate from saved run evidence.')
    if not config.get('lifts'):
        raise ValueError('This saved run has no configured lifts.')
    node, modules = _spreadsheet_runtime()
    sidecar = Path(str(events)+'.run.json')
    sidecar_hash = file_hash(sidecar)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.lift-charts-', dir=target.parent) as folder:
        folder = Path(folder)
        data = extract_chart_data(events, config, interval_minutes)
        selected_charts(data, day, include_reposition)  # validate before writing output
        data.update(initial_day=day or ALL_DAYS, include_reposition=bool(include_reposition),
                    source=source.name, source_sha256=checksum)
        payload = folder/'charts.json'
        payload.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        output = folder/'lift-movement-charts.xlsx'
        command = [node, str(Path(__file__).with_name('amr_lift_movement_workbook.mjs')),str(payload),str(output)]
        if preview_directory:
            command.append(str(Path(preview_directory).resolve()))
        result = subprocess.run(command, env=dict(os.environ, AMR_REPORT_NODE_MODULES=str(modules)),
            capture_output=True, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not output.is_file():
            raise RuntimeError('Lift chart Excel export failed: '+(result.stderr or result.stdout)[-3000:])
        if file_hash(events) != checksum or file_hash(sidecar) != sidecar_hash:
            raise ValueError('Saved evidence changed during export; no output was replaced.')
        if source.is_dir():
            _, _, checked = verified_source(source)
            if checked != checksum:
                raise ValueError('Saved run changed during export.')
        output.replace(target)
    return dict(lifts=len(data['lifts']), movements=data['movements'], days=len(data['days']))
