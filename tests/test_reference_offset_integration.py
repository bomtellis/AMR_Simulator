"""Configured offset geometry must reach body-centred endpoints and replay them."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

from PySide6.QtWidgets import QApplication
from amr_reference_inputs import DEFAULT_REFERENCE_POINT, reference_point_options
from amr_geometric_routing import geometry_input_findings, simulation_project_from_study
from amr_trajectories import trajectory_from_dict
from simulator import Simulation
from tests.test_angular_dynamics_simulation import angular_corner_config
from tests.test_motion_dynamics_simulation import dynamics_config
from visualiser.geometry_workbench import EXAMPLE, GeometryWorkbench
from amr_sim_visualiser_pyside6 import LayoutModel, SimulationLog, SimulationVisualizer


def reference_config():
    config = angular_corner_config()
    config['amrs'][0]['manoeuvring']['reference_point'] = dict(DEFAULT_REFERENCE_POINT,
        longitudinal_mm=500, lateral_mm=200)
    return config


class ReferenceOffsetIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_explicit_reference_contract_is_validated_without_mutating_inputs(self):
        config = reference_config()
        before = copy.deepcopy(config)
        self.assertFalse(geometry_input_findings(config))
        self.assertEqual(before, config)
        for value in (None, {}, dict(DEFAULT_REFERENCE_POINT, pivot_axis='guess'),
                      dict(DEFAULT_REFERENCE_POINT, timing_reference='body_centre'),
                      dict(DEFAULT_REFERENCE_POINT, longitudinal_mm=True),
                      dict(DEFAULT_REFERENCE_POINT, lateral_mm=math.inf)):
            with self.subTest(value=value):
                config['amrs'][0]['manoeuvring']['reference_point'] = value
                self.assertTrue(any(path.endswith('/reference_point') for path, _ in geometry_input_findings(config)))
                with self.assertRaises(ValueError):
                    Simulation(config)

    def test_body_endpoints_independent_reference_distance_timing_and_saved_playback(self):
        config = reference_config()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'steps.csv')
            sim = Simulation(config, verbose=True, verbose_csv_path=path)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            self.assertEqual(['T'], [row['task_id'] for row in sim.completed_task_records])
            # Shifted reference support lines intersect at (5.8,.2). Ref radius2
            # gives line lengths3.3 and4.3, with quarter-circle lengthpi.
            # Firstline triangular:2sqrt3.3; lastline v2,a=b1:4.15s;
            # same angular arc as previous reference:5.25s; handling4s.
            expected_motion = 2*math.sqrt(3.3)+4.15+5.25
            self.assertAlmostEqual(expected_motion+4, sim.current_time)
            self.assertAlmostEqual(750*1.035*expected_motion/3600000, sim.amrs[0].total_energy_used_kwh)
            layout, log = LayoutModel(), SimulationLog()
            layout.load_data(config)
            log.load(path, parallel=False)
            event = next(event for event in log.events if event.row['event_type'] == 'segment_corridor')
            trajectory = trajectory_from_dict(json.loads(event.row['trajectory_json']))
            self.assertAlmostEqual(7.6+math.pi, trajectory.length_m)
            self.assertEqual((0, 0), (trajectory.motions[0].start.x, trajectory.motions[0].start.y))
            self.assertAlmostEqual(6, trajectory.motions[-1].end.x)
            self.assertAlmostEqual(6, trajectory.motions[-1].end.y)
            arc = trajectory.motions[1]
            self.assertAlmostEqual(math.sqrt(.5**2+2.2**2), arc.centre_orbit_radius_m)
            # One second into arc: yaw5deg. Reference=(3.8+2sinθ,2.2−2cosθ),
            # body=reference−rotation(θ)*(.5,.2).
            theta = math.radians(5)
            elapsed = 2+2*math.sqrt(3.3)+1
            state = log.state_at(log.start_time+timedelta(seconds=elapsed), layout)[0]['R-1']
            self.assertAlmostEqual(3.8+2*math.sin(theta)-.5*math.cos(theta)+.2*math.sin(theta), state['x'], delta=.002)
            self.assertAlmostEqual(2.2-2*math.cos(theta)-.5*math.sin(theta)-.2*math.cos(theta), state['y'], delta=.002)
            endpoint = log.state_at(log.start_time+timedelta(seconds=sim.current_time), layout)[0]['R-1']
            self.assertAlmostEqual(6, endpoint['x'], delta=.001)
            self.assertAlmostEqual(6, endpoint['y'], delta=.001)

    def test_workbench_reference_controls_undo_and_export_the_same_per_robot_values(self):
        window = GeometryWorkbench()
        self.addCleanup(window.close)
        before = copy.deepcopy(window.study)
        window.reference_controls['longitudinal_mm'].setValue(500)
        window.reference_controls['lateral_mm'].setValue(200)
        window.apply_parameters()
        self.assertEqual(1, window.undo_stack.count())
        self.assertEqual(3, window.trajectory.to_dict()['schema_version'])
        configured = window.study['parameters']['reference_point']
        self.assertEqual(dict(DEFAULT_REFERENCE_POINT, longitudinal_mm=500, lateral_mm=200), configured)
        project = simulation_project_from_study(window.study)
        self.assertEqual(configured, project['amrs'][0]['manoeuvring']['reference_point'])
        window.undo_stack.undo()
        self.assertEqual(before, window.study)
        window.undo_stack.redo()
        self.assertEqual(configured, window.study['parameters']['reference_point'])

    def test_keep_right_lane_transitions_keep_reference_radius_and_body_endpoints(self):
        config = dynamics_config()
        config['amrs'][0]['manoeuvring']['reference_point'] = dict(DEFAULT_REFERENCE_POINT,
            longitudinal_mm=500, lateral_mm=200)
        config['corridors']['edges'][0].update(traffic_mode='keep_right', width_m=4)
        sim = Simulation(config)
        robot = sim.amrs[0]
        segments, duration, distance = sim._same_floor_segments(robot, sim.locations['A'], sim.locations['B'])
        path = trajectory_from_dict(segments[0]['trajectory'])
        self.assertEqual(3, path.to_dict()['schema_version'])
        self.assertAlmostEqual(0, path.motions[0].start.x)
        self.assertAlmostEqual(0, path.motions[0].start.y)
        self.assertAlmostEqual(20, path.motions[-1].end.x)
        self.assertAlmostEqual(0, path.motions[-1].end.y)
        arcs = [motion for motion in path.motions if motion.kind == 'arc']
        self.assertEqual(4, len(arcs))
        self.assertTrue(all(motion.radius_m >= 2 for motion in arcs))
        for motion in arcs:
            sign = 1 if motion.sweep_rad > 0 else -1
            self.assertAlmostEqual(math.hypot(.5, sign*motion.radius_m+.2), motion.centre_orbit_radius_m)
        self.assertAlmostEqual(path.duration_sec, duration)
        self.assertAlmostEqual(path.length_m, distance)

    def test_successive_tasks_start_at_previous_body_endpoint_and_honour_pivot_axis(self):
        config = reference_config()
        config['locations'].append(dict(name='C', floor=0, x=0, y=6))
        config['corridors']['edges'].append(dict(**{'from': 'B', 'to': 'C'}, width_m=2,
                                               traffic_mode='single_file'))
        config['tasks'].append(dict(id='Next', pickup='B', dropoff='C', payload='Box', release_time=30))
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(['T', 'Next'], [row['task_id'] for row in sim.completed_task_records])
        row = next(row for row in sim.verbose_rows if row['event_type'] == 'segment_corridor'
                   and row['task_id'] == 'Next')
        path = trajectory_from_dict(json.loads(row['trajectory_json']))
        pivot = path.motions[0]
        self.assertEqual('pivot', pivot.kind)
        self.assertEqual('body_centre', pivot.reference['pivot_axis'])
        self.assertAlmostEqual(6, pivot.start.x)
        self.assertAlmostEqual(6, pivot.start.y)
        self.assertEqual(pivot.start.x, pivot.end.x)
        self.assertEqual(pivot.start.y, pivot.end.y)
        self.assertAlmostEqual(0, path.motions[-1].end.x)
        self.assertAlmostEqual(6, path.motions[-1].end.y)
        self.assertAlmostEqual(44.25, sim.current_time)

    def test_lane_offsets_cannot_create_a_forbidden_body_pivot_without_dynamics(self):
        config = dynamics_config()
        robot = config['amrs'][0]
        del robot['movement']
        robot['manoeuvring'].update(pivot_allowed=False, reference_point=dict(DEFAULT_REFERENCE_POINT,
            longitudinal_mm=0, lateral_mm=2000))
        config['corridors']['edges'][0].update(traffic_mode='keep_right', width_m=4)
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertTrue(any(row['event_type'] == 'task_geometry_unresolved' and 'pivot permission' in row['details']
                            for row in sim.verbose_rows))

    def test_body_footprint_reference_marker_uses_heading_and_saved_robot_type(self):
        from types import SimpleNamespace
        layout = LayoutModel()
        layout.load_data(reference_config())
        viewer = SimpleNamespace(layout_model=layout,
            _amr_heading_radians_for_state=lambda state: state['geometry_heading'])
        point = SimulationVisualizer._amr_reference_position_for_state(viewer,
            dict(amr_id='R-1', x=6, y=6, geometry_heading=math.pi/2))
        self.assertAlmostEqual(5.8, point[0])
        self.assertAlmostEqual(6.5, point[1])
