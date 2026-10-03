"""Department service/zone aliases must have the same routing meaning everywhere."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class DepartmentLocationContractTests(unittest.TestCase):
    def config(self, entry):
        cfg = grouped_config()
        cfg['locations'].extend([dict(name='Ward Bay', floor=0, x=12, y=16),
                                 dict(name='Zone X', floor=0, x=9, y=12)])
        cfg['corridors']['edges'].extend([{'from': 'B', 'to': 'Zone X', 'width_m': 3},
                                          {'from': 'Zone X', 'to': 'Ward Bay', 'width_m': 3}])
        cfg['departments'][0]['task_generation_locations'] = {'stores': entry}
        return cfg

    def generated(self, cfg):
        records = Simulation(cfg).task_generation_manager.update_until(61)
        self.assertEqual(1, len(records))
        return records[0].task

    def test_service_alias_shorthand_and_scalar_select_one_whole_destination(self):
        for entry in (dict(pickup_dropoff_locations=['Ward Bay']), dict(pickup_dropoff_locations='Ward Bay'),
                      dict(locations=['Ward Bay']), dict(locations='Ward Bay'), ['Ward Bay'], 'Ward Bay'):
            cfg = self.config(entry)
            for data in (cfg, JsonStore(cfg).data):
                with self.subTest(entry=entry):
                    self.assertEqual('Ward Bay', self.generated(data).dropoff)

    def test_zone_alias_string_has_same_handoff_before_and_after_import(self):
        for key in ('dropoff_zone_locations', 'drop_off_zone_locations'):
            cfg = self.config(dict(locations='Ward Bay', **{key: 'Zone X'}))
            for data in (cfg, JsonStore(cfg).data):
                task = self.generated(data)
                self.assertEqual(('Zone X', 'Ward Bay'), (task.dropoff_zone, task.final_destination))
                self.assertEqual('Zone X', task.dropoff)
                self.assertTrue(task.requires_staff)

    def test_empty_modern_values_shadow_legacy_without_disabling_category(self):
        cfg = self.config(dict(pickup_dropoff_locations=[], locations=['Ward Bay'],
                               dropoff_zone_locations=[], drop_off_zone_locations=['Zone X']))
        for data in (cfg, JsonStore(cfg).data):
            task = self.generated(data)
            self.assertEqual('B', task.dropoff)  # Empty service assignment retains category routing.
            self.assertEqual('', task.dropoff_zone)

    def test_report_catalog_agrees_on_legacy_service_and_zone_names(self):
        from report.amr_report_analysis import load_location_catalog, load_task_generation_report_metadata
        cfg = self.config(dict(locations='Ward Bay', drop_off_zone_locations='Zone X'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project.json'
            path.write_text(json.dumps(cfg), encoding='utf-8')
            catalog = load_location_catalog(path).set_index('location')
            metadata = load_task_generation_report_metadata(path)
        self.assertEqual('Department', catalog.loc['Ward Bay', 'department'])
        self.assertTrue(catalog.loc['Zone X', 'is_dropoff_zone'])
        self.assertEqual('Department (Stores)', metadata['location_display_names']['Ward Bay'])

    def test_rename_updates_scalar_and_shorthand_references(self):
        for entry in ('Ward Bay', ['Ward Bay'], dict(locations='Ward Bay'),
                      dict(pickup_dropoff_locations='Ward Bay', dropoff_zone_locations='Zone X')):
            store = JsonStore(self.config(entry))
            store.rename_point('Ward Bay', 'Renamed')
            task = self.generated(store.data)
            self.assertEqual('Renamed', task.final_destination or task.dropoff)

    def test_deletion_does_not_promote_shadowed_legacy_destination(self):
        store = JsonStore(self.config(dict(pickup_dropoff_locations=['Zone X'], locations=['Ward Bay'], note='retain')))
        store.remove_location_references('Zone X')
        entry = store.data['departments'][0]['task_generation_locations']['stores']
        self.assertEqual([], entry['pickup_dropoff_locations'])
        self.assertEqual(['Ward Bay'], entry['locations'])
        self.assertEqual('retain', entry['note'])
        self.assertEqual('B', self.generated(store.data).dropoff)

    def test_invalid_assignment_shapes_reject_before_mutation(self):
        for entry in (None, 1, [True], dict(locations=[5]), dict(pickup_dropoff_locations=None),
                      dict(dropoff_zone_locations={'name': 'Zone X'})):
            cfg = self.config(entry)
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(entry=entry), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)
            self.assertTrue(any(f.severity == 'error' and '/task_generation_locations/' in f.path
                                for f in check_project(cfg).findings))

    def test_unknown_effective_location_is_visible_but_shadowed_alias_is_not(self):
        cfg = self.config(dict(pickup_dropoff_locations=['Missing'], locations=['Ward Bay']))
        findings = [f for f in check_project(cfg).findings if f.code == 'DEPARTMENT_LOCATION_REFERENCE']
        self.assertTrue(any('Missing' in f.message for f in findings))
        cfg = self.config(dict(pickup_dropoff_locations=['Ward Bay'], locations=['Missing']))
        self.assertFalse(any(f.code == 'DEPARTMENT_LOCATION_REFERENCE' for f in check_project(cfg).findings))

    def test_literal_commas_and_duplicate_names_do_not_change_destination(self):
        cfg = self.config(dict(locations=[' Ward, Bay ', 'Ward, Bay', '']))
        cfg['locations'][2]['name'] = 'Ward, Bay'
        cfg['corridors']['edges'][-1]['to'] = 'Ward, Bay'
        for data in (cfg, JsonStore(cfg).data):
            self.assertEqual('Ward, Bay', self.generated(data).dropoff)

    def test_generated_locations_are_validated_and_committed_atomically(self):
        for invalid in ({'floor': 1.5}, {'x': float('nan')}, {'y': True},
                        {'name': 'A'}, {'name': 'Department'}, {'name': ''}):
            store = JsonStore(self.config({}))
            before = copy.deepcopy(store.data)
            row = copy.deepcopy(before['departments'][0])
            row['_create_locations'] = [dict(name='New', x=1.23456789, y=2, floor=0),
                                        dict(name='Other', x=1, y=2, floor=0)]
            row['_create_locations'][1].update(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                store.replace_departments([row])
            self.assertEqual(before, store.data)
        row['_create_locations'] = [dict(name='New', x=1.23456789, y=2, floor=0)]
        store.replace_departments([row])
        self.assertNotIn('_create_locations', store.data['departments'][0])
        new = next(loc for loc in store.data['locations'] if loc['name'] == 'New')
        self.assertEqual((1.23456789, 2, 0), (new['x'], new['y'], new['floor']))

    def test_malformed_or_duplicate_provisional_locations_cannot_partially_save(self):
        for pending in (None, {}, [None], [dict(name='New'), dict(name='New')]):
            store = JsonStore(self.config({}))
            before = copy.deepcopy(store.data)
            row = dict(before['departments'][0], _create_locations=pending)
            with self.subTest(pending=pending), self.assertRaises(ValueError):
                store.upsert_department(row, previous_id='D')
            self.assertEqual(before, store.data)


class DepartmentLocationEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def editor_dialog(self, parent=None, entry=None):
        from visualiser.dialogs import DepartmentEditorDialog
        seed = copy.deepcopy(grouped_config()['departments'][0])
        seed['task_generation_locations'] = {'stores': entry if entry is not None else {'locations': 'B', 'note': 'retain'},
                                             'unlisted': {'locations': ['A'], 'custom': 42}}
        return DepartmentEditorDialog(parent, ['A', 'B'], [], seed=seed,
                                      task_generation_categories=[('stores', 'Stores', '-STORES')])

    def test_accept_preserves_metadata_and_explicit_removal(self):
        from visualiser.dialogs import DepartmentListDialog, QMessageBox
        dialog = self.editor_dialog()
        self.assertEqual(['B'], dialog.category_location_selections['stores'])
        dialog.category_location_selections['stores'] = []
        with patch.object(QMessageBox, 'critical') as critical:
            dialog.accept()
        self.assertFalse(critical.called, critical.call_args)
        listing = DepartmentListDialog(None, [dialog.seed], ['A', 'B'], [], 0, Mock(), lambda: 'E')
        row = listing._commit_department_editor_result(dialog.result)
        self.assertEqual([], row['task_generation_locations']['stores']['pickup_dropoff_locations'])
        self.assertEqual('B', row['task_generation_locations']['stores']['locations'])
        self.assertEqual('retain', row['task_generation_locations']['stores']['note'])
        self.assertEqual(dialog.seed['task_generation_locations']['unlisted'], row['task_generation_locations']['unlisted'])

    def test_legacy_waste_fields_are_not_silently_migrated_by_dialog(self):
        from visualiser.dialogs import DepartmentEditorDialog
        seed = copy.deepcopy(grouped_config()['departments'][0])
        seed.update(waste_pickup_locations=['A'], waste_dropoff_locations=['B'])
        dialog = DepartmentEditorDialog(None, ['A', 'B'], [], seed=seed,
                                       task_generation_categories=[('waste', 'Waste', '-WASTE')])
        self.assertEqual([], dialog.category_location_selections.get('waste', []))
        dialog.accept()
        self.assertEqual(['A'], dialog.result['waste_pickup_locations'])

    def test_zone_placement_and_child_ok_remain_provisional_until_list_save(self):
        from visualiser.dialogs import DepartmentListDialog, QMessageBox
        store = JsonStore(grouped_config())
        before = copy.deepcopy(store.data)
        save = Mock(side_effect=lambda rows: store.replace_departments(rows))
        listing = DepartmentListDialog(None, before['departments'], ['A', 'B'], [], 0, save, lambda: 'E')
        child = self.editor_dialog(listing)
        child.pending_dropoff_zone_creation = {'category_keys': ['stores']}
        child._finish_dropoff_zone_placement('dropoff_zone', dict(name='New Zone', x=3, y=4, floor=0))
        self.assertEqual(before['departments'], listing.items)
        child.accept()
        listing.items[0] = listing._commit_department_editor_result(child.result)
        listing.reject()
        self.assertFalse(save.called)
        self.assertEqual(before, store.data)
        # Failed Save must retain the placement for correction/retry.
        pending = listing.items[0]['_create_locations']
        pending[0]['floor'] = 1.5
        with patch.object(QMessageBox, 'critical') as critical:
            listing.save_items()
        self.assertTrue(critical.called)
        self.assertEqual(before, store.data)
        self.assertEqual(1, len(listing.items[0]['_create_locations']))
        pending[0]['floor'] = 0
        listing.save_items()
        self.assertIn('New Zone', [loc['name'] for loc in store.data['locations']])
        self.assertEqual(['New Zone'], store.data['departments'][0]['task_generation_locations']['stores']['dropoff_zone_locations'])

    def test_placement_cancel_is_nonmutating_and_save_is_one_undo(self):
        from tests import test_corridor_editing as editing
        from visualiser.dialogs import DepartmentListDialog
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
                listing = DepartmentListDialog(editor, before['departments'], ['A', 'B'], [], 0,
                                               editor._save_departments, lambda: 'E')
                child = self.editor_dialog(listing)
                editor.start_department_location_placement('New Bay', 'stores', child._finish_category_location_placement, child)
                editor.finish_department_location_placement(1.23456789, 2, 0)
                self.assertEqual(before, editor.store.data)
                self.assertEqual(before['departments'], listing.items)
                child.reject()
                self.assertEqual(before, editor.store.data)
                self.assertFalse(editor.undo_edit())
                # A second accepted placement stays pending through child OK and reopen.
                child = self.editor_dialog(listing)
                editor.start_department_location_placement('New Bay', 'stores', child._finish_category_location_placement, child)
                editor.finish_department_location_placement(1.23456789, 2, 0)
                child.accept()
                listing.items[0] = listing._commit_department_editor_result(child.result)
                self.assertEqual(before, editor.store.data)
                from visualiser.dialogs import DepartmentEditorDialog
                reopened = DepartmentEditorDialog(listing, listing.location_names, [], seed=listing.items[0],
                                                 task_generation_categories=[('stores', 'Stores', '-STORES')])
                reopened.accept()
                listing.items[0] = listing._commit_department_editor_result(reopened.result)
                listing.save_items()
                after = copy.deepcopy(editor.store.data)
                self.assertIn('New Bay', [loc['name'] for loc in after['locations']])
                self.assertNotIn('_create_locations', after['departments'][0])
                self.assertTrue(editor.undo_edit())
                self.assertEqual(before, editor.store.data)
                self.assertFalse(editor.undo_edit())
                self.assertTrue(editor.redo_edit())
                self.assertEqual(after, editor.store.data)
            finally:
                with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                    editor.close()
