"""Journal resource changes made by one serial route commit.

Only touched entries are copied; large reservation tables are not duplicated.
Read-only routing jobs never open a transaction. Derived route estimates are
invalidated on rollback rather than restoring potentially stale cached plans.
"""
from copy import deepcopy


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

    def remember_mapping(self, mapping, key):
        identity = (id(mapping), key)
        if identity not in self.entries:
            self.entries[identity] = (mapping, key, key in mapping, deepcopy(mapping.get(key)))

    def remember_dict(self, value):
        if id(value) not in self.dictionaries:
            self.dictionaries[id(value)] = (value, deepcopy(value))

    def remember_attributes(self, value, names):
        for name in names:
            key = (id(value), name)
            if key not in self.attributes:
                self.attributes[key] = (value, name, hasattr(value, name), deepcopy(getattr(value, name, None)))

    def remember_appends(self, value):
        """Remember the boundary of an append-only operational record list."""
        self.appended_lists.setdefault(id(value), (value, len(value)))

    def __enter__(self):
        if getattr(self.simulation, '_route_reservation_transaction', None) is not None:
            raise RuntimeError('Route commits must be serial and cannot nest')
        self.simulation._route_reservation_transaction = self
        self.remember_dict(vars(self.amr))
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
        if self.committed and exc_type is None:
            return False
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
