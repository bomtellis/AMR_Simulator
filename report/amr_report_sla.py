"""SLA assignments from the simulator's effective rules and recorded requests."""
import math

import pandas as pd


SLA_COLUMNS = ['category', 'scope', 'task_type', 'target_s', 'target_minutes', 'detail', 'source']


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def build_sla_assignments(config, requests=None):
    """Use the same override/group/waste precedence as task generation, without schedules."""
    from amr_sim_task_generation import DynamicCategoryTaskGenerator, _timeframe_minutes_from_cfg

    config = config or {}
    generation = config.get('task_generation', {}) or {}
    rows = []

    def add(category, scope, task_type, target, detail, source):
        rows.append(dict(category=category, scope=scope, task_type=task_type,
                         target_s=target, target_minutes=target / 60 if target else None,
                         detail=detail, source=source))

    if generation.get('enabled', True):
        generator = DynamicCategoryTaskGenerator(
            generation, config.get('departments', []), {}, {}, None,
            waste_streams={str(item.get('name', '')).strip(): item for item in config.get('waste_streams', [])},
            prepare_runtime=False)
        for instance in generator.instances:
            cfg = instance['cfg']
            category = str(instance['category_key'])
            scope = instance.get('department_name') or instance.get('department_id') or 'Category-wide'
            if instance.get('waste_stream'):
                scope += ' / ' + str(instance['waste_stream'])
            source = 'Effective generation rule: ' + instance['key']
            target = positive(cfg.get('target_time'))
            mode = str(cfg.get('generation_mode', cfg.get('mode', ''))).lower()
            if mode == 'timeframe' and all(value is not None for value in _timeframe_minutes_from_cfg(cfg)):
                add(category, scope, 'Outbound', None,
                    f"Complete by {cfg['timeframe_end']} within {cfg['timeframe_start']}-{cfg['timeframe_end']}; "
                    'target seconds are the remaining time from actual release to the window deadline (including overnight windows).', source)
            elif target:
                add(category, scope, 'Outbound', target,
                    'Complete within the target after task release; includes assignment wait, travel and handling.', source)
            return_target = positive(cfg.get('return_target_time', cfg.get('target_time')))
            if cfg.get('return_enabled') and return_target:
                add(category, scope, 'Return / collection', return_target,
                    'Complete within the target after the return task is released.', source)

    for task in config.get('tasks', []) or []:
        target = positive(task.get('target_time'))
        if target:
            labels = task.get('labels') or []
            if isinstance(labels, str):
                labels = [labels]
            category = str(labels[0]) if labels else str(task.get('category') or 'Explicit tasks')
            if category == 'Explicit tasks' and requests is not None and not requests.empty:
                recorded = requests.loc[requests.task_id.eq(str(task.get('id', ''))), 'stream']
                if not recorded.empty and recorded.iloc[0] != 'Unclassified':
                    category = str(recorded.iloc[0])
            add(category, str(task.get('id') or 'Configured task'), 'Explicit task', target,
                'Complete within the target after task release.', 'Task configuration')

    observed = []
    if requests is not None and not requests.empty:
        eligible = requests[pd.to_numeric(requests.target_s, errors='coerce').gt(0)]
        for (stream, target), group in eligible.groupby(['stream', 'target_s'], dropna=False):
            completed = group.outcome.eq('completed')
            assessed = completed | group.overdue | group.outcome.eq('failed')
            on_time = completed & ~group.overdue
            observed.append(dict(category=stream, target_s=target, target_minutes=target / 60,
                requests=len(group), completed=int(completed.sum()), overdue=int(group.overdue.sum()),
                assessed=int(assessed.sum()), compliance_pct=100 * on_time.sum() / assessed.sum() if assessed.any() else None))
    return dict(sla_assignments=pd.DataFrame(rows, columns=SLA_COLUMNS),
                sla_observed_targets=pd.DataFrame(observed, columns=['category', 'target_s', 'target_minutes',
                    'requests', 'completed', 'overdue', 'assessed', 'compliance_pct']))
