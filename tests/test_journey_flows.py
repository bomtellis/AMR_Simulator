import unittest

import pandas as pd

from report.amr_report_analysis import (
    build_journey_flows, build_lift_movement_detail, level_label, parse_time_column,
)


class JourneyFlowTests(unittest.TestCase):
    def build(self, rows, catalog=None):
        frame, ctx = parse_time_column(pd.DataFrame(rows))
        frame['_event_text'] = frame.event_type
        tasks = pd.DataFrame([
            {'task_id': task, 'amr': 'AMR-1', 'payload': 'Trolley', 'release': 0,
             # Simulate the existing multi-stop report overriding request endpoints.
             'origin': 'Previous ward', 'destination': 'Final stop'}
            for task in frame.task_id.unique()
        ])
        return build_journey_flows(frame, ctx, tasks, catalog)

    def event(self, task='T1', kind='task_assigned', **kwargs):
        return dict(sim_time_sec=0, task_id=task, amr_id='AMR-1', event_type=kind,
                    from_location='Stores', to_location='Ward', **kwargs)

    def test_request_endpoints_survive_multi_stop_and_return_links(self):
        delivery = self.event(start_floor=2, end_floor=4)
        completion = {**delivery, 'event_type': 'task_complete', 'sim_time_sec': 20,
                      'from_location': 'Final stop', 'to_location': 'Final stop'}
        ret = {**delivery, 'task_id': 'RETURN-T1-7', 'event_type': 'return_task_generated',
               'from_location': 'Shared zone', 'to_location': 'Stores',
               'start_floor': 3, 'end_floor': 2, 'task_source': 'task_generation_return',
               'details': 'Generated delayed return for T1'}
        catalog = pd.DataFrame([
            {'location': 'Stores', 'department': 'Supply', 'floor': 2},
            {'location': 'Ward', 'department': 'Surgery', 'floor': 4},
            {'location': 'Shared zone', 'department': 'Surgery, Medicine', 'floor': 3},
        ])
        detail, summary = self.build([delivery, completion, ret], catalog)
        d, r = detail.set_index('task_id').loc[['T1', 'RETURN-T1-7']].to_dict('records')
        self.assertEqual(('Stores', 'Ward', 'L02', 'L04'),
                         (d['origin_location'], d['destination_location'], d['origin_level'], d['destination_level']))
        self.assertEqual(('Return', 'T1', 'Shared zone', 'L03'),
                         (r['journey_type'], r['parent_task_id'], r['origin_location'], r['origin_level']))
        self.assertEqual('Surgery, Medicine', r['origin_department'])
        self.assertEqual('incomplete', r['outcome'])
        self.assertEqual('', r['completion_time'])
        self.assertEqual(2, summary.journeys.sum())

    def test_missing_config_keeps_logged_floors_and_unknown_departments(self):
        detail, _ = self.build([self.event(start_floor=0, end_floor=-1)])
        row = detail.iloc[0]
        self.assertEqual(('L00', 'L-01', 'Unknown', 'Yes'),
                         (row.origin_level, row.destination_level, row.origin_department, row.cross_level))
        self.assertIn('metadata incomplete', row.endpoint_quality)
        detail, _ = self.build([self.event()])
        self.assertEqual('Unknown', detail.iloc[0].origin_level)
        self.assertEqual('Unknown', detail.iloc[0].cross_level)

    def test_empty_return_is_distinct_from_payload_return(self):
        detail, _ = self.build([self.event(task='RETURN-AMR-1-3')])
        self.assertEqual('Empty AMR return', detail.iloc[0].journey_type)
        self.assertEqual('', detail.iloc[0].parent_task_id)

    def test_failed_and_pending_not_counted_as_completed(self):
        detail, summary = self.build([
            self.event(task='Failed'), self.event(task='Failed', kind='task_failed'),
            self.event(task='Pending', kind='task_generated'),
            self.event(task='Pending', kind='staff_handling_complete'),
        ])
        self.assertEqual({'failed', 'incomplete'}, set(detail.outcome))
        self.assertEqual(2, summary.journeys.sum())

    def test_grouped_task_row_does_not_duplicate_demand(self):
        detail, _ = self.build([self.event(task='T1'), self.event(task='T2'),
                                self.event(task='T1,T2')])
        self.assertEqual({'T1', 'T2'}, set(detail.task_id))

    def test_one_lift_movement_for_multiple_tasks_and_reposition(self):
        frame, ctx = parse_time_column(pd.DataFrame([
            self.event(task='T1,T2', start_floor=0, end_floor=3),
            self.event(task='', start_floor=3, end_floor=0),
        ]))
        frame['_lift_id'] = 'Lift-1'
        frame['_segment_text'] = ['lift_transfer', 'lift_reposition']
        frame['lift_time_s'] = 30
        frame['details'] = ['', '{"from": "Lift-1-F3", "to": "Lift-1-F0"}']
        result = build_lift_movement_detail(frame, ctx)
        self.assertEqual(2, len(result))
        self.assertEqual('T1,T2', result.iloc[0].task_ids)
        self.assertEqual('L03', result.iloc[1].origin_level)
        self.assertEqual('30s', result.iloc[0].finish_time)

    def test_named_levels_and_empty_outputs(self):
        self.assertEqual('LG', level_label('LG'))
        self.assertEqual('Unknown', level_label(None))
        detail, summary = self.build([self.event(kind='segment_charge')])
        self.assertTrue(detail.empty)
        self.assertIn('journeys', summary.columns)


if __name__ == '__main__':
    unittest.main()
