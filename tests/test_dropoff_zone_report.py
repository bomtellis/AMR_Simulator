import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from report.amr_report_analysis import (
    Context,
    build_dropoff_zone_peak_occupancy,
    build_location_peak_occupancy,
    load_location_catalog,
)


class DropoffZoneReportTests(unittest.TestCase):
    def test_catalog_marks_locations_assigned_as_dropoff_zones(self):
        config = {
            "departments": [
                {
                    "id": "D1",
                    "name": "Ward",
                    "task_generation_locations": {
                        "stores": {
                            "pickup_dropoff_locations": ["Ward destination"],
                            "dropoff_zone_locations": ["Zone"],
                        },
                        "catering": {
                            "pickup_dropoff_locations": ["Ward destination"],
                            "dropoff_zone_locations": ["Zone"],
                        },
                    },
                }
            ],
            "locations": [
                {"name": "Ward destination", "floor": 0},
                {
                    "name": "Zone",
                    "floor": 0,
                    "inventory_spaces": [{"name": "A"}, {"name": "B"}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            catalog = load_location_catalog(path)

        zone = catalog[catalog["location"] == "Zone"].iloc[0]
        self.assertTrue(bool(zone["is_dropoff_zone"]))
        self.assertEqual("Ward", zone["department"])
        self.assertEqual("Catering, Stores", zone["category"])
        self.assertEqual(2, int(zone["inventory_spaces_current"]))

    def test_true_simultaneous_peak_is_calculated_across_zones(self):
        times = pd.to_datetime(
            [
                "2026-01-01 08:00:00",
                "2026-01-01 08:01:00",
                "2026-01-01 08:02:00",
            ]
        )
        events = pd.DataFrame(
            [
                {
                    "_event_time": times[0],
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone A",
                    "payload": "Trolley",
                    "payload_instance_id": "P1",
                    "task_id": "T1",
                },
                {
                    "_event_time": times[1],
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone B",
                    "payload": "Trolley",
                    "payload_instance_id": "P2",
                    "task_id": "T2",
                },
                {
                    "_event_time": times[2],
                    "_event_text": "location_payload_exit",
                    "to_location": "Zone A",
                    "payload": "Trolley",
                    "payload_instance_id": "P1",
                    "task_id": "T1",
                },
            ]
        )
        catalog = pd.DataFrame(
            [
                {
                    "location": "Zone A",
                    "department": "Ward A",
                    "category": "Stores",
                    "is_dropoff_zone": True,
                    "inventory_spaces_current": 3,
                },
                {
                    "location": "Zone B",
                    "department": "Ward B",
                    "category": "Catering",
                    "is_dropoff_zone": True,
                    "inventory_spaces_current": 2,
                },
            ]
        )
        peaks = pd.DataFrame(
            [
                {
                    "location": "Zone A",
                    "peak_payload_count": 1,
                    "peak_area_used_m2": 1.2,
                    "peak_volume_m3": 1.5,
                },
                {
                    "location": "Zone B",
                    "peak_payload_count": 1,
                    "peak_area_used_m2": 1.2,
                    "peak_volume_m3": 1.5,
                },
            ]
        )
        ctx = Context(cols={}, has_datetime=True, time_col="_event_time")

        detail, summary = build_dropoff_zone_peak_occupancy(
            events, ctx, catalog, peaks
        )

        self.assertEqual([1, 1], detail["peak_occupied_spaces"].tolist())
        network_peak = summary[
            summary["metric"]
            == "Maximum occupied spaces across all drop-off zones"
        ].iloc[0]
        self.assertEqual(2, int(network_peak["value"]))
        peak_time = summary[
            summary["metric"] == "Time of simultaneous maximum"
        ].iloc[0]
        self.assertEqual("01/01/2026 08:01:00", peak_time["value"])

    def test_stale_explicit_exit_does_not_remove_another_payload_instance(self):
        events = pd.DataFrame(
            [
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:00:00"),
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "P1",
                },
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:01:00"),
                    "_event_text": "location_payload_exit",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "already-removed",
                },
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:02:00"),
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "P2",
                },
            ]
        )
        catalog = pd.DataFrame(
            [
                {
                    "location": "Zone",
                    "department": "Ward",
                    "category": "Stores",
                    "inventory_area_m2": 4.0,
                    "is_dropoff_zone": True,
                    "inventory_spaces_current": 4,
                }
            ]
        )
        payloads = pd.DataFrame(
            [
                {
                    "payload": "Trolley",
                    "payload_length_m": 1.0,
                    "payload_width_m": 1.0,
                    "payload_height_m": 1.0,
                }
            ]
        )
        ctx = Context(cols={}, has_datetime=True, time_col="_event_time")

        peaks = build_location_peak_occupancy(events, ctx, catalog, payloads)
        zone_peak = peaks[peaks["location"] == "Zone"].iloc[0]
        self.assertEqual(2, int(zone_peak["peak_payload_count"]))

        _, summary = build_dropoff_zone_peak_occupancy(
            events, ctx, catalog, peaks
        )
        network_peak = summary[
            summary["metric"]
            == "Maximum occupied spaces across all drop-off zones"
        ].iloc[0]
        self.assertEqual(2, int(network_peak["value"]))

    def test_same_timestamp_enter_and_exit_do_not_create_false_peak(self):
        timestamp = pd.Timestamp("2026-01-01 08:01:00")
        events = pd.DataFrame(
            [
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:00:00"),
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "P1",
                },
                {
                    "_event_time": timestamp,
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "P2",
                },
                {
                    "_event_time": timestamp,
                    "_event_text": "location_payload_exit",
                    "to_location": "Zone",
                    "payload": "Trolley",
                    "payload_instance_id": "P1",
                },
            ]
        )
        catalog = pd.DataFrame(
            [
                {
                    "location": "Zone",
                    "department": "Ward",
                    "category": "Stores",
                    "inventory_area_m2": 2.0,
                    "is_dropoff_zone": True,
                    "inventory_spaces_current": 1,
                }
            ]
        )
        payloads = pd.DataFrame(
            [
                {
                    "payload": "Trolley",
                    "payload_length_m": 1.0,
                    "payload_width_m": 1.0,
                    "payload_height_m": 1.0,
                }
            ]
        )
        ctx = Context(cols={}, has_datetime=True, time_col="_event_time")

        peaks = build_location_peak_occupancy(events, ctx, catalog, payloads)
        zone_peak = peaks[peaks["location"] == "Zone"].iloc[0]
        self.assertEqual(1, int(zone_peak["peak_payload_count"]))

        detail, summary = build_dropoff_zone_peak_occupancy(
            events, ctx, catalog, peaks
        )
        self.assertEqual(1, int(detail.iloc[0]["peak_occupied_spaces"]))
        network_peak = summary[
            summary["metric"]
            == "Maximum occupied spaces across all drop-off zones"
        ].iloc[0]
        self.assertEqual(1, int(network_peak["value"]))

    def test_dropoff_shortfall_respects_flexible_space_dimensions(self):
        events = pd.DataFrame(
            [
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:00:00"),
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Tall trolley",
                    "payload_instance_id": "P1",
                },
                {
                    "_event_time": pd.Timestamp("2026-01-01 08:01:00"),
                    "_event_text": "location_payload_enter",
                    "to_location": "Zone",
                    "payload": "Tall trolley",
                    "payload_instance_id": "P2",
                },
            ]
        )
        catalog = pd.DataFrame(
            [
                {
                    "location": "Zone",
                    "department": "Ward",
                    "category": "Stores",
                    "is_dropoff_zone": True,
                    "inventory_spaces_current": 2,
                    "inventory_space_definitions": [
                        {
                            "name": "Low",
                            "length_m": 1.0,
                            "width_m": 1.0,
                            "height_m": 1.0,
                            "flexible": True,
                        },
                        {
                            "name": "Tall",
                            "length_m": 1.0,
                            "width_m": 1.0,
                            "height_m": 2.0,
                            "flexible": True,
                        },
                    ],
                }
            ]
        )
        peaks = pd.DataFrame(
            [
                {
                    "location": "Zone",
                    "peak_payload_count": 2,
                    "peak_area_used_m2": 2.0,
                    "peak_volume_m3": 3.0,
                }
            ]
        )
        payloads = pd.DataFrame(
            [
                {
                    "payload": "Tall trolley",
                    "payload_length_m": 1.0,
                    "payload_width_m": 1.0,
                    "payload_height_m": 1.5,
                }
            ]
        )
        ctx = Context(cols={}, has_datetime=True, time_col="_event_time")

        detail, _ = build_dropoff_zone_peak_occupancy(
            events, ctx, catalog, peaks, payloads
        )

        self.assertEqual(1, int(detail.iloc[0]["free_spaces_at_peak"]))
        self.assertEqual(1, int(detail.iloc[0]["space_shortfall_at_peak"]))


if __name__ == "__main__":
    unittest.main()
