import unittest
import tempfile
from pathlib import Path

import pandas as pd

from report.amr_report_analysis import (
    Context,
    build_lift_trip_cohorts,
    build_lift_usage_profile,
    extract_lift_cohorts,
)


class LiftTripCohortTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(cols={}, has_datetime=True, time_col="_event_time")
        self.rows = pd.DataFrame(
            [
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:02:00"),
                    "_lift_id": "Lift-1",
                    "_segment_text": "lift_transfer",
                    "lift_time_s": 20.0,
                },
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:04:30"),
                    "_lift_id": "Lift-1",
                    "_segment_text": "lift_reposition",
                    "lift_time_s": 10.0,
                },
                {
                    "_event_time": pd.Timestamp("2026-01-02 08:02:30"),
                    "_lift_id": "Lift-1",
                    "_segment_text": "lift_transfer",
                    "lift_time_s": 20.0,
                },
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:06:00"),
                    "_lift_id": "Lift-2",
                    "_segment_text": "lift_transfer",
                    "lift_time_s": 30.0,
                },
            ]
        )

    def test_five_minute_cohorts_count_each_lift_and_segment_type(self):
        result = build_lift_trip_cohorts(self.rows, self.ctx, interval_minutes=5)

        self.assertEqual(2 * 288 * 2, len(result))
        first_day_lift_1 = result[
            (result["cohort_date"] == "2026-01-01")
            & (result["interval"] == "08:00")
            & (result["lift_id"] == "Lift-1")
        ].iloc[0]
        second_day_lift_1 = result[
            (result["cohort_date"] == "2026-01-02")
            & (result["interval"] == "08:00")
            & (result["lift_id"] == "Lift-1")
        ].iloc[0]
        self.assertEqual(2, int(first_day_lift_1["trips"]))
        self.assertEqual(1, int(first_day_lift_1["transfer_trips"]))
        self.assertEqual(1, int(first_day_lift_1["reposition_trips"]))
        self.assertEqual(30.0, float(first_day_lift_1["travel_time_s"]))
        self.assertEqual(1, int(second_day_lift_1["trips"]))
        self.assertEqual(20.0, float(second_day_lift_1["travel_time_s"]))
        self.assertNotEqual(
            first_day_lift_1["cohort_start"],
            second_day_lift_1["cohort_start"],
        )

        lift_2 = result[
            (result["cohort_date"] == "2026-01-01")
            & (result["interval"] == "08:05")
            & (result["lift_id"] == "Lift-2")
        ].iloc[0]
        self.assertEqual(1, int(lift_2["trips"]))
        self.assertEqual("08:10", lift_2["interval_end"])

    def test_hourly_cohorts_aggregate_five_minute_buckets(self):
        result = build_lift_trip_cohorts(self.rows, self.ctx, interval_minutes=60)

        self.assertEqual(2 * 24 * 2, len(result))
        first_day_lift_1 = result[
            (result["cohort_date"] == "2026-01-01")
            & (result["interval"] == "08:00")
            & (result["lift_id"] == "Lift-1")
        ].iloc[0]
        second_day_lift_1 = result[
            (result["cohort_date"] == "2026-01-02")
            & (result["interval"] == "08:00")
            & (result["lift_id"] == "Lift-1")
        ].iloc[0]
        first_day_lift_2 = result[
            (result["cohort_date"] == "2026-01-01")
            & (result["interval"] == "08:00")
            & (result["lift_id"] == "Lift-2")
        ].iloc[0]
        self.assertEqual(2, int(first_day_lift_1["trips"]))
        self.assertEqual(1, int(second_day_lift_1["trips"]))
        self.assertEqual(1, int(first_day_lift_2["trips"]))
        self.assertEqual("09:00", first_day_lift_1["interval_end"])

    def test_existing_lift_usage_profile_keeps_its_public_shape(self):
        result = build_lift_usage_profile(
            self.rows, self.ctx, interval_minutes=30
        )

        self.assertEqual(
            ["interval", "interval_start_min", "lift_id", "trips"],
            result.columns.tolist(),
        )
        lift_1 = result[
            (result["interval"] == "08:00") & (result["lift_id"] == "Lift-1")
        ].iloc[0]
        self.assertEqual(3, int(lift_1["trips"]))

    def test_empty_input_returns_export_columns(self):
        result = build_lift_trip_cohorts(
            pd.DataFrame(), self.ctx, interval_minutes=5
        )

        self.assertTrue(result.empty)
        self.assertIn("transfer_trips", result.columns)
        self.assertIn("travel_time_s", result.columns)

    def test_direct_csv_export_matches_existing_cohorts_without_task_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            self.rows.rename(columns={'_event_time': 'event_time', '_lift_id': 'lift_id',
                '_segment_text': 'segment_type', 'lift_time_s': 'duration_sec'}).to_csv(path, index=False)
            result = extract_lift_cohorts(path)
        for minutes, key in [(5, 'lift_trip_cohorts_5min'), (60, 'lift_trip_cohorts_hourly')]:
            pd.testing.assert_frame_equal(build_lift_trip_cohorts(self.rows, self.ctx, minutes), result[key])

    def test_event_only_multi_stop_lift_segments_and_empty_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            pd.DataFrame([dict(sim_time_sec=300, event_type='multi_stop_segment_lift_transfer',
                               from_location='Lift L1 (0)', to_location='Lift L1 (1)', duration_sec=20)]).to_csv(path, index=False)
            result = extract_lift_cohorts(path)['lift_trip_cohorts_5min']
            self.assertEqual(1, result.trips.sum())
            self.assertEqual(20, result.travel_time_s.sum())
            pd.DataFrame([dict(sim_time_sec=0, event_type='task_assigned')]).to_csv(path, index=False)
            self.assertTrue(extract_lift_cohorts(path)['lift_trip_cohorts_5min'].empty)


if __name__ == "__main__":
    unittest.main()
