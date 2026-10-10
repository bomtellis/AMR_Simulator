import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd
from report.amr_department_review import build_department_reviews, export_department_reviews


def configuration():
    return {
        'simulation': {'start_datetime': '2026-01-05T05:00:00', 'end_datetime': '2026-01-12T05:00:00'},
        'locations': [{'name': name, 'floor': 1} for name in ['Hub', 'Ward', 'Zone']],
        'payloads': [{'name': 'Trolley'}],
        'departments': [{'id': 'D1', 'name': 'Ward', 'enabled': True, 'floor': 1,
                         'operating_start_time': '00:00', 'operating_end_time': '24:00',
                         'task_generation_locations': {'linen': {'pickup_dropoff_locations': ['Ward'], 'dropoff_zone_locations': ['Zone']}}}],
        'task_generation': {'enabled': True, 'categories': {
            'linen': {'enabled': False, 'pickup_location': 'Hub', 'payload': 'Trolley', 'return_enabled': True,
                      'departments': {'D1': {'enabled': True, 'generation_mode': 'scheduled', 'schedule_times': ['08:00']}}},
            'ssd': {'enabled': False, 'departments': {}}}},
    }


def log_rows():
    task = 'GEN_LINEN_D1_00001'
    def row(event, time, tid=task, **kwargs):
        return dict(task_id=tid, event_type=event, sim_datetime=time, duration_sec=0, **kwargs)
    return [
        row('task_generated', '2026-01-05 08:00:10', department_id='D1', from_location='Hub', to_location='Zone',
            payload='Trolley', details='Generated scheduled linen task at 08:00; final destination=Ward'),
        dict(row('segment_dropoff', '2026-01-05 08:10:00'), duration_sec=20),
        row('task_complete', '2026-01-05 08:10:20'),
        dict(row('staff_payload_transport', '2026-01-05 08:12:00', from_location='Zone', to_location='Ward'), duration_sec=60),
        row('return_task_generated', '2026-01-05 09:00:00', 'RETURN-GEN_LINEN_D1_00001-1', from_location='Zone', to_location='Hub',
            details='Generated delayed return for ' + task, task_source='task_generation_return'),
        dict(row('segment_pickup', '2026-01-05 09:10:00', 'RETURN-GEN_LINEN_D1_00001-1'), duration_sec=20),
        row('task_complete', '2026-01-05 09:30:00', 'RETURN-GEN_LINEN_D1_00001-1'),
        row('task_assigned', '2026-01-05 10:00:00', 'RETURN-AMR-A-1-1'),
        row('segment_pickup', '2026-01-05 10:00:00', 'RETURN-AMR-A-1-1'),
        row('task_complete', '2026-01-05 10:30:00', 'RETURN-AMR-A-1-1'),
    ]


