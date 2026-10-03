"""Physical payload contracts and shared storage envelope inference."""
import math

from amr_sim_payload_instances import is_empty_payload_name


def payload_dimensions(payload):
    size = float(payload.get('size_units', 1))
    return tuple(float(payload.get(axis + '_m', size)) for axis in ('length', 'width', 'height'))


def inventory_space_dimensions(space, payloads):
    """Retain runtime alias/default semantics without import-time rounding.

    This is an axis-aligned envelope, not a swept polygon clearance check.
    Explicit zero bay dimensions retain the legacy inferred-value fallback.
    """
    xs, ys = [], []
    for point in space.get('points', []) or []:
        if not isinstance(point, dict):
            continue
        keys = ('dx', 'dy') if 'dx' in point and 'dy' in point else ('x', 'y')
        try:
            x, y = (float(point.get(key, 0)) for key in keys)
        except (TypeError, ValueError, OverflowError):
            continue
        xs.append(x)
        ys.append(y)
    length = abs(max(xs) - min(xs)) if xs else 0
    width = abs(max(ys) - min(ys)) if ys else 0
    heights = []
    for slot in space.get('payload_slots', []) or []:
        if isinstance(slot, dict):
            payload = payloads.get(str(slot.get('payload', '') or '').strip())
            if payload is not None:
                heights.append(payload_dimensions(payload)[2])
    height = max((h for h in heights if h > 0), default=999999.0)
    return tuple(float(space.get(axis + '_m', space.get(axis, inferred)) or inferred or 0)
                 for axis, inferred in (('length', length), ('width', width), ('height', height)))


def payload_input_findings(config, *, require_complete=False):
    if not isinstance(config, dict):
        return
    rows = config.get('payloads', [])
    if not isinstance(rows, list):
        yield '/payloads', 'Payloads must be a list of objects.'
        return
    names = set()
    for index, payload in enumerate(rows):
        path = f'/payloads/{index}'
        if not isinstance(payload, dict):
            yield path, 'Each payload must be an object.'
            continue
        if require_complete:
            for field in ('name', 'weight_kg'):
                if field not in payload:
                    yield path + '/' + field, f'{field} is required for a runnable payload.'
        if 'name' in payload:
            name = payload['name']
            if not isinstance(name, str) or not name or name != name.strip() or is_empty_payload_name(name):
                yield path + '/name', 'Payload name must be a nonblank string without surrounding whitespace and cannot be a reserved empty-load alias.'
            elif name in names:
                yield path + '/name', 'Payload names must be unique.'
            else:
                names.add(name)
        for field in ('weight_kg', 'length_m', 'width_m', 'height_m', 'size_units'):
            if field not in payload:
                continue
            value = payload[field]
            try:
                numeric = float(value)
                valid = not isinstance(value, bool) and math.isfinite(numeric) and (
                    numeric >= 0 if field == 'weight_kg' else numeric > 0)
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                yield path + '/' + field, f'{field} must be a finite {"nonnegative mass" if field == "weight_kg" else "positive dimension"}; booleans are invalid.'
        if 'prefer_multi_stop_amr' in payload and type(payload['prefer_multi_stop_amr']) is not bool:
            yield path + '/prefer_multi_stop_amr', 'prefer_multi_stop_amr must be a JSON boolean.'


def validate_payload_inputs(config, *, require_complete=False):
    findings = list(payload_input_findings(config, require_complete=require_complete))
    if findings:
        raise ValueError('Invalid payload inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
