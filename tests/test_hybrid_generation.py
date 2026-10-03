"""Continuous volume plus discrete demand must not fund the same event twice."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication
from dialogs import (TaskGenerationSettingsDialog, DepartmentWasteStreamItemDialog,
                     BulkDepartmentTaskGenerationDialog, BulkDepartmentWasteStreamControlDialog)
from simulator import Simulation
from tests.test_waste_conservation import dynamic_config
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore
from amr_demand_preview import build_demand_preview


def hybrid_config():
    config = dynamic_config()
    config['simulation'].update(end_datetime='2026-01-05T01:00:00', generated_task_release_stagger_sec=0)
    config['task_generation']['update_interval_sec'] = 3600
    config['task_generation']['categories']['waste'].update(
        generation_mode='hybrid', base_daily_volume_m3=9.6, frequency_per_day=24,
        volume_per_event_m3=0.4, threshold_volume_m3=0.4)
    return config


def hybrid_transport_config():
    config = grouped_config()
    config['simulation'].update(end_datetime='2026-01-05T01:00:00', generated_task_release_stagger_sec=0)
    config['task_generation']['update_interval_sec'] = 3600
    config['task_generation']['categories']['stores'].update(generation_mode='hybrid',
        scheduled_times=[], base_daily_volume_m3=9.6, frequency_per_day=24,
        volume_per_event_m3=0.4, threshold_volume_m3=0.4, requires_staff=False)
    return config


class HybridGenerationTests(unittest.TestCase):
    def generated(self, config):
        manager = Simulation(config).task_generation_manager
        records = manager.update_until(3600)
        generator = manager.generators[0]
        return records, generator._runtime_for_volume_key(generator.instances[0]), manager

    def test_one_hour_has_one_continuous_and_one_discrete_collection(self):
        for config in (hybrid_config(), JsonStore(hybrid_config()).data):
            records, runtime, manager = self.generated(config)
            self.assertEqual(2, len(records))
            self.assertAlmostEqual(0.8, sum(r.task.waste_volume_m3 for r in records))
            self.assertAlmostEqual(0, runtime['volume'])
            row, = manager.waste_volume_balance()
            self.assertAlmostEqual(0.4, row['accrued_m3'])  # continuous pool only
            self.assertAlmostEqual(0.4, row['pending_m3'])

    def test_zero_base_rate_cannot_make_a_second_threshold_collection(self):
        config = hybrid_config()
        config['task_generation']['categories']['waste']['base_daily_volume_m3'] = 0
        records, runtime, _ = self.generated(config)
        self.assertEqual(1, len(records))
        self.assertIn('sporadic', records[0].task.labels)
        self.assertEqual(0, runtime['volume'])

    def test_zero_frequency_is_only_continuous_threshold_demand(self):
        config = hybrid_config()
        config['task_generation']['categories']['waste']['frequency_per_day'] = 0
        records, _, _ = self.generated(config)
        self.assertEqual(1, len(records))
        self.assertIn('threshold', records[0].task.labels)

    def test_threshold_mode_still_uses_event_volume_as_fill(self):
        config = hybrid_config()
        config['task_generation']['categories']['waste'].update(generation_mode='threshold', base_daily_volume_m3=0)
        records, _, manager = self.generated(config)
        self.assertEqual(1, len(records))
        self.assertIn('threshold', records[0].task.labels)
        self.assertAlmostEqual(0.4, manager.waste_volume_balance()[0]['accrued_m3'])

    def test_partial_continuous_fill_is_separate_from_dispatched_event(self):
        config = hybrid_config()
        config['task_generation']['categories']['waste']['base_daily_volume_m3'] = 4.8
        records, runtime, manager = self.generated(config)
        self.assertEqual(1, len(records))
        self.assertAlmostEqual(0.4, records[0].task.waste_volume_m3)
        self.assertAlmostEqual(0.2, runtime['volume'])
        self.assertAlmostEqual(0.2, manager.waste_volume_balance()[0]['accrued_m3'])

    def test_closing_poll_preserves_both_components_without_duplicating_them(self):
        config = hybrid_config()
        config['simulation'].update(start_datetime='2026-01-05T08:00:00', end_datetime='2026-01-06T09:00:00')
        config['departments'][0].update(operating_start_time='09:00', operating_end_time='10:00')
        manager = Simulation(config).task_generation_manager
        self.assertEqual([], manager.update_until(7200))
        records = manager.update_until(90000)
        self.assertEqual(2, len(records))
        self.assertAlmostEqual(0.8, sum(r.task.waste_volume_m3 for r in records))
        self.assertAlmostEqual(0.4, manager.waste_volume_balance()[0]['pending_m3'])

    def test_scheduled_threshold_keeps_clock_fill_and_frequency_fill(self):
        config = hybrid_config()
        config['task_generation']['categories']['waste'].update(generation_mode='scheduled_threshold',
            base_daily_volume_m3=0, scheduled_times=['00:30'])
        records, _, manager = self.generated(config)
        self.assertEqual([1800, 3600], [r.task.release_time for r in records])
        self.assertAlmostEqual(0.8, manager.waste_volume_balance()[0]['accrued_m3'])

    def test_full_nonwaste_simulation_completes_two_independent_components(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/hybrid-demand.json'
        config = json.loads(path.read_text(encoding='utf-8'))
        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual(set(), sim.failed_task_ids)

    def test_preview_explains_component_scope_without_claiming_outcome(self):
        preview = build_demand_preview(hybrid_config())
        rule = next(r for r in preview['rules'] if r['category'] == 'waste' and r.get('field_provenance'))
        self.assertIsNone(rule['total_demand'])
        self.assertIn('only once', rule['explanation'])


class HybridEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_threshold_event_inputs_are_visible_in_category_editor(self):
        config = grouped_config()
        dialog = TaskGenerationSettingsDialog(None, config['task_generation'], ['A', 'B'], ['Box'], [], config['departments'], lambda data: None)
        try:
            for mode in ['threshold', 'scheduled_threshold', 'hybrid']:
                dialog.mode_combo.setCurrentText(mode)
                self.assertFalse(dialog.frequency_edit.isHidden())
                self.assertFalse(dialog.volume_per_event_edit.isHidden())
            self.assertIn('only once', dialog.mode_combo.toolTip())
        finally:
            dialog.close()

    def test_scheduled_waste_exposes_volume_but_not_unused_frequency(self):
        dialog = DepartmentWasteStreamItemDialog(None, ['General'], {'name': 'General', 'generation_mode': 'scheduled'})
        try:
            self.assertFalse(dialog.frequency_edit.isEnabled())
            self.assertTrue(dialog.volume_edit.isEnabled())
            dialog.mode_combo.setCurrentText('threshold')
            self.assertTrue(dialog.frequency_edit.isEnabled())
            self.assertTrue(dialog.volume_edit.isEnabled())
        finally:
            dialog.close()

    def test_bulk_editors_expose_the_same_active_inputs_and_mode_help(self):
        config = hybrid_config()
        category = BulkDepartmentTaskGenerationDialog(None, 'stores', 'Stores', config['departments'],
            {'generation_mode': 'threshold'}, ['A', 'B'], ['Box'], [])
        streams = BulkDepartmentWasteStreamControlDialog(None, ['General'], config['departments'])
        try:
            self.assertFalse(category.frequency_edit.isHidden())
            self.assertFalse(category.volume_per_event_edit.isHidden())
            category.mode_combo.setCurrentText('hybrid')
            self.assertIn('only once', category.mode_combo.toolTip())
            widgets = streams._row_widgets['General']
            widgets['mode_combo'].setCurrentText('scheduled')
            self.assertFalse(widgets['frequency_edit'].isEnabled())
            self.assertTrue(widgets['volume_edit'].isEnabled())
            widgets['mode_combo'].setCurrentText('hybrid')
            self.assertTrue(widgets['frequency_edit'].isEnabled())
            self.assertIn('only once', widgets['mode_combo'].toolTip())
        finally:
            category.close()
            streams.close()


if __name__ == '__main__':
    unittest.main()
