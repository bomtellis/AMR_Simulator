"""End-to-end sideways yielding with fixed body heading and saved playback."""
import contextlib
import io
import json
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from simulator import Simulation, LocalManoeuvreError
from amr_trajectories import trajectory_from_dict
from tests.test_geometric_yielding import yielding_config
from amr_sim_visualiser_pyside6 import LayoutModel, SimulationLog


def lateral_config(*, permitted=True):
    config = yielding_config()
    # C(8,0)→B(16,0)→P(24,0). North-facing S cannot travel east through
    # forward/reverse steering because pivots are explicitly disabled.
    config['geometry']['initial_placements'][1]['heading_deg'] = 90
    for state, profile in config['amrs'][1]['movement'].items():
        profile.update(lateral_allowed=permitted, lateral_speed_m_per_sec=1 if state == 'empty' else .25)
    return config


class LateralRecoveryTests(unittest.TestCase):
    def test_lateral_cross_corridor_width_is_body_length(self):
        config = lateral_config()
        config['amrs'][1]['length_m'] = 1.2
        sim = Simulation(config)
        robot = sim.amrs_by_id['S-1']
        self.assertIsNone(sim._same_floor_segments(robot,sim.locations['C'],sim.locations['B'],movement='lateral'))
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertEqual('C',robot.location_name)

    def test_long_bent_graph_cannot_be_shortcut_by_a_lateral_line(self):
        config = lateral_config()
        config['locations'][2]['x'] = 10008
        config['corridors']['nodes'] = [dict(name='Bent',floor=0,x=5008,y=.1)]
        config['corridors']['edges'] = [{'from':a,'to':b,'width_m':1,'traffic_mode':'single_file'}
            for a,b in [('A','C'),('C','Bent'),('Bent','B')]]
        config['geometry']['floors'][0].update(bounds=[-3,-3,10010,3],passing_places=[])
        sim = Simulation(config)
        with self.assertRaisesRegex(LocalManoeuvreError,'straight graph alignment'):
            sim._same_floor_segments(sim.amrs_by_id['S-1'],sim.locations['C'],sim.locations['B'],movement='lateral')

    def test_lateral_yield_finishes_delivery_with_independent_duration_energy_and_heading(self):
        sim = Simulation(lateral_config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(['T'], [r['task_id'] for r in sim.completed_task_records])
        robot = sim.amrs_by_id['S-1']
        self.assertEqual('P', robot.location_name)
        self.assertEqual(0, robot.completed_tasks)
        # Empty lateral cap1m/s, a=b1: .5m+15m+.5m in1+15+1 seconds.
        self.assertAlmostEqual(17, robot.total_busy_time)
        self.assertAlmostEqual(750 * .75 * 17 / 3600000, robot.total_energy_used_kwh)
        self.assertAlmostEqual(90, robot.rotation_deg)
        rows = [r for r in sim.verbose_rows if r['amr_id'] == 'S-1' and r['event_type'] == 'segment_corridor']
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertFalse(row['task_id'])
        self.assertTrue(row['journey_id'])
        path = trajectory_from_dict(json.loads(row['trajectory_json']))
        self.assertEqual(['lateral'], [m.movement for m in path.motions])
        self.assertEqual(['line'], [m.kind for m in path.motions])
        self.assertAlmostEqual(16, path.length_m)
        self.assertAlmostEqual(17, path.duration_sec)
        midpoint = path.pose_at_time(8.5)
        self.assertAlmostEqual(16, midpoint.x)
        self.assertAlmostEqual(0, midpoint.y)
        self.assertAlmostEqual(math.pi / 2, midpoint.heading)
        self.assertFalse(any(r['amr_id'] == 'S-1' and r['event_type'] in
                             ('payload_pickup', 'payload_dropoff', 'task_complete') for r in sim.verbose_rows))

    def test_disallowed_lateral_motion_does_not_fall_back_to_pivot_or_teleport(self):
        sim = Simulation(lateral_config(permitted=False), verbose=True)
        initial = sim.geometric_occupancy
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.completed_task_records)
        robot = sim.amrs_by_id['S-1']
        self.assertEqual('C', robot.location_name)
        self.assertAlmostEqual(90, robot.rotation_deg)
        self.assertEqual(0, robot.total_busy_time)
        self.assertEqual(0, robot.total_energy_used_kwh)
        self.assertIs(initial, sim.geometric_occupancy)
        self.assertFalse(any(r['event_type'] == 'geometric_yield_started' for r in sim.verbose_rows))
        failures = [failure for outcome in sim.geometric_recovery_outcomes
                    for failure in outcome.get('failures', [])]
        self.assertTrue(any(f['movement'] == 'lateral' and f['reason'] == 'infeasible_route'
                            for f in failures))

    def test_saved_csv_playback_follows_lateral_profile_and_retains_north_heading(self):
        config = lateral_config()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = str(Path(directory) / 'steps.csv')
            sim = Simulation(config, verbose=True, verbose_csv_path=csv_path)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            layout, log = LayoutModel(), SimulationLog()
            layout.load_data(config)
            log.load(csv_path, parallel=False)
            # Nonmonotonic seeks prove replay uses frozen timing evidence.
            for seconds, expected_x in ((8.5, 16), (.5, 8.125), (16.5, 23.875), (8.5, 16)):
                state = log.state_at(log.start_time + timedelta(seconds=seconds), layout)[0]['S-1']
                self.assertAlmostEqual(expected_x, state['x'])
                self.assertAlmostEqual(0, state['y'])
                self.assertAlmostEqual(math.pi / 2, state['geometry_heading'])
                self.assertFalse(state.get('geometry_error'))


if __name__ == '__main__':
    unittest.main()