class DepartmentReviewTests(unittest.TestCase):
    def test_completed_services_use_final_delivery_and_actual_return_pickup(self):
        model = build_department_reviews(configuration(), pd.DataFrame(log_rows()))
        review = model['categories']['linen']
        self.assertEqual((1, 1, 2), (review['total_deliveries'], review['total_collections'], len(review['events'])))
        events = {e['service']: e for e in review['events']}
        self.assertEqual('2026-01-05 08:13:00', events['Delivery']['actual'])
        self.assertEqual('2026-01-05 09:10:20', events['Collection']['actual'])
        self.assertEqual('D1', events['Collection']['department_id'])
        self.assertEqual('L01', events['Delivery']['level'])
        self.assertEqual(24, model['common']['coverage_hours']['Mon'])
        self.assertEqual(0, model['categories']['ssd']['total_deliveries'])

    def test_group_override_replaces_department_schedule_and_not_release_stagger(self):
        cfg = configuration()
        cfg['task_generation']['categories']['linen']['department_groups'] = [
            {'id': 'weekend', 'departments': ['D1'], 'payload': {'enabled': True, 'generation_mode': 'scheduled',
                                                               'schedule_times': ['11:00'], 'days_active': ['sat']}}]
        model = build_department_reviews(cfg, pd.DataFrame(log_rows()))
        times = [t['time'] for t in model['categories']['linen']['timetable'] if t['kind'] == 'Scheduled release']
        self.assertEqual(['2026-01-10 11:00:00'], times)

    def test_incomplete_and_end_boundary_are_not_counted_and_duplicate_completion_is_safe(self):
        rows = log_rows()
        rows.append(copy.deepcopy(rows[2]))
        # Service completes exactly at reporting end, even though generated earlier.
        rows += [dict(rows[0], task_id='GEN_LINEN_D1_00002'),
                 dict(rows[1], task_id='GEN_LINEN_D1_00002', sim_datetime='2026-01-12 04:59:40'),
                 dict(rows[2], task_id='GEN_LINEN_D1_00002', sim_datetime='2026-01-12 05:00:00'),
                 dict(rows[0], task_id='GEN_LINEN_D1_00003'), dict(rows[1], task_id='GEN_LINEN_D1_00003')]
        model = build_department_reviews(configuration(), pd.DataFrame(rows))['categories']['linen']
        self.assertEqual(1, model['total_deliveries'])
        self.assertEqual(4, len(model['events']))
        self.assertEqual(1, sum(e['status'] == 'Not completed' for e in model['events']))

    def test_collection_category_empty_return_is_a_delivery(self):
        cfg = configuration()
        rows = log_rows()[:3]
        rows[0].update(from_location='Ward', to_location='Hub', details='Generated threshold linen task')
        rows[1].update(event_type='segment_pickup')
        model = build_department_reviews(cfg, pd.DataFrame(rows))['categories']['linen']
        self.assertEqual((0, 1), (model['total_deliveries'], model['total_collections']))
        self.assertEqual('threshold', model['events'][0]['trigger'])

    def test_pdf_only_cli_exports_separate_categories_without_main_report(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            config = folder / 'config.json'
            config.write_text(json.dumps(configuration()), encoding='utf-8')
            csv = folder / 'events.csv'
            pd.DataFrame(log_rows()).to_csv(csv, index=False)
            output = folder / 'reviews'
            result = subprocess.run([sys.executable, 'report/amr_report_main.py', str(csv), '--config-json', str(config),
                '--department-review-only', '--department-review-formats', 'pdf', '--department-review-dir', str(output)],
                capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(['linen_department_review.pdf', 'linen_executive_summary.pdf',
                              'ssd_department_review.pdf', 'ssd_executive_summary.pdf'], sorted(p.name for p in output.glob('*')))
            self.assertFalse((folder / 'events_report.pdf').exists())
            self.assertFalse(list(folder.glob('*lift*.csv')))

    def test_missing_verbose_events_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'verbose'):
            build_department_reviews(configuration(), pd.DataFrame([{'task_id': 'x'}]))

    def test_tracked_exchange_is_not_labelled_as_a_return(self):
        rows = log_rows()
        rows[0]['details'] = 'Generated tracked item exchange for Bed sheet at Ward'
        review = build_department_reviews(configuration(), pd.DataFrame(rows))['categories']['linen']
        primary = next(e for e in review['events'] if not e['parent_task'])
        self.assertEqual('tracked item exchange', primary['trigger'])

    def test_executive_page_contains_all_events_and_is_exactly_one_a4_page(self):
        from pypdf import PdfReader
        from report.amr_department_executive import executive_data, export_executive_pdf
        from report.amr_department_review import export_department_pdf
        model = build_department_reviews(configuration(), pd.DataFrame(log_rows()))
        review = model['categories']['linen']
        data = executive_data(review, model['common'])
        self.assertEqual(2, data['generated'])
        self.assertEqual(['08:00'], data['scheduled_times'])
        self.assertEqual(2 + len(review['timetable']), sum(len(points) for points in data['points'].values()))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'executive.pdf'
            export_executive_pdf(review, model['common'], path)
            result = PdfReader(path)
            self.assertEqual(1, len(result.pages))
            self.assertAlmostEqual(595.28, float(result.pages[0].mediabox.width), places=1)
            self.assertAlmostEqual(841.89, float(result.pages[0].mediabox.height), places=1)
            self.assertIn('Weekly event timeline', result.pages[0].extract_text())
            self.assertIn('Scheduled times: 08:00', result.pages[0].extract_text())
            full = Path(folder) / 'full.pdf'
            export_department_pdf(review, model['common'], full)
            result = PdfReader(full)
            self.assertAlmostEqual(595.28, float(result.pages[0].mediabox.width), places=1)
            self.assertAlmostEqual(841.89, float(result.pages[1].mediabox.width), places=1)
            self.assertIn('Executive summary', result.pages[0].extract_text())

    def test_long_period_executive_timeline_retains_every_event(self):
        from report.amr_department_executive import executive_data
        cfg = configuration()
        cfg['simulation']['end_datetime'] = '2026-02-12T05:00:00'
        model = build_department_reviews(cfg, pd.DataFrame(log_rows()))
        review = model['categories']['linen']
        data = executive_data(review, model['common'])
        self.assertTrue(data['weekly'])
        self.assertEqual(7, len(data['keys']))
        self.assertEqual(2 + len(review['timetable']), sum(len(points) for points in data['points'].values()))


if __name__ == '__main__':
    unittest.main()
