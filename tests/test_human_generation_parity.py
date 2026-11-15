"""Contingency transport consumes the native project's demand contracts."""
import copy
import unittest

from simulator import Simulation
from amr_contingency_runtime import HumanSimulation, simulate_candidate
from tests.test_human_contingency import fixture
from tests.test_generation_reference import grouped_config
from tests.test_tracked_stock_reference import stock_config
from tests.test_generation_layers import at_layer, LAYERS


class HumanGenerationParityTests(unittest.TestCase):
    def close_sim(self, sim):
        if sim.routing_executor is not None:
            sim.routing_executor.shutdown(wait=True)
        if sim.event_store is not None and not sim.event_store.closed:
            sim.event_store.close()

    def test_native_generated_records_match_at_every_rule_layer(self):
        modes = [dict(generation_mode='scheduled', scheduled_times=['00:01', '00:04']),
                 dict(generation_mode='sporadic', frequency_per_day=48, volume_per_event_m3=.2),
                 dict(generation_mode='timeframe', timeframe_start='00:02',
                      timeframe_end='00:08', timeframe_payload_multiple=3),
                 dict(generation_mode='threshold', scheduled_times=[],
                      tracked_item_exchange=True, exchange_mode='top_up_only')]
        for mode in modes:
            for layer in LAYERS:
                with self.subTest(mode=mode['generation_mode'], layer=layer):
                    c = stock_config() if mode['generation_mode']=='threshold' else grouped_config()
                    at_layer(c, layer).update(mode, requires_staff=False, target_time=300)
                    # Retain a second service in the native generator even though
                    # only stores is selected for human transport.
                    c['task_generation']['categories']['linen'] = copy.deepcopy(
                        c['task_generation']['categories']['stores'])
                    before = copy.deepcopy(c)
                    _, s, r = fixture()
                    native = Simulation(copy.deepcopy(c))
                    human = HumanSimulation(c, s, r)
                    self.addCleanup(self.close_sim, native)
                    self.addCleanup(self.close_sim, human)
                    self.assertEqual(native.config['task_generation'], human.config['task_generation'])
                    expected = native.task_generation_manager.update_until(7200)
                    actual = human.task_generation_manager.update_until(7200)
                    self.assertTrue(expected)
                    self.assertEqual([(v.rule_id, vars(v.task)) for v in expected],
                                     [(v.rule_id, vars(v.task)) for v in actual])
                    self.assertEqual(c, before)

    def test_subset_keeps_native_release_staggering_and_targets(self):
        c = grouped_config()
        stores = c['task_generation']['categories']['stores']
        stores.update(target_time=300, requires_staff=False)
        c['task_generation']['categories'] = dict(linen=copy.deepcopy(stores), stores=stores)
        c['simulation']['task_release_stagger_sec'] = 17
        _, s, r = fixture()
        native = Simulation(copy.deepcopy(c))
        self.addCleanup(self.close_sim, native)
        records = native.task_generation_manager.update_until(600)
        for record in records:
            native._schedule_generated_task_record(record)
        expected = [(record.task.id, record.task.release_time,
                     record.task.release_time+record.task.target_time)
                    for record in records if record.task.labels[0]=='stores']
        self.assertTrue(expected)
        for buffered in (False, True):
            for pool in ('shared', 'stores'):
                with self.subTest(buffered=buffered, pool=pool):
                    roster = [dict(r[0], pool=pool)]
                    result = simulate_candidate(c, s, roster, buffered=buffered)
                    self.assertTrue(result['passed'], result['unresolved'])
                    self.assertEqual(expected, [(t['id'], t['release'], t['deadline'])
                                                for t in result['tasks']])

    def test_unselected_stock_does_not_fail_selected_service(self):
        c = stock_config()
        stores = copy.deepcopy(grouped_config()['task_generation']['categories']['stores'])
        c['task_generation']['categories']['linen'] = c['task_generation']['categories']['stores']
        c['task_generation']['categories']['stores'] = stores
        _, s, r = fixture()
        s['shifts']['lengths_hours'] = [8]
        r[0]['end'] = 28800
        sim = HumanSimulation(c, s, r)
        result = sim.evaluate()
        self.assertTrue(result['passed'], result['unresolved'])
        self.assertTrue(all(t['service']=='stores' for t in result['tasks']))
        native_balances = sim.task_generation_manager.tracked_item_balance()
        self.assertTrue(any(row['unmet'] > 0 for row in native_balances))
        self.assertFalse(any(row['rule_id'].startswith('linen:') for row in result['balances']['tracked']))

    def test_deferral_limit_applies_until_human_assignment(self):
        c, s, r = fixture()
        c['simulation']['max_task_deferral_minutes'] = .1
        assigned = simulate_candidate(c, s, r)
        self.assertTrue(assigned['passed'], assigned['unresolved'])
        self.assertGreater(assigned['tasks'][0]['completed'], 6)
        r[0]['start'] = 60
        deferred = simulate_candidate(c, s, r)
        self.assertFalse(deferred['passed'])
        self.assertEqual(0, deferred['completed'])
        self.assertIn('deferral limit', deferred['unresolved'][0]['reason'])
        self.assertIn('human assignment', deferred['unresolved'][0]['reason'])

    def test_timeframe_deadline_does_not_move_with_staff_shift(self):
        c = grouped_config()
        c['task_generation']['categories']['stores'].update(generation_mode='timeframe',
            timeframe_start='00:02', timeframe_end='00:08', timeframe_payload_multiple=1,
            target_time=3600, requires_staff=False)
        _, s, r = fixture()
        early = simulate_candidate(c, s, r)
        self.assertTrue(early['passed'], early['unresolved'])
        r[0]['start'] = 490
        late = simulate_candidate(c, s, r)
        self.assertFalse(late['passed'])
        self.assertEqual(480, early['tasks'][0]['deadline'])
        self.assertEqual(480, late['tasks'][0]['deadline'])

    def test_global_generator_disable_and_explicit_tasks_are_preserved(self):
        c, s, r = fixture()
        c['task_generation'] = grouped_config()['task_generation']
        c['task_generation']['enabled'] = False
        result = simulate_candidate(c, s, r)
        self.assertTrue(result['passed'], result['unresolved'])
        self.assertEqual(['T1'], [t['id'] for t in result['tasks']])

    def test_service_selection_keeps_native_waste_generator_precedence(self):
        for dynamic_waste in (False, True):
            with self.subTest(dynamic_waste=dynamic_waste):
                c = grouped_config()
                c['waste_streams'] = [dict(name='General', payload='Box')]
                if dynamic_waste:
                    c['task_generation']['categories']['waste'] = copy.deepcopy(
                        c['task_generation']['categories']['stores'])
                _, s, r = fixture()
                native = Simulation(copy.deepcopy(c))
                human = HumanSimulation(c, s, r)
                self.addCleanup(self.close_sim, native)
                self.addCleanup(self.close_sim, human)
                expected = [g.generator_type for g in native.task_generation_manager.generators]
                actual = [g.generator_type for g in human.task_generation_manager.generators]
                self.assertEqual(expected, actual)
                self.assertEqual(not dynamic_waste, 'department_waste' in actual)


if __name__ == '__main__':
    unittest.main()
