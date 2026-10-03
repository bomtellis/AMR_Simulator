"""Raw generation checks shared by import, preflight and runtime entry points.

This is a bounded contract, not a complete schema. Never mutate, fill defaults,
or recursively interpret unrelated user metadata as generator configuration.
"""
import math
import re


MODES = {'scheduled', 'scheduled_threshold', 'scheduled_sporadic', 'threshold',
         'continuous', 'sporadic', 'hybrid', 'timeframe'}
PATTERNS = {'none', 'four_on_four_off_12h'}
PATTERN_ALIASES = {'4_on_4_off_12h', 'four_on_four_off', 'four_on_four_off_12_hour'}
LEGACY_CATEGORIES = {'catering', 'pharmacy', 'linen', 'waste', 'stores', 'ssd'}
FLAGS = {'enabled', 'requires_staff', 'staff_required', 'return_enabled',
         'tracked_item_exchange', 'release_next_after_return_pickup',
         'staff_use_custom_working_hours', 'staff_department_fallback_enabled',
         'staff_handoff_only', 'run_every_fortnight', 'reusable_return_pool_enabled'}
COUNTS = {'staff_initial_count', 'timeframe_payload_multiple', 'payload_multiple'}
DURATIONS = {'return_delay_minutes', 'staff_handling_minutes', 'staff_collection_delay_minutes'}
DAYS = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}


