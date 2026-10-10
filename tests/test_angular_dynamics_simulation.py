"""Independent loaded-corner timing with finite rotational acceleration limits."""
import contextlib
import csv
import io
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from amr_geometric_occupancy import stationary_claim
from amr_geometric_traffic import first_traffic_slot, swept_cells
from amr_motion_profiles import MotionProfile
from amr_trajectories import Pose, Trajectory, plan_trajectory, trajectory_from_dict
from simulator import Simulation
from tests.test_motion_dynamics_simulation import dynamics_config
from visualiser.models import JsonStore
from amr_sim_visualiser_pyside6 import LayoutModel, SimulationLog


def angular_corner_config():
    config = dynamics_config()
    config['locations'][1].update(x=6, y=6)
    config['corridors'] = {'auto_connect': False,
        'nodes': [dict(name='J', floor=0, x=6, y=0)],
        'edges': [{'from': a, 'to': b, 'width_m': 2, 'traffic_mode': 'single_file'}
                  for a, b in [('A', 'J'), ('J', 'B')]]}
    config['geometry']['floors'][0].update(bounds=[-3, -3, 9, 9], obstacles=[])
    config['amrs'][0]['movement']['loaded'].update(minimum_radius_m=2,
        rotation_speed_deg_per_sec=30, angular_acceleration_deg_per_sec2=10,
        angular_braking_deg_per_sec2=20)
    return config


