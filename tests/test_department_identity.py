"""Department replacement must preserve demand and reject ambiguous identities."""
import copy
import unittest
from unittest.mock import Mock, patch

from simulator import Simulation
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from tests.test_generation_reference import grouped_config


class DepartmentIdentityTests(unittest.TestCase):
    def test_rename_remaps_group_override_and_task_without_duplicating_demand(self):
        cfg = grouped_config()
        cfg['task_generation']['categories']['stores']['departments'] = {'D': {'priority': 22}}
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', department_id='D')]
        store = JsonStore(cfg)
        changed = copy.deepcopy(store.data['departments'][0])
        changed.update(id='New', name='Renamed')
        store.upsert_department(changed, previous_id='D')
        self.assertEqual(1, len(store.data['departments']))
        category = store.data['task_generation']['categories']['stores']
        self.assertEqual(['New'], category['department_groups'][0]['departments'])
        self.assertEqual({'New': {'priority': 22}}, category['departments'])
        self.assertEqual('New', store.data['tasks'][0]['department_id'])
        records = Simulation(store.data).task_generation_manager.update_until(61)
        self.assertEqual([(60, 'New', 7)], [(r.task.release_time, r.task.department_id, r.task.priority) for r in records])

    def test_rename_collision_and_deleted_reference_are_atomic(self):
        store = JsonStore(grouped_config())
        store.data['task_generation']['categories']['stores']['departments'] = {'New': {'priority': 2}, 'D': {}}
        before = copy.deepcopy(store.data)
        changed = dict(store.data['departments'][0], id='New')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            store.upsert_department(changed, previous_id='D')
        self.assertEqual(before, store.data)
        with self.assertRaisesRegex(ValueError, 'referenced'):
            store.delete_department('D')
        self.assertEqual(before, store.data)

    def test_unreferenced_delete_preserves_locations_and_other_project_data(self):
        cfg = grouped_config()
        cfg['task_generation']['categories'] = {}
        store = JsonStore(cfg)
        before = copy.deepcopy(store.data)
        store.delete_department('D')
        before['departments'] = []
        self.assertEqual(before, store.data)

    def test_duplicate_ids_names_and_effective_fallback_reject_raw_and_editor(self):
        for second in (dict(id='D', name='Other'), dict(id='E', name='Department'), dict(name='D')):
            cfg = grouped_config()
            cfg['departments'].append(second)
            for consumer in (JsonStore, Simulation):
                with self.subTest(second=second), self.assertRaises(ValueError):
                    consumer(cfg)

    def test_malformed_identity_and_position_values_reject_without_mutation(self):
        for key, values in {'id': [True, 3, ' D '], 'name': [None, ' Name '],
            'x': [True, 'nan'], 'y': [float('inf'), None], 'floor': [1.5, True, '1.5']}.items():
            for value in values:
                cfg = grouped_config()
                cfg['departments'][0][key] = value
                before = copy.deepcopy(cfg)
                for consumer in (JsonStore, Simulation):
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertEqual(before, cfg)
                self.assertTrue(any(f.path == f'/departments/0/{key}' and f.severity == 'error'
                                    for f in check_project(cfg).findings))

    def test_department_movement_keeps_precision_and_is_atomic(self):
        store = JsonStore(grouped_config())
        store.set_point_position('Department', 1.23456789, -2.3456789)
        self.assertEqual((1.23456789, -2.3456789), tuple(store.data['departments'][0][key] for key in ('x', 'y')))
        before = copy.deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.set_point_position('Department', float('nan'), 0)
        self.assertEqual(before, store.data)

    def test_missing_original_cannot_create_a_duplicate(self):
        store = JsonStore(grouped_config())
        before = copy.deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.upsert_department(dict(id='E', name='Other'), previous_id='Missing')
        self.assertEqual(before, store.data)

    def test_name_fallback_generates_legacy_waste_instead_of_silently_skipping(self):
        from tests.test_waste_conservation import legacy_config
        cfg = legacy_config()
        del cfg['departments'][0]['id']
        for data in (cfg, JsonStore(cfg).data):
            records = Simulation(data).task_generation_manager.update_until(90000)
            self.assertEqual(3, len(records))
            self.assertTrue(all(r.task.department_id == 'Department' for r in records))

    def test_unknown_assignment_is_explicit_and_malformed_members_reject(self):
        cfg = grouped_config()
        cfg['task_generation']['categories']['stores']['department_groups'][0]['departments'] = ['Future']
        self.assertTrue(any(f.code == 'DEPARTMENT_REFERENCE' and f.severity == 'warning'
                            for f in check_project(cfg).findings))
        for members in ('D', ['D', 'D'], [True], [' D ']):
            cfg['task_generation']['categories']['stores']['department_groups'][0]['departments'] = members
            for consumer in (JsonStore, Simulation):
                with self.subTest(members=members), self.assertRaises(ValueError):
                    consumer(cfg)

    def test_department_name_cannot_hide_graph_point(self):
        cfg = grouped_config()
        cfg['departments'][0].update(name='A', x=999, y=999)
        store = JsonStore(cfg)
        self.assertEqual('location', store.all_points()['A']['kind'])
        self.assertEqual(0, store.all_points()['A']['x'])
        self.assertTrue(any(f.code == 'DEPARTMENT_NAME_COLLISION' and f.severity == 'error'
                            for f in check_project(cfg).findings))

    def test_blank_id_falls_back_consistently_in_checks_and_generation(self):
        cfg = grouped_config()
        cfg['departments'][0]['id'] = ''
        cfg['task_generation']['categories']['stores']['department_groups'][0]['departments'] = ['Department']
        self.assertFalse(any(f.code == 'IDENTIFIER' and f.path.startswith('/departments') for f in check_project(cfg).findings))
        records = Simulation(cfg).task_generation_manager.update_until(61)
        self.assertEqual(['Department'], [r.task.department_id for r in records])

    def test_unidentified_department_is_editable_but_not_runnable(self):
        cfg = grouped_config()
        cfg['departments'][0].pop('id')
        cfg['departments'][0].pop('name')
        JsonStore(cfg)
        with self.assertRaisesRegex(ValueError, 'requires a nonblank'):
            Simulation(cfg)
        self.assertTrue(any(f.severity == 'error' and f.path.startswith('/departments')
                            for f in check_project(cfg).findings))


class DepartmentIdentityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def test_list_cancellation_keeps_nested_project_data(self):
        from visualiser.dialogs import DepartmentListDialog
        rows = grouped_config()['departments']
        rows[0]['task_generation_locations'] = {'stores': {'pickup_dropoff_locations': ['B']}}
        before = copy.deepcopy(rows)
        save = Mock()
        dialog = DepartmentListDialog(None, rows, ['A', 'B'], [], 0, save, lambda: 'E')
        dialog.items[0]['task_generation_locations']['stores']['pickup_dropoff_locations'].append('A')
        dialog.reject()
        self.assertEqual(before, rows)
        self.assertFalse(save.called)

    def test_list_tracks_two_id_edits_back_to_original(self):
        from visualiser import dialogs
        store = JsonStore(grouped_config())
        dialog = dialogs.DepartmentListDialog(None, store.data['departments'], ['A', 'B'], [], 0,
            lambda items, **kwargs: store.replace_departments(items, **kwargs), lambda: 'E')
        with patch.object(dialog, '_selected_department_indexes', return_value=[0]):
            for new_id in ('E', 'F'):
                result = dict(dialog.items[0], id=new_id)
                child = Mock(result=result)
                child.exec.return_value = dialogs.QDialog.Accepted
                with patch.object(dialogs, 'DepartmentEditorDialog', return_value=child):
                    dialog.edit_item()
        self.assertEqual({'D': 'F'}, dialog.department_id_changes)
        dialog.save_items()
        self.assertEqual(['F'], store.data['task_generation']['categories']['stores']['department_groups'][0]['departments'])

    def test_canvas_rename_is_one_undo_and_does_not_rename_graph_nodes(self):
        import tempfile
        from pathlib import Path
        from tests import test_corridor_editing as editing
        import app as app_module
        with tempfile.TemporaryDirectory() as directory:
            editor = editing.AMRGraphEditor()
            editor._recovery_store = editing.RecoveryStore(Path(directory) / 'recovery')
            editor._drawings_enabled = False
            try:
                editor.store = editing.JsonStore(grouped_config())
                editor.refresh_canvas()
                editor._saved_state = editor._configuration_state()
                editor._reset_edit_history()
                before = copy.deepcopy(editor.store.data)
                result = dict(before['departments'][0], id='New', name='Renamed')
                child = Mock(result=result)
                child.exec.return_value = app_module.QDialog.Accepted
                with patch.object(app_module, 'DepartmentEditorDialog', return_value=child):
                    editor.edit_department_by_name('Department')
                after = copy.deepcopy(editor.store.data)
                self.assertEqual(['New'], [row['id'] for row in after['departments']])
                self.assertEqual(before['locations'], after['locations'])
                self.assertEqual(before['corridors'], after['corridors'])
                self.assertTrue(editor.undo_edit())
                self.assertEqual(before, editor.store.data)
                self.assertTrue(editor.redo_edit())
                self.assertEqual(after, editor.store.data)
            finally:
                with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                    editor.close()
