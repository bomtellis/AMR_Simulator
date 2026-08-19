import unittest

import pandas as pd

from report.amr_report_analysis import (
    Context,
    build_lift_trip_cohorts,
    build_lift_usage_profile,
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


if __name__ == "__main__":
    unittest.main()
