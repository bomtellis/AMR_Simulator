"""Independent coordinate, area, persistence and model-scope references."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class LocationOutlineTests(unittest.TestCase):
    def config(self):
        cfg = reference_config()
        cfg['locations'][0].update(x=100, y=200, bounding_box=[
            {'dx': 0, 'dy': 0}, {'x': 104, 'y': 200}, {'dx': 0, 'dy': 3}])
        return cfg

    def test_mixed_coordinates_editor_and_report_use_same_triangle(self):
        from report.amr_report_analysis import load_location_catalog
        cfg = self.config()
        store = JsonStore(cfg)
        self.assertEqual([{'x': 100., 'y': 200.}, {'x': 104., 'y': 200.},
                          {'x': 100., 'y': 203.}], store.get_location_bounding_box_points('A'))
        self.assertEqual(dict(length=4., width=3., area=6.), store.location_bounding_box_metrics('A'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'layout.json'
            path.write_text(json.dumps(cfg), encoding='utf-8')
            row = load_location_catalog(path).set_index('location').loc['A']
        self.assertEqual((4, 3, 6), (row.length_m, row.width_m, row.area_m2))

    def test_edit_and_save_preserve_submillimetre_coordinates(self):
        store = JsonStore(self.config())
        points = [{'x': 100.0000123, 'y': 200.0000456},
                  {'x': 104.1234567, 'y': 200.0000456}, {'x': 100.0000123, 'y': 203.7654321}]
        store.set_location_bounding_box('A', points)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'layout.json'
            store.save(str(path))
            loaded = JsonStore.from_file(str(path))
        self.assertEqual(points, loaded.get_location_bounding_box_points('A'))
        self.assertEqual(store.get_location('A')['bounding_box'], loaded.get_location('A')['bounding_box'])

    def test_large_origin_area_is_translation_invariant(self):
        cfg = self.config()
        cfg['locations'][0].update(x=1e12, y=-1e12, bounding_box=[
            {'dx': 0, 'dy': 0}, {'dx': 4, 'dy': 0}, {'dx': 0, 'dy': 3}])
        self.assertEqual(dict(length=4., width=3., area=6.), JsonStore(cfg).location_bounding_box_metrics('A'))

    def test_invalid_outlines_block_consumers_without_mutation(self):
        values = [None, {}, 'box', [None], [{'x': 0}], [{'dx': 1, 'y': 2}],
                  [{'dx': True, 'dy': 0}], [{'x': 'nan', 'y': 0}],
                  [{'dx': 1e308, 'dy': 0}, {'dx': -1e308, 'dy': 1}, {'dx': 0, 'dy': 2}]]
        for value in values:
            cfg = self.config()
            cfg['locations'][0]['bounding_box'] = value
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)
            self.assertTrue(any(f.severity == 'error' and '/bounding_box' in f.path
                                for f in check_project(cfg).findings))

    def test_failed_outline_edit_is_atomic(self):
        store = JsonStore(self.config())
        before = copy.deepcopy(store.data)
        for points in ([{'x': 1, 'y': float('inf')}], [{'x': True, 'y': 0}], None):
            with self.subTest(points=points), self.assertRaises(ValueError):
                store.set_location_bounding_box('A', points)
            self.assertEqual(before, store.data)

    def test_local_pair_precedence_and_location_move(self):
        cfg = self.config()
        cfg['locations'][0]['bounding_box'][0].update(x=999, y=999)
        store = JsonStore(cfg)
        store.set_point_position('A', 110, 220)
        self.assertEqual([{'x': 110., 'y': 220.}, {'x': 104., 'y': 200.},
                          {'x': 110., 'y': 223.}], store.get_location_bounding_box_points('A'))

    def test_compressed_project_preserves_representations_and_point_metadata(self):
        from amr_project import Project
        cfg = self.config()
        cfg['locations'][0]['bounding_box'][0].update(dx='0.000123456789', label='Corner')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'outline.amrproj'
            Project().save(path, cfg, base_dir=directory)
            loaded = Project.open(path).materialize(Path(directory) / 'cache')
        self.assertEqual(cfg['locations'], loaded['locations'])
        store = JsonStore(loaded)
        store.set_location_bounding_box('A', cfg['locations'][0]['bounding_box'])
        self.assertEqual('Corner', store.get_location('A')['bounding_box'][0]['label'])
        self.assertEqual('0.000123456789', store.get_location('A')['bounding_box'][0]['dx'])

    def test_missing_short_and_reversed_outlines_have_defined_metrics(self):
        store = JsonStore(self.config())
        self.assertEqual(dict(length=0., width=0., area=0.), store.location_bounding_box_metrics('B'))
        store.set_location_bounding_box('A', [{'dx': 0, 'dy': 0}, {'dx': 4, 'dy': 3}])
        self.assertEqual(dict(length=0., width=0., area=0.), store.location_bounding_box_metrics('A'))
        store.set_location_bounding_box('A', [{'dx': 0, 'dy': 3}, {'dx': 4, 'dy': 0}, {'dx': 0, 'dy': 0}])
        self.assertEqual(dict(length=4., width=3., area=6.), store.location_bounding_box_metrics('A'))
        store.remove_location_bounding_box('A')
        self.assertEqual([], store.get_location_bounding_box_points('A'))

    def test_report_standalone_import_resolves_shared_outline_contract(self):
        import subprocess
        import sys
        report = Path(__file__).resolve().parents[1] / 'report'
        code = (f'import sys; sys.path.insert(0, {str(report)!r}); '
                'from amr_report_analysis import load_location_catalog; '
                'load_location_catalog(sys.argv[1])')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'layout.json'
            path.write_text(json.dumps(self.config()), encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', '-c', code, str(path)],
                                    cwd=directory, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_scope_is_explicit_and_outline_does_not_change_task(self):
        cfg = reference_config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        for outline in ([], [{'dx': 100, 'dy': 100}],
                        [{'dx': 0, 'dy': 0}, {'dx': .01, 'dy': 0}, {'dx': 0, 'dy': .01}]):
            cfg['locations'][0]['bounding_box'] = outline
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(cfg)
                sim.run()
            self.assertEqual(9, sim.completed_task_records[0]['duration_sec'])
            findings = [f for f in check_project(cfg).findings if f.code == 'LOCATION_OUTLINE_SCOPE']
            self.assertEqual(bool(outline), bool(findings))
            if findings:
                self.assertEqual('info', findings[0].severity)

    def test_playback_selection_does_not_offset_absolute_points_twice(self):
        from visualiser.amr_sim_visualiser_pyside6 import SimulationVisualizer
        class Selection:
            _point_in_world_rect = staticmethod(SimulationVisualizer._point_in_world_rect)
            _world_bbox_intersects_rect = staticmethod(SimulationVisualizer._world_bbox_intersects_rect)
        location = dict(x=100, y=200, bounding_box=[{'x': 104, 'y': 200}, {'x': 100, 'y': 203}])
        self.assertFalse(SimulationVisualizer._location_intersects_visible_world(Selection(), location, (150, 300, 160, 310)))
        self.assertTrue(SimulationVisualizer._location_intersects_visible_world(Selection(), location, (103, 200, 104, 201)))


class LocationOutlineUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def test_completed_boundary_is_one_undo_and_cancel_preserves_it(self):
        from tests import test_corridor_editing as editing
        with tempfile.TemporaryDirectory() as directory:
            editor = editing.AMRGraphEditor()
            editor._recovery_store = editing.RecoveryStore(Path(directory) / 'recovery')
            editor._drawings_enabled = False
            try:
                editor.store = JsonStore(reference_config())
                editor.refresh_canvas()
                editor._saved_state = editor._configuration_state()
                editor._reset_edit_history()
                before = copy.deepcopy(editor.store.data)
                points = [{'x': .000123456, 'y': 0}, {'x': 4, 'y': 0}, {'x': 0, 'y': 3}]
                editor.start_location_bounding_box_draw('A')
                editor.bounding_box_points = points
                editor.finish_location_bounding_box_draw()
                after = copy.deepcopy(editor.store.data)
                self.assertEqual(points, editor.store.get_location_bounding_box_points('A'))
                self.assertEqual(2, len(editor.edit_history.entries))
                self.assertTrue(editor.undo_edit())
                self.assertEqual(before, editor.store.data)
                self.assertTrue(editor.redo_edit())
                self.assertEqual(after, editor.store.data)
                editor.start_location_bounding_box_draw('A', keep_existing=True)
                editor.bounding_box_points[0] = dict(x=99, y=99)
                editor.cancel_location_bounding_box_draw()
                self.assertEqual(after, editor.store.data)
                self.assertEqual(2, len(editor.edit_history.entries))
            finally:
                with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                    editor.close()
