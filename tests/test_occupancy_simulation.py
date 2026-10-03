"""Full-plan traffic acceptance: parked robots, service, charging and rollback."""
import contextlib
import io
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_route_reservations import RouteReservationTransaction
from amr_sim_models import Task
from simulator import Simulation, LocalManoeuvreError
from tests.test_geometric_traffic import traffic_config
from amr_sim_visualiser_pyside6 import LayoutModel, SimulationLog


def fleet(x=10, y=0, heading=0):
    config = traffic_config(width=1)
    config['amrs'][0]['quantity'] = 2
    config['locations'].append(dict(name='C', floor=0, x=x, y=y))
    config['geometry']['initial_placements'] = [
        dict(amr_id='R-1', location='A', heading_deg=0),
        dict(amr_id='R-2', location='C', heading_deg=heading)]
    return config


class OccupancySimulationTests(unittest.TestCase):
    def test_parked_robot_blocks_route_without_consuming_energy_or_reservations(self):
        sim = Simulation(fleet())
        before = sim.geometric_occupancy
        energy = sim.amrs[0].battery_energy_kwh()
        task = Task('blocked', 'A', 'B', 'Box')
        for reserve in (False, True):
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=reserve))
            self.assertIn('traffic_blocked', task.pending_reason)
            self.assertIs(before, sim.geometric_occupancy)
            self.assertEqual(energy, sim.amrs[0].battery_energy_kwh())
            self.assertFalse(sim.geometric_route_reservations)
        self.assertTrue(sim._task_commit_failure_is_transient(task))

    def test_zero_distance_loading_checks_full_payload_footprint(self):
        for handling in (2,0):
            config = fleet(x=0, y=.8)
            config['payloads'][0]['width_m'] = 2
            config['building']['load_unload_time_sec'] = handling
            sim = Simulation(config)
            before = sim.geometric_occupancy
            task = Task('local', 'A', 'A', 'Box')
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
            self.assertIs(before, sim.geometric_occupancy)
            evidence = sim.geometric_candidate_outcomes[('R-1', 'local')]
            self.assertEqual('traffic_blocked', evidence['reason'])
            self.assertEqual('R-2', evidence['conflicts'][0]['blocking_owner'])
            self.assertEqual('0:pickup', evidence['conflicts'][0]['proposed_source_id'])
            self.assertIsNone(evidence['conflicts'][0]['blocking_release'])

    def test_future_endpoint_attributes_cannot_teleport_parked_robot(self):
        sim = Simulation(traffic_config(width=1))
        before = sim.geometric_occupancy
        with RouteReservationTransaction(sim,sim.amrs[0],[]):
            with self.assertRaisesRegex(LocalManoeuvreError,'teleportation'):
                sim._check_geometric_occupancy(sim.amrs[0],[],0,sim.locations['B'],0,reserve=True)
        self.assertIs(before,sim.geometric_occupancy)

    def test_departure_trims_initial_tail_and_reserves_handling_and_final_parking(self):
        sim = Simulation(traffic_config(width=1))
        task = Task('delivery', 'A', 'B', 'Box', release_time=5)
        plan = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
        self.assertIsNotNone(plan)
        rows = sim.geometric_occupancy.rows(0)
        stationary = [r for r in rows if r['occupancy_kind']=='stationary']
        self.assertEqual([(0,5), (5,7), (17,19), (19,math.inf)],
                         [(r['start'],r['end']) for r in stationary])
        self.assertEqual([-.5,-.35,.5,.35], stationary[1]['envelope'])
        self.assertEqual([19.5,-.3,20.5,.3], stationary[-1]['envelope'])
        self.assertFalse(sim.geometric_route_reservations)  # no duplicate moving claims

    def test_finite_blocker_release_allows_travel_before_other_robot_finishes_charging(self):
        config = fleet(heading=90)
        config['locations'].append(dict(name='D',floor=0,x=10,y=4))
        config['corridors']['edges'].append({'from':'C','to':'D','width_m':1})
        sim = Simulation(config)
        robot = sim.amrs[1]
        route,_,_ = sim._same_floor_segments(robot,sim.locations['C'],sim.locations['D'],start_time_value=10)
        segments = [dict(type='wait',duration=10)] + route + [dict(type='charge',duration=50)]
        with RouteReservationTransaction(sim,robot,[]) as transaction:
            sim._check_geometric_occupancy(robot,segments,0,sim.locations['C'],90,reserve=True)
            transaction.committed = True
        plan = sim._estimate_task_for_amr(sim.amrs[0],Task('delivery','A','B','Box'),reserve=True)
        self.assertIsNotNone(plan)
        wait = next(s for s in plan['segments'] if s['type']=='wait_for_geometry')
        self.assertGreater(wait['duration'],0)
        self.assertLess(plan['finish_time'],62)
        self.assertTrue(any(r['source_id'].endswith(':charge') for r in sim.geometric_occupancy.rows()))

    def test_exception_after_occupancy_commit_restores_exact_ledger_reference(self):
        sim = Simulation(traffic_config(width=1))
        before = sim.geometric_occupancy
        energy = sim.amrs[0].battery_energy_kwh()
        with patch.object(sim.amrs[0], 'consume_energy', side_effect=RuntimeError('injected commit failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                result = sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','B','Box'),reserve=True)
        self.assertIsNone(result)
        self.assertIs(before, sim.geometric_occupancy)
        self.assertEqual(energy, sim.amrs[0].battery_energy_kwh())
        self.assertFalse(sim.location_reservations)

    def test_charge_travel_keeps_destination_occupied_after_arrival(self):
        sim = Simulation(traffic_config(width=1))
        sim.charge_location_names = ['B']
        sim.charge_location_name = 'B'
        plan = sim._plan_return_to_charge(sim.amrs[0],sim.locations['A'],0,reserve=True)
        self.assertIsNotNone(plan)
        tail = sim.geometric_occupancy.rows()[-1]
        self.assertEqual((10,math.inf),(tail['start'],tail['end']))
        self.assertEqual([19.5,-.3,20.5,.3],tail['envelope'])

    def test_explicit_initial_position_and_heading_replay_without_stale_charger_event(self):
        config = fleet(x=10,y=3,heading=90)
        config['tasks'] = []
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'steps.csv')
            sim = Simulation(config,verbose=True,verbose_csv_path=path)
            initial = [r for r in sim.verbose_rows if r['event_type'].startswith('initial_amr')]
            self.assertEqual(2,len(initial))
            self.assertTrue(all(r['event_type']=='initial_amr_placement' for r in initial))
            with contextlib.redirect_stdout(io.StringIO()): sim.write_verbose_csv()
            layout,log = LayoutModel(),SimulationLog()
            layout.load_data(config)
            log.load(path,parallel=False)
            state = log.state_at(log.start_time,layout)[0]['R-2']
            self.assertAlmostEqual(10,state['x'])
            self.assertAlmostEqual(3,state['y'])
            self.assertAlmostEqual(90,state['amr_rotation_deg'])


if __name__=='__main__': unittest.main()
