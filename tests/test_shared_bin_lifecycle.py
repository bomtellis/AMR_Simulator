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


def swap_config():
    config = bin_config()
    config['simulation']['waste_bin_return_policy'] = 'second_amr_swap'
    config['amrs'][0]['quantity'] = 2
    config['locations'][1]['inventory_spaces'] = [
        {'name': 'Store', 'length_m': 1.5, 'width_m': 1.0, 'height_m': 1.5, 'flexible': True}
    ]
    config['mass_collections'] = [
        {'id': 'store', 'location': 'B', 'payloads': ['Box'], 'scheduled_times': ['23:00'],
         'capacity_trigger_fraction': 0, 'capacity_trigger_count': 0}
    ]
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
        config['task_generation']['categories']['waste']['department_groups'][0]['departments'].append('E')
        sim = Simulation(config)
        records = sim.payload_instance_store.records_at('A')
        expected = next(r.instance_id for r in records if r.metadata['container_group'] == 'shared:OTHER')
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:OTHER'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertEqual('', task.payload_instance_id)
        self.assertFalse(sim.payload_instance_store._reservations)
        self.assertEqual([expected], [row.instance_id for row in sim._pickup_instance_candidates(task)])
        self.assertTrue(sim._plan_payload_claims([task], reserve=True))
        self.assertEqual(expected, task.payload_instance_id)
        self.assertTrue(task.return_same_payload_instance)

    def test_shared_bin_can_be_collected_from_its_actual_group_location(self):
        sim = Simulation(bin_config())
        original = sim.payload_instance_store.records_at('A')[0].instance_id
        task = Task('PROBE', 'B', 'A', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertEqual(('A', ''), (task.pickup, task.payload_instance_id))
        self.assertFalse(sim.payload_instance_store.reservation_owner(original))
        self.assertTrue(task.return_enabled)

    def test_swap_pickup_stays_at_shared_collection_point_while_local_bin_is_claimed(self):
        sim = Simulation(swap_config())
        store = sim.payload_instance_store
        local_bin = store.records_at('A')[0]
        store.reserve_instance(local_bin.instance_id, 'EARLIER-COLLECTION')
        store_bin = store.records_at('B')[0]
        store_bin.metadata.update(container_group='shared:BIN', container_state='empty')
        task = Task('PROBE', 'B', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertTrue(task.waste_bin_swap)
        self.assertEqual('A', task.pickup)
        self.assertFalse(sim._pickup_instance_available(task))
        self.assertEqual('', task.payload_instance_id)
        self.assertFalse(store.reservation_owner(store_bin.instance_id))

    def test_pending_collection_claims_bin_only_when_amr_is_assigned(self):
        sim = Simulation(bin_config(), verbose=True)
        amr = sim.amrs[0]
        amr.is_charging = True
        original = sim.payload_instance_store.records_at('A')[0].instance_id
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        sim._queue_pending_task(task)
        sim._try_assign_tasks(0)
        self.assertEqual('', task.payload_instance_id)
        self.assertFalse(sim.payload_instance_store.reservation_owner(original))
        amr.is_charging = False
        sim._try_assign_tasks(20)
        self.assertEqual(original, task.payload_instance_id)
        self.assertEqual(task.id, sim.payload_instance_store.reservation_owner(original))
        assignments = [row['task_id'] for row in sim.verbose_rows if row['event_type'] == 'task_assigned']
        self.assertEqual([task.id], assignments)

    def test_return_happens_before_work_released_while_collection_is_in_flight(self):
        sim = Simulation(bin_config(), verbose=True)
        other = Task('OTHER', 'B', 'A', 'Box', release_time=66, priority=1)
        sim.schedule_task_release(other)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        assignments = [row for row in sim.verbose_rows if row['event_type'] == 'task_assigned']
        first, second = assignments[:2]
        self.assertTrue(first['task_id'].startswith('GEN_'))
        self.assertTrue(second['task_id'].startswith(f"RETURN-{first['task_id']}-"))
        self.assertEqual(first['amr_id'], second['amr_id'])
        returned = next(row for row in sim.verbose_rows
                        if row['event_type'] == 'task_complete' and row['task_id'] == second['task_id'])
        other_started = next(row for row in assignments if row['task_id'] == other.id)
        self.assertGreaterEqual(other_started['sim_time_sec'], returned['sim_time_sec'])
        self.assertFalse(sim.failed_task_ids)

    def test_second_amr_exchanges_a_real_store_bin_before_collection(self):
        config = swap_config()
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        sim = Simulation(config, verbose=True)
        initial_full = sim.payload_instance_store.records_at('A')[0].instance_id
        spare = sim.payload_instance_store.records_at('B')[0].instance_id
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        assignments = [row for row in sim.verbose_rows if row['event_type'] == 'task_assigned']
        delivery, collection = assignments
        self.assertNotEqual(delivery['amr_id'], collection['amr_id'])
        self.assertEqual([spare, initial_full], [row['payload_instance_id'] for row in assignments])
        staged = next(row for row in sim.verbose_rows if row['event_type'] == 'waste_replacement_staged')
        self.assertLessEqual(staged['sim_time_sec'], collection['sim_time_sec'])
        self.assertEqual([spare], [row.instance_id for row in sim.payload_instance_store.records_at('A')])
        self.assertEqual([initial_full], [row.instance_id for row in sim.payload_instance_store.records_at('B')])

    def test_advance_stages_next_spare_before_the_second_collection_is_due(self):
        config = swap_config()
        config['simulation']['waste_swap_advance_staging'] = True
        config['locations'][1]['inventory_spaces'].append(
            dict(config['locations'][1]['inventory_spaces'][0], name='Store 2'))
        config['mass_collections'][0]['initial_empty_overflow'] = {'Box': 1}
        sim = Simulation(config, verbose=True)
        self.assertEqual(3, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(2, len(sim.inventory_spaces_by_location['B']))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        staged = [row for row in sim.verbose_rows if row['event_type'] == 'waste_replacement_staged']
        self.assertEqual(3, len(staged))
        self.assertLess(staged[1]['sim_time_sec'], 120)
        self.assertIn('initial_empty-overflow', staged[-1]['payload_instance_id'])
        completed = [row for row in sim.verbose_rows
                     if row['event_type'] == 'task_complete' and row['task_source'] == 'department_waste']
        self.assertEqual(2, len(completed))

    def test_rejects_negative_overflow_stock(self):
        config = swap_config()
        config['mass_collections'][0]['initial_empty_overflow'] = {'Box': -1}
        with self.assertRaisesRegex(ValueError, 'nonnegative whole bin counts'):
            Simulation(config)

    def test_stages_opening_spare_before_the_first_collection_is_due(self):
        config = swap_config()
        config['simulation'].update(waste_swap_advance_staging=True, waste_swap_stage_initial_spares=True)
        config['locations'][1]['inventory_spaces'].append(
            dict(config['locations'][1]['inventory_spaces'][0], name='Store 2'))
        config['mass_collections'][0]['initial_empty_overflow'] = {'Box': 1}
        sim = Simulation(config, verbose=True)
        self.assertEqual(1, len(sim._waste_bin_replacements))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        staged = [row for row in sim.verbose_rows if row['event_type'] == 'waste_replacement_staged']
        self.assertEqual(3, len(staged))
        self.assertLess(staged[0]['sim_time_sec'], 60)
        self.assertLess(staged[1]['sim_time_sec'], 120)
        assignments = [row for row in sim.verbose_rows
                       if row['event_type'] == 'task_assigned' and row['task_source'] == 'department_waste']
        self.assertEqual(2, len(assignments))
        self.assertNotEqual(staged[0]['amr_id'], assignments[0]['amr_id'])

    def test_two_opening_spares_are_distinct_and_replenished(self):
        config = swap_config()
        config['simulation'].update(waste_swap_advance_staging=True, waste_swap_stage_initial_spares=True,
                                    waste_swap_spare_targets={'A': {'Box': 2}})
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        base = config['locations'][1]['inventory_spaces'][0]
        config['locations'][1]['inventory_spaces'].extend(
            dict(base, name=f'Store {index}') for index in (2, 3))
        sim = Simulation(config, verbose=True)
        pool, = sim._waste_bin_replacements.values()
        self.assertEqual(2, len(pool))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        staged = [row for row in sim.verbose_rows if row['event_type'] == 'waste_replacement_staged']
        self.assertEqual(3, len(staged))
        opening = {row['payload_instance_id']: row['amr_id'] for row in staged if row['sim_time_sec'] < 60}
        self.assertEqual(2, len(opening))
        swapped = next(row for row in sim.verbose_rows if row['event_type'] == 'location_payload_enter'
                       and row['task_source'] == 'waste_bin_replacement')
        collection = next(row for row in sim.verbose_rows if row['event_type'] == 'task_assigned'
                          and row['task_source'] == 'department_waste')
        self.assertNotEqual(opening[swapped['payload_instance_id']], collection['amr_id'])
        self.assertEqual(2, len(pool))
        self.assertTrue(all(spare.payload_dropoff_processed for spare in pool))

    def test_earliest_pickup_swap_dispatch_uses_time_of_physical_swap(self):
        config = swap_config()
        config['simulation'].update(waste_swap_advance_staging=True, waste_swap_stage_initial_spares=True,
                                    waste_swap_collection_dispatch={'A': 'earliest_pickup'})
        sim = Simulation(config)
        spare, = next(iter(sim._waste_bin_replacements.values()))
        spare.payload_dropoff_processed = True
        spare.waste_replacement_amr_id = 'OPENING-STAGER'
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        soon_at_pickup, soon_at_store = sim.amrs
        by_amr = {
            soon_at_pickup.id: {'pickup_complete_time': 20, 'finish_time': 90},
            soon_at_store.id: {'pickup_complete_time': 40, 'finish_time': 60},
        }
        with patch.object(sim, '_estimate_candidate_jobs', side_effect=lambda jobs: [
                (job, by_amr[job['amr'].id]) for job in jobs]):
            selection = sim._select_single_candidate_window([(0, 0, 0, task)], [], {}, {})
            self.assertIs(soon_at_pickup, selection[0])
            sim.waste_swap_collection_dispatch.clear()
            selection = sim._select_single_candidate_window([(0, 0, 0, task)], [], {}, {})
            self.assertIs(soon_at_store, selection[0])

    def test_opening_working_bin_can_be_claimed_while_the_first_bin_is_reserved(self):
        config = swap_config()
        config['simulation'].update(waste_swap_advance_staging=True, waste_swap_stage_initial_spares=True,
                                    waste_swap_opening_working_bins={'A': 'Box'})
        config['task_generation']['categories']['waste']['scheduled_times'] = ['00:01']
        base = config['locations'][1]['inventory_spaces'][0]
        config['locations'][0]['inventory_spaces'] = [
            dict(base, name=f'Working {index}') for index in (1, 2)]
        config['locations'][1]['inventory_spaces'].extend(
            dict(base, name=f'Store {index}') for index in (2, 3))
        sim, original = self.run_case(config)
        self.assertFalse(sim.failed_task_ids)
        store = sim.payload_instance_store
        working = store.records_at('A')
        self.assertEqual(2, len(working))
        self.assertEqual({row.instance_id for row in working},
                         {bay['payload_instance_id'] for bay in sim.inventory_spaces_by_location['A']})
        pool, = sim._waste_bin_replacements.values()
        self.assertEqual(1, len(pool))
        self.assertTrue(pool[0].payload_dropoff_processed)
        self.assertEqual(original, set(store._known_instances))
        store.reserve_instance(working[0].instance_id, 'EARLIER-COLLECTION')
        task = Task('PROBE', 'A', 'B', 'Box', waste_stream='General', task_source='department_waste')
        task.container_group = 'shared:BIN'
        sim._mark_generated_waste_task_requires_existing_container(task)
        self.assertEqual([working[1].instance_id], [row.instance_id for row in sim._pickup_instance_candidates(task)])

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
