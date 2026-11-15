"""Journal resource changes made by one serial route commit.

Only touched entries are copied; large reservation tables are not duplicated.
Read-only routing jobs never open a transaction. Derived route estimates are
invalidated on rollback rather than restoring potentially stale cached plans.
"""
from copy import deepcopy
from bisect import bisect_right
from amr_runtime_data import immutable


def snapshot(value, memo=None):
    return value if immutable(value) else deepcopy(value, memo)


class LiftReservations(list):
    """Complete booking history with an exact, mutation-aware maximum finish.

    Keep list ordering and max's first-on-ties behaviour, including when a
    transaction inserts then rolls back a booking or a test replaces a slice.
    Queries are O(1); mutations that can remove/reorder the maximum recompute it.
    """
    def __init__(self, values=()):
        super().__init__(values)
        self._refresh_latest()

    def _refresh_latest(self):
        self.latest = max(self, key=lambda row: row[1], default=None)

    def append(self, value):
        super().append(value)
        latest = getattr(self, 'latest', None)
        if latest is None or value[1] > latest[1]:
            self.latest = value

    def extend(self, values):
        # Materialise self-extension before append changes the iterable.
        if values is self:
            values = list(values)
        for value in values:
            self.append(value)

    def insert(self, index, value):
        super().insert(index, value)
        latest = getattr(self, 'latest', None)
        if latest is None or value[1] > latest[1]:
            self.latest = value
        elif value[1] == latest[1]:
            self._refresh_latest()

    def pop(self, index=-1):
        value = super().pop(index)
        if value is self.latest:
            self._refresh_latest()
        return value

    def clear(self):
        super().clear()
        self.latest = None

    def __delitem__(self, key):
        super().__delitem__(key)
        self._refresh_latest()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._refresh_latest()

    def remove(self, value):
        super().remove(value)
        self._refresh_latest()

    def reverse(self):
        super().reverse()
        self._refresh_latest()

    def sort(self, *args, **kwargs):
        try:
            super().sort(*args, **kwargs)
        finally:
            self._refresh_latest()

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __imul__(self, count):
        super().__imul__(count)
        self._refresh_latest()
        return self


def latest_lift_reservation(values):
    """Allow legacy/plain lists supplied by callers without trusting their order."""
    if isinstance(values, LiftReservations):
        return values.latest
    return max(values, key=lambda row: row[1], default=None)


class RouteReservationTransaction:
    def __init__(self, simulation, amr, tasks):
        self.simulation = simulation
        self.amr = amr
        self.tasks = tasks
        self.task_ids = {str(task.id) for task in tasks}
        self.entries = {}
        self.dictionaries = {}
        self.attributes = {}
        self.appended_lists = {}
        self.committed = False
        self.operations = []
        self.entities = {}
        self.copy_memo = {}
        self.appended_mappings = set()

    def remember_mapping_appends(self, mapping, key):
        if getattr(self.simulation, 'runtime_backend', 'compact') == 'reference':
            self.remember_mapping(mapping, key)
            return
        identity = (id(mapping), key)
        if identity not in self.appended_mappings:
            existed = key in mapping
            values = mapping[key]
            self.operations.append(('appends', mapping, key, values, len(values), existed))
            self.appended_mappings.add(identity)

    def remember_entity(self, value):
        if getattr(self.simulation, 'runtime_backend', 'compact') == 'reference':
            self.remember_dict(vars(value))
            return
        from amr_sim_models import TransactionalEntity
        if not isinstance(value, TransactionalEntity):
            self.remember_dict(vars(value))
            return
        if id(value) in self.entities:
            return
        # Unconverted mutable attributes may be changed in place. Keep the safe
        # fallback for those, using one memo to retain relationships between them.
        mutable = tuple(name for name, item in vars(value).items() if not immutable(item))
        self.remember_attributes(value, mutable)
        self.entities[id(value)] = value
        object.__setattr__(value, '_reservation_journal', self)

    def insert_sorted(self, mapping, key, item):
        existed = key in mapping
        values = mapping[key]
        index = bisect_right(values, item)
        values.insert(index, item)
        self.operations.append((mapping, key, values, index, existed))

    def remember_mapping(self, mapping, key):
        identity = (id(mapping), key)
        if identity not in self.entries:
            self.entries[identity] = (mapping, key, key in mapping, snapshot(mapping.get(key), self.copy_memo))

    def remember_dict(self, value):
        if id(value) not in self.dictionaries:
            copied = (deepcopy(value) if getattr(self.simulation, 'runtime_backend', 'compact') == 'reference'
                      else {key: snapshot(item, self.copy_memo) for key, item in value.items()})
            self.dictionaries[id(value)] = (value, copied)

    def remember_attributes(self, value, names):
        for name in names:
            key = (id(value), name)
            if key not in self.attributes:
                self.attributes[key] = (value, name, hasattr(value, name), snapshot(getattr(value, name, None), self.copy_memo))

    def remember_immutable_attribute(self, value, name):
        """Journal a value whose object graph is immutable without copying history."""
        key = (id(value), name)
        if key not in self.attributes:
            self.attributes[key] = (value, name, hasattr(value, name), getattr(value, name, None))

    def remember_appends(self, value):
        """Remember the boundary of an append-only operational record list."""
        self.appended_lists.setdefault(id(value), (value, len(value)))

    def __enter__(self):
        if getattr(self.simulation, '_route_reservation_transaction', None) is not None:
            raise RuntimeError('Route commits must be serial and cannot nest')
        self.simulation._route_reservation_transaction = self
        self.evidence_sequence = getattr(self.simulation, '_evidence_sequence', 0)
        self.event_store = getattr(self.simulation, 'event_store', None)
        if self.event_store is not None:
            self.event_store.begin_stage()
        self.remember_entity(self.amr)
        self.remember_appends(self.simulation.charge_intervals)
        self.remember_attributes(self.simulation, (
            'scenario_delay_sec', 'scenario_affected_segments', 'people_delay_sec',
            'people_affected_segments', 'wash_cycles_completed'))
        for task in self.tasks:
            self.remember_attributes(task, (
                'assigned_inventory_space', 'payload_orientation', 'wash_cycle_required',
                'pickup', 'dropoff', 'target_charge_location', 'assigned_amr_inventory_space',
                'reserved_exchange_empty_id', 'payload_instance_id'))
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        self.simulation._route_reservation_transaction = None
        for value in self.entities.values():
            object.__delattr__(value, '_reservation_journal')
        success = self.committed and exc_type is None
        if self.event_store is not None:
            self.event_store.end_stage(success)
        if not success:
            self.simulation._evidence_sequence = self.evidence_sequence
        if success:
            return False
        for operation in reversed(self.operations):
            if len(operation) == 6:
                _, mapping, key, values, index, existed = operation
                del values[index:]
            else:
                mapping, key, values, index, existed = operation
                values.pop(index)
            if not existed:
                mapping.pop(key, None)
        for value, original in self.dictionaries.values():
            value.clear()
            value.update(original)
        for mapping, key, existed, original in self.entries.values():
            if existed:
                mapping[key] = original
            else:
                mapping.pop(key, None)
        for value, name, existed, original in self.attributes.values():
            if existed:
                setattr(value, name, original)
            elif hasattr(value, name):
                delattr(value, name)
        for value, length in self.appended_lists.values():
            del value[length:]
        self.simulation._invalidate_route_estimate_cache()
        return False
