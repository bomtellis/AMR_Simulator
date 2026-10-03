"""Lift floor identities must describe the same graph at every entry point."""
import contextlib
import copy
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_delivery_energy_reference import lift_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class LiftStructureTests(unittest.TestCase):
    def test_dialog_rejects_rename_collisions_before_emitting_result(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from PySide6.QtWidgets import QApplication, QWidget, QDialog
        from dialogs import LiftEditorDialog
        app = QApplication.instance() or QApplication([])
        cfg = lift_config()
        cfg['lifts'].append({**copy.deepcopy(cfg['lifts'][0]), 'id': 'Other'})
        parent = QWidget()
        parent.store = JsonStore(cfg)
        before = copy.deepcopy(parent.store.data)
        dialog = LiftEditorDialog(parent, cfg['lifts'][0])
        try:
            dialog.id_edit.setText('Other')
            with patch('dialogs.QMessageBox.warning') as warning:
                dialog.accept()
            warning.assert_called_once()
            self.assertIsNone(dialog.result)
            self.assertEqual(before, parent.store.data)
            dialog.id_edit.setText('L1')
            dialog.accept()
            self.assertEqual('L1', dialog.result['id'])
            self.assertEqual(QDialog.Accepted, QDialog.result(dialog))
        finally:
            dialog.close()
            parent.close()

    def test_graph_identity_findings_become_stale_after_external_point_edits(self):
        cfg = lift_config()
        cfg['corridors']['nodes'].append(dict(name='L1-F0', floor=0, x=1, y=0))
        report = check_project(cfg)
        finding = next(f for f in report.findings if f.path == '/lifts/0/id')
        changed = copy.deepcopy(cfg)
        changed['corridors']['nodes'].clear()
        self.assertEqual(['corridors'], report.changed_inputs(finding, changed))

    def assert_rejected(self, cfg, path):
        before = copy.deepcopy(cfg)
        for consumer in (Simulation, JsonStore):
            with self.subTest(consumer=consumer.__name__), self.assertRaises(ValueError):
                consumer(cfg)
        report = check_project(cfg)
        self.assertTrue(any(f.path == path and f.severity == 'error' for f in report.findings), path)
        self.assertFalse(report.can_run(cfg))
        self.assertEqual(before, cfg)

    def test_served_floors_are_nonempty_unique_json_integers(self):
        for value in ([], '0,1', None, [0, 0, 1], [False, 1], ['0', 1], [0, 1.0], [0, 1.5]):
            with self.subTest(value=value):
                cfg = lift_config()
                cfg['lifts'][0]['served_floors'] = value
                self.assert_rejected(cfg, '/lifts/0/served_floors')

    def test_start_floor_is_an_integer_served_floor_including_default(self):
        for value in (True, '0', .5, 1.0, 2):
            with self.subTest(value=value):
                cfg = lift_config()
                cfg['lifts'][0]['start_floor'] = value
                self.assert_rejected(cfg, '/lifts/0/start_floor')
        cfg = lift_config()
        cfg['lifts'][0].update(served_floors=[1], floor_locations={'1': {'x': 1, 'y': 0}})
        self.assert_rejected(cfg, '/lifts/0/start_floor')

    def test_coordinate_keys_cannot_alias_or_truncate_floor_identity(self):
        for key in ('01', '+1', '1.0', '-0', 'bad', 'true'):
            with self.subTest(key=key):
                cfg = lift_config()
                cfg['lifts'][0]['floor_locations'][key] = {'x': 1, 'y': 0}
                self.assert_rejected(cfg, '/lifts/0/floor_locations')

    def test_missing_and_extra_positions_cannot_create_phantom_connections(self):
        for extra in (False, True):
            cfg = lift_config()
            if extra:
                cfg['lifts'][0]['floor_locations']['2'] = {'x': 1, 'y': 0}
            else:
                del cfg['lifts'][0]['floor_locations']['1']
            self.assert_rejected(cfg, '/lifts/0/floor_locations')

    def test_coordinates_are_complete_finite_and_not_boolean(self):
        for position in (None, [], [1, 0], {}, {'x': 1}, {'x': True, 'y': 0},
                         {'x': 'nan', 'y': 0}, {'x': 1, 'y': 'inf'}):
            with self.subTest(position=position):
                cfg = lift_config()
                cfg['lifts'][0]['floor_locations']['0'] = position
                self.assert_rejected(cfg, '/lifts/0/floor_locations/0')

    def test_lift_ids_are_unique_nonblank_strings(self):
        for identity in ('', ' ', ' L1', 1, None):
            cfg = lift_config()
            cfg['lifts'][0]['id'] = identity
            self.assert_rejected(cfg, '/lifts/0/id')
        cfg = lift_config()
        cfg['lifts'].append(copy.deepcopy(cfg['lifts'][0]))
        self.assert_rejected(cfg, '/lifts/1/id')

    def test_lift_stops_cannot_overwrite_existing_graph_points(self):
        for section in ('locations', 'corridors'):
            cfg = lift_config()
            rows = cfg['locations'] if section == 'locations' else cfg['corridors']['nodes']
            rows.append(dict(name='L1-F0', floor=0, x=99, y=99))
            self.assert_rejected(cfg, '/lifts/0/id')

    def test_incomplete_drafts_open_but_preflight_and_simulation_block(self):
        for key in ('id', 'served_floors', 'floor_locations'):
            cfg = lift_config()
            del cfg['lifts'][0][key]
            self.assertNotIn(key, JsonStore(cfg).data['lifts'][0])
            with self.assertRaisesRegex(ValueError, key):
                Simulation(cfg)
            report = check_project(cfg)
            self.assertTrue(any(f.path == f'/lifts/0/{key}' and f.severity == 'error' for f in report.findings))

    def test_negative_floors_and_numeric_coordinate_strings_keep_graph_and_timing(self):
        cfg = lift_config()
        cfg['locations'][0]['floor'] = -2
        cfg['locations'][1]['floor'] = -1
        cfg['lifts'][0].update(served_floors=[-2, -1], start_floor=-1,
            floor_locations={'-2': {'x': '1', 'y': '0'}, '-1': {'x': '1', 'y': '0'}})
        for edge in cfg['corridors']['edges']:
            for key in ('from', 'to'):
                edge[key] = edge[key].replace('L1-F0', 'L1-F-2').replace('L1-F1', 'L1-F-1')
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertEqual({'A', 'B', 'L1-F-2', 'L1-F-1'}, set(sim.graph_nodes))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            # Original 10 s service plus one floor of empty reposition at 1 floor/s.
            self.assertEqual(11, sim.amrs[0].available_time)
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertFalse(any(f.severity == 'error' for f in check_project(data).findings))

    def test_invalid_editor_floor_change_is_atomic(self):
        store = JsonStore(lift_config())
        before = copy.deepcopy(store.data)
        for floors, positions, start in [([0, 0], {0: (1, 0)}, 0),
            ([0, 1], {0: (1, 0)}, 0), ([0], {0: (1, 0)}, 1),
            ([0], {0: (float('nan'), 0)}, 0)]:
            with self.assertRaises(ValueError):
                store.upsert_lift('L1', floors, positions, start_floor=start)
            self.assertEqual(before, store.data)


if __name__ == '__main__':
    unittest.main()