class AngularDynamicsSimulationTests(unittest.TestCase):
    def run_case(self, config=None, path=None):
        sim = Simulation(config or angular_corner_config(), verbose=True, verbose_csv_path=path)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            if path:
                sim.write_verbose_csv()
        return sim

    def trajectory(self, sim):
        row = next(row for row in sim.verbose_rows if row['event_type'] == 'segment_corridor')
        return trajectory_from_dict(json.loads(row['trajectory_json']))

    def test_loaded_corner_has_independent_time_distance_and_motor_energy(self):
        for imported in (False, True):
            with self.subTest(imported=imported):
                config = angular_corner_config()
                sim = self.run_case(JsonStore(config).data if imported else config)
                self.assertEqual('finished', sim._evidence_run_status)
                self.assertEqual(1, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                # Each 4m straight: accelerate2s/2m, brake2s/2m =>4s.
                # Arc: alpha10deg/s² to30deg/s in3s over45deg; cruise
                # .75s over22.5deg; beta20deg/s² stops in1.5s over22.5deg.
                # Thus moving=4+5.25+4=13.25s plus2+2s handling.
                self.assertAlmostEqual(17.25, sim.current_time)
                recorded = self.trajectory(sim)
                self.assertAlmostEqual(8+math.pi, recorded.length_m)
                self.assertAlmostEqual(13.25, recorded.duration_sec)
                self.assertEqual(['line', 'arc', 'line'], [m.kind for m in recorded.motions])
                self.assertAlmostEqual(750*1.035*13.25/3600000, sim.amrs[0].total_energy_used_kwh)
                self.assertAlmostEqual(90, sim.amrs[0].rotation_deg)

    def test_recorded_profiles_enforce_angular_caps_and_stop_at_curvature_changes(self):
        recorded = self.trajectory(self.run_case())
        first, arc, last = recorded.motions
        self.assertAlmostEqual(4, first.duration_sec)
        self.assertAlmostEqual(5.25, arc.duration_sec)
        self.assertAlmostEqual(4, last.duration_sec)
        for previous, following in zip(recorded.motions, recorded.motions[1:]):
            self.assertEqual(0, previous.profile['end_speed'])
            self.assertEqual(0, following.profile['start_speed'])
        profile = MotionProfile(**arc.profile)
        self.assertAlmostEqual(math.pi/3, profile.max_speed)       # 30deg/s * r2
        self.assertAlmostEqual(math.pi/9, profile.acceleration)  # 10deg/s² * r2
        self.assertAlmostEqual(2*math.pi/9, profile.braking)      # 20deg/s² * r2
        self.assertAlmostEqual(3, profile.acceleration_time)
        self.assertAlmostEqual(.75, profile.cruise_time)
        self.assertAlmostEqual(1.5, profile.braking_time)
        for time, expected_degrees_per_second in ((1, 10), (3.25, 30), (4, 25)):
            with self.subTest(time=time):
                step = 1e-5
                before = recorded.pose_at_time(4+time-step)
                after = recorded.pose_at_time(4+time+step)
                observed = (after.heading-before.heading)/(2*step)
                self.assertAlmostEqual(math.radians(expected_degrees_per_second), observed, delta=1e-7)
                self.assertAlmostEqual(profile.speed_at_time(time)/arc.radius_m, observed, delta=1e-7)

    def test_saved_playback_follows_slow_loaded_angular_acceleration_forward_and_backward(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'steps.csv')
            sim = self.run_case(path=path)
            layout, log = LayoutModel(), SimulationLog()
            layout.load_data(sim.config)
            log.load(path, parallel=False)
            # Arc begins after handling2s + first straight4s =6s. During
            # its firstsecond, theta=.5*10deg/s²*1²=5deg, rather than a
            # constant angular-speed interpolation across the quarter-circle.
            for elapsed, degrees in ((7, 5), (9.5, 60), (7, 5)):
                theta = math.radians(degrees)
                state = log.state_at(log.start_time+timedelta(seconds=elapsed), layout)[0]['R-1']
                self.assertAlmostEqual(4+2*math.sin(theta), state['x'], delta=.001)
                self.assertAlmostEqual(2-2*math.cos(theta), state['y'], delta=.001)
                self.assertAlmostEqual(theta, state['geometry_heading'], delta=.001)

    def test_continuous_occupancy_cells_use_angular_time_and_block_a_probe_at_actual_pose(self):
        sim = self.run_case()
        recorded = self.trajectory(sim)
        arc = recorded.motions[1]
        cells = swept_cells(Trajectory((arc,), 2, True), length_m=1, width_m=.7, clearance_m=0)
        self.assertEqual(21, len(cells))  # 5.25s / .25s per temporal enclosure
        first = cells[0]
        self.assertAlmostEqual(0, first['start'])
        self.assertAlmostEqual(.25, first['end'])
        # Exact firstcell midpoint angle and certified rotational displacement
        # bound, calculated from alpha rather than the implementation's profile.
        theta_end = .5*math.radians(10)*.25**2
        theta_mid = theta_end/2
        corner = math.hypot(.5, .35)
        inflation = 2*(2+corner)*math.sin(theta_end/4)
        expected_right = (4+2*math.sin(theta_mid)
                          +(.5+inflation)*math.cos(theta_mid)
                          +(.35+inflation)*math.sin(theta_mid))
        self.assertAlmostEqual(expected_right, first['envelope'][2])
        published = [row for row in sim.geometric_occupancy.rows(0) if row['occupancy_kind'] == 'moving']
        self.assertTrue(any(abs(row['start']-6)<1e-9 and abs(row['end']-6.25)<1e-9 for row in published))
        theta = math.radians(5)
        probe = stationary_claim(Pose(4+2*math.sin(theta), 2-2*math.cos(theta), 0),
            start=0, end=.001, owner='probe', length_m=.01, width_m=.01)
        start, blockers = first_traffic_slot(published, [probe], 7, 'probe', 0)
        self.assertGreater(start, 7)
        self.assertEqual(['R-1'], blockers)
        clear_probe = stationary_claim(Pose(0, 8, 0), start=0, end=.001,
            owner='probe', length_m=.01, width_m=.01)
        self.assertEqual((7, []), first_traffic_slot(published, [clear_probe], 7, 'probe', 0))

    def test_simple_corner_and_detailed_straight_times_remain_unchanged(self):
        simple = angular_corner_config()
        simple['simulation']['motion_model'] = 'legacy'
        sim = self.run_case(simple)
        self.assertAlmostEqual(10, sim.current_time)  # 12m /2m/s +4s handling
        self.assertFalse(any(row.get('trajectory_json') for row in sim.verbose_rows))
        straight = self.run_case(dynamics_config())
        self.assertAlmostEqual(16, straight.current_time)  # 20m with loaded a=b1, vmax2 +handling

    def test_old_recorded_nonzero_curvature_boundary_speeds_replay_unchanged(self):
        # Old source evidence used continuous translation at line/arc joins.
        # Preserve those recorded results even though new runs now stop there.
        data = plan_trajectory([(0, 0), (6, 0), (6, 6)], minimum_radius_m=2,
            speed_m_per_sec=2, pivot_allowed=True, pivot_speed_deg_per_sec=90).to_dict()
        profiles = [dict(distance=4, max_speed=2, acceleration=1, braking=1, start_speed=0, end_speed=1),
                    dict(distance=math.pi, max_speed=1, acceleration=1, braking=1, start_speed=1, end_speed=1),
                    dict(distance=4, max_speed=2, acceleration=1, braking=1, start_speed=1, end_speed=0)]
        # First line: accelerate2s/2m, cruise.25s/.5m, brake1s/1.5m.
        # Arc cruises at1m/s forpi seconds. Final line is symmetric.
        for motion, profile, seconds in zip(data['motions'], profiles, (3.25, math.pi, 3.25)):
            motion.update(profile=profile, duration_sec=seconds)
        data['duration_sec'] = 6.5+math.pi
        decoded = trajectory_from_dict(json.loads(json.dumps(data)))
        self.assertAlmostEqual(6.5+math.pi, decoded.duration_sec)
        self.assertEqual(1, decoded.motions[0].profile['end_speed'])
        self.assertEqual(1, decoded.motions[1].profile['start_speed'])
        elapsed = 3.25+math.pi/2
        midpoint = decoded.pose_at_time(elapsed)
        self.assertAlmostEqual(4+math.sqrt(2), midpoint.x)
        self.assertAlmostEqual(2-math.sqrt(2), midpoint.y)
        self.assertAlmostEqual(math.pi/4, midpoint.heading)
        # Exercise the saved CSV playback adapter too: no current robot setting
        # or revised retimer may silently change an old run's recorded trajectory.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'old-curve.csv'
            start = datetime(2026, 1, 5, 8)
            row = dict(event_type='segment_corridor', amr_id='R-1', sim_time_sec=0,
                sim_datetime=start.isoformat(), start_time=start.isoformat(),
                end_time=(start+timedelta(seconds=data['duration_sec'])).isoformat(),
                duration_sec=data['duration_sec'], segment_type='corridor',
                from_location='A', to_location='B', start_node='A', end_node='B',
                start_x=0, start_y=0, end_x=6, end_y=6, start_floor=0, end_floor=0,
                motion_model='geometric_v1', trajectory_json=json.dumps(data))
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            layout, log = LayoutModel(), SimulationLog()
            layout.load_data(angular_corner_config())
            log.load(str(path), parallel=False)
            state = log.state_at(start+timedelta(seconds=elapsed), layout)[0]['R-1']
            self.assertAlmostEqual(midpoint.x, state['x'], delta=.001)
            self.assertAlmostEqual(midpoint.y, state['y'], delta=.001)
            self.assertAlmostEqual(midpoint.heading, state['geometry_heading'], delta=.001)


if __name__ == '__main__':
    unittest.main()
