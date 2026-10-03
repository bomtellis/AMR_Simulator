"""Department drafts cannot orphan shared pending points or overwrite newer work."""
import copy
import unittest
from unittest.mock import Mock, patch

from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore


class DepartmentDraftTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def listing(self, rows, parent=None, save=None):
        from visualiser.dialogs import DepartmentListDialog
        return DepartmentListDialog(parent, rows, ['A', 'B'], [], 0, save or Mock(), lambda: 'E',
                                    task_generation_categories=[('stores', 'Stores', '-STORES')])

    def drafts(self, shared=True):
        owner = dict(id='New', name='New department', _create_locations=[dict(name='Shared Bay', x=1.25, y=2.5, floor=0)])
        other = copy.deepcopy(grouped_config()['departments'][0])
        other['task_generation_locations'] = {'stores': {'dropoff_zone_locations': ['Shared Bay'] if shared else [],
                                                        'pickup_dropoff_locations': ['B']}}
        return [owner, other]

    def delete_first(self, listing):
        from visualiser.dialogs import QMessageBox
        with patch.object(listing, '_selected_department_indexes', return_value=[0]), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            listing.delete_item()

    def test_shared_pending_zone_survives_deleting_its_draft_owner(self):
        store = JsonStore(grouped_config())
        listing = self.listing(self.drafts(), save=store.replace_departments)
        self.delete_first(listing)
        listing.save_items()
        self.assertEqual(['D'], [row['id'] for row in store.data['departments']])
        self.assertEqual(1, sum(loc['name'] == 'Shared Bay' for loc in store.data['locations']))
        bay = next(loc for loc in store.data['locations'] if loc['name'] == 'Shared Bay')
        self.assertEqual((1.25, 2.5), (bay['x'], bay['y']))
        self.assertNotIn('_create_locations', store.data['departments'][0])

    def test_unshared_pending_point_is_discarded_with_its_owner(self):
        rows = self.drafts(shared=False)
        listing = self.listing(rows)
        self.assertIn('Shared Bay', listing.location_names)
        self.delete_first(listing)
        self.assertNotIn('Shared Bay', listing.location_names)
        self.assertFalse(any(row.get('_create_locations') for row in listing.items))
        self.assertEqual(rows[0]['_create_locations'][0]['name'], 'Shared Bay')

    def test_shadowed_alias_does_not_keep_a_deleted_pending_point_alive(self):
        rows = self.drafts(shared=False)
        rows[1]['task_generation_locations']['stores']['drop_off_zone_locations'] = ['Shared Bay']
        listing = self.listing(rows)
        self.delete_first(listing)
        self.assertNotIn('Shared Bay', listing.location_names)
        self.assertFalse(any(row.get('_create_locations') for row in listing.items))

    def test_two_surviving_departments_share_one_creation(self):
        rows = self.drafts()
        rows.append(dict(rows[1], id='E', name='Other'))
        listing = self.listing(rows)
        self.delete_first(listing)
        pending = [p for row in listing.items for p in row.get('_create_locations', [])]
        self.assertEqual(['Shared Bay'], [p['name'] for p in pending])
        self.assertEqual(2, len(listing.items))

    def test_shared_pending_point_can_transfer_again_after_another_deletion(self):
        rows = self.drafts()
        rows[1]['task_generation_locations']['stores']['pickup_dropoff_locations'] = 'Shared Bay'
        rows.append(dict(rows[1], id='E', name='Other'))
        listing = self.listing(rows)
        self.delete_first(listing)
        self.delete_first(listing)
        self.assertEqual('E', listing.items[0]['id'])
        self.assertEqual(['Shared Bay'], [p['name'] for p in listing.items[0]['_create_locations']])
        self.assertIn('Shared Bay', listing.location_names)

    def test_conflicting_shared_placement_rejects_deletion_without_losing_drafts(self):
        from visualiser.dialogs import QMessageBox
        rows = self.drafts()
        rows[1]['_create_locations'] = [dict(name='Shared Bay', x=9, y=8, floor=0)]
        listing = self.listing(rows)
        before = copy.deepcopy(listing.items)
        with patch.object(QMessageBox, 'critical') as critical:
            self.delete_first(listing)
        self.assertTrue(critical.called)
        self.assertEqual(before, listing.items)

    def test_stale_list_save_preserves_newer_project_and_pending_draft(self):
        from PySide6.QtWidgets import QWidget
        from visualiser.dialogs import QMessageBox
        parent = QWidget()
        parent.store = JsonStore(grouped_config())
        save = Mock(side_effect=parent.store.replace_departments)
        listing = self.listing(parent.store.data['departments'], parent, save)
        listing.items[0]['_create_locations'] = [dict(name='Draft Bay', x=0, y=0, floor=0)]
        parent.store.data['departments'][0]['name'] = 'Newer name'
        newer = copy.deepcopy(parent.store.data)
        with patch.object(QMessageBox, 'critical') as critical:
            listing.save_items()
        self.assertTrue(critical.called)
        self.assertFalse(save.called)
        self.assertEqual(newer, parent.store.data)
        self.assertEqual('Draft Bay', listing.items[0]['_create_locations'][0]['name'])

    def test_stale_child_accept_preserves_draft_and_has_no_result(self):
        from PySide6.QtWidgets import QWidget
        from visualiser.dialogs import DepartmentEditorDialog, QMessageBox
        parent = QWidget()
        parent.store = JsonStore(grouped_config())
        listing = self.listing(parent.store.data['departments'], parent)
        child = DepartmentEditorDialog(listing, ['A', 'B'], [], seed=listing.items[0],
                                       task_generation_categories=[('stores', 'Stores', '-STORES')])
        child.name_edit.setText('Draft name')
        parent.store.data['locations'][0]['x'] = 5
        newer = copy.deepcopy(parent.store.data)
        with patch.object(QMessageBox, 'critical') as critical:
            child.accept()
        self.assertTrue(critical.called)
        self.assertIsNone(child.result)
        self.assertEqual('Draft name', child.name_edit.text())
        self.assertEqual(newer, parent.store.data)

    def test_replaced_project_with_identical_data_also_invalidates_draft(self):
        from PySide6.QtWidgets import QWidget
        from visualiser.dialogs import QMessageBox
        parent = QWidget()
        parent.store = JsonStore(grouped_config())
        save = Mock()
        listing = self.listing(parent.store.data['departments'], parent, save)
        parent.store = JsonStore(copy.deepcopy(parent.store.data))
        with patch.object(QMessageBox, 'critical') as critical:
            listing.save_items()
        self.assertTrue(critical.called)
        self.assertFalse(save.called)

    def test_child_cannot_overwrite_newer_parent_list_edits(self):
        from visualiser.dialogs import DepartmentEditorDialog, QMessageBox
        listing = self.listing(grouped_config()['departments'])
        child = DepartmentEditorDialog(listing, ['A', 'B'], [], seed=listing.items[0],
                                       task_generation_categories=[('stores', 'Stores', '-STORES')])
        listing.items[0]['name'] = 'Newer parent draft'
        with patch.object(QMessageBox, 'critical') as critical:
            child.accept()
        self.assertTrue(critical.called)
        self.assertIsNone(child.result)
        self.assertEqual('Newer parent draft', listing.items[0]['name'])
        self.assertEqual('Department', child.seed['name'])