def generation_input_findings(config):
    """Return (severity, JSON pointer, explanation) triples, including warnings."""
    findings = []
    if not isinstance(config, dict):
        return findings

    def pointer(path, key):
        return path + '/' + str(key).replace('~', '~0').replace('/', '~1')

    def error(path, message):
        findings.append(('error', path, message))

    def obj(value, path):
        if not isinstance(value, dict):
            error(path, 'Expected a JSON object; this value cannot be interpreted as generation settings.')
            return None
        return value

    def number(row, path, name, minimum=0, positive=False, integer=False):
        if name not in row:
            return
        try:
            value = float(row[name])
            valid = (not isinstance(row[name], bool) and math.isfinite(value)
                     and (value > minimum if positive else value >= minimum)
                     and (not integer or value.is_integer()))
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            qualifier = 'integer' if integer else 'number'
            bound = 'greater than' if positive else 'at least'
            error(pointer(path, name), f'{name} must be a finite {qualifier} {bound} {minimum}; booleans are not numbers.')

    def flags(row, path, names):
        for name in sorted(names):
            if name in row and not isinstance(row[name], bool):
                error(pointer(path, name), f'{name} must be a JSON boolean (true or false). Omit it to use the default.')

    def clock(row, path, name):
        if name not in row:
            return
        value = row[name]
        if (not isinstance(value, str) or
                not (re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value.strip())
                     or (name == 'end_time' and value.strip() == '24:00'))):
            error(pointer(path, name), f'{name} must be a valid HH:MM time (24:00 is permitted for end_time).')

    def rule(value, path):
        row = obj(value, path)
        if row is None:
            return
        flags(row, path, FLAGS)
        for name in sorted(COUNTS):
            number(row, path, name, minimum=1, integer=True)
        for name in sorted(DURATIONS):
            number(row, path, name)
        if 'generation_mode' in row:
            mode = row['generation_mode']
            if not isinstance(mode, str) or (mode.strip() and mode.strip() not in MODES):
                error(pointer(path, 'generation_mode'), 'Unsupported generation mode. Use: ' + ', '.join(sorted(MODES)) + '.')
        if 'staff_shift_pattern' in row:
            pattern = row['staff_shift_pattern']
            if not isinstance(pattern, str) or (pattern.strip().lower() and pattern.strip().lower() not in PATTERNS | PATTERN_ALIASES):
                error(pointer(path, 'staff_shift_pattern'), 'Unsupported staff pattern. Use none or four_on_four_off_12h.')
        if 'staff_working_hours' in row:
            weekly_path = pointer(path, 'staff_working_hours')
            weekly = obj(row['staff_working_hours'], weekly_path)
            if weekly is not None:
                for day, hours in weekly.items():
                    day_path = pointer(weekly_path, day)
                    if day not in DAYS:
                        error(day_path, 'Unknown weekday; use mon, tue, wed, thu, fri, sat or sun.')
                    hours = obj(hours, day_path)
                    if hours is not None:
                        flags(hours, day_path, {'enabled'})
                        clock(hours, day_path, 'start_time')
                        clock(hours, day_path, 'end_time')

    def category(value, path):
        rule(value, path)
        if not isinstance(value, dict):
            return
        if 'departments' in value:
            overrides = obj(value['departments'], pointer(path, 'departments'))
            if overrides is not None:
                for name, override in overrides.items():
                    rule(override, pointer(pointer(path, 'departments'), name))
        if 'department_groups' in value:
            groups_path = pointer(path, 'department_groups')
            groups = value['department_groups']
            if not isinstance(groups, list):
                error(groups_path, 'department_groups must be a list of JSON objects.')
            else:
                for index, group in enumerate(groups):
                    group_path = pointer(groups_path, index)
                    group = obj(group, group_path)
                    if group is not None and 'payload' in group:
                        rule(group['payload'], pointer(group_path, 'payload'))

    def staff(value, path):
        row = obj(value, path)
        if row is None:
            return
        flags(row, path, {'enabled', 'spread_timeframe_tasks', 'space_timeframe_tasks'})
        number(row, path, 'walking_speed_m_per_sec', positive=True)
        for name in ('lift_wait_seconds', 'default_handling_minutes', 'amr_hold_for_exchange_max_minutes'):
            number(row, path, name)
        if 'shift_patterns' not in row:
            return
        patterns_path = pointer(path, 'shift_patterns')
        patterns = obj(row['shift_patterns'], patterns_path)
        if patterns is None:
            return
        for name, pattern in patterns.items():
            pattern_path = pointer(patterns_path, name)
            if name not in PATTERNS:
                error(pattern_path, 'Only none and four_on_four_off_12h global pattern definitions are supported.')
            pattern = obj(pattern, pattern_path)
            if pattern is None:
                continue
            clock(pattern, pattern_path, 'start_time')
            clock(pattern, pattern_path, 'end_time')
            for field in ('work_days', 'rest_days'):
                number(pattern, pattern_path, field, integer=True)
                if field in pattern:
                    try:
                        value = float(pattern[field])
                    except (TypeError, ValueError, OverflowError):
                        continue
                    expected = 4 if name == 'four_on_four_off_12h' else 0
                    if math.isfinite(value) and value >= 0 and value.is_integer() and value != expected:
                        findings.append(('warning', pointer(pattern_path, field),
                            f'Custom {field}={pattern[field]} is not implemented. The {name} allocator uses {expected}; this setting is ignored.'))

    if 'task_generation' in config:
        path = '/task_generation'
        generation = obj(config['task_generation'], path)
        if generation is not None:
            flags(generation, path, {'enabled'})
            # Zero is a retained legacy value; the simulator applies its 60 s minimum.
            number(generation, path, 'update_interval_sec')
            for name in ('staff_config', 'staff'):
                if name in generation:
                    staff(generation[name], pointer(path, name))
            if 'categories' in generation:
                cats_path = pointer(path, 'categories')
                categories = obj(generation['categories'], cats_path)
                if categories is not None:
                    for name, value in categories.items():
                        category(value, pointer(cats_path, name))
            for name in sorted(LEGACY_CATEGORIES | {'department_waste'}):
                if name in generation:
                    category(generation[name], pointer(path, name))
    departments = config.get('departments', [])
    if isinstance(departments, list):
        for index, department in enumerate(departments):
            if not isinstance(department, dict):
                continue
            path = f'/departments/{index}'
            if 'waste' in department:
                rule(department['waste'], pointer(path, 'waste'))
            streams = department.get('waste_streams', [])
            if isinstance(streams, list):
                for stream_index, stream in enumerate(streams):
                    # A bare stream name is a supported department reference.
                    if not isinstance(stream, str):
                        rule(stream, pointer(pointer(path, 'waste_streams'), stream_index))
            else:
                error(pointer(path, 'waste_streams'), 'waste_streams must be a list of names or JSON objects.')
    tasks = config.get('tasks', [])
    if isinstance(tasks, list):
        for index, task in enumerate(tasks):
            if isinstance(task, dict):
                rule(task, f'/tasks/{index}')
    return findings


def validate_generation_inputs(config):
    errors = [(path, message) for severity, path, message in generation_input_findings(config)
              if severity == 'error']
    if errors:
        raise ValueError('Invalid generation inputs: ' + '; '.join(f'{path}: {message}' for path, message in errors))
