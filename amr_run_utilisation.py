"""Small, read-only utilisation summary from retained memory-run evidence."""
from collections import defaultdict
import math
import re

from amr_memory_runs import check_cancelled
from amr_simulation_inputs import simulation_horizon_seconds


FIELDS = ('sim_time_sec', 'precise_time_sec', 'event_type', 'segment_type',
          'duration_sec', 'amr_id', 'lift_id')


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def summarise_utilisation(rows, metadata, *, cancel=None):
    """Use report interval semantics without building a full investigation/report.

    The window starts at simulation time zero, includes the configured horizon,
    and extends to the final observed time if the simulation drains work later.
    Future segment plans are clipped to that window. Partial/reduced runs cannot
    establish a full-run utilisation and must be rejected by the caller.
    """
    from report.amr_report_analysis import merge_intervals, interval_total, is_physical_amr_id

    config = metadata['frozen_inputs']
    horizon = max(0., simulation_horizon_seconds(config))
    amrs = {str(identity): [] for identity in metadata['summary']['battery_amr_ids']}
    lifts = {str(lift['id']): [] for lift in config.get('lifts', [])}
    intervals = {'amrs': defaultdict(list), 'lifts': defaultdict(list)}
    for row in rows:
        check_cancelled(cancel)
        timestamp = number(row.get('precise_time_sec'))
        if timestamp is None:
            timestamp = number(row.get('sim_time_sec'))
        if timestamp is None or timestamp < 0:
            continue
        horizon = max(horizon, timestamp)
        duration = number(row.get('duration_sec'))
        if duration is None or duration <= 0 or not math.isfinite(timestamp + duration):
            continue
        event = str(row.get('event_type') or '').lower()
        segment = str(row.get('segment_type') or '').lower()
        amr = str(row.get('amr_id') or '').strip()
        lift = str(row.get('lift_id') or '').strip()
        if is_physical_amr_id(amr) and (
                re.search(r'segment|multi_stop_segment|charge', event)
                or re.search(r'corridor|lift|pickup|dropoff|wait|charge|reposition', segment)):
            intervals['amrs'][amr].append((timestamp, timestamp + duration))
        if lift and (segment in ('lift_transfer', 'lift_reposition')
                     or event in ('segment_lift_transfer', 'segment_lift_reposition')):
            intervals['lifts'][lift].append((timestamp, timestamp + duration))

    def resources(configured, recorded):
        result = []
        for identity in sorted(set(configured) | set(recorded)):
            check_cancelled(cancel)
            bounded = [(start, min(end, horizon)) for start, end in recorded.get(identity, [])
                       if start < horizon]
            busy = interval_total(merge_intervals(bounded))
            result.append(dict(id=identity, busy_seconds=busy, idle_seconds=max(0., horizon - busy),
                               utilisation_pct=100 * busy / horizon if horizon > 0 else None))
        return result

    return dict(horizon_seconds=horizon, amrs=resources(amrs, intervals['amrs']),
                lifts=resources(lifts, intervals['lifts']))


def load_memory_utilisation(run, *, cancel=None):
    metadata = run.require_reviewable()
    if run.status != 'complete' or metadata.get('termination'):
        raise ValueError('Utilisation is available for completed runs. Use Investigation to review a stopped run.')
    with run.using_store(cancel) as store:
        result = summarise_utilisation(store.iter_rows(FIELDS), metadata, cancel=cancel)
        check_cancelled(cancel)
        run.require_reviewable()
        return result
