"""Rejected multi-stop tours must not consume capacity or operational state."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_multi_stop_route_rules import multi_route_config, multi_lift_config


def storage_config(bays=1, *, lifts=False):
    config = multi_lift_config() if lifts else multi_route_config()
    config['locations'][1]['inventory_spaces'] = [
        dict(name=f'Bay-{i + 1}', length_m=2, width_m=2, height_m=2,
             payload_slots=[dict(payload='Box')]) for i in range(bays)]
    return config


def resource_state(sim):
    mappings = ('location_reservations', 'location_reservation_max_duration',
                'edge_reservations', 'edge_reservation_max_duration',
                'directed_edge_reservations', 'directed_edge_reservation_max_duration',
                'node_reservations', 'node_reservation_max_duration', 'lift_reservations',
                'inventory_spaces_by_location')
    return copy.deepcopy(dict(
        mappings={name: dict(getattr(sim, name)) for name in mappings},
        lifts=[vars(lift) for lift in sim.lifts],
        battery=[amr.battery_soc_percent for amr in sim.amrs],
        energy=[amr.total_energy_used_kwh for amr in sim.amrs],
        impacts={name: getattr(sim, name) for name in
                 ('scenario_delay_sec', 'scenario_affected_segments', 'people_delay_sec',
                  'people_affected_segments', 'wash_cycles_completed')},
    ))


class ReservationAtomicityTests(unittest.TestCase):
    def test_review_projects_raw_and_editor_normalised(self):
        for name, completed, failed, stock in [('storage-return', 4, 0, 0),
                                               ('storage-timeout', 1, 1, 1),
                                               ('storage-two-bays', 2, 0, 2)]:
            path = Path(__file__).resolve().parents[1] / 'verification' / 'scenarios' / f'{name}.json'
            raw = json.loads(path.read_text(encoding='utf-8'))
            for normalise in (False, True):
                with self.subTest(project=name, editor_normalised=normalise):
                    config = copy.deepcopy(raw)
                    if normalise:
                        config = JsonStore(config).data
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim = Simulation(config, verbose=True)
                        sim.run()
                    self.assertEqual(completed, len(sim.completed_task_records))
                    self.assertEqual(failed, len(sim.failed_task_ids))
                    self.assertEqual(stock, len(sim.payload_instance_store.records_at('B')))

    def prepare(self, config):
        sim = Simulation(config)
        tasks = [Task(f'T{i}', 'A', 'B', 'Box') for i in (1, 2)]
        for task in tasks:
            sim._queue_pending_task(task)
        return sim, tasks

    def test_two_payloads_cannot_both_estimate_the_same_single_bay(self):
        sim, tasks = self.prepare(storage_config())
        before = resource_state(sim)
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=False)
        self.assertIsNone(plan)
        self.assertEqual(before, resource_state(sim))

    def test_rejected_capacity_commit_leaves_no_route_or_bay_reservations(self):
        sim, tasks = self.prepare(storage_config())
        before = resource_state(sim)
        self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, resource_state(sim))
        self.assertEqual(['', ''], [task.assigned_inventory_space for task in tasks])

    def test_insufficient_battery_rolls_back_corridors_and_inventory(self):
        sim, tasks = self.prepare(storage_config(2))
        sim.amrs[0].battery_soc_percent = 0
        before = resource_state(sim)
        self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, resource_state(sim))
        self.assertEqual(['', ''], [task.assigned_inventory_space for task in tasks])

    def test_insufficient_battery_rolls_back_lift_position_wear_and_bookings(self):
        sim, tasks = self.prepare(storage_config(2, lifts=True))
        sim.amrs[0].battery_soc_percent = 0
        for lift in sim.lifts:
            lift.health_loss_per_journey_percent = 1
            lift.mean_time_between_failures_hours = 0.000001
            lift.mean_time_to_repair_hours = 1
        before = resource_state(sim)
        self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, resource_state(sim))

    def test_exception_after_energy_consumption_restores_committed_state(self):
        sim, tasks = self.prepare(storage_config(2))
        before = resource_state(sim)
        def fail_late(_segments):
            sim.scenario_delay_sec += 10
            raise RuntimeError('Injected late commit failure')
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=fail_late):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, resource_state(sim))

    def test_successful_two_bay_commit_keeps_distinct_claims(self):
        sim, tasks = self.prepare(storage_config(2))
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        spaces = sim.inventory_spaces_by_location['B']
        self.assertEqual({'T1', 'T2'}, {space['reserved_by_task'] for space in spaces})
        self.assertEqual(2, len({task.assigned_inventory_space for task in tasks}))
        self.assertEqual(['Bay-1', 'Bay-2'], [task.assigned_inventory_space for task in tasks])
        self.assertTrue(sim.edge_reservations)
        self.assertLess(sim.amrs[0].battery_soc_percent, 100)

    def test_stale_assignment_name_cannot_overwrite_another_active_task_claim(self):
        sim, tasks = self.prepare(storage_config())
        space = sim._reserve_inventory_space_for_task(tasks[0], sim.payloads['Box'])
        tasks[1].assigned_inventory_space = space['name']
        self.assertIsNone(sim._reserve_inventory_space_for_task(tasks[1], sim.payloads['Box']))
        self.assertEqual('T1', space['reserved_by_task'])

    def test_rollback_preserves_prior_reservations_and_next_successful_route(self):
        sim, tasks = self.prepare(storage_config(2))
        sim._reserve_edge('A', 'X', 100, 110, 'OTHER')
        sim._reserve_node('X', 100, 101, 'OTHER')
        sim._reserve_location('B', 100, 105)
        sim.amrs[0].battery_soc_percent = 0
        before = resource_state(sim)
        self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, resource_state(sim))
        sim.amrs[0].battery_soc_percent = 100
        result = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True)
        fresh, fresh_tasks = self.prepare(storage_config(2))
        expected = fresh._estimate_multi_stop_for_amr(fresh.amrs[0], fresh_tasks, reserve=True)
        self.assertEqual(expected['duration'], result['duration'])
        self.assertIn((100, 110, 'OTHER'), sim.edge_reservations[sim._physical_edge_key('A', 'X')])

    def test_feasible_estimate_claims_no_bays_or_other_resources(self):
        sim, tasks = self.prepare(storage_config(2))
        before = resource_state(sim)
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=False))
        self.assertEqual(before, resource_state(sim))
        self.assertEqual(['', ''], [task.assigned_inventory_space for task in tasks])

    def test_three_bay_matching_rearranges_choices_instead_of_rejecting_feasible_batch(self):
        config = storage_config(3)
        config['payloads'] = [dict(config['payloads'][0], name=name) for name in ('P', 'Q', 'R')]
        config['amrs'][0]['payload_slots'].append(dict(config['amrs'][0]['payload_slots'][0], name='Three'))
        for bay, allowed in zip(config['locations'][1]['inventory_spaces'], [('P', 'Q', 'R'), ('P',), ('Q', 'R')]):
            bay['payload_slots'] = [dict(payload=name) for name in allowed]
            bay['flexible'] = False
        sim = Simulation(config)
        tasks = [Task(f'T{i}', 'A', 'B', name) for i, name in enumerate(('P', 'Q', 'R'), 1)]
        for task in tasks:
            sim._queue_pending_task(task)
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(['Bay-2', 'Bay-3', 'Bay-1'], [task.assigned_inventory_space for task in tasks])

    def test_strict_task_keeps_bay_even_when_overflow_task_is_first(self):
        sim, tasks = self.prepare(storage_config())
        tasks[0].dropoff_zone = 'B'
        tasks[0].final_destination = 'A'
        tasks[0].requires_staff = True
        tasks[0].dropoff_zone_capacity_policy = 'allow_temporary_overflow'
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual('', tasks[0].assigned_inventory_space)
        self.assertEqual('Bay-1', tasks[1].assigned_inventory_space)
        self.assertEqual('T2', sim.inventory_spaces_by_location['B'][0]['reserved_by_task'])

    def test_disabled_storage_capacity_remains_explicitly_unlimited(self):
        config = storage_config()
        config['simulation']['disable_inventory_spaces'] = True
        sim, tasks = self.prepare(config)
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual('', sim.inventory_spaces_by_location['B'][0]['reserved_by_task'])

    def test_one_bay_run_completes_one_task_instead_of_rejecting_both(self):
        config = storage_config()
        config['simulation']['max_task_deferral_minutes'] = 1
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        self.assertEqual(['T1'], [r['task_id'] for r in sim.completed_task_records])
        self.assertEqual({'T2'}, sim.failed_task_ids)
        failure = next(r for r in sim.verbose_rows if r['event_type'] == 'task_failed')
        self.assertEqual(60, failure['sim_time_sec'])
        self.assertIn('Task deferral limit exceeded', failure['details'])
        waits = [r for r in sim.verbose_rows if r['event_type'] == 'task_wait']
        self.assertTrue(any('T2: All compatible inventory spaces are full at B' in r['details']
                            for r in waits))
        self.assertFalse(any('No AMRs currently available' in r['details'] for r in waits))
        self.assertEqual(1, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(1, sum(bool(s['occupied']) for s in sim.inventory_spaces_by_location['B']))
        self.assertFalse(any(r['event_type'] == 'multi_stop_task_assigned' for r in sim.verbose_rows))

    def test_full_bay_without_deferral_limit_remains_pending(self):
        config = storage_config()
        config['simulation']['max_task_deferral_minutes'] = 0
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual(['T2'], [task.id for _, _, _, task in sim.pending_tasks
                                 if not sim._pending_task_removed(task)])

    def test_no_compatible_bay_is_still_terminal(self):
        config = storage_config()
        config['locations'][1]['inventory_spaces'][0]['height_m'] = 0.01
        config['tasks'] = [dict(id='T1', pickup='A', dropoff='B', payload='Box')]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        self.assertEqual({'T1'}, sim.failed_task_ids)
        failure = next(r for r in sim.verbose_rows if r['event_type'] == 'task_failed')
        self.assertEqual(0, failure['sim_time_sec'])

    def test_returns_free_the_single_bay_for_each_later_delivery(self):
        config = storage_config()
        config['simulation']['max_task_deferral_minutes'] = 5
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box',
                                return_enabled=True, return_payload='Box') for i in (1, 2)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(0, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(2, len(sim.payload_instance_store.records_at('A')))
        self.assertFalse(any(s['reserved_by_task'] or s['occupied'] for s in sim.inventory_spaces_by_location['B']))


if __name__ == '__main__':
    unittest.main()
