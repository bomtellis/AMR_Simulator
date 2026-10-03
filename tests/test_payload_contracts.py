"""Physical payload inputs and independently specified storage-envelope cases."""
import copy
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def storage_config():
    cfg = reference_config()
    cfg['locations'][1]['inventory_spaces'] = [dict(name='Bay', length_m=2, width_m=2,
        flexible=True, payload_slots=[{'payload': 'Box'}])]
    return cfg


class PayloadContractTests(unittest.TestCase):
    def test_storage_envelope_tolerance_is_one_micrometre(self):
        sim = Simulation(storage_config())
        box = sim.payloads['Box']
        bay = dict(length_m=1, width_m=.7, height_m=1, flexible=True)
        for reduction, fits in ((0.5e-6, True), (2e-6, False)):
            for field in ('length_m', 'width_m', 'height_m'):
                self.assertEqual(fits, sim._inventory_space_can_fit_payload(
                    dict(bay, **{field: bay[field] - reduction}), box))

    def test_inferred_bay_dimensions_keep_precision_through_import(self):
        cfg = storage_config()
        cfg['payloads'][0].update(length_m=1.0004, width_m=.7004, height_m=1.0004)
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Precise', payload_slots=[{'payload': 'Box'}],
            points=[{'dx': 0, 'dy': 0}, {'dx': 1.0004, 'dy': 0},
                    {'dx': 1.0004, 'dy': .7004}, {'dx': 0, 'dy': .7004}])]
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            bay, = sim.inventory_spaces_by_location['B']
            self.assertEqual((1.0004, .7004, 1.0004), tuple(bay[k] for k in ('length_m', 'width_m', 'height_m')))
            self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))

    def test_legacy_bay_dimension_and_flexibility_aliases_survive_import(self):
        cfg = storage_config()
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Other'))
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Legacy', length=2, width=3, height=4,
            flexible_payloads=True, payload_slots=[{'payload': 'Box'}])]
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            bay, = sim.inventory_spaces_by_location['B']
            self.assertEqual((2, 3, 4), tuple(bay[k] for k in ('length_m', 'width_m', 'height_m')))
            self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Other']))
        cfg['locations'][1]['inventory_spaces'][0].update(length_m=1, width_m=1, height_m=1)
        for data in (cfg, JsonStore(cfg).data):
            bay, = Simulation(data).inventory_spaces_by_location['B']
            self.assertEqual((1, 1, 1), tuple(bay[k] for k in ('length_m', 'width_m', 'height_m')))

    def test_invalid_mass_dimensions_and_flags_reject_before_coercion(self):
        for field, values in {
            'weight_kg': [-1, True, 'nan', None],
            'length_m': [0, -1, True, 'inf'], 'width_m': [0, None],
            'height_m': [0, 'nan'], 'size_units': [0, -1],
            'prefer_multi_stop_amr': ['false', 0, None],
        }.items():
            for value in values:
                cfg = reference_config()
                cfg['payloads'][0][field] = value
                before = copy.deepcopy(cfg)
                for consumer in (Simulation, JsonStore):
                    with self.subTest(field=field, value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertTrue(any(f.path == f'/payloads/0/{field}' and f.severity == 'error'
                                    for f in check_project(cfg).findings))
                self.assertEqual(before, cfg)

    def test_duplicate_blank_and_reserved_payload_names_cannot_bypass_handling(self):
        for name in ('', ' Box', 'Box ', None, 1, '__empty__', 'empty', 'NONE', '-'):
            cfg = reference_config()
            cfg['payloads'][0]['name'] = name
            for consumer in (Simulation, JsonStore):
                with self.subTest(name=name, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
        cfg = reference_config()
        cfg['payloads'].append(copy.deepcopy(cfg['payloads'][0]))
        for consumer in (Simulation, JsonStore):
            with self.assertRaises(ValueError):
                consumer(cfg)

    def test_missing_mass_is_an_editable_draft_but_not_runnable(self):
        cfg = reference_config()
        del cfg['payloads'][0]['weight_kg']
        draft = JsonStore(cfg).data
        self.assertEqual(draft, JsonStore(draft).data)
        with self.assertRaisesRegex(ValueError, 'weight_kg'):
            Simulation(cfg)
        self.assertFalse(check_project(cfg).can_run(cfg))

    def test_massless_load_numeric_strings_and_dimension_precedence(self):
        cfg = reference_config()
        cfg['payloads'][0] = dict(name='Box', weight_kg='0', size_units='2', width_m='.5')
        for data in (cfg, JsonStore(cfg).data):
            payload = Simulation(data).payloads['Box']
            self.assertEqual((0, 2, .5, 2), (payload.weight_kg, payload.length_m, payload.width_m, payload.height_m))

    def test_omitted_dimensions_mean_one_metre(self):
        cfg = reference_config()
        cfg['payloads'][0] = dict(name='Box', weight_kg=10)
        for data in (cfg, JsonStore(cfg).data):
            payload = Simulation(data).payloads['Box']
            self.assertEqual((1, 1, 1), (payload.length_m, payload.width_m, payload.height_m))

    def test_legacy_payload_height_limits_inferred_bay_height(self):
        cfg = storage_config()
        cfg['payloads'][0] = dict(name='Box', weight_kg=10, size_units=2)
        cfg['payloads'].append(dict(name='Tall', weight_kg=10, length_m=1, width_m=1, height_m=2.01))
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            bay, = sim.inventory_spaces_by_location['B']
            self.assertEqual(2, bay['height_m'])
            self.assertFalse(sim._inventory_space_can_fit_payload(bay, sim.payloads['Tall']))
            self.assertIsNone(sim._find_free_inventory_space('B', sim.payloads['Tall']))
            self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))

    def test_missing_template_dimensions_have_the_same_defaults_in_storage(self):
        cfg = storage_config()
        cfg['payloads'][0] = dict(name='Box', weight_kg=10)
        for data in (cfg, JsonStore(cfg).data):
            bay, = Simulation(data).inventory_spaces_by_location['B']
            self.assertEqual(1, bay['height_m'])

    def test_storage_rotation_is_separate_from_robot_carry_orientation(self):
        cfg = storage_config()
        cfg['locations'][1]['inventory_spaces'][0].update(length_m=.7, width_m=1, height_m=1)
        cfg['payloads'][0]['allowed_carry_orientations'] = ['lengthways']
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            bay, = sim.inventory_spaces_by_location['B']
            self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
            for field in ('length_m', 'width_m', 'height_m'):
                small = dict(bay)
                small[field] -= .0001
                self.assertFalse(sim._inventory_space_can_fit_payload(small, sim.payloads['Box']))

    def test_fixed_bay_payload_restriction_and_flexible_override(self):
        cfg = storage_config()
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Other'))
        sim = Simulation(cfg)
        bay, = sim.inventory_spaces_by_location['B']
        self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Other']))
        bay['flexible'] = False
        self.assertFalse(sim._inventory_space_can_fit_payload(bay, sim.payloads['Other']))
        self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
        bay['stores_amr'] = True
        self.assertFalse(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))

    def test_payload_volume_metadata_does_not_replace_geometric_volume(self):
        cfg = reference_config()
        cfg['payloads'][0].update(length_m=2, width_m=.5, height_m=3, volume_m3=999)
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Bay', length_m=2,
            width_m=.5, height_m=3, flexible=True, capacity_volume_m3=.01)]
        sim = Simulation(cfg)
        bay, = sim.inventory_spaces_by_location['B']
        self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
        sim.payload_instance_store.store('B', 'Box', 'Physical-1')
        sim._record_location_storage_peak('B')
        self.assertEqual(3, sim.location_storage_peak['B']['current_volume_m3'])
        self.assertTrue(any(f.path == '/payloads/0/volume_m3' and f.kind == 'unsupported'
                            for f in check_project(cfg).findings))
        self.assertTrue(any(f.path.endswith('/capacity_volume_m3') and f.kind == 'unsupported'
                            for f in check_project(cfg).findings))


if __name__ == '__main__':
    unittest.main()
