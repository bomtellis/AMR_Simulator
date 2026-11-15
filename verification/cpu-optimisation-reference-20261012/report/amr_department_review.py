"""Owner-specific service reviews from configuration and observed simulation events.

The PDF and workbook consume the same review model. No simulation is re-run.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from amr_sim_task_generation import (
    DynamicCategoryTaskGenerator, SCHEDULED_MODES, _scheduled_times_from_cfg,
)
from amr_sim_time_utils import SimulationClock

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
EVENTS = {'task_generated', 'waste_task_generated', 'return_task_generated',
          'task_assigned', 'task_complete', 'multi_stop_task_complete',
          'segment_pickup', 'segment_dropoff', 'staff_payload_transport', 'task_failed'}


def _text(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def _level(value):
    try:
        return f'L{int(float(value)):02d}'
    except (ValueError, TypeError):
        return _text(value)


def _stamp(value):
    return '' if value is None or pd.isna(value) else pd.Timestamp(value).isoformat(sep=' ', timespec='seconds')


def _resolver(config, start):
    # Resolve precisely the same group, department and waste-stream overrides as
    # the simulator. Avoid constructing runtime state or emitting new tasks.
    generator = DynamicCategoryTaskGenerator.__new__(DynamicCategoryTaskGenerator)
    generator.task_generation = config.get('task_generation', {})
    generator.departments = config.get('departments', [])
    generator.locations = {x['name']: x for x in config.get('locations', [])}
    generator.payloads = {x['name']: x for x in config.get('payloads', [])}
    streams = config.get('waste_streams', {})
    generator.waste_streams = streams if isinstance(streams, dict) else {x['name']: x for x in streams}
    generator.clock = SimulationClock(start)
    return generator


def build_department_reviews(config: dict, log: pd.DataFrame, sources=None) -> dict:
    """Pure aggregation, also used by regression tests and both export formats."""
    if log.empty or 'event_type' not in log or 'task_id' not in log:
        raise ValueError('The department review requires a verbose simulation event CSV with task IDs.')
    log = log.copy().fillna('')
    for col in ['department_id', 'details', 'task_source', 'from_location', 'to_location', 'payload', 'waste_stream']:
        if col not in log:
            log[col] = ''
    log['_time'] = pd.to_datetime(log.get('sim_datetime'), format='mixed', errors='coerce')
    if log['_time'].notna().sum() == 0:
        raise ValueError('The event CSV needs sim_datetime values to report calendar weekdays.')
    sim = config.get('simulation', {})
    start = pd.Timestamp(sim.get('start_datetime') or log['_time'].min()).to_pydatetime()
    end = pd.Timestamp(sim.get('end_datetime') or (log['_time'].max() + pd.Timedelta(seconds=1))).to_pydatetime()
    if end <= start:
        raise ValueError('The configuration reporting end must be after its start.')
    generator = _resolver(config, start)
    instances = generator._build_instances()
    categories = config.get('task_generation', {}).get('categories', {})
    departments = {_text(x.get('id') or x.get('name')): x for x in config.get('departments', [])}
    locations = {_text(x.get('name')): x for x in config.get('locations', [])}
    groups = {str(k): v.sort_values('_time') for k, v in log.groupby('task_id') if str(k)}
    requests = {}
    for task_id, rows in groups.items():
        generated = rows[rows.event_type.isin(['task_generated', 'waste_task_generated', 'return_task_generated'])]
        if generated.empty:
            continue  # Excludes automatic charging/accommodation and manual work.
        requests[task_id] = generated.iloc[0]
    task_meta = {}
    category_tokens = {re.sub(r'[^a-z0-9]', '', key.lower()): key for key in categories}
    for task_id, row in requests.items():
        match = re.search(r'GEN_([A-Z0-9]+)_', task_id, re.I)
        category = match.group(1).lower() if match else ''
        category = category_tokens.get(category, category)
        if not category:
            match = re.search(r'Generated (?:scheduled-threshold|scheduled|sporadic|threshold|timeframe) (\S+) task', row.details, re.I)
            category = match.group(1).lower() if match else ''
        if not category and row.task_source == 'department_waste':
            category = 'waste'
        parent_match = re.search(r'(?:return for|return of) (\S+)', row.details, re.I)
        parent = parent_match.group(1).rstrip('.;') if parent_match else ''
        if not parent:
            match = re.match(r'RETURN[-_](GEN_.+)[-_]\d+$', task_id, re.I)
            parent = match.group(1) if match else ''
        mode_match = re.search(r'Generated (scheduled-threshold|scheduled|sporadic|threshold|timeframe) ', row.details, re.I)
        trigger = mode_match.group(1).replace('-', '_') if mode_match else (
            'tracked item exchange' if 'generated tracked item exchange' in row.details.lower() else
            'return' if parent or row.event_type == 'return_task_generated' else 'unspecified')
        task_meta[task_id] = dict(category=category, parent=parent, department=_text(row.department_id),
                                  trigger=trigger)
    for meta in task_meta.values():
        parent = task_meta.get(meta['parent'], {})
        meta['category'] = meta['category'] or parent.get('category', '') or 'unclassified'
        meta['department'] = meta['department'] or parent.get('department', '') or 'Unassigned'

    def direction(task_id, seen=None):
        meta, row = task_meta[task_id], requests[task_id]
        seen = set(seen or ())
        if task_id in seen:
            return 'Unclassified'
        seen.add(task_id)
        if meta['parent'] in task_meta:
            parent_direction = direction(meta['parent'], seen)
            return {'Delivery': 'Collection', 'Collection': 'Delivery'}.get(parent_direction, 'Unclassified')
        dept = departments.get(meta['department'], {})
        entry = dept.get('task_generation_locations', {}).get(meta['category'], {})
        endpoints = set(entry.get('pickup_dropoff_locations', []) + entry.get('dropoff_zone_locations', entry.get('drop_off_zone_locations', [])))
        if row.from_location in endpoints and row.to_location not in endpoints:
            return 'Collection'
        if row.to_location in endpoints and row.from_location not in endpoints:
            return 'Delivery'
        applicable = [i for i in instances if i['category_key'] == meta['category'] and i.get('department_id') == meta['department']]
        roles = {i.get('department_location_role', i['cfg'].get('department_location_role', 'dropoff')) for i in applicable}
        if roles == {'pickup'} or row.task_source == 'department_waste':
            return 'Collection'
        if roles == {'dropoff'}:
            return 'Delivery'
        return 'Unclassified'

    coverage = Counter()
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        coverage[DAYS[day.weekday()]] += max(0, (min(day + timedelta(days=1), end) - max(day, start)).total_seconds()) / 3600
        day += timedelta(days=1)
    common = {
        'start': _stamp(start), 'end': _stamp(end), 'observed_end': _stamp(log['_time'].max()),
        'sources': sources or {}, 'coverage_hours': dict(coverage),
        'notes': [
            'Counts are simulated payload tasks, not AMR visits or measured current service. Each completed task counts once. Deliveries include empty-container returns to collection departments.',
            'Deliveries use the logged staff final arrival at the department where available; otherwise the AMR drop-off completion.',
            'Collections use AMR pickup completion at the department or shared zone. Staff return legs and AMR accommodation trips are not counted again.',
            'Only service times in the reporting interval [start, end) enter weekday totals. Late completions remain in Events; weekdays are calendar days, not shifts.',
            'Timetables distinguish configuration schedule times from actual service times. Scheduled waste fill events are not collection promises.',
            'The configuration is a supplied snapshot; the event log does not prove it was the configuration used for this run. Actual counts always come from the log.',
            'Current-service comparison cells are blank for the category owner to complete. Unclassified movements are retained for review, excluded from delivery/collection totals.',
        ],
    }
    reviews = {}
    for key in dict.fromkeys(list(categories) + [m['category'] for m in task_meta.values()]):
        category = categories.get(key, {})
        configured = [i for i in instances if i['category_key'] == key]
        events, timetable = [], []
        for task_id, meta in task_meta.items():
            if meta['category'] != key:
                continue
            rows, request = groups[task_id], requests[task_id]
            service = direction(task_id)
            completed = rows[rows.event_type.isin(['task_complete', 'multi_stop_task_complete'])]
            segment = rows[rows.event_type.eq('segment_pickup' if service == 'Collection' else 'segment_dropoff')]
            actual, handover, basis = None, None, ''
            if not completed.empty and not segment.empty and service != 'Unclassified':
                s = segment.iloc[-1]
                actual = s['_time'] + pd.Timedelta(seconds=float(s.get('duration_sec', 0) or 0))
                handover = actual
                basis = 'AMR pickup completed' if service == 'Collection' else 'AMR drop-off completed'
                if service == 'Delivery':
                    staff = rows[rows.event_type.eq('staff_payload_transport') & rows.from_location.eq(request.to_location)]
                    if not staff.empty:
                        s = staff.iloc[0]
                        actual = s['_time'] + pd.Timedelta(seconds=float(s.get('duration_sec', 0) or 0))
                        basis = 'Staff final delivery arrival'
            in_period = bool(actual is not None and start <= actual < end)
            dept = departments.get(meta['department'], {})
            destination = _text(request.to_location)
            final_match = re.search(r'final destination=([^;]+)', request.details)
            final_destination = final_match.group(1).strip() if final_match else destination
            if service == 'Delivery' and basis == 'Staff final delivery arrival':
                final_destination = _text(s.to_location)
            event = dict(task_id=task_id, parent_task=meta['parent'], department_id=meta['department'],
                department=dept.get('name', meta['department']), level=_level(dept.get('floor', '')),
                service=service, trigger=meta['trigger'], generated=_stamp(request['_time']), actual=_stamp(actual),
                weekday=DAYS[actual.weekday()] if actual is not None else '', in_period=in_period,
                status='Completed' if not completed.empty else ('Failed' if (rows.event_type == 'task_failed').any() else 'Not completed'),
                payload=_text(request.payload), origin=_text(request.from_location), destination=destination,
                final_destination=final_destination, basis=basis, amr_handover=_stamp(handover), details=_text(request.details))
            events.append(event)
            if in_period:
                timetable.append(dict(time=_stamp(actual), department_id=meta['department'], department=event['department'],
                                      kind='Actual ' + service.lower(), trigger=meta['trigger'], task_id=task_id))
        # Configuration timetable uses the simulator's recurrence and opening-hour gates.
        if config.get('task_generation', {}).get('enabled', True):
            for instance in configured:
                cfg = instance['cfg']
                if cfg.get('generation_mode', 'scheduled') not in SCHEDULED_MODES:
                    continue
                day = start.replace(hour=0, minute=0, second=0, microsecond=0)
                while day < end:
                    for hhmm in _scheduled_times_from_cfg(cfg):
                        scheduled = day + timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:]))
                        seconds = generator._adjust_release_to_department_open(instance, (scheduled - start).total_seconds())
                        if seconds is None:
                            continue
                        effective = start + timedelta(seconds=seconds)
                        if start <= effective < end and generator._instance_is_active(instance, seconds):
                            fill = key == 'waste' and cfg.get('generation_mode') == 'scheduled_threshold'
                            timetable.append(dict(time=_stamp(effective), department_id=instance.get('department_id') or 'Unassigned',
                                department=instance.get('department_name') or 'Unassigned', kind='Scheduled fill' if fill else 'Scheduled release',
                                trigger=cfg.get('generation_mode', 'scheduled'), task_id=instance['key']))
                    day += timedelta(days=1)
        scope = set(i.get('department_id') or 'Unassigned' for i in configured) | {e['department_id'] for e in events}
        directory = []
        for dept_id, dept in departments.items():
            linked = dept.get('task_generation_locations', {}).get(key, {})
            directory.append(dict(id=dept_id, name=dept.get('name', dept_id), level=_level(dept.get('floor', '')),
                enabled=bool(dept.get('enabled', True)), in_scope=dept_id in scope,
                hours=f"{dept.get('operating_start_time', '00:00')}-{dept.get('operating_end_time', '24:00')}",
                days=', '.join(dept.get('days_active', [])), beds=dept.get('bed_count', ''),
                locations=', '.join(linked.get('pickup_dropoff_locations', [])),
                zones=', '.join(linked.get('dropoff_zone_locations', linked.get('drop_off_zone_locations', [])))))
        rules = []
        for i in configured:
            c = i['cfg']
            rules.append(dict(department=i.get('department_name') or 'Unassigned', id=i.get('department_id') or 'Unassigned',
                instance=i['key'], mode=c.get('generation_mode', 'scheduled'), payload=c.get('payload', ''),
                schedule=', '.join(_scheduled_times_from_cfg(c)), days=', '.join(c.get('days_active', [])) or 'Every day',
                fortnightly=bool(c.get('run_every_fortnight')), window=f"{c.get('timeframe_start', '')}-{c.get('timeframe_end', '')}",
                threshold=c.get('threshold_volume_m3', ''), frequency=c.get('frequency_per_day', ''),
                origin=', '.join(i.get('pickup_locations', [])), destination=', '.join(i.get('dropoff_locations', [])),
                returns=bool(c.get('return_enabled')), notes=c.get('notes', '')))
        counts = Counter((e['department_id'], e['service'], e['weekday']) for e in events if e['in_period'])
        summary = []
        for dept_id in sorted(scope, key=lambda x: (departments.get(x, {}).get('name', x), x)):
            for service in ['Delivery', 'Collection']:
                values = [counts[dept_id, service, d] for d in DAYS]
                summary.append(dict(id=dept_id, department=departments.get(dept_id, {}).get('name', dept_id), service=service, values=values, total=sum(values)))
        reviews[key] = dict(key=key, name=category.get('display_name') or key.title(),
            owner=category.get('owner') or 'Category owner to confirm', departments=directory, rules=rules,
            summary=summary, events=events, timetable=sorted(timetable, key=lambda x: (x['time'], x['department_id'], x['kind'])),
            total_deliveries=sum(s['total'] for s in summary if s['service'] == 'Delivery'),
            total_collections=sum(s['total'] for s in summary if s['service'] == 'Collection'))
    return dict(common=common, categories=reviews)


def load_department_reviews(csv_path, config_path):
    csv_path, config_path = Path(csv_path), Path(config_path)
    before = csv_path.stat()
    config_bytes = config_path.read_bytes()
    frames = []
    columns = {'task_id', 'event_type', 'sim_datetime', 'department_id', 'details', 'task_source',
               'from_location', 'to_location', 'payload', 'waste_stream', 'duration_sec'}
    for chunk in pd.read_csv(csv_path, usecols=lambda c: c in columns, chunksize=100000, low_memory=False):
        if 'event_type' not in chunk:
            raise ValueError('Export a verbose simulation event CSV for department reviews.')
        frames.append(chunk[chunk.event_type.isin(EVENTS)])
    after = csv_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('The simulation CSV changed while it was being read. Retry when the run has finished.')
    sources = dict(csv=str(csv_path.resolve()), config=str(config_path.resolve()),
                   csv_bytes=after.st_size, csv_modified=datetime.fromtimestamp(after.st_mtime).isoformat(),
                   config_sha256=hashlib.sha256(config_bytes).hexdigest())
    return build_department_reviews(json.loads(config_bytes), pd.concat(frames, ignore_index=True), sources)


def timeline_groups(review):
    grouped = defaultdict(list)
    for event in review['timetable']:
        stamp = datetime.fromisoformat(event['time'])
        grouped[(stamp.strftime('%Y-%m-%d %a'), event['department_id'], event['department'], event['kind'])].append(stamp)
    return sorted(grouped.items())


def export_department_pdf(review, common, path):
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak, Flowable
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('smallReview', fontName='Helvetica', fontSize=8, leading=11))
    styles.add(ParagraphStyle('cellReview', fontName='Helvetica', fontSize=7, leading=9))
    styles.add(ParagraphStyle('headerReview', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white))
    navy, cyan = colors.HexColor('#152A3C'), colors.HexColor('#167F9A')
    story = []
    width = landscape(A4)[0] - 64

    def p(text, style='smallReview'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])

    def table(headers, rows, widths):
        data = [[p(h, 'headerReview') for h in headers]] + [[p(v, 'cellReview') for v in row] for row in rows]
        t = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), navy), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F5F8')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5)]))
        story.append(t)

    story.extend([p(review['name'] + ' | Department service review', 'Title'),
                  p(f"Reporting period: {common['start']} to {common['end']} (end excluded). Owner: {review['owner']}"),
                  Spacer(1, 8), p(f"{review['total_deliveries']:,} deliveries   |   {review['total_collections']:,} collections   |   {len(review['summary']) // 2} departments in category scope", 'Heading2')])
    for note in common['notes']:
        story.extend([p(note), Spacer(1, 3)])
    story.extend([p('Weekday coverage: ' + ' | '.join(f'{d} {common["coverage_hours"].get(d, 0):g} h' for d in DAYS)), Spacer(1, 10)])
    table(['Department', 'Service'] + DAYS + ['Total'],
          [[s['id'] + ' - ' + s['department'], s['service']] + s['values'] + [s['total']] for s in review['summary']] or [['No configured or observed departments', ''] + [0] * 8],
          [225, 80] + [(width - 305) / 8] * 8)
    story.extend([Spacer(1, 12), p('Current service comparison / owner comments: _______________________________________________________'),
                  p('________________________________________________________________________________________________')])
    story.extend([PageBreak(), p('Configured departments', 'Heading1'),
                  p('Full configuration directory. Scope marks departments with enabled category rules or observed category tasks. Linked locations can also identify source departments.'), Spacer(1, 8)])
    table(['Department', 'Level', 'Scope', 'Open / days', 'Category locations', 'Shared AMR zones'],
          [[d['id'] + ' - ' + d['name'], d['level'], 'Yes' if d['in_scope'] else 'No',
            ('Enabled' if d['enabled'] else 'Disabled') + '\n' + d['hours'] + '\n' + d['days'], d['locations'], d['zones']] for d in review['departments']],
          [165, 40, 38, 160, 190, width - 593])
    story.extend([PageBreak(), p('Generation rules', 'Heading1'), p('Effective category, department-group and waste-stream settings from the supplied configuration.'), Spacer(1, 8)])
    table(['Department / rule', 'Mode / payload', 'Times / days', 'Window / frequency', 'Threshold / return', 'AMR route'],
          [[r['id'] + ' - ' + r['department'] + '\n' + r['instance'], r['mode'] + '\n' + r['payload'],
            r['schedule'] + '\n' + r['days'] + ('\nAlternate weeks' if r['fortnightly'] else ''),
            r['window'] + '\nFrequency/day: ' + str(r['frequency']),
            (f"{r['threshold']:g}" if isinstance(r['threshold'], (float, int)) else str(r['threshold'])) + ' m3\nReturn: ' + str(r['returns']),
            r['origin'] + '\nto ' + r['destination']] for r in review['rules']] or [['No enabled rules', '', '', '', '', '']],
          [165, 110, 140, 90, 90, width - 595])

    class Strip(Flowable):
        def __init__(self, stamps, kind):
            Flowable.__init__(self)
            self.width, self.height, self.stamps, self.kind = width, 32, stamps, kind

        def draw(self):
            canvas = self.canv
            left, span = 15, self.width - 30
            canvas.setFont('Helvetica', 6)
            canvas.setStrokeColor(colors.HexColor('#CFD9E0'))
            for hour in range(25):
                x = left + span * hour / 24
                canvas.line(x, 10, x, 22)
                if hour % 2 == 0:
                    canvas.drawCentredString(x, 1, f'{hour:02}')
            color = colors.HexColor('#BA6B11') if self.kind.startswith('Scheduled') else (cyan if 'delivery' in self.kind else colors.HexColor('#367C4B'))
            canvas.setFillColor(color)
            for stamp in self.stamps:
                x = left + span * (stamp.hour * 3600 + stamp.minute * 60 + stamp.second) / 86400
                canvas.circle(x, 16, 2.5, stroke=0, fill=1)

    story.extend([PageBreak(), p('Service timetable', 'Heading1'),
                  p('Orange: configuration schedule (release or fill). Blue: actual delivery. Green: actual collection. Each strip covers 00:00-24:00; exact event times are listed above it. Repeated times represent separate tasks.'), Spacer(1, 10)])
    from reportlab.platypus import KeepTogether
    daily = defaultdict(list)
    for event in review['timetable']:
        stamp = datetime.fromisoformat(event['time'])
        daily[(stamp.strftime('%Y-%m-%d %a'), event['kind'])].append((stamp, event['department_id']))
    for (date, kind), entries in sorted(daily.items()):
        # Category timetable, with department IDs beside exact times. Chunk long
        # days so even a high-frequency category cannot exceed one page block.
        for offset in range(0, len(entries), 70):
            subset = entries[offset:offset + 70]
            suffix = f' (continued, events {offset + 1}-{offset + len(subset)})' if offset else ''
            story.append(KeepTogether([p(f'{date} | {kind}{suffix}', 'Heading3'),
                p(', '.join(t.strftime('%H:%M:%S') + ' ' + dept for t, dept in subset)),
                Strip([t for t, _ in subset], kind), Spacer(1, 6)]))
    if not review['timetable']:
        story.append(p('No scheduled or performed category events in this reporting interval.'))
    story.extend([PageBreak(), p('Delivery and collection detail', 'Heading1'),
                  p('Payloads and routes are grouped within this category. Counted = completed service in the reporting period. Other = outside-period, incomplete or unclassified tasks. The spreadsheet also contains the full task-by-task audit.'), Spacer(1, 8)])
    flows = defaultdict(lambda: [0, 0])
    for e in review['events']:
        key = (e['department_id'] + ' - ' + e['department'], e['service'], e['payload'], e['origin'], e['destination'], e['final_destination'])
        flows[key][0 if e['in_period'] else 1] += 1
    table(['Department', 'Service / payload', 'AMR route', 'Final destination', 'Count', 'Other'],
          [[k[0], k[1] + '\n' + k[2], k[3] + '\nto ' + k[4], k[5], v[0], v[1]] for k, v in sorted(flows.items())]
          or [['No generated category tasks', '', '', '', 0, 0]], [175, 125, 205, width - 585, 40, 40])
    story.extend([Spacer(1, 10), p('Sources: ' + json.dumps(common['sources'], ensure_ascii=False))])

    def footer(canvas, doc):
        canvas.setPageSize(landscape(A4))
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(navy)
        canvas.drawString(32, 19, review['name'] + ' | Simulated service review')
        canvas.drawRightString(landscape(A4)[0] - 32, 19, str(doc.page))

    try:
        from .amr_department_executive import draw_executive_summary
    except ImportError:
        from amr_department_executive import draw_executive_summary
    SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=32, leftMargin=32,
                      topMargin=30, bottomMargin=32, title=review['name'] + ' department review').build(
                          [Spacer(1, 1), PageBreak()] + story,
                          onFirstPage=lambda canvas, doc: draw_executive_summary(canvas, review, common), onLaterPages=footer)


def _spreadsheet_runtime():
    runtime = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    node = os.environ.get('AMR_REPORT_NODE') or (str(runtime / 'bin/node.exe') if (runtime / 'bin/node.exe').exists() else shutil.which('node'))
    modules = Path(os.environ.get('AMR_REPORT_NODE_MODULES', str(runtime / 'node_modules')))
    if not node or not (modules / '@oai/artifact-tool').exists():
        raise RuntimeError('Spreadsheet export requires Node.js and @oai/artifact-tool. Set AMR_REPORT_NODE and AMR_REPORT_NODE_MODULES to their installed locations, or select PDF only.')
    return node, modules


def export_department_reviews(csv_path, config_path, output_dir, formats=('pdf', 'xlsx'), progress=None, previews=False):
    if not config_path:
        raise ValueError('Select the matching configuration JSON for the department review.')
    formats = tuple(dict.fromkeys(formats))
    if not formats or set(formats) - {'pdf', 'xlsx'}:
        raise ValueError('Choose PDF, XLSX, or both for the department review.')
    if 'xlsx' in formats:
        node, modules = _spreadsheet_runtime()
    model = load_department_reviews(csv_path, config_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    used_stems = set()
    # Stage all files before publishing a complete set. Never overwrite source data.
    with tempfile.TemporaryDirectory(prefix='amr-department-review-') as temporary:
        temporary = Path(temporary)
        for index, (key, review) in enumerate(model['categories'].items()):
            stem = re.sub(r'[^a-zA-Z0-9_-]+', '_', key).strip('_') or 'category'
            if stem.lower() in used_stems:
                stem += '_' + str(index + 1)
            used_stems.add(stem.lower())
            if progress:
                progress(index, len(model['categories']), 'Exporting ' + review['name'])
            payload = dict(review=review, common=model['common'])
            data_path = temporary / (stem + '.json')
            data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            for fmt in formats:
                target = temporary / (stem + '_department_review.' + fmt)
                if fmt == 'pdf':
                    export_department_pdf(review, model['common'], target)
                    try:
                        from .amr_department_executive import export_executive_pdf
                    except ImportError:
                        from amr_department_executive import export_executive_pdf
                    executive = temporary / (stem + '_executive_summary.pdf')
                    export_executive_pdf(review, model['common'], executive)
                    paths.append((executive, output_dir / executive.name))
                else:
                    env = dict(os.environ)
                    # Resolve the package through documented Node resolution, rather
                    # than depending on its internal entry filename.
                    env['AMR_REPORT_NODE_MODULES'] = str(modules)
                    result = subprocess.run([node, str(Path(__file__).with_name('amr_department_workbook.mjs')),
                        str(data_path), str(target), str(output_dir / 'previews') if previews else ''],
                        env=env, capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode:
                        raise RuntimeError('Department spreadsheet export failed:\n' + result.stderr[-3000:])
                paths.append((target, output_dir / target.name))
        for source, target in paths:
            if target.resolve() in {Path(csv_path).resolve(), Path(config_path).resolve()}:
                raise ValueError('Review outputs must not replace the input files.')
            shutil.copy2(source, target)
    if progress:
        progress(1, 1, 'Department reviews exported')
    return [target for _, target in paths]
