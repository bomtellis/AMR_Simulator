"""Shared robot capacity resolution and explicit input checks.

Legacy capacity is a dimensional fallback, not a volume or total multi-slot limit.
"""
import math

CAPACITIES = ('payload_capacity_kg', 'payload_length_capacity_m',
              'payload_width_capacity_m', 'payload_height_capacity_m')
POSITIVE = (*CAPACITIES, 'payload_size_capacity', 'length_m', 'width_m', 'height_m',
            'speed_m_per_sec', 'battery_capacity_kwh', 'battery_charge_rate_kw')
PERCENT = ('battery_soc_percent', 'recharge_threshold_percent')
ORIENTATIONS = ('lengthways', 'sideways')


def normalise_orientations(value):
    """Accept the editor's legacy comma-separated form without dropping errors."""
    values = value.split(',') if isinstance(value, str) else value
    if not isinstance(values, list) or not values or any(
            not isinstance(v, str) or v.strip().lower() not in ORIENTATIONS for v in values):
        raise ValueError('Orientations must be a nonempty list of lengthways/sideways values or a comma-separated string.')
    return list(dict.fromkeys(v.strip().lower() for v in values))


def normalise_amr_payload_slots(amr):
    """Resolve validated explicit slots or legacy single-slot values identically."""
    slots = amr.get('payload_slots', [])
    if not slots:
        size = float(amr.get('payload_size_capacity', 1))
        return [dict(name='Slot 1', payload_capacity_kg=float(amr.get('payload_capacity_kg', 100)),
            payload_length_capacity_m=float(amr.get('payload_length_capacity_m', size)),
            payload_width_capacity_m=float(amr.get('payload_width_capacity_m', size)),
            payload_height_capacity_m=float(amr.get('payload_height_capacity_m', size)),
            allowed_payload_orientations=list(ORIENTATIONS))]
    return [dict(name=slot.get('name', '').strip() or f'Slot {i}',
                 **{key: float(slot[key]) for key in CAPACITIES if key in slot},
                 allowed_payload_orientations=normalise_orientations(slot.get('allowed_payload_orientations', list(ORIENTATIONS))))
            for i, slot in enumerate(slots, 1)]


def robot_input_findings(config, *, require_complete=False):
    if not isinstance(config, dict):
        return

    def number(row, key, path, minimum=0, exclusive=True, maximum=None):
        if key not in row:
            return
        raw = row[key]
        try:
            value = float(raw)
            valid = (not isinstance(raw, bool) and math.isfinite(value)
                     and (value > minimum if exclusive else value >= minimum)
                     and (maximum is None or value <= maximum))
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            yield path + '/' + key, f'{key} must be finite and {">" if exclusive else ">="} {minimum}' + (
                f' and <= {maximum}; booleans are invalid.' if maximum is not None else '; booleans are invalid.')

    rows = config.get('amrs', [])
    if not isinstance(rows, list):
        yield '/amrs', 'AMRs must be a list of objects.'
        return
    ids = set()
    for index, robot in enumerate(rows):
        path = f'/amrs/{index}'
        if not isinstance(robot, dict):
            yield path, 'Each AMR type must be an object.'
            continue
        if require_complete:
            for field in ('id', 'speed_m_per_sec'):
                if field not in robot:
                    yield path + '/' + field, f'{field} is required for a runnable AMR type.'
        if 'id' in robot:
            identity = robot['id']
            if not isinstance(identity, str) or not identity or identity != identity.strip():
                yield path + '/id', 'AMR type id must be a nonblank string without surrounding whitespace.'
            elif identity in ids:
                yield path + '/id', 'AMR type ids must be unique; duplicate ids would collide at runtime.'
            else:
                ids.add(identity)
        for field in POSITIVE:
            yield from number(robot, field, path)
        yield from number(robot, 'motor_power_w', path, exclusive=False)
        for field in PERCENT:
            yield from number(robot, field, path, exclusive=False, maximum=100)
        if 'quantity' in robot:
            value = robot['quantity']
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(value)) and float(value) == int(value) and int(value) >= 0
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                yield path + '/quantity', 'quantity must be a nonnegative whole count; booleans and fractions are invalid.'
        if 'multi_stop_enabled' in robot and type(robot['multi_stop_enabled']) is not bool:
            yield path + '/multi_stop_enabled', 'multi_stop_enabled must be a JSON boolean.'
        slots = robot.get('payload_slots', [])
        if not isinstance(slots, list):
            yield path + '/payload_slots', 'payload_slots must be a list; an empty list uses the legacy single-slot definition.'
            continue
        names = set()
        for i, slot in enumerate(slots):
            slot_path = path + f'/payload_slots/{i}'
            if not isinstance(slot, dict):
                yield slot_path, 'Each payload slot must be an object.'
                continue
            name = slot.get('name', '')
            if not isinstance(name, str):
                yield slot_path + '/name', 'Slot name must be a string; omission or blank uses its numbered default.'
            else:
                name = name.strip() or f'Slot {i + 1}'
                if name in names:
                    yield slot_path + '/name', 'Resolved slot names must be unique within the robot.'
                names.add(name)
            for field in CAPACITIES:
                if require_complete and field not in slot:
                    yield slot_path + '/' + field, f'{field} is required for an explicit runnable slot.'
                yield from number(slot, field, slot_path)
            if 'allowed_payload_orientations' in slot:
                try:
                    normalise_orientations(slot['allowed_payload_orientations'])
                except ValueError as exc:
                    yield slot_path + '/allowed_payload_orientations', str(exc)
    payloads = config.get('payloads', [])
    if isinstance(payloads, list):
        for index, payload in enumerate(payloads):
            if isinstance(payload, dict) and 'allowed_carry_orientations' in payload:
                try:
                    normalise_orientations(payload['allowed_carry_orientations'])
                except ValueError as exc:
                    yield f'/payloads/{index}/allowed_carry_orientations', str(exc)


def validate_robot_inputs(config, *, require_complete=False):
    findings = list(robot_input_findings(config, require_complete=require_complete))
    if findings:
        raise ValueError('Invalid robot inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
