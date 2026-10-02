"""Independent lift service, wear and deterministic repair references."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simulator import Simulation
from amr_sim_models import Task
from tests.test_delivery_energy_reference import lift_config
from tests.test_single_charge_atomicity import state
from visualiser.models import JsonStore
from amr_results_investigation import load_investigation


def config(*, slowdown=False):
    cfg = lift_config()
    cfg['amrs'][0].update(quantity=2, multi_stop_enabled=False)
    cfg['simulation']['task_release_stagger_sec'] = 0
    cfg['lifts'][0].update(health_loss_per_journey_percent=0,
        mean_time_between_failures_hours=1/3600, mean_time_to_repair_hours=70/3600)
    cfg['tasks'] = [dict(id=f'T{i}',pickup='A',dropoff='B',payload='Box') for i in (1,2)]
    if slowdown:
        cfg['scenario_testing'] = dict(enabled=True,enhanced_logging=True,active_scenario='Slower lift',
            scenarios=[dict(name='Slower lift',events=[dict(resource_type='lift',resource_ids=['L1'],
                start_time='00:01',end_time='00:02',availability_percent=100,speed_factor=.5)])])
    return cfg


class LiftRepairReferenceTests(unittest.TestCase):
    def run_case(self, cfg):
        sim = Simulation(cfg,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim

    def test_repair_wait_and_future_speed_use_actual_service_time(self):
        sim = Simulation(config(slowdown=True),verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2,len(sim.completed_task_records))
        # First lift: 2.5 + 2 boarding + 1 vertical + 2 alighting = 7.5.
        # Repair ends 77.5. Half-speed reposition 2 + boarding 2 + loaded 2
        # + alighting 2 ends 85.5; connector .5 + final handling 2 => 88.
        self.assertEqual([10,88],sorted(a.available_time for a in sim.amrs))
        self.assertEqual(2,sim.lifts[0].journeys_completed)
        self.assertEqual(2,sim.lifts[0].failures_count)
        self.assertAlmostEqual(155.5,sim.lifts[0].failed_until)

    def test_no_repair_and_zero_repair_duration_have_normal_service_times(self):
        for disabled in (False,True):
            cfg = config()
            cfg['lifts'][0]['mean_time_to_repair_hours'] = 0
            if disabled:
                cfg['lifts'][0]['mean_time_between_failures_hours'] = 0
            sim = self.run_case(cfg)
            self.assertEqual([10,16],sorted(a.available_time for a in sim.amrs))
            self.assertEqual(0 if disabled else 2,sim.lifts[0].failures_count)

    def test_repair_without_slowdown_waits_exactly_seventy_seconds(self):
        sim = self.run_case(config())
        self.assertEqual([10,86],sorted(a.available_time for a in sim.amrs))
        self.assertEqual([(2.5,7.5),(77.5,83.5)],[(r[0],r[1]) for r in sim.lift_reservations['L1']])
        self.assertEqual(2,sim.lifts[0].failures_count)

    def test_estimation_cannot_apply_wear_or_start_repair(self):
        sim = Simulation(config())
        before = state(sim)
        for _ in range(3):
            self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','B','Box')))
        self.assertEqual(before,state(sim))

    def test_failed_commit_restores_wear_repair_and_reservations(self):
        sim = Simulation(config())
        before = state(sim)
        with patch.object(sim,'_record_committed_segment_impacts',side_effect=RuntimeError('late failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','B','Box'),reserve=True))
        self.assertEqual(before,state(sim))

    def test_shared_journey_applies_wear_once_for_two_payloads(self):
        cfg = lift_config()
        cfg['lifts'][0].update(health_loss_per_journey_percent=2.5,mean_time_between_failures_hours=0)
        cfg['tasks'] = [dict(id=f'T{i}',pickup='A',dropoff='B',payload='Box') for i in (1,2)]
        sim = self.run_case(cfg)
        self.assertEqual(2,len(sim.completed_task_records))
        self.assertEqual(1,sim.lifts[0].journeys_completed)
        self.assertAlmostEqual(97.5,sim.lifts[0].health_percent)
        self.assertAlmostEqual(1,sim.lifts[0].operating_time_since_failure_sec)

    def test_minimum_health_is_inclusive_then_wear_can_disable_lift(self):
        cfg = config()
        cfg['lifts'][0].update(health_percent=20,minimum_operational_health_percent=20,
            health_loss_per_journey_percent=1,mean_time_between_failures_hours=0)
        sim = self.run_case(cfg)
        self.assertEqual(1,len(sim.completed_task_records))
        self.assertEqual(1,len(sim.failed_tasks))
        self.assertAlmostEqual(19,sim.lifts[0].health_percent)
        self.assertIn('operational health threshold',sim.failed_tasks[0]['reason'])

    def test_post_wear_health_scales_the_deterministic_failure_threshold(self):
        cfg = config()
        cfg['lifts'][0].update(health_percent=50,health_loss_per_journey_percent=10,
            mean_time_between_failures_hours=10/3600,mean_time_to_repair_hours=10/3600)
        sim = Simulation(cfg)
        lift = sim.lifts[0]
        lift.operating_time_since_failure_sec = 3
        plan = sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','B','Box'),reserve=True)
        self.assertIsNotNone(plan)
        # At 50% health speed factor is .75: 1/.75 vertical seconds.
        # Post-wear 40% health sets failure threshold to 10*.4=4 seconds.
        self.assertAlmostEqual(40,lift.health_percent)
        self.assertEqual(1,lift.failures_count)
        self.assertAlmostEqual(2.5+2+1/.75+2+10,lift.failed_until)

    def test_loaded_speed_is_sampled_after_boarding(self):
        sim = Simulation(config(slowdown=True))
        slot = sim._find_lift_journey_slot(sim.lifts[0],59,0,1)
        self.assertEqual(61,slot['loaded_start'])
        self.assertEqual(2,slot['loaded_travel_sec'])
        self.assertEqual(65,slot['lift_finish'])

    def test_unavailable_future_phase_does_not_commit_nonfinite_route(self):
        cfg = config(slowdown=True)
        cfg['scenario_testing']['scenarios'][0]['events'][0].update(availability_percent=0,speed_factor=1)
        sim = self.run_case(cfg)
        self.assertEqual(2,len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        # Recovery at 120: normal approach/pickup and reposition add 11 s.
        self.assertEqual([10,131],sorted(a.available_time for a in sim.amrs))
        self.assertTrue(all(r[1]<float('inf') for r in sim.lift_reservations['L1']))

    def test_saved_reference_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1]/'verification/scenarios/lift-repair-slowdown.json'
        for normalise in (False,True):
            with self.subTest(normalise=normalise),tempfile.TemporaryDirectory() as directory:
                cfg = json.loads(path.read_text(encoding='utf-8'))
                log = Path(directory)/'steps.csv'
                sim = Simulation(JsonStore(cfg).data if normalise else cfg,verbose=True,verbose_csv_path=str(log))
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                    sim.write_verbose_csv()
                self.assertEqual([10,88],sorted(a.available_time for a in sim.amrs))
                inv=load_investigation(log)
                self.assertTrue(all(r['matches'] for r in inv['reconciliation']))
                self.assertTrue(all(r['matches'] for r in inv['energy']['battery']['records']))


if __name__ == '__main__':
    unittest.main()
