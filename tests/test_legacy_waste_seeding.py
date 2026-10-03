"""Legacy collection rules and their physical initial stock must agree."""
import contextlib
import copy
import io
import unittest

from simulator import Simulation
from tests.test_shared_bin_lifecycle import bin_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def legacy_bin_config():
    cfg = bin_config()
    cfg['simulation']['end_datetime'] = '2026-01-05T00:02:00'
    cfg['task_generation'] = {'enabled': True, 'department_waste': {'enabled': True}}
    cfg['departments'][0].update(bed_count=1, waste={'alpha': 24, 'pickup_location': 'A', 'dropoff_location': 'B'})
    return cfg


class LegacyWasteSeedingTests(unittest.TestCase):
    def run_case(self, cfg):
        sim = Simulation(cfg, verbose=True)
        original = set(sim.payload_instance_store._known_instances)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim, original

    def test_seed_uses_global_payload_and_actual_legacy_pickup(self):
        cfg = legacy_bin_config()
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Other'))
        cfg['departments'][0]['waste_streams'][0]['payload'] = 'Other'
        cfg['departments'][0]['waste_pickup_locations'] = ['B']
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            records = sim.payload_instance_store.records_at('A')
            self.assertEqual(['Box'], [r.payload for r in records])
            self.assertEqual([], sim.payload_instance_store.records_at('B'))
            generated = sim.task_generation_manager.update_until(60)
            self.assertEqual(1, len(generated))
            self.assertEqual(('A', 'B', 'Box'), (generated[0].task.pickup, generated[0].task.dropoff, generated[0].task.payload))

    def test_initial_presence_opt_out_seeds_nothing_and_issues_outbound_work(self):
        cfg = legacy_bin_config()
        cfg['departments'][0]['waste_streams'][0]['initial_container_present'] = False
        sim, original = self.run_case(cfg)
        self.assertEqual(set(), original)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))

    def test_default_initial_bin_returns_with_same_identity(self):
        sim, original = self.run_case(legacy_bin_config())
        self.assertEqual(1, len(original))
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        self.assertEqual(original, set(sim.payload_instance_store._known_instances))

    def test_legacy_generated_task_has_the_seeded_group_identity(self):
        cfg = legacy_bin_config()
        sim = Simulation(cfg)
        generated = sim.task_generation_manager.update_until(60)
        self.assertEqual('shared:BIN', generated[0].task.container_group)
        self.assertEqual('shared:BIN', sim.payload_instance_store.records_at('A')[0].metadata['container_group'])

    def test_disabled_legacy_generation_preserves_independent_custom_stock(self):
        cfg = legacy_bin_config()
        cfg['task_generation']['department_waste']['enabled'] = False
        self.assertEqual(1, len(Simulation(cfg).payload_instance_store._known_instances))
        cfg['task_generation']['enabled'] = False
        self.assertEqual(1, len(Simulation(cfg).payload_instance_store._known_instances))

    def test_additional_legacy_pickups_preserve_explicit_independent_bins(self):
        cfg = legacy_bin_config()
        cfg['departments'][0]['waste_streams'][0].pop('shared_container_group')
        cfg['departments'][0]['waste_pickup_locations'] = ['A', 'B']
        sim = Simulation(cfg)
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))
        self.assertEqual(1, len(sim.payload_instance_store.records_at('A')))
        self.assertEqual(1, len(sim.payload_instance_store.records_at('B')))

    def test_legacy_automatic_sharing_is_per_pickup_not_one_bin_for_all_pickups(self):
        cfg = legacy_bin_config()
        stream = cfg['departments'][0]['waste_streams'][0]
        stream.pop('shared_container_group')
        stream['shared_container'] = True
        cfg['departments'][0]['waste_pickup_locations'] = ['B']
        sim = Simulation(cfg)
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))
        self.assertEqual('pickup:General:A', sim.payload_instance_store.records_at('A')[0].metadata['container_group'])
        self.assertEqual('pickup:General:B', sim.payload_instance_store.records_at('B')[0].metadata['container_group'])

    def test_raw_custom_adapter_honours_empty_modern_alias_and_literal_scalar_names(self):
        cfg = legacy_bin_config()
        cfg['task_generation'] = {'enabled': False}
        dept = cfg['departments'][0]
        dept['waste'] = {}
        dept['waste_pickup_locations'] = []
        dept['task_generation_locations'] = {'waste': {'pickup_dropoff_locations': [], 'locations': ['A']}}
        self.assertFalse(Simulation(cfg).payload_instance_store._known_instances)
        cfg['locations'][0]['name'] = 'Ward Bay'
        cfg['corridors']['edges'][0]['from'] = 'Ward Bay'
        cfg['building']['charge_locations'] = ['Ward Bay']
        for entry in ('Ward Bay', {'locations': 'Ward Bay'}, {'pickup_dropoff_locations': 'Ward Bay'}):
            dept['task_generation_locations']['waste'] = entry
            for data in (cfg, JsonStore(cfg).data):
                with self.subTest(entry=entry):
                    sim = Simulation(data)
                    self.assertEqual(1, len(sim.payload_instance_store.records_at('Ward Bay')))

    def test_legacy_pickup_lists_accept_whole_names_and_rename_without_splitting(self):
        cfg = legacy_bin_config()
        cfg['task_generation'] = {'enabled': False}
        cfg['departments'][0]['waste'] = {'pickup_locations': 'A'}
        cfg['departments'][0]['waste_pickup_locations'] = 'A'
        store = JsonStore(cfg)
        store.rename_point('A', 'Ward Bay')
        dept = store.data['departments'][0]
        self.assertEqual('Ward Bay', dept['waste_pickup_locations'])
        self.assertEqual('Ward Bay', dept['waste']['pickup_locations'])
        self.assertEqual(1, len(Simulation(store.data).payload_instance_store.records_at('Ward Bay')))

    def test_malformed_legacy_pickup_lists_reject_without_mutation(self):
        for key in ('waste_pickup_locations', 'pickup_locations'):
            for value in (None, [True], 4, {'name': 'A'}):
                cfg = legacy_bin_config()
                target = cfg['departments'][0] if key == 'waste_pickup_locations' else cfg['departments'][0]['waste']
                target[key] = value
                before = copy.deepcopy(cfg)
                for consumer in (JsonStore, Simulation):
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertEqual(before, cfg)

    def test_legacy_shared_definition_conflicts_are_rejected_by_checks_and_runtime(self):
        from amr_sim_task_generation import SharedContainerConflictError
        cfg = legacy_bin_config()
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Other'))
        cfg['waste_streams'].append(dict(cfg['waste_streams'][0], name='Other', payload='Other'))
        cfg['departments'][0]['waste_streams'].append(dict(name='Other', shared_container_group='BIN'))
        with self.assertRaises(SharedContainerConflictError):
            Simulation(cfg)
        conflicts = [f for f in check_project(cfg).findings if f.code == 'SHARED_CONTAINER_CONFLICT']
        self.assertTrue(conflicts)
        self.assertTrue(all(f.path == '/departments' for f in conflicts))

    def test_ignored_legacy_overrides_and_missing_actual_routes_are_visible(self):
        cfg = legacy_bin_config()
        cfg['departments'][0]['waste_streams'][0]['base_daily_volume_m3'] = 48
        findings = check_project(cfg, include_legacy=False).findings
        self.assertTrue(any(f.code == 'LEGACY_WASTE_STREAM_SCOPE' and f.severity == 'warning' for f in findings))
        cfg['departments'][0]['waste']['dropoff_location'] = 'Missing'
        findings = check_project(cfg, include_legacy=False).findings
        self.assertTrue(any(f.path == '/departments/0/waste/dropoff_location' and f.severity == 'error' for f in findings))

    def test_shared_legacy_group_seeds_once_for_two_contributors(self):
        cfg = legacy_bin_config()
        cfg['departments'].append(dict(copy.deepcopy(cfg['departments'][0]), id='E', name='Other department'))
        sim = Simulation(cfg)
        self.assertEqual(1, len(sim.payload_instance_store._known_instances))
        records = sim.task_generation_manager.update_until(60)
        # Each contributor accrues .4 m3 in one minute; sharing a physical bin
        # does not merge the legacy departmental volume pools.
        self.assertEqual(2, len(records))
        self.assertAlmostEqual(.8, sum(r.task.waste_volume_m3 for r in records))
        self.assertEqual({'shared:BIN'}, {r.task.container_group for r in records})

    def test_removing_scalar_reference_does_not_seed_or_revive_it(self):
        cfg = legacy_bin_config()
        cfg['task_generation'] = {'enabled': False}
        cfg['departments'][0]['waste'] = {'pickup_locations': 'A'}
        cfg['departments'][0]['waste_pickup_locations'] = 'A'
        store = JsonStore(cfg)
        store.remove_location_references('A')
        self.assertFalse(Simulation(store.data).payload_instance_store._known_instances)


class DepartmentSuffixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def test_auto_assignment_matches_exact_suffix_or_underscore_extensions(self):
        from unittest.mock import Mock, patch
        from visualiser.dialogs import DepartmentListDialog, QMessageBox
        cfg = legacy_bin_config()
        row = cfg['departments'][0]
        row['task_generation_location_suffixes'] = {'waste': '-BIN'}
        row['task_generation_locations'] = {'waste': {'locations': 'A', 'note': 'retain'}}
        locations = ['A', 'D-BIN', 'D-BIN_2', 'D-BIN2', 'D2-BIN']
        dialog = DepartmentListDialog(None, [row], locations, [], 0, Mock(), lambda: 'E',
                                     task_generation_categories=[('waste', 'Waste', '-WASTE')])
        with patch.object(QMessageBox, 'information'):
            dialog.auto_assign_locations()
        entry = dialog.items[0]['task_generation_locations']['waste']
        self.assertEqual(['A', 'D-BIN', 'D-BIN_2'], entry['pickup_dropoff_locations'])
        self.assertEqual('retain', entry['note'])
        self.assertEqual('A', entry['locations'])
        self.assertEqual('A', row['task_generation_locations']['waste']['locations'])

    def test_suffixes_require_string_values_without_mutating_input(self):
        for value in (None, [], {'waste': 5}, {'waste': False}):
            cfg = legacy_bin_config()
            cfg['departments'][0]['task_generation_location_suffixes'] = value
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)
