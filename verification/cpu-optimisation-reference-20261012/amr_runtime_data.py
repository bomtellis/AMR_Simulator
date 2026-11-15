"""Owned, compact execution inputs and immutable, reusable asset definitions."""
from dataclasses import dataclass
from types import MappingProxyType
from collections import OrderedDict
import json
import hashlib
import threading

from amr_run_evidence import config_hash

COMPILER_VERSION = 2
PRESENTATION_KEYS = frozenset(('description', 'notes', 'display_colour', 'display_color'))
EDITOR_KEYS = frozenset(('tutorial', 'editor_state', 'workspace', 'model_layers', 'floor_dxf_files'))
_cores = OrderedDict()
_cache_lock = threading.RLock()


def runtime_identity(config):
    # Generation order is meaningful; a sorted-key hash is insufficient here.
    return hashlib.sha256(json.dumps(config, ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


class FrozenDict(dict):
    def _readonly(self, *args, **kwargs):
        raise TypeError('Runtime definitions are immutable')
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly
    def __deepcopy__(self, memo):
        return self


class FrozenList(list):
    def _readonly(self, *args, **kwargs):
        raise TypeError('Runtime definitions are immutable')
    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = reverse = sort = __iadd__ = __imul__ = _readonly
    def __deepcopy__(self, memo):
        return self


def freeze(value):
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, dict):
        return FrozenDict((key, freeze(item)) for key, item in value.items())
    if isinstance(value, list):
        return FrozenList(freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value):
    if isinstance(value, dict):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def compact(value):
    if isinstance(value, dict):
        result = {key: compact(item) for key, item in value.items() if key not in PRESENTATION_KEYS}
        if isinstance(value, FrozenDict) and len(result) == len(value) and all(result[key] is value[key] for key in result):
            return value
        return freeze(result)
    if isinstance(value, list):
        result = [compact(item) for item in value]
        if isinstance(value, FrozenList) and all(left is right for left, right in zip(result, value)):
            return value
        return freeze(result)
    return value


@dataclass(frozen=True)
class RuntimeInputs:
    source: FrozenDict
    definitions: FrozenDict
    identifiers: object
    identity: str
    version: int = COMPILER_VERSION

    def execution_config(self):
        # Fresh mutable loader inputs: runtime generation may legitimately add
        # tasks. Immutable definitions never belong to a mutable trial state.
        return thaw(self.definitions)

    def numeric_id(self, kind, identity):
        return self.identifiers[kind][identity]


def compile_runtime_inputs(config):
    owned = json.loads(json.dumps(config, ensure_ascii=False, allow_nan=False))
    core = {key: value for key, value in owned.items() if key not in ('simulation', 'scenario_testing', 'floor_dxf_files')}
    from amr_simulation_modes import resolve_simulation_mode
    key = (COMPILER_VERSION, resolve_simulation_mode(config)['mode'], runtime_identity(core))
    with _cache_lock:
        cached = _cores.get(key)
        if cached is None:
            cached = freeze(core)
            _cores[key] = cached
            while len(_cores) > 2:
                _cores.popitem(last=False)
        else:
            _cores.move_to_end(key)
    source = FrozenDict((name, cached[name] if name in cached else freeze(value)) for name, value in owned.items())
    definitions = FrozenDict((name, compact(value)) for name, value in source.items() if name not in EDITOR_KEYS)
    # Scenario notes/descriptions are presentation data; preserve them in source.
    tables = {}
    for kind, section, key in (('location', 'locations', 'name'), ('payload', 'payloads', 'name'),
                               ('amr', 'amrs', 'id'), ('lift', 'lifts', 'id')):
        tables[kind] = MappingProxyType({str(row[key]): index for index, row in enumerate(owned.get(section, []))})
    return RuntimeInputs(source, definitions, MappingProxyType(tables), runtime_identity(owned))


def immutable(value):
    if value is None or isinstance(value, (str, bool, int, float, FrozenDict, FrozenList)):
        return True
    return isinstance(value, tuple) and all(immutable(item) for item in value)
