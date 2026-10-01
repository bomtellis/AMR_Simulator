import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from report.amr_report_analysis import extract_lift_movements


class LiftTravelExportTests(unittest.TestCase):
    def source(self, folder, rows=None):
        if rows is None:
            rows = [
                dict(sim_time_sec=20, amr_id='AMR-1', task_id='T1,T2',
                     lift_id='Lift-7', segment_type='lift_transfer',
                     from_location='Lift-7-F1', to_location='Lift-7-F0',
                     start_floor=1, end_floor=0, duration_sec=40, distance_m=4),
                dict(sim_time_sec=10, amr_id='AMR-1', task_id='T1',
                     lift_id='Lift-7', segment_type='lift_reposition',
                     from_location='Waiting node', to_location='Waiting node',
                     start_floor=1, end_floor=1, duration_sec=8, distance_m=16,
                     details=json.dumps(dict(
                         # Floor metadata was overwritten with the waiting AMR floor.
                         amr_wait_node='Waiting node', from_floor=1, to_floor=1,
                         **{'from': 'Lift-7-F5', 'to': 'Lift-7-F1'},
                         vertical_distance_m=16,
                     ))),
            ]
        path = Path(folder) / 'simulation.csv'
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_real_lift_endpoints_override_waiting_robot_position(self):
        with tempfile.TemporaryDirectory() as folder:
            detail = extract_lift_movements(self.source(folder))
        self.assertEqual(2, len(detail))
        reposition, transfer = detail.to_dict('records')
        self.assertEqual(('L05', 'L01', 'L01'),
                         (reposition['origin_level'], reposition['destination_level'], reposition['destination_location']))
        self.assertTrue(detail['origin_location'].equals(detail['origin_level']))
        self.assertTrue(detail['destination_location'].equals(detail['destination_level']))
        self.assertEqual(16, reposition['travel_distance_m'])
        self.assertFalse(reposition['amr_onboard'])
        self.assertEqual('Down', reposition['direction'])
        self.assertEqual('10s', reposition['start_time'])
        self.assertEqual('18s', reposition['finish_time'])
        self.assertEqual(('L01', 'L00', 'T1,T2'),
                         (transfer['origin_level'], transfer['destination_level'], transfer['task_ids']))
        self.assertTrue(transfer['amr_onboard'])

    def test_missing_reposition_endpoints_are_explicitly_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            detail = extract_lift_movements(self.source(folder, [dict(
                sim_time_sec=0, lift_id='Lift-1', segment_type='lift_reposition',
                from_location='Waiting node', to_location='Waiting node',
                start_floor=2, end_floor=2, duration_sec=10,
                details='not json',
            )]))
        self.assertEqual('Unknown', detail.iloc[0].origin_level)
        self.assertEqual('Unknown', detail.iloc[0].destination_location)

    def test_negative_floors_and_event_only_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            detail = extract_lift_movements(self.source(folder, [dict(
                sim_time_sec=0, lift_id='Lift-2', event_type='segment_lift_transfer',
                from_location='Lift-2-F-1', to_location='Lift-2-F2', duration_sec=10,
            )]))
        self.assertEqual('L-01', detail.iloc[0].origin_level)
        self.assertEqual('L02', detail.iloc[0].destination_level)
        self.assertEqual('Up', detail.iloc[0].direction)

    def test_no_lift_segments_returns_header_only_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            detail = extract_lift_movements(self.source(folder, [dict(
                sim_time_sec=0, event_type='task_generated', task_id='T1', amr_id='',
            )]))
        self.assertTrue(detail.empty)
        self.assertIn('destination_location', detail.columns)
        self.assertIn('travel_distance_m', detail.columns)

    def test_csv_only_cli_writes_custom_destination_without_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'exports' / 'lift_travel.csv'
            pdf = Path(folder) / 'unused.pdf'
            script = Path(__file__).resolve().parents[1] / 'report' / 'amr_report_main.py'
            result = subprocess.run([
                sys.executable, str(script), str(source), '--output', str(pdf),
                '--lift-travel-csv', str(target), '--lift-csv-only',
            ], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(pdf.exists())
            self.assertEqual([target], list(target.parent.iterdir()))
            self.assertEqual(2, len(pd.read_csv(target)))
            self.assertIn('Lift travel CSV written', result.stdout)

    def test_onboard_weights_use_config_instances_and_sum_distinct_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            data = pd.read_csv(source)
            data['amr_id'] = 'AMR-C-2'
            data['onboard_payloads'] = json.dumps([
                {'payload': 'Trolley', 'payload_instance_id': 'P1'},
                {'payload': 'Trolley', 'payload_instance_id': 'P2'},
                {'payload': 'Trolley', 'payload_instance_id': 'P1'},
            ])
            data.to_csv(source, index=False)
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps({
                'amrs': [{'id': 'AMR-C', 'quantity': 2, 'weight_kg': 135, 'payload_capacity_kg': 500}],
                'payloads': [{'name': 'Trolley', 'weight_kg': 80}],
            }))
            detail = extract_lift_movements(source, config)
        reposition, transfer = detail.to_dict('records')
        self.assertTrue(pd.isna(reposition['payload_weight_kg']))
        self.assertTrue(pd.isna(reposition['amr_weight_kg']))
        self.assertEqual(160, transfer['payload_weight_kg'])
        self.assertEqual(135, transfer['amr_weight_kg'])

    def test_empty_amr_approach_does_not_count_its_future_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, [dict(
                sim_time_sec=0, amr_id='AMR-1', lift_id='Lift-1',
                segment_type='lift_transfer', duration_sec=20,
                payload='Future collection', onboard_payloads='[]',
            )])
            detail = extract_lift_movements(source)
        self.assertEqual(0, detail.iloc[0].payload_weight_kg)
        self.assertTrue(pd.isna(detail.iloc[0].amr_weight_kg))

    def test_unknown_and_suppressed_loads_remain_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            common = dict(sim_time_sec=0, amr_id='AMR-1', lift_id='Lift-1',
                          segment_type='lift_transfer', duration_sec=20)
            source = self.source(folder, [
                dict(common, onboard_payloads='[{"payload": "Unknown type"}]'),
                dict(common, onboard_payloads='[]', scenario_mode=True),
                dict(common, payload='Task payload'),
            ])
            detail = extract_lift_movements(source)
        self.assertTrue(detail.payload_weight_kg.isna().all())
        self.assertTrue(detail.amr_weight_kg.isna().all())

    def test_explicit_logged_weights_take_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, [dict(
                sim_time_sec=0, amr_id='AMR-1', lift_id='Lift-1',
                segment_type='lift_transfer', duration_sec=20,
                payload_weight_kg=45.5, amr_weight_kg=100,
            )])
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps({'amrs': [{'id': 'AMR', 'quantity': 1, 'weight_kg': 99}]}))
            detail = extract_lift_movements(source, config)
        self.assertEqual(45.5, detail.iloc[0].payload_weight_kg)
        self.assertEqual(100, detail.iloc[0].amr_weight_kg)


if __name__ == '__main__':
    unittest.main()
