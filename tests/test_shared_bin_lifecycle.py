"""Physical identity references for shared-bin collection and return cycles."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_waste_conservation import dynamic_config
from amr_sim_models import Task
from amr_sim_task_generation import SharedContainerConflictError
from visualiser.project_checks import check_project
from visualiser.models import JsonStore


def bin_config():
    config = dynamic_config()
    config['simulation'].update(end_datetime='2026-01-05T00:04:00', seed_waste_stream_containers_at_start=True,
                                max_task_deferral_minutes=5)
    config['building'].update(edge_slowdown_per_amr=0)
    config['departments'][0]['waste_pickup_locations'] = ['A']
    config['departments'][0]['waste_streams'][0].update(shared_container_group='BIN', initial_container_present=True)
    config['task_generation']['categories']['waste'].update(
        generation_mode='scheduled', scheduled_times=['00:01', '00:02'],
        base_daily_volume_m3=0, return_enabled=False, return_delay_minutes=2,
        staff_handling_minutes=0, staff_collection_delay_minutes=0)
    return config


class SharedBinLifecycleTests(unittest.TestCase):
    def run_case(self, config):
        sim = Simulation(config, verbose=True)
        original = set(sim.payload_instance_store._known_instances)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim, original

    def test_task_waiting_for_bin_still_returns_same_bin_after_late_assignment(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/shared-bin-return.json'
        sim, original = self.run_case(json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual(1, len(original))
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(4, len(sim.completed_task_records))  # two collections plus two returns
        self.assertEqual(original, set(sim.payload_instance_store._known_instances))
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        moves = [r for r in sim.verbose_rows if r['event_type'] == 'location_payload_exit']
        self.assertEqual(4, len(moves))
        self.assertEqual(original, {r['payload_instance_id'] for r in moves})
        # Each leg takes 2 s loading + 10 m / 2 m/s + 2 s unloading.
        # First return is released at 69 + 120 = 189; the second collection
        # released at 120 must wait for its bin until 198.
        arrivals = [r for r in sim.verbose_rows if r['event_type'] == 'location_payload_enter']
        self.assertEqual([0, 69, 198, 207, 336], [r['sim_time_sec'] for r in arrivals])
        self.assertEqual(['A', 'B', 'A', 'B', 'A'], [r['to_location'] for r in arrivals])

    def test_department_payload_override_is_the_seeded_physical_payload(self):
        config = bin_config()
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        other = copy.deepcopy(config['payloads'][0]); other['name'] = 'Other'
        config['payloads'].append(other)
        config['departments'][0]['waste_streams'][0]['payload'] = 'Other'
        sim = Simulation(config, verbose=True)
        self.assertEqual(['Other'], [r.payload for r in sim.payload_instance_store.records_at('A')])
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual(['Other'], [r.payload for r in sim.payload_instance_store.records_at('A')])

    def test_shared_group_cannot_reserve_another_groups_bin_at_same_location(self):
        config = bin_config()
        other = copy.deepcopy(config['departments'][0]); other.update(id='E', name='Other')
        other['waste_streams'][0]['shared_container_group'] = 'OTHER'
        config['departments'].append(other)
        sim = Simulation(config)
        records = sim.payload_instance_store.records_at('A')
        expected = next(r.instance_id for r in records if r.metadata['container_group'] == 'shared:OTHER')
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:OTHER'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertEqual(expected, task.payload_instance_id)
        self.assertTrue(task.return_same_payload_instance)

    def test_shared_bin_can_be_collected_from_its_actual_group_location(self):
        sim = Simulation(bin_config())
        original = sim.payload_instance_store.records_at('A')[0].instance_id
        task = Task('PROBE', 'B', 'A', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertEqual(('A', original), (task.pickup, task.payload_instance_id))
        self.assertTrue(task.return_enabled)

    def test_initial_container_opt_out_does_not_require_a_seeded_bin(self):
        config = bin_config()
        config['departments'][0]['waste_streams'][0]['initial_container_present'] = False
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        sim, original = self.run_case(config)
        self.assertEqual(set(), original)
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual(1, len(sim.payload_instance_store._known_instances))

    def test_department_group_without_shared_id_keeps_legacy_seed_identity(self):
        config = bin_config()
        config['departments'][0]['waste_streams'][0].pop('shared_container_group')
        sim, original = self.run_case(config)
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})

    def test_failed_outbound_keeps_bin_at_pickup_and_releases_reservation(self):
        config = bin_config()
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim, original = self.run_case(config)
        self.assertEqual(2, len(sim.failed_task_ids))
        self.assertEqual([], sim.completed_task_records)
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        self.assertEqual(original, set(sim.payload_instance_store._known_instances))
        self.assertFalse(sim.payload_instance_store._reservations)
        self.assertFalse(any(r['event_type'] == 'location_payload_exit' for r in sim.verbose_rows))

    def test_failed_return_leaves_one_bin_at_destination_and_later_collection_fails(self):
        config = bin_config()
        config['route_profiles'] = {'OutboundOnly': {'allowed_edges': [['A', 'Door'], ['Door', 'B']]}}
        config['task_generation']['categories']['waste']['return_route_profile'] = 'OutboundOnly'
        sim, original = self.run_case(config)
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual(2, len(sim.failed_task_ids))  # return plus waiting second collection
        self.assertEqual([], sim.payload_instance_store.records_at('A'))
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('B')})
        self.assertEqual(original, set(sim.payload_instance_store._known_instances))
        self.assertFalse(sim.payload_instance_store._reservations)
        self.assertEqual(1, sum(r['event_type'] == 'location_payload_exit' for r in sim.verbose_rows))

    def test_other_group_bin_is_not_substituted_when_requested_group_is_unavailable(self):
        sim = Simulation(bin_config())
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:MISSING'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertFalse(task.payload_instance_id)
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_blank_payload_override_falls_back_to_global_stream_payload(self):
        config = bin_config()
        config['departments'][0]['waste_streams'][0]['payload'] = '  '
        sim, original = self.run_case(config)
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})

    def two_contributors(self):
        config = bin_config()
        other = copy.deepcopy(config['departments'][0]); other.update(id='E', name='Other')
        config['departments'].append(other)
        config['task_generation']['categories']['waste']['department_groups'][0]['departments'].append('E')
        return config

    def test_shared_definition_conflicts_block_runtime_and_structured_preflight(self):
        for field, value in [('payload', 'Other'), ('container_capacity_m3', 2),
                             ('threshold_volume_m3', 1), ('initial_container_present', False)]:
            with self.subTest(field=field):
                config = self.two_contributors()
                config['payloads'].append(dict(config['payloads'][0], name='Other'))
                config['departments'][1]['waste_streams'][0][field] = value
                before = copy.deepcopy(config)
                with self.assertRaisesRegex(SharedContainerConflictError, field):
                    Simulation(config)
                report = check_project(config, include_legacy=False)
                findings = [f for f in report.findings if f.code == 'SHARED_CONTAINER_CONFLICT']
                self.assertTrue(any(field in f.message and 'shared:BIN' in f.message for f in findings))
                self.assertTrue(all(f.severity == 'error' and f.section == 'task_generation' for f in findings))
                report.acknowledge_warnings()
                self.assertFalse(report.can_run(config))
                config['waste_streams'][0]['payload'] = 'Other'
                self.assertIn('waste_streams', report.changed_inputs(findings[0], config))
                config['waste_streams'][0]['payload'] = 'Box'
                self.assertEqual(before, config)

    def test_compatible_shared_contributors_use_one_physical_bin_after_editor_import(self):
        config = self.two_contributors()
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        config['departments'][1]['waste_streams'][0].update(container_capacity_m3='0.5', priority=99)
        for data in (config, JsonStore(copy.deepcopy(config)).data):
            with self.subTest(normalised=data is not config):
                sim, original = self.run_case(data)
                self.assertEqual(1, len(original))
                self.assertEqual(4, len(sim.completed_task_records))
                self.assertEqual(set(), sim.failed_task_ids)
                self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})

    def test_disabled_contributor_does_not_conflict_with_active_definition(self):
        config = self.two_contributors()
        config['departments'][1]['waste_streams'][0].update(enabled=False, threshold_volume_m3=1)
        sim, original = self.run_case(config)
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(1, len(original))

    def test_global_seed_opt_out_uses_ordinary_outbound_payloads(self):
        config = bin_config()
        config['simulation']['seed_waste_stream_containers_at_start'] = False
        sim, original = self.run_case(config)
        self.assertFalse(original)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(2, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))

    def test_definition_checks_do_not_expand_runtime_task_counts(self):
        config = self.two_contributors()
        config['task_generation']['categories']['waste']['timeframe_payload_multiple'] = 999999999
        with patch('amr_sim_task_generation.DynamicCategoryTaskGenerator._prepare_instance_runtime_fields',
                   side_effect=AssertionError('Preflight must not allocate runtime task counts')):
            report = check_project(config, include_legacy=False)
        self.assertFalse(any(f.severity == 'error' for f in report.findings))
        self.assertEqual('completed', report.check_groups['shared_containers']['execution'])


if __name__ == '__main__':
    unittest.main()
