"""Editable movement capability templates and explicit version migration.

Templates name supported permissions, not physical robot/vendor specifications.
No template supplies speeds, acceleration, radii, reference offsets or a reverse
permission. Empty and loaded settings are edited independently. A modified
template is simply custom capabilities: no preset name controls runtime physics.
"""
from collections.abc import Mapping
from copy import deepcopy


MOVEMENT_SCHEMA_VERSION = 2
MOVEMENT_PRESETS = ('steering', 'pivoting', 'omnidirectional')
_PRESETS = {
    'steering': dict(pivot_allowed=False, lateral_allowed=False),
    'pivoting': dict(pivot_allowed=True, lateral_allowed=False),
    'omnidirectional': dict(pivot_allowed=True, lateral_allowed=True),
}


def movement_preset(name):
    """Return only the two advertised, independently editable capability flags."""
    if not isinstance(name, str) or name not in _PRESETS:
        raise ValueError('Choose steering, pivoting or omnidirectional.')
    return dict(_PRESETS[name])


def apply_movement_preset(movement, *, state, preset):
    """Copy/edit a draft without inventing its missing engineering parameters.

    This authoring helper does not promise a runnable result. For example,
    enabling lateral motion still requires an explicitly entered lateral speed.
    Migration is a separate visible action, never a side effect of applying a
    capability template or merely reopening an existing project.
    """
    if state not in ('empty', 'loaded'):
        raise ValueError('Choose the empty or loaded movement state.')
    if not isinstance(movement, Mapping):
        raise ValueError('Movement draft must be an object.')
    values = movement.get(state, {})
    if not isinstance(values, Mapping):
        raise ValueError(f'Movement {state} draft must be an object.')
    result = deepcopy(dict(movement))
    result[state] = {**deepcopy(dict(values)), **movement_preset(preset)}
    return result


def resolve_movement_inputs(movement):
    """Return validated effective schema-2 inputs and explicit compatibility decisions.

    Input dictionaries are never modified. Unversioned/schema-1 configurations
    retain their previously unconditional reverse permission when omitted.
    Explicit values are honoured; schema 2 requires a boolean in both states.
    Numeric inputs remain unchanged, including optional radius inheritance.
    """
    # Lazy import keeps either module usable as an entry point. MotionSettings
    # construction never calls this resolver, so selection cannot recurse.
    from amr_motion_profiles import MotionProfileError, MotionSettings
    if not isinstance(movement, Mapping):
        raise MotionProfileError('movement must contain explicit empty and loaded settings.')
    version = movement.get('schema_version', 1)
    if type(version) is not int or version not in (1, MOVEMENT_SCHEMA_VERSION):
        raise MotionProfileError('movement.schema_version must be 1 or 2; omission means legacy version 1.')
    result = deepcopy(dict(movement))
    result['schema_version'] = MOVEMENT_SCHEMA_VERSION
    decisions = []
    if version == 1:
        decisions.append(dict(code='MOVEMENT_SCHEMA_UPGRADE', path='/schema_version', value=2,
                              source='legacy_movement_schema',
                              explanation='Legacy movement settings resolve to schema 2 without altering numerical inputs.'))
    for state in ('empty', 'loaded'):
        values = movement.get(state)
        if not isinstance(values, Mapping):
            raise MotionProfileError(f'movement.{state} must be an explicit settings mapping.')
        values = deepcopy(dict(values))
        if 'reverse_allowed' not in values:
            if version == 2:
                raise MotionProfileError(f'movement.{state}.reverse_allowed must be an explicit boolean in schema 2.')
            values['reverse_allowed'] = True
            decisions.append(dict(code='LEGACY_REVERSE_ALLOWED', path=f'/{state}/reverse_allowed',
                                  value=True, source='legacy_reverse_enabled',
                                  explanation=f'Legacy {state} movement permitted reversing; the effective permission remains true.'))
        try:
            MotionSettings(**values)
        except (TypeError, ValueError) as exc:
            raise MotionProfileError(f'movement.{state}: {exc}') from None
        result[state] = values
    return {'movement': result, 'decisions': decisions}


def migrate_movement_inputs(movement):
    """Produce a reviewable schema upgrade; the caller decides when to persist it."""
    return resolve_movement_inputs(movement)
