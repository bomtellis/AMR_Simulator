"""Initial bins must agree with the active resolved waste service definitions."""
import contextlib
import copy
import io
import unittest

from simulator import Simulation
from tests.test_shared_bin_lifecycle import bin_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class WasteSeedResolutionTests(unittest.TestCase):
    def run_case(self, config):
        sim = Simulation(config, verbose=True)
        original = set(sim.payload_instance_store._known_instances)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim, original

    def test_category_pickup_seeds_without_duplicate_department_pickup_setting(self):
        config = bin_config()
        del config['departments'][0]['waste_pickup_locations']
        for data in (config, JsonStore(copy.deepcopy(config)).data):
            sim, original = self.run_case(data)
            self.assertEqual(1, len(original))
            self.assertEqual(4, len(sim.completed_task_records))
            self.assertFalse(sim.failed_task_ids)
            self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})

    def test_group_route_overrides_obsolete_raw_seed_pickup(self):
        config = bin_config()
        group = config['task_generation']['categories']['waste']['department_groups'][0]['payload']
        group.update(pickup_location='B', dropoff_location='A')
        sim, original = self.run_case(config)
        initial = next(r for r in sim.verbose_rows if r['event_type'] == 'location_payload_enter')
        self.assertEqual('B', initial['to_location'])
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('B')})

    def test_inherited_initial_presence_false_does_not_seed_unused_stock(self):
        config = bin_config()
        del config['departments'][0]['waste_streams'][0]['initial_container_present']
        config['task_generation']['categories']['waste']['initial_container_present'] = False
        sim, original = self.run_case(config)
        self.assertFalse(original)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))
        self.assertFalse(sim.failed_task_ids)

    def test_department_presence_override_wins_over_category_opt_out(self):
        config = bin_config()
        config['task_generation']['categories']['waste']['initial_container_present'] = False
        sim, original = self.run_case(config)
        self.assertEqual(1, len(original))
        self.assertEqual(4, len(sim.completed_task_records))

    def test_group_shared_identity_is_used_by_seed_and_collection(self):
        config = bin_config()
        del config['departments'][0]['waste_streams'][0]['shared_container_group']
        config['task_generation']['categories']['waste']['department_groups'][0]['payload']['shared_container_group'] = 'INHERITED'
        sim, original = self.run_case(config)
        self.assertEqual(4, len(sim.completed_task_records))
        records = sim.payload_instance_store.records_at('A')
        self.assertEqual(original, {r.instance_id for r in records})
        self.assertEqual(['shared:INHERITED'], [r.metadata['container_group'] for r in records])

    def test_disabled_first_contributor_cannot_choose_shared_bin_payload(self):
        for disabled_department in (False, True):
            with self.subTest(disabled_department=disabled_department):
                config = bin_config()
                other = copy.deepcopy(config['departments'][0]); other.update(id='E', name='Other')
                other['waste_streams'][0]['payload'] = 'Other'
                if disabled_department:
                    other['enabled'] = False
                else:
                    other['waste_streams'][0]['enabled'] = False
                config['departments'].insert(0, other)
                config['payloads'].append(dict(config['payloads'][0], name='Other'))
                config['task_generation']['categories']['waste']['department_groups'][0]['departments'].insert(0, 'E')
                self.assertFalse(any(f.code == 'SHARED_CONTAINER_CONFLICT'
                                     for f in check_project(config, include_legacy=False).findings))
                sim, original = self.run_case(config)
                self.assertEqual(1, len(original))
                self.assertEqual(4, len(sim.completed_task_records))
                self.assertFalse(sim.failed_task_ids)
                self.assertEqual(['Box'], [r.payload for r in sim.payload_instance_store.records_at('A')])

    def multi_pickup_config(self):
        config = bin_config()
        config['locations'].append(dict(name='C', floor=0, x=0, y=5))
        config['corridors']['edges'].append(dict(**{'from': 'A', 'to': 'C'}, width_m=3))
        category = config['task_generation']['categories']['waste']
        category['pickup_locations'] = ['C']
        category['scheduled_times'] = ['00:01']
        stream = config['departments'][0]['waste_streams'][0]
        stream.pop('shared_container_group'); stream['shared_container'] = True
        return config

    def test_automatic_shared_group_uses_complete_pickup_signature(self):
        sim, original = self.run_case(self.multi_pickup_config())
        records = sim.payload_instance_store.records_at('A')
        self.assertEqual(1, len(records))
        self.assertEqual('pickup:General:A,C', records[0].metadata['container_group'])
        self.assertEqual(1, len(original))
        self.assertEqual(original, set(sim.payload_instance_store._known_instances))
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)

    def test_shared_bin_uses_next_pickup_when_first_has_no_fitting_inventory_space(self):
        config = self.multi_pickup_config()
        config['locations'][0]['inventory_spaces'] = [
            dict(name='Too small', length_m=0.1, width_m=0.1, height_m=0.1)]
        sim, original = self.run_case(config)
        self.assertEqual(1, len(original))
        initial = next(r for r in sim.verbose_rows if r['event_type'] == 'location_payload_enter')
        self.assertEqual('C', initial['to_location'])
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('C')})
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)

    def test_unavailable_seed_space_does_not_fabricate_replacement_stock(self):
        config = bin_config()
        config['locations'][0]['inventory_spaces'] = [
            dict(name='Too small', length_m=0.1, width_m=0.1, height_m=0.1)]
        sim, original = self.run_case(config)
        self.assertFalse(original)
        self.assertFalse(sim.payload_instance_store._known_instances)
        self.assertFalse(sim.completed_task_records)
        self.assertEqual(2, len(sim.failed_task_ids))

    def test_global_generation_disable_does_not_seed_modern_rule_stock(self):
        config = bin_config()
        config['task_generation']['enabled'] = False
        sim, original = self.run_case(config)
        self.assertFalse(original)
        self.assertFalse(sim.completed_task_records)

    def test_disabled_group_does_not_revive_raw_department_stock(self):
        config = bin_config()
        config['task_generation']['categories']['waste']['department_groups'][0]['payload']['enabled'] = False
        sim, original = self.run_case(config)
        self.assertFalse(original)
        self.assertFalse(sim.completed_task_records)


if __name__ == '__main__':
    unittest.main()
