"""Staff report acceptance from real simulator bookings and exported event rows."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from report.amr_report_analysis import (
    build_payload_handling_timetable, build_staff_handling_summary, parse_time_column,
)
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_staff_contention import staff_task


class StaffReportingTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(reference_config(), verbose=True)

    def book(self, name, start, duration, **settings):
        task = staff_task(name, **settings)
        assignment = self.sim._assign_staff_for_handling(task, start, duration)
        with contextlib.redirect_stdout(io.StringIO()):
            self.sim._log_staff_handling_assignment(task, assignment)
        return assignment

    def events(self):
        df, ctx = parse_time_column(pd.DataFrame(self.sim.verbose_rows))
        df['_event_text'] = df['event_type']
        return df, ctx

    def summary(self, metadata=None):
        df, ctx = self.events()
        return build_staff_handling_summary(df, ctx, metadata)

    def test_exchange_is_in_summary_and_timetable(self):
        self.book('exchange', 100, 60, tracked_item_exchange=True)
        summary = self.summary()
        self.assertEqual(1, len(summary))
        self.assertEqual(1, summary.iloc[0]['handling_tasks'])
        self.assertEqual(60, summary.iloc[0]['total_handling_time_s'])
        df, ctx = self.events()
        self.assertEqual(1, len(build_payload_handling_timetable(df, ctx)))

    def test_recorded_initial_count_takes_precedence_over_category_metadata(self):
        self.book('one', 100, 60)
        self.book('two', 110, 60)
        row = self.summary({'category_staff_initial': {'stores': 9}}).iloc[0]
        self.assertEqual((1, 2, 1), (row['initial_people'], row['people_required'], row['added_people']))

    def test_shared_handling_time_and_person_busy_time_are_distinct(self):
        self.book('one', 100, 60, policy='batch_same_location')
        self.book('two', 110, 80, policy='batch_same_location')
        row = self.summary().iloc[0]
        self.assertEqual(140, row['total_handling_time_s'])  # 60 + 80 task seconds
        self.assertEqual(90, row['recorded_busy_time_s'])  # union [100,190]

    def test_two_people_busy_time_is_sum_of_each_person_union(self):
        self.book('one', 100, 60)
        self.book('two', 110, 80)
        self.assertEqual(140, self.summary().iloc[0]['recorded_busy_time_s'])

    def test_missing_person_evidence_is_unknown_not_zero_busy_time(self):
        self.book('one', 100, 60)
        df, ctx = self.events()
        df['person_id'] = ''
        row = build_staff_handling_summary(df, ctx).iloc[0]
        self.assertTrue(pd.isna(row['recorded_busy_time_s']))

    def test_explicit_linen_record_is_not_removed_by_configured_hours(self):
        task = staff_task('linen')
        task.staff_category_key = 'linen'
        assignment = self.sim._assign_staff_for_handling(task, 100, 60)
        with contextlib.redirect_stdout(io.StringIO()):
            self.sim._log_staff_handling_assignment(task, assignment)
        metadata = {'category_staff_hours': {'linen': {'start': '09:00', 'end': '17:00'}}}
        self.assertEqual(1, len(self.summary(metadata)))
        df, ctx = self.events()
        wards = []
        self.assertEqual(1, len(build_payload_handling_timetable(df, ctx, metadata, wards)))
        self.assertEqual([], wards)

    def test_unusable_hours_flag_survives_logging_and_report(self):
        self.book('one', 100, 60, staff_use_custom_working_hours=True, staff_working_hours={})
        df, _ = self.events()
        handling = df[df['event_type'] == 'staff_payload_handling'].iloc[0]
        self.assertTrue(handling['staff_working_hours_fallback'])
        self.assertIn('Working-hours fallback', self.summary().iloc[0]['evidence_notes'])

    def test_alternating_teams_reconcile_rostered_counts(self):
        period = 4 * 24 * 3600
        first = self.book('A', 100, 60, staff_shift_pattern='four_on_four_off_12h')
        second = self.book('B', period + 100, 60, staff_shift_pattern='four_on_four_off_12h')
        third = self.book('A-again', 2 * period + 100, 60, staff_shift_pattern='four_on_four_off_12h')
        self.assertEqual(['A', 'B', 'A'], [x['staff_shift_team'] for x in (first, second, third)])
        self.assertEqual(first['person_id'], third['person_id'])
        self.assertEqual(2, self.sim._staff_handling_summary()['total_people_required'])
        row = self.summary().iloc[0]
        self.assertEqual((2, 2, 0), (row['people_required'], row['initial_people'], row['added_people']))
        self.assertEqual(180, row['recorded_busy_time_s'])

    def test_recorded_multiplier_overrides_different_configuration_metadata(self):
        self.book('one', 100, 60)
        row = self.summary({'category_staff_shift_multiplier': {'stores': 2}}).iloc[0]
        self.assertEqual(1, row['people_required'])

    def test_legacy_fallback_status_remains_unknown_and_events_are_traceable(self):
        self.book('one', 100, 60)
        df, ctx = self.events()
        df['staff_working_hours_fallback'] = float('nan')
        row = build_staff_handling_summary(df, ctx).iloc[0]
        self.assertIn('unavailable', row['evidence_notes'])
        self.assertNotIn('Working-hours fallback:', row['evidence_notes'])
        event_id = df[df['event_type'] == 'staff_payload_handling'].iloc[0]['event_id']
        self.assertEqual(event_id, row['event_ids'])

    def test_untracked_department_fallback_does_not_invent_a_person(self):
        task = staff_task('department', dropoff_zone='B', final_destination='A',
                          staff_department_fallback_enabled=True,
                          staff_use_custom_working_hours=True, staff_working_hours={})
        assignment = self.sim._assign_staff_for_handling(task, 100, 60)
        with contextlib.redirect_stdout(io.StringIO()):
            self.sim._log_staff_handling_assignment(task, assignment)
        row = self.summary().iloc[0]
        self.assertEqual(0, row['people_required'])
        self.assertEqual(0, row['initial_people'])
        self.assertTrue(pd.isna(row['recorded_busy_time_s']))
        df, ctx = self.events()
        legacy = build_staff_handling_summary(df.drop(columns='staff_resource_tracked'), ctx).iloc[0]
        self.assertEqual(0, legacy['people_required'])
        self.assertTrue(pd.isna(legacy['recorded_busy_time_s']))

    def test_csv_roundtrip_preserves_flags_counts_intervals_and_event_links(self):
        self.book('one', 100, 60, policy='batch_same_location')
        self.book('two', 110, 80, policy='batch_same_location')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'staff.csv'
            self.sim.verbose_csv_path = str(path)
            with contextlib.redirect_stdout(io.StringIO()):
                self.sim.write_verbose_csv()
            df, ctx = parse_time_column(pd.read_csv(path))
        df['_event_text'] = df['event_type']
        row = build_staff_handling_summary(df, ctx).iloc[0]
        self.assertEqual((2, 1, 90), (row['handling_tasks'], row['people_required'], row['recorded_busy_time_s']))
        self.assertNotIn('fallback:', row['evidence_notes'])
        self.assertEqual(2, len(row['event_ids'].split(', ')))

    def test_exact_four_day_boundary_changes_team_and_work_period_deferral_uses_new_team(self):
        period = 4 * 24 * 3600
        before = self.book('before', period - 1, 1, staff_shift_pattern='four_on_four_off_12h')
        after = self.book('after', period, 60, staff_shift_pattern='four_on_four_off_12h')
        self.assertEqual(('A', 'B'), (before['staff_shift_team'], after['staff_shift_team']))
        self.setUp()
        deferred = self.book('deferred', period - 1, 60, staff_shift_pattern='four_on_four_off_12h',
                             staff_shift_start_time='09:00', staff_shift_end_time='21:00')
        self.assertEqual(period + 9 * 3600, deferred['start_time'])
        self.assertEqual('B', deferred['staff_shift_team'])

    def test_malformed_interval_keeps_busy_time_unknown(self):
        self.book('one', 100, 60)
        df, ctx = self.events()
        df.loc[df['event_type'] == 'staff_payload_handling', 'end_time'] = '2026-01-05 00:01:39'
        self.assertTrue(pd.isna(build_staff_handling_summary(df, ctx).iloc[0]['recorded_busy_time_s']))


if __name__ == '__main__':
    unittest.main()
