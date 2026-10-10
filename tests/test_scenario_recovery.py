"""Temporary outages must delay valid work, then wake it at recovery."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_delivery_energy_reference import lift_config
from tests.test_multi_stop_route_rules import multi_route_config
from tests.test_single_charge_atomicity import state
from visualiser.models import JsonStore
from amr_results_investigation import load_investigation


def scenario(cfg, resource, *, start='00:00', end='00:01', days=None):
    cfg['scenario_testing'] = dict(enabled=True, enhanced_logging=True, active_scenario='Outage',
        scenarios=[dict(name='Outage', events=[dict(resource_type=resource,
            resource_ids=['R' if resource=='amr' else 'L1'], start_time=start, end_time=end,
            days_active=days or [], availability_percent=0, speed_factor=1)])])
    cfg['tasks'] = [dict(id='T',pickup='A',dropoff='B',payload='Box')]
    return cfg


class ScenarioRecoveryTests(unittest.TestCase):
    def run_case(self, cfg):
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim

    def test_robot_recovers_at_end_of_outage_without_other_events(self):
        sim = self.run_case(scenario(reference_config(),'amr'))
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertAlmostEqual(69, sim.amrs[0].available_time)

    def test_lift_outage_does_not_terminally_fail_routable_task(self):
        sim = self.run_case(scenario(lift_config(),'lift'))
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertAlmostEqual(70, sim.amrs[0].available_time)

    def test_multi_stop_robot_cannot_pick_up_during_outage(self):
        cfg = scenario(multi_route_config(),'amr')
        cfg['tasks'].append(dict(id='T2',pickup='A',dropoff='B',payload='Box'))
        sim = self.run_case(cfg)
        assigned = [r for r in sim.verbose_rows if r['event_type']=='multi_stop_task_assigned']
        self.assertEqual(2,len(assigned))
        self.assertTrue(all(float(r['sim_time_sec'])>=60 for r in assigned))

    def test_overnight_window_uses_the_day_it_started(self):
        cfg = scenario(reference_config(),'amr', start='23:00',end='01:00',days=['mon'])
        cfg['simulation'].update(start_datetime='2026-01-06T00:00:00',end_datetime='2026-01-06T02:00:00')
        sim = Simulation(cfg)
        self.assertEqual(0,sim._scenario_event_state('amr','R-1',0)['availability_percent'])
        self.assertEqual(100,sim._scenario_event_state('amr','R-1',3600)['availability_percent'])

    def test_end_is_exclusive_with_fractional_seconds(self):
        sim = Simulation(scenario(reference_config(),'amr'))
        before = sim._scenario_event_state('amr','R-1',59.999999)
        self.assertEqual(0,before['availability_percent'])
        self.assertAlmostEqual(60,before['blocked_until'])
        self.assertEqual(100,sim._scenario_event_state('amr','R-1',60)['availability_percent'])

    def test_adjacent_and_overlapping_outages_resume_at_last_end(self):
        for start in ('00:00','00:01'):
            cfg = scenario(reference_config(),'amr')
            events = cfg['scenario_testing']['scenarios'][0]['events']
            events.append(dict(events[0],start_time=start,end_time='00:02'))
            sim = self.run_case(cfg)
            self.assertEqual(1,len(sim.completed_task_records))
            self.assertAlmostEqual(129,sim.amrs[0].available_time)
            boundaries = [r['sim_time_sec'] for r in sim.verbose_rows if r['event_type']=='scenario_boundary']
            self.assertEqual([0,60,120],boundaries)

    def test_original_deferral_deadline_can_expire_before_recovery(self):
        cfg = scenario(lift_config(),'lift')
        cfg['simulation']['max_task_deferral_minutes'] = .5
        sim = self.run_case(cfg)
        self.assertEqual(0,len(sim.completed_task_records))
        self.assertEqual(1,len(sim.failed_tasks))
        self.assertAlmostEqual(30,sim.failed_tasks[0]['sim_time_sec'])

    def test_outage_beyond_horizon_remains_pending_not_failed(self):
        cfg = scenario(lift_config(),'lift',end='01:00')
        sim = self.run_case(cfg)
        self.assertFalse(sim.completed_task_records)
        self.assertFalse(sim.failed_tasks)
        self.assertTrue(any(not sim._pending_task_removed(t) for _,_,_,t in sim.pending_tasks))

    def test_temporary_outage_does_not_hide_a_permanent_route_restriction(self):
        cfg = scenario(lift_config(),'lift')
        cfg['tasks'][0]['allowed_lifts'] = ['MissingLift']
        sim = self.run_case(cfg)
        self.assertFalse(sim.completed_task_records)
        self.assertEqual(1,len(sim.failed_tasks))
        self.assertIn('route restrictions',sim.failed_tasks[0]['reason'])

    def test_unavailable_robot_cannot_start_charging(self):
        sim = Simulation(scenario(reference_config(),'amr'),verbose=True)
        sim.amrs[0].battery_soc_percent = 10
        before = state(sim)
        self.assertFalse(sim._schedule_charge_cycle(sim.amrs[0],0))
        self.assertEqual(before,state(sim))
        self.assertTrue(any(r['event_type']=='charge_wait' for r in sim.verbose_rows))

    def test_disabled_or_unmatched_scenario_leaves_normal_timing(self):
        for disabled in (False,True):
            cfg = scenario(reference_config(),'amr')
            if disabled:
                cfg['scenario_testing']['enabled'] = False
            else:
                cfg['scenario_testing']['scenarios'][0]['events'][0]['resource_ids'] = ['OtherRobot']
            sim = self.run_case(cfg)
            self.assertEqual(1,len(sim.completed_task_records))
            self.assertAlmostEqual(9,sim.amrs[0].available_time)

    def test_equal_times_are_all_day_on_the_selected_weekday(self):
        cfg = scenario(reference_config(),'amr',start='08:00',end='08:00',days=['mon'])
        sim = Simulation(cfg)
        self.assertEqual(0,sim._scenario_event_state('amr','R-1',0)['availability_percent'])
        self.assertEqual(0,sim._scenario_event_state('amr','R-1',86399.9)['availability_percent'])
        self.assertEqual(100,sim._scenario_event_state('amr','R-1',86400)['availability_percent'])

    def test_saved_recovery_projects_before_and_after_editor_normalisation(self):
        root = Path(__file__).resolve().parents[1]/'verification/scenarios'
        for name, finish in [('robot-outage-recovery',69),('lift-outage-recovery',70)]:
            for normalise in (False,True):
                with self.subTest(name=name,normalise=normalise), tempfile.TemporaryDirectory() as directory:
                    cfg = json.loads((root/(name+'.json')).read_text(encoding='utf-8'))
                    log = Path(directory)/'steps.csv'
                    sim = Simulation(JsonStore(cfg).data if normalise else cfg,verbose=True,verbose_csv_path=str(log))
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim.run()
                        sim.write_verbose_csv()
                    self.assertEqual(1,len(sim.completed_task_records))
                    self.assertAlmostEqual(finish,sim.amrs[0].available_time)
                    inv = load_investigation(log)
                    self.assertTrue(all(r['matches'] for r in inv['reconciliation']))


if __name__ == '__main__':
    unittest.main()
