import unittest

from visualiser.playback_state import (
    onboard_snapshot_is_authoritative,
    row_completes_payload_transport,
)


class VisualiserPayloadMonitorTests(unittest.TestCase):
    def test_legacy_empty_corridor_snapshot_is_not_authoritative(self):
        row = {
            "event_type": "segment_corridor",
            "segment_type": "corridor",
            "status": "completed",
            "onboard_payloads": "[]",
            "multi_stop_task_ids": "[]",
        }
        self.assertFalse(onboard_snapshot_is_authoritative(row, []))
        self.assertFalse(row_completes_payload_transport(row))

    def test_nonempty_and_multi_stop_snapshots_are_authoritative(self):
        self.assertTrue(
            onboard_snapshot_is_authoritative(
                {"event_type": "segment_corridor"}, [{"task_id": "T1"}]
            )
        )
        self.assertTrue(
            onboard_snapshot_is_authoritative(
                {
                    "event_type": "multi_stop_segment_corridor",
                    "multi_stop_task_ids": '["T1"]',
                },
                [],
            )
        )

    def test_only_dropoff_or_task_complete_clears_payload(self):
        self.assertTrue(
            row_completes_payload_transport(
                {"event_type": "segment_dropoff", "status": "completed"}
            )
        )
        self.assertTrue(
            row_completes_payload_transport({"event_type": "task_complete"})
        )


if __name__ == "__main__":
    unittest.main()
