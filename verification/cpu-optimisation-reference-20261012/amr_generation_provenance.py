"""Evidence of assignments made while resolving a generation rule.

Histories record writes, including equal-value overrides; they never infer a
source by comparing values. Derived settings have explanations rather than
invented JSON pointers. This describes rule configuration, not runtime outcomes.
"""
import copy


def pointer(value):
    return str(value).replace('~', '~0').replace('/', '~1')


class RuleTrace:
    def __init__(self):
        self.fields = {}

    def record(self, key, value, layer, explanation=''):
        if key in {'departments', 'department_groups'}:
            return
        self.fields.setdefault(key, []).append({
            'value': copy.deepcopy(value), 'layer': layer, 'explanation': explanation})

    def resolve(self, config, origins, labels=None):
        result = {}
        for key, value in config.items():
            if key in {'departments', 'department_groups'}:
                continue
            history = copy.deepcopy(self.fields.get(key, []))
            for step in history:
                origin = origins.get(step['layer'])
                step['path'] = origin + '/' + pointer(key) if origin is not None else ''
                step['layer'] = (labels or {}).get(step['layer'], step['layer'])
            if not history or history[-1]['value'] != value:
                history.append({'value': copy.deepcopy(value), 'layer': 'Unattributed adjustment',
                                'path': '', 'explanation': 'Source has not yet been instrumented.'})
            result[key] = {'value': copy.deepcopy(value), 'history': history,
                           'source': history[-1]['layer'], 'path': history[-1]['path']}
        return result
