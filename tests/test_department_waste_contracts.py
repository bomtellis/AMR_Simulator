"""Sparse department waste overrides must survive editing without changing demand."""
import copy
import unittest
from unittest.mock import Mock, patch

from simulator import Simulation
from tests.test_waste_conservation import dynamic_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class DepartmentWasteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def counts(self, config):
        records = Simulation(config).task_generation_manager.update_until(3600)
        return len(records), sum(r.task.waste_volume_m3 for r in records)

    def department_dialog(self, config):
        from visualiser.dialogs import DepartmentEditorDialog
        return DepartmentEditorDialog(None, ['A', 'B'], ['General'], seed=config['departments'][0],
                                      task_generation_categories=[('waste', 'Waste', '-WASTE')])

    def test_untouched_department_preserves_inherited_one_hour_demand(self):
        for stream in ('General', {'name': 'General'}):
            cfg = dynamic_config()
            cfg['departments'][0]['waste_streams'] = [stream]
            before = copy.deepcopy(cfg)
            dialog = self.department_dialog(cfg)
            dialog.accept()
            cfg['departments'] = [dialog.result]
            # 24 m3/day * 1/24 day = 1 m3; .5 m3 capacity * .8 = .4 m3/collection.
            for data in (before, cfg, JsonStore(cfg).data):
                self.assertEqual((2, .8), self.counts(data))
                manager = Simulation(data).task_generation_manager
                manager.update_until(3600)
                self.assertAlmostEqual(.2, manager.generators[0].runtime['department:D:General']['volume'])
            self.assertNotIn('base_daily_volume_m3', dialog.result['waste_streams'][0])

    def test_department_and_nested_dialogs_retain_payload_capacity_and_metadata(self):
        from visualiser.dialogs import DepartmentWasteStreamSettingsDialog, DepartmentWasteStreamItemDialog
        cfg = dynamic_config()
        stream = cfg['departments'][0]['waste_streams'][0]
        stream.update(payload='Box', container_capacity_m3=2, full_threshold_fraction=.5,
                      custom={'note': 'retain'}, shared_container_id='Bin-1')
        before = copy.deepcopy(stream)
        dialog = self.department_dialog(cfg)
        dialog.accept()
        settings = DepartmentWasteStreamSettingsDialog(None, ['General'], dialog.result['waste_streams'])
        item = DepartmentWasteStreamItemDialog(settings, ['General'], seed=settings.items[0])
        item.accept()
        self.assertEqual(before, item.result)
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((1, 1), self.counts(cfg))

    def test_explicit_numeric_edit_changes_only_its_override_and_expected_volume(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog
        cfg = dynamic_config()
        item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'custom': {'note': 'keep'}})
        item.base_daily_edit.setText('48')
        item.accept()
        self.assertEqual({'name': 'General', 'custom': {'note': 'keep'}, 'base_daily_volume_m3': 48}, item.result)
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((5, 2), self.counts(cfg))

    def test_blank_numeric_override_restores_inheritance_instead_of_zero(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog
        item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'base_daily_volume_m3': 48})
        item.base_daily_edit.clear()
        item.accept()
        self.assertNotIn('base_daily_volume_m3', item.result)
        cfg = dynamic_config()
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((2, .8), self.counts(cfg))

    def test_bulk_untouched_settings_do_not_copy_first_department_overrides(self):
        from visualiser.dialogs import BulkDepartmentWasteStreamControlDialog
        rows = copy.deepcopy(dynamic_config()['departments'])
        rows[0]['waste_streams'][0]['base_daily_volume_m3'] = 24
        rows.append(copy.deepcopy(rows[0]))
        rows[1].update(id='E', name='Other')
        rows[1]['waste_streams'][0]['base_daily_volume_m3'] = 48
        dialog = BulkDepartmentWasteStreamControlDialog(None, ['General'], rows)
        dialog.accept()
        self.assertEqual({}, dialog.result['update_stream_settings'].get('General', {}))

    def test_bulk_partial_update_preserves_other_settings_and_unedited_streams(self):
        from visualiser import dialogs
        rows = copy.deepcopy(dynamic_config()['departments'])
        stream = rows[0]['waste_streams'][0]
        stream.update(payload='Box', container_capacity_m3=2, custom={'note': 'keep'})
        rows[0]['waste_streams'].append({'name': 'Other', 'custom': {'note': 'also keep'}})
        listing = dialogs.DepartmentListDialog(None, rows, ['A', 'B'], ['General', 'Other'], 0, Mock(), lambda: 'E')
        bulk = Mock(result={'add_streams': ['General'], 'update_stream_settings': {'General': {'base_daily_volume_m3': 48}}})
        bulk.exec.return_value = dialogs.QDialog.Accepted
        with patch.object(listing, '_selected_department_indexes', return_value=[0]), \
             patch.object(dialogs, 'BulkDepartmentWasteStreamControlDialog', return_value=bulk), \
             patch.object(dialogs.QMessageBox, 'information'):
            listing.manage_waste_streams_for_selected_departments()
        self.assertEqual(dict(stream, base_daily_volume_m3=48), listing.items[0]['waste_streams'][0])
        self.assertEqual(rows[0]['waste_streams'][1], listing.items[0]['waste_streams'][1])

    def test_invalid_names_and_duplicate_stream_assignments_reject_without_mutation(self):
        for streams in ([{'name': 5}], [{}], [''], ['General', {'name': 'General'}]):
            cfg = dynamic_config()
            cfg['departments'][0]['waste_streams'] = streams
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(streams=streams, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)
            self.assertTrue(any(f.severity == 'error' and '/waste_streams/' in f.path for f in check_project(cfg).findings))

    def test_single_stream_editor_rejects_invalid_volume_before_returning_result(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog, QMessageBox
        item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General'})
        item.base_daily_edit.setText('-1')
        with patch.object(QMessageBox, 'critical') as critical:
            item.accept()
        self.assertTrue(critical.called)
        self.assertIsNone(item.result)

    def test_mode_schedule_and_boolean_inheritance_are_explicit(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog, Qt
        item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'generation_mode': 'scheduled',
            'scheduled_times': ['00:30'], 'initial_container_present': False})
        item.accept()
        cfg = dynamic_config()
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((1, .4), self.counts(cfg))
        item.mode_combo.setCurrentText('Inherit')
        item.inherit_times()
        item.initial_container_check.setCheckState(Qt.PartiallyChecked)
        item.accept()
        self.assertEqual({'name': 'General'}, item.result)
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((2, .8), self.counts(cfg))

    def test_explicit_empty_schedule_is_not_replaced_by_an_inherited_schedule(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog
        item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'generation_mode': 'scheduled'})
        item.clear_times()
        item.accept()
        self.assertEqual([], item.result['scheduled_times'])
        cfg = dynamic_config()
        cfg['task_generation']['categories']['waste']['scheduled_times'] = ['00:30']
        cfg['departments'][0]['waste_streams'] = [item.result]
        self.assertEqual((0, 0), self.counts(cfg))

    def test_blank_default_and_timeframe_modes_survive_untouched_edit(self):
        from visualiser.dialogs import DepartmentWasteStreamItemDialog
        for mode in ('', 'timeframe'):
            item = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'generation_mode': mode})
            item.accept()
            self.assertEqual(mode, item.result['generation_mode'])

    def test_bulk_explicit_edit_and_reset_produce_sparse_patches(self):
        from visualiser.dialogs import BulkDepartmentWasteStreamControlDialog
        rows = dynamic_config()['departments']
        dialog = BulkDepartmentWasteStreamControlDialog(None, ['General'], rows)
        widgets = dialog._row_widgets['General']
        widgets['base_daily_edit'].setText('48')
        dialog.accept()
        self.assertEqual({'base_daily_volume_m3': 48}, dialog.result['update_stream_settings']['General'])
        widgets['base_daily_edit'].clear()
        widgets['mode_combo'].setCurrentText('Inherit')
        dialog.accept()
        self.assertEqual({}, dialog.result['update_stream_settings']['General'])
        self.assertEqual(['base_daily_volume_m3', 'generation_mode'], dialog.result['remove_stream_settings']['General'])

    def test_bulk_invalid_edits_do_not_return_a_patch(self):
        from visualiser.dialogs import BulkDepartmentWasteStreamControlDialog, QMessageBox
        dialog = BulkDepartmentWasteStreamControlDialog(None, ['General'], dynamic_config()['departments'])
        dialog._row_widgets['General']['base_daily_edit'].setText('nan')
        with patch.object(QMessageBox, 'critical') as critical:
            dialog.accept()
        self.assertTrue(critical.called)
        self.assertIsNone(dialog.result)

    def test_bulk_inheritance_reset_removes_only_requested_fields(self):
        from visualiser import dialogs
        rows = copy.deepcopy(dynamic_config()['departments'])
        rows[0]['waste_streams'][0].update(base_daily_volume_m3=48, custom={'note': 'retain'})
        listing = dialogs.DepartmentListDialog(None, rows, ['A', 'B'], ['General'], 0, Mock(), lambda: 'E')
        bulk = Mock(result={'remove_stream_settings': {'General': ['base_daily_volume_m3']}})
        bulk.exec.return_value = dialogs.QDialog.Accepted
        with patch.object(listing, '_selected_department_indexes', return_value=[0]), \
             patch.object(dialogs, 'BulkDepartmentWasteStreamControlDialog', return_value=bulk), \
             patch.object(dialogs.QMessageBox, 'information'):
            listing.manage_waste_streams_for_selected_departments()
        self.assertEqual({'name': 'General', 'custom': {'note': 'retain'}}, listing.items[0]['waste_streams'][0])
