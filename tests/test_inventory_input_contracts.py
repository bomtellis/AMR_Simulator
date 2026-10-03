"""Bay identity, reference and edit-preservation contracts."""
import copy
import unittest

from simulator import Simulation
from tests.test_payload_contracts import storage_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class InventoryInputContractTests(unittest.TestCase):
    def test_unknown_payload_template_blocks_run_without_broadening_compatibility(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'][0].update(
            flexible=False, payload_slots=[{'payload': 'Typo'}])
        draft = JsonStore(cfg).data
        self.assertEqual('Typo', draft['locations'][1]['inventory_spaces'][0]['payload_slots'][0]['payload'])
        for data in (cfg, draft):
            with self.assertRaisesRegex(ValueError, 'Typo'):
                Simulation(data)
            self.assertTrue(any(f.code == 'INVENTORY_INPUT' and f.path.endswith('/payload_slots/0/payload')
                                for f in check_project(data).findings))

    def test_amr_restrictions_accept_type_and_existing_instance_only(self):
        for value, valid in [('R', True), ('R-1', True), ('R-2', False), ('Typo', False)]:
            for in_slot in (False, True):
                cfg = storage_config()
                bay = cfg['locations'][1]['inventory_spaces'][0]
                bay.update(stores_amr=True, payload_slots=[])
                if in_slot:
                    bay['payload_slots'] = [{'slot_type': 'amr', 'amr_type': value}]
                else:
                    bay['amr_type'] = value
                with self.subTest(value=value, in_slot=in_slot):
                    if valid:
                        Simulation(cfg)
                    else:
                        with self.assertRaisesRegex(ValueError, value):
                            Simulation(cfg)

    def test_duplicate_resolved_bay_names_reject_raw_and_editor(self):
        for names in [('Bay', 'Bay'), ('', 'Space 1')]:
            cfg = storage_config()
            bay = cfg['locations'][1]['inventory_spaces'][0]
            cfg['locations'][1]['inventory_spaces'] = [dict(bay, name=name) for name in names]
            for consumer in (Simulation, JsonStore):
                with self.subTest(names=names, consumer=consumer.__name__), self.assertRaisesRegex(ValueError, 'unique'):
                    consumer(cfg)

    def test_malformed_bays_reject_before_coercion(self):
        cases = [('stores_amr', 'false'), ('has_charger', 1), ('occupied', 'false'),
                 ('points', [{'dx': 1}]), ('points', [{'x': float('inf'), 'y': 0}]),
                 ('points', [{'dx': True, 'dy': 0}]), ('points', [None]),
                 ('payload_slots', [None]), ('length', -1), ('width_m', 'nan')]
        for field, value in cases:
            cfg = storage_config()
            cfg['locations'][1]['inventory_spaces'][0][field] = value
            for consumer in (Simulation, JsonStore):
                with self.subTest(field=field, value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)

    def test_malformed_slot_coordinates_and_references_are_not_discarded(self):
        for slot in ({'payload': 5}, {'payload': 'Box', 'dx': 1},
                     {'payload': 'Box', 'rotation_deg': 'nan'}, {'amr_type': []}):
            cfg = storage_config()
            cfg['locations'][1]['inventory_spaces'][0]['payload_slots'] = [slot]
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                JsonStore(cfg)

    def test_invalid_edit_is_atomic(self):
        store = JsonStore(storage_config())
        before = copy.deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.set_location_inventory_spaces('B', [{'name': 'Invalid', 'points': [{'dx': 0}]}])
        self.assertEqual(before, store.data)

    def test_container_shapes_reject_without_mutating_input(self):
        for spaces in (None, {}, [None], [{'points': None}], [{'payload_slots': {}}]):
            cfg = storage_config()
            cfg['locations'][1]['inventory_spaces'] = spaces
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(spaces=spaces, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)

    def test_reference_findings_track_catalog_edits(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'][0]['payload_slots'] = [{'payload': 'Typo'}]
        report = check_project(cfg)
        finding = next(f for f in report.findings if f.code == 'INVENTORY_INPUT')
        self.assertEqual([], report.changed_inputs(finding, cfg))
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Typo'))
        self.assertEqual(['payloads'], report.changed_inputs(finding, cfg))
        self.assertFalse(any(f.code == 'INVENTORY_INPUT' for f in check_project(cfg).findings))

    def test_dimension_only_bay_and_occupancy_markers_survive_edit(self):
        cfg = storage_config()
        bay = cfg['locations'][1]['inventory_spaces'][0]
        bay.update(name='', length_m=1.0004, occupied=True, payload='Box',
                   payload_instance_id='Blocked-1', reserved_by_task='Pending', task_id='Pending')
        store = JsonStore(cfg)
        store.set_location_inventory_spaces('B', store.get_location_inventory_spaces('B'))
        saved, = store.get_location_inventory_spaces('B')
        self.assertEqual('Space 1', saved['name'])
        self.assertEqual(1.0004, saved['length_m'])
        for field in ('occupied', 'payload', 'payload_instance_id', 'reserved_by_task', 'task_id'):
            self.assertEqual(bay[field], saved[field])
        self.assertEqual(saved, JsonStore(store.data).get_location_inventory_spaces('B')[0])

    def test_legacy_dimensions_flexibility_and_precision_survive_edit(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Legacy', length=1.0004,
            width=.7004, height=1.0004, flexible_payloads=True,
            points=[{'x': 6, 'y': 8}, {'x': 7.0004, 'y': 8.7004}],
            payload_slots=[{'payload': 'Box', 'x': 6.0004, 'y': 8, 'rotation_deg': .0004}])]
        store = JsonStore(cfg)
        store.set_location_inventory_spaces('B', cfg['locations'][1]['inventory_spaces'])
        saved, = store.get_location_inventory_spaces('B')
        self.assertEqual((1.0004, .7004, 1.0004), tuple(saved[k] for k in ('length_m', 'width_m', 'height_m')))
        self.assertTrue(saved['flexible'])
        self.assertAlmostEqual(.0004, saved['payload_slots'][0]['dx'])
        self.assertEqual(.0004, saved['payload_slots'][0]['rotation_deg'])

    def test_initial_occupancy_blocks_storage_without_creating_stock(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'][0]['occupied'] = True
        sim = Simulation(cfg)
        self.assertIsNone(sim._find_free_inventory_space('B', sim.payloads['Box']))
        self.assertFalse(sim.payload_instance_store.counts_at('B'))
        self.assertTrue(any(f.code == 'INVENTORY_OCCUPANCY_SCOPE' for f in check_project(cfg).findings))

    def test_local_coordinates_precede_absolute_and_zero_dimensions_infer(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'][0].update(length_m=0, width_m=0,
            points=[{'dx': 0, 'dy': 0, 'x': 100, 'y': 100}, {'dx': 2, 'dy': 3}])
        for data in (cfg, JsonStore(cfg).data):
            bay, = Simulation(data).inventory_spaces_by_location['B']
            self.assertEqual((2, 3), (bay['length_m'], bay['width_m']))


if __name__ == '__main__':
    unittest.main()
