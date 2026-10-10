"""Opt-in local fallback never represents its direct path as validated geometry."""
import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.test_simulation_run_controls import SimulationSettingsDialog
from tests.test_engineering_reference import reference_config
from tests.test_local_manoeuvre_safety import RING
from tests.test_route_reservation_atomicity import storage_config
from simulator import Simulation, LocalManoeuvreError
from visualiser.project_checks import check_project
from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtGui import QBrush, QColor


class UnverifiedLocalManoeuvreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def sim(self, enabled=True):
        config = reference_config()
        config['simulation']['ignore_invalid_local_manoeuvres'] = enabled
        return Simulation(config)

    def test_direct_fallback_distance_time_reason_and_repeat_calls(self):
        sim = self.sim()
        bay = dict(name='Bay', points=[dict(dx=4, dy=0)], rotation_deg=0)
        sim.amrs[0].rotation_deg = 0
        for obstacles, reason in [(RING, 'search_exhausted'), ([(-1,-1,1,1)], 'invalid_endpoint')]:
            with self.subTest(reason=reason), patch.object(sim, '_local_obstacle_bboxes', return_value=obstacles):
                for _ in range(2):
                    segments, seconds, distance = sim._local_manoeuvre_segments_to_inventory_space(sim.amrs[0], 'A', bay, 0)
                    self.assertEqual(4, distance)
                    self.assertAlmostEqual(4 / sim.amrs[0].speed_m_per_sec, seconds)
                    self.assertEqual(1, len(segments))
                    self.assertEqual('unverified_direct_fallback', segments[0]['local_manoeuvre_validation'])
                    self.assertIn(reason, segments[0]['local_manoeuvre_failure'])
        self.assertFalse(sim.local_manoeuvre_waypoint_cache)

    def test_false_strings_keep_default_rejection_and_invalid_flags_are_errors(self):
        sim = self.sim('false')
        with patch.object(sim, '_local_obstacle_bboxes', return_value=RING), self.assertRaises(LocalManoeuvreError):
            sim._local_manoeuvre_segments_to_inventory_space(sim.amrs[0], 'A', dict(name='Bay', points=[dict(dx=4,dy=0)]), 0)
        with self.assertRaises(ValueError):
            self.sim('perhaps')

    def test_option_never_suppresses_traffic_failures_or_nonfinite_endpoints(self):
        sim = self.sim()
        bay = dict(name='Bay', points=[dict(dx=4, dy=0)])
        with patch.object(sim, '_local_manoeuvre_waypoints', side_effect=LocalManoeuvreError('traffic_blocked', 'reserved')), \
                self.assertRaisesRegex(LocalManoeuvreError, 'traffic_blocked'):
            sim._local_manoeuvre_segments_to_inventory_space(sim.amrs[0], 'A', bay, 0)
        target = SimpleNamespace(x=float('nan'), y=0)
        with patch.object(sim, '_inventory_space_centre_location', return_value=target), self.assertRaises(LocalManoeuvreError):
            sim._local_manoeuvre_segments_to_inventory_space(sim.amrs[0], 'A', bay, 0)

    def test_settings_roundtrip_and_preflight_warning(self):
        config = reference_config()
        dialog = SimulationSettingsDialog(None, config['simulation'])
        try:
            self.assertFalse(dialog.ignore_invalid_local_manoeuvres_check.isChecked())
            dialog.ignore_invalid_local_manoeuvres_check.setChecked(True)
            dialog.accept()
            config['simulation'] = dialog.result
            self.assertTrue(config['simulation']['ignore_invalid_local_manoeuvres'])
            warnings = [f for f in check_project(config).findings if f.code == 'UNVERIFIED_LOCAL_MOVEMENT']
            self.assertEqual(1, len(warnings))
            self.assertEqual('warning', warnings[0].severity)
        finally:
            dialog.close()

    def test_completed_run_records_unverified_segments_in_event_details(self):
        config = storage_config()
        config['simulation']['ignore_invalid_local_manoeuvres'] = True
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        config['locations'][1]['inventory_spaces'][0]['points'] = [dict(dx=4,dy=0)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            obstacles = [(a+sim.locations['B'].x, b+sim.locations['B'].y,
                          c+sim.locations['B'].x, d+sim.locations['B'].y) for a,b,c,d in RING]
            with patch.object(sim, '_local_obstacle_bboxes', return_value=obstacles):
                sim.run()
        self.assertTrue(sim.completed_task_records)
        self.assertAlmostEqual(11, sim.completed_task_records[0]['duration_sec'])
        rows = [row for row in sim.verbose_rows if row['event_type'] == 'segment_local_manoeuvre']
        self.assertTrue(rows)
        self.assertTrue(any(json.loads(row['details']).get('local_manoeuvre_validation') == 'unverified_direct_fallback' for row in rows))

    def test_departure_preserves_unverified_flag_and_clear_paths_are_not_flagged(self):
        sim = self.sim()
        bay = dict(name='Bay', points=[dict(dx=4,dy=0)])
        sim.inventory_spaces_by_location['A'] = [bay]
        with patch.object(sim, '_local_obstacle_bboxes', return_value=RING):
            segments, _, _ = sim._local_manoeuvre_segments_from_inventory_space(sim.amrs[0], 'A', 'Bay', 0)
        self.assertEqual(4, segments[0]['from_x'])
        self.assertEqual(0, segments[-1]['to_x'])
        self.assertEqual('unverified_direct_fallback', segments[0]['local_manoeuvre_validation'])
        with patch.object(sim, '_local_obstacle_bboxes', return_value=[]):
            segments, _, _ = sim._local_manoeuvre_segments_to_inventory_space(sim.amrs[0], 'A', bay, 0)
        self.assertTrue(all('local_manoeuvre_validation' not in row for row in segments))

    def test_playback_keeps_original_robot_body_without_reference_cross(self):
        from amr_sim_visualiser_pyside6 import SimulationVisualizer
        items = []
        viewer = SimpleNamespace(graphics_scene=QGraphicsScene(),
            _amr_dimensions_for_state=lambda state: (1., .6),
            _amr_heading_radians_for_state=lambda state: 0.,
            world_to_scene=lambda x,y: (x,y),
            _texture_brush=lambda colour, alpha: QBrush(QColor(colour)),
            _active_dynamic_items=lambda: items, draw_line_item=Mock(),
            _amr_reference_position_for_state=Mock(return_value=(0,0)))
        SimulationVisualizer._draw_amr_box_colored_qt(viewer, dict(x=0,y=0))
        self.assertEqual(1, len(items))
        self.assertAlmostEqual(1., items[0].polygon().boundingRect().width())
        viewer.draw_line_item.assert_called_once()
        viewer._amr_reference_position_for_state.assert_not_called()
