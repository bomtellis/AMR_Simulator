"""Route-plan energy evidence shared by investigation and PDF report analysis.

This ledger counts movement records, never per-task copies of shared journeys.
Charging input and stationary auxiliaries are outside its defined scope.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

CAPABILITY = 'segment_energy_sources_v1'
SOURCES = {'amr_battery': 'Planned AMR traction', 'lift_supply': 'Planned lift supply'}


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def summarize_energy(rows, *, complete=False, capabilities=()):
    totals = {source: dict(observed_kwh=0.0, event_ids=[], missing_event_ids=[]) for source in SOURCES}
    lifts, journeys, seen = {}, {}, {}
    for index, row in enumerate(rows, 2):
        kind = str(row.get('event_type', '')).removeprefix('multi_stop_')
        if not kind.startswith('segment_'):
            continue
        segment = row.get('segment_type') or kind.removeprefix('segment_')
        source = ('amr_battery' if segment in ('corridor', 'local_manoeuvre') else
                  'lift_supply' if segment in ('lift_transfer', 'lift_reposition') else None)
        if source is None:
            continue
        event_id = row.get('event_id') or f'legacy-row:{index}'
        if event_id in seen:
            if seen[event_id] != row:
                raise ValueError(f'Conflicting energy records share event identifier {event_id}.')
            continue
        seen[event_id] = row
        try:
            details = json.loads(row.get('details') or '{}')
        except (ValueError, TypeError):
            details = {}
        details = details if isinstance(details, dict) else {}
        energy = _number(row.get('energy_kwh'))
        detail_energy = _number(details.get('energy_kwh'))
        attributed = details.get('energy_source') == source
        valid = (energy is not None and attributed and row.get('event_id')
                 and detail_energy is not None and math.isclose(energy, detail_energy, abs_tol=1e-12))
        bucket = totals[source]
        if not valid:
            bucket['missing_event_ids'].append(event_id)
            continue
        bucket['observed_kwh'] += energy
        bucket['event_ids'].append(event_id)
        if source == 'lift_supply':
            lift = str(row.get('lift_id') or '')
            lifts[lift] = lifts.get(lift, 0.0) + energy
        journey = row.get('journey_id')
        if journey:
            item = journeys.setdefault(journey, {'amr_battery': 0.0, 'lift_supply': 0.0, 'event_ids': []})
            item[source] += energy
            item['event_ids'].append(event_id)
    for source, bucket in totals.items():
        bucket['known'] = bool(complete and CAPABILITY in capabilities and not bucket['missing_event_ids'])
        bucket['value_kwh'] = bucket['observed_kwh'] if bucket['known'] else None
        bucket['title'] = SOURCES[source]
    return {'sources': totals, 'lifts': lifts, 'journeys': journeys,
            'total_kwh': sum(b['observed_kwh'] for b in totals.values())
                         if all(b['known'] for b in totals.values()) else None}


def read_energy_evidence(path):
    """Verify bound coverage while streaming only the energy ledger into memory."""
    path = Path(path)
    def digest():
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    original = digest()
    metadata = {}
    sidecar = Path(str(path) + '.run.json')
    if sidecar.is_file():
        candidate = json.loads(sidecar.read_text(encoding='utf-8-sig'))
        frozen_hash = hashlib.sha256(json.dumps(candidate.get('frozen_inputs'), sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        if (candidate.get('schema_version') == 1 and candidate.get('log_sha256') == original
                and candidate.get('config_sha256') == frozen_hash):
            metadata = candidate
    complete = bool(metadata.get('run_status') == 'finished' and metadata.get('logging_enabled')
                    and not metadata.get('reduced_logging') and metadata.get('log_kind') == 'full')
    with path.open(newline='', encoding='utf-8-sig') as stream:
        def rows():
            for row in csv.DictReader(stream):
                if None in row:
                    raise ValueError('Malformed energy CSV row.')
                if metadata and row.get('run_id') != metadata.get('run_id'):
                    raise ValueError('Energy row belongs to a different run.')
                yield row
        result = summarize_energy(rows(), complete=complete, capabilities=metadata.get('event_capabilities', []))
    if digest() != original:
        raise ValueError('Energy log changed while being read.')
    return result
