"""Nonmutating storage-bay checks shared by import, editing and preflight."""
import math
from amr_payload_inputs import inventory_space_dimensions


def inventory_slot_amr_type(slot):
    """Modern key wins, including an explicit empty value, over the legacy alias."""
    return str(slot.get('amr_type', slot.get('amr', '')) or '').strip()


def inventory_slot_is_amr(slot):
    return isinstance(slot, dict) and (str(slot.get('slot_type', '')).strip().lower() == 'amr'
                                      or bool(inventory_slot_amr_type(slot)))


def inventory_space_is_amr(space):
    """Any AMR marker makes the bay AMR-only; a charger flag alone does not."""
    return isinstance(space, dict) and bool(
        space.get('stores_amr', False) or str(space.get('space_type', '')).strip().lower() == 'amr'
        or str(space.get('amr_type', '') or '').strip()
        or any(inventory_slot_is_amr(slot) for slot in space.get('payload_slots', []) or []))


def inventory_space_amr_types(space):
    """Parent and slot restrictions form the existing union of allowed identities."""
    values = {str(space.get('amr_type', '') or '').strip()}
    values.update(inventory_slot_amr_type(slot) for slot in space.get('payload_slots', []) or []
                  if inventory_slot_is_amr(slot))
    return values - {''}


def _number_valid(value, *, nonnegative=False):
    try:
        number = float(value)
        return not isinstance(value, bool) and math.isfinite(number) and (not nonnegative or number >= 0)
    except (TypeError, ValueError, OverflowError):
        return False


def _point_findings(point, path, *, optional=False):
    if not isinstance(point, dict):
        yield path, 'Coordinates must be an object.'
        return
    present = False
    for pair in (('dx', 'dy'), ('x', 'y')):
        if any(key in point for key in pair):
            present = True
            for key in pair:
                if key not in point or not _number_valid(point[key]):
                    yield path + '/' + key, 'Coordinates require a complete finite numeric pair; booleans are invalid.'
    if not present and not optional:
        yield path, 'An outline point requires dx/dy or x/y coordinates.'


def inventory_input_findings(config, *, check_references=False):
    if not isinstance(config, dict) or not isinstance(config.get('locations', []), list):
        return
    definitions = {row['name']: row for row in config.get('payloads', [])
                   if isinstance(row, dict) and isinstance(row.get('name'), str)} if isinstance(config.get('payloads', []), list) else {}
    payloads = set(definitions)
    robots = {}
    for robot in config.get('amrs', []) if isinstance(config.get('amrs', []), list) else []:
        if isinstance(robot, dict) and isinstance(robot.get('id'), str):
            try:
                robots[robot['id']] = int(robot.get('quantity', 1))
            except (TypeError, ValueError, OverflowError):
                pass  # The robot contract owns malformed quantities.

    def reference_findings(row, path, key, kind):
        if key not in row:
            return
        value = row[key]
        if not isinstance(value, str) or value != value.strip():
            yield path + '/' + key, f'{key} must be a string without surrounding whitespace; use an empty string for no restriction.'
        elif value and check_references:
            if kind == 'payload':
                known = value in payloads
            else:
                base, _, suffix = value.rpartition('-')
                known = value in robots or (base in robots and suffix.isdecimal()
                    and str(int(suffix)) == suffix and 1 <= int(suffix) <= robots[base])
            if not known:
                yield path + '/' + key, f'Unknown {kind} restriction {value!r}; resolve the reference before running.'

    for location_index, location in enumerate(config.get('locations', [])):
        if not isinstance(location, dict):
            continue
        path = f'/locations/{location_index}/inventory_spaces'
        spaces = location.get('inventory_spaces', [])
        if not isinstance(spaces, list):
            yield path, 'Inventory spaces must be a list of objects.'
            continue
        names = set()
        for index, space in enumerate(spaces):
            space_path = f'{path}/{index}'
            if not isinstance(space, dict):
                yield space_path, 'Each inventory space must be an object.'
                continue
            name = space.get('name', '')
            if not isinstance(name, str) or name != name.strip():
                yield space_path + '/name', 'Bay names must be strings without surrounding whitespace.'
            else:
                name = name or f'Space {index + 1}'
                if name in names:
                    yield space_path + '/name', 'Resolved bay names must be unique within their location.'
                names.add(name)
            for key in ('stores_amr', 'has_charger', 'occupied', 'flexible', 'flexible_payloads'):
                if key in space and type(space[key]) is not bool:
                    yield space_path + '/' + key, f'{key} must be a JSON boolean.'
            if 'space_type' in space and (not isinstance(space['space_type'], str)
                    or space['space_type'].strip().lower() not in {'', 'payload', 'amr'}):
                yield space_path + '/space_type', 'Space type must be payload, amr or empty (infer from other markers).'
            for key in ('length', 'width', 'height', 'length_m', 'width_m', 'height_m'):
                if key in space and not _number_valid(space[key], nonnegative=True):
                    yield space_path + '/' + key, f'{key} must be finite and nonnegative; zero retains legacy envelope inference.'
            yield from reference_findings(space, space_path, 'amr_type', 'AMR')
            points = space.get('points', [])
            if not isinstance(points, list):
                yield space_path + '/points', 'Bay points must be a list; empty outlines are permitted for dimension-only bays.'
            else:
                for point_index, point in enumerate(points):
                    yield from _point_findings(point, f'{space_path}/points/{point_index}')
            slots = space.get('payload_slots', [])
            if not isinstance(slots, list):
                yield space_path + '/payload_slots', 'Bay templates must be a list of objects.'
                continue
            for slot_index, slot in enumerate(slots):
                slot_path = f'{space_path}/payload_slots/{slot_index}'
                if not isinstance(slot, dict):
                    yield slot_path, 'Each bay template must be an object.'
                    continue
                yield from _point_findings(slot, slot_path, optional=True)
                if 'slot_type' in slot and (not isinstance(slot['slot_type'], str)
                        or slot['slot_type'].strip().lower() not in {'', 'payload', 'amr'}):
                    yield slot_path + '/slot_type', 'Slot type must be payload, amr or empty (infer from its reference).'
                for key, kind in (('payload', 'payload'), ('amr_type', 'AMR')):
                    yield from reference_findings(slot, slot_path, key, kind)
                if 'amr_type' not in slot:
                    yield from reference_findings(slot, slot_path, 'amr', 'AMR')
                if 'rotation_deg' in slot and not _number_valid(slot['rotation_deg']):
                    yield slot_path + '/rotation_deg', 'Template rotation must be finite degrees; booleans are invalid.'
            try:
                dimensions = inventory_space_dimensions(space, definitions)
            except (TypeError, ValueError, OverflowError, AttributeError):
                continue  # Explicit malformed inputs have their own findings above.
            if not all(math.isfinite(value) for value in dimensions):
                yield space_path, 'The resolved bay envelope must be finite; outline coordinates overflow the dimensional calculation.'


def validate_inventory_inputs(config, *, check_references=False):
    findings = list(inventory_input_findings(config, check_references=check_references))
    if findings:
        raise ValueError('Invalid inventory inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
