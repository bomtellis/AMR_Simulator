"""Independent arithmetic and lifecycle edge cases for operational KPIs."""
import json
import unittest

import pandas as pd

from report.amr_report_analysis import parse_time_column
from report.amr_report_kpis import build_kpis


class ReportKpiTests(unittest.TestCase):
    def event(self, time, kind, task='', amr='', **kwargs):
        return dict(sim_time_sec=time, event_type=kind, task_id=task or None,
                    amr_id=amr or None, **kwargs)

    def build(self, events, tasks, config=None, **kwargs):
        frame, ctx = parse_time_column(pd.DataFrame(events))
        frame['_event_text'] = frame.event_type.fillna('')
        frame['_duration_s'] = pd.to_numeric(frame.get('duration_sec', pd.Series(0., index=frame.index)), errors='coerce')
        frame['_distance_m'] = pd.to_numeric(frame.get('distance_m', pd.Series(0., index=frame.index)), errors='coerce')
        tasks = pd.DataFrame([dict(task_id=name, origin='Stores', destination='Ward',
                                  payload='Box', target_s=target) for name, target in tasks])
        return build_kpis(frame, ctx, tasks, kwargs.pop('journeys', pd.DataFrame()),
                          config=config or {'amrs': [{'quantity': 2}]}, **kwargs)

    def value(self, result, name):
        return result['kpi_summary'].set_index('metric').loc[name, 'value']

    def test_request_peak_includes_queue_and_overdue_unfinished_work(self):
        events = [self.event(0, 'task_generated', 'GEN_LINEN_1'),
            self.event(0, 'task_generated', 'GEN_LINEN_2'),
            self.event(0, 'task_generated', 'GEN_WASTE_3'),
            self.event(10, 'task_assigned', 'GEN_LINEN_1', 'A'),
            self.event(10, 'task_assigned', 'GEN_LINEN_2', 'A'),
            self.event(100, 'task_complete', 'GEN_LINEN_1', 'A'),
            self.event(200, 'task_complete', 'GEN_LINEN_2', 'A'),
            self.event(3600, 'scenario_summary')]
        result = self.build(events, [('GEN_LINEN_1', 150), ('GEN_LINEN_2', 150), ('GEN_WASTE_3', 300)])
        self.assertEqual(3, self.value(result, 'Peak concurrent demand'))
        self.assertEqual(3, self.value(result, 'Task requests per hour'))
        self.assertEqual(150, self.value(result, 'Request to delivery time'))
        self.assertEqual(195, self.value(result, '95th percentile delivery time'))
        self.assertAlmostEqual(100/3, self.value(result, 'Service level compliance'))
        self.assertEqual(2, self.value(result, 'Overdue tasks'))
        self.assertEqual({'GEN_LINEN_2', 'GEN_WASTE_3'}, set(result['kpi_overdue'].task_id))
        # Two tasks share one vehicle: 190 seconds, not 90 + 190.
        self.assertAlmostEqual(190/7200*100, self.value(result, 'Fleet utilisation'))
        self.assertAlmostEqual(2*3600/190, self.value(result, 'Deliveries per hour'))
        self.assertEqual(1, self.value(result, 'Vehicles required'))
        self.assertEqual(50, self.value(result, 'Peak utilisation'))

    def test_shared_movement_empty_containers_and_duplicate_events(self):
        events = [self.event(0, 'task_released', name) for name in ('T1', 'T2')]
        events += [self.event(0, 'multi_stop_task_assigned', name, 'A') for name in ('T1', 'T2')]
        empty = self.event(0, 'multi_stop_segment_corridor', 'T1,T2', 'A', event_id='E',
            segment_type='corridor', duration_sec=10, distance_m=20, onboard_payloads='[]')
        loaded = self.event(10, 'multi_stop_segment_corridor', 'T1,T2', 'A', event_id='L',
            segment_type='corridor', duration_sec=20, distance_m=80,
            onboard_payloads=json.dumps([{'payload': 'Empty linen trolley'}]))
        events += [empty, empty.copy(), loaded]
        events += [self.event(30, 'task_complete', name, 'A') for name in ('T1', 'T2')]
        events += [self.event(100, 'scenario_summary')]
        result = self.build(events, [('T1', None), ('T2', None)])
        self.assertEqual(20, self.value(result, 'Empty running percentage'))
        self.assertEqual(50, self.value(result, 'Distance per delivery'))
        self.assertEqual(10, self.value(result, 'Productive utilisation'))
        self.assertEqual(100, result['kpi_routes'].allocated_distance_m.sum())
        self.assertTrue(pd.isna(self.value(result, 'Service level compliance')))

    def test_partial_run_clips_future_plans_and_preserves_pending_status(self):
        events = [self.event(0, 'task_released', 'T1'), self.event(0, 'task_assigned', 'T1', 'A'),
            self.event(50, 'segment_corridor', 'T1', 'A', segment_type='corridor',
                       duration_sec=100, distance_m=100, onboard_payloads='[]'),
            self.event(500, 'segment_corridor', 'T1', 'A', segment_type='corridor',
                       duration_sec=100, distance_m=100, onboard_payloads='[]'),
            self.event(100, 'battery_balance_summary', amr='A')]
        result = self.build(events, [('T1', 50)])
        self.assertEqual(100, result['kpi_observation']['horizon_s'])
        self.assertEqual(50, self.value(result, 'Fleet utilisation'))
        self.assertEqual(1, self.value(result, 'Overdue tasks'))
        self.assertEqual('incomplete', result['kpi_requests'].iloc[0].outcome)
        self.assertTrue(pd.isna(self.value(result, 'Energy per delivery')))

    def test_release_column_survives_assignment_fallback_and_custom_stream_mapping(self):
        events = [self.event(0, 'scenario_summary'),
            self.event(100, 'task_assigned', 'Manual', 'A', task_release_time_sec=10),
            self.event(200, 'task_complete', 'Manual', 'A'), self.event(3600, 'scenario_summary')]
        result = self.build(events, [('Manual', 250)], config={'amrs': [{'quantity': 2}],
            'report_kpis': {'task_streams': {'Manual': 'receipt and distribution'}}})
        self.assertEqual(190, self.value(result, 'Request to delivery time'))
        self.assertEqual('Receipt and distribution', result['kpi_requests'].iloc[0].stream)
        self.assertEqual(90, self.value(result, 'Queue time'))

    def test_costs_and_reliability_need_complete_period_inputs(self):
        events = [self.event(0, 'task_released', 'T'), self.event(0, 'task_assigned', 'T', 'A'),
                  self.event(60, 'task_complete', 'T', 'A'), self.event(3600, 'scenario_summary')]
        inputs = {'costs': {'currency': 'GBP', 'labour_cost': 20, 'total_operating_cost': 50},
                  'reliability': {'planned_vehicle_hours': 20, 'unavailable_vehicle_hours': 2,
                      'planned_fms_hours': 10, 'unavailable_fms_hours': .5, 'operating_hours': 18,
                      'failure_count': 2, 'repair_durations_hours': [.5, 1.5]}}
        result = self.build(events, [('T', None)], config={'amrs': [{'quantity': 2}], 'report_kpis': inputs})
        self.assertEqual(50, self.value(result, 'Cost per delivery'))
        self.assertEqual(20, self.value(result, 'Labour cost per delivery'))
        self.assertEqual(90, self.value(result, 'Availability'))
        self.assertEqual(9, self.value(result, 'Mean time between failures'))
        self.assertEqual(1, self.value(result, 'Mean time to repair'))
        result = self.build(events, [('T', None)])
        for name in ('Cost per delivery', 'Availability', 'Mean time between failures', 'Mean time to repair'):
            self.assertTrue(pd.isna(self.value(result, name)))

    def test_no_service_requests_does_not_turn_missing_evidence_into_zero(self):
        result = self.build([self.event(0, 'initial_charge_location', amr='A'),
            self.event(100, 'scenario_summary')], [])
        self.assertEqual(0, self.value(result, 'Task requests per hour'))
        for name in ('Cost per delivery', 'Failed task percentage', '95th percentile delivery time', 'Charger wait time'):
            self.assertTrue(pd.isna(self.value(result, name)))
        self.assertEqual(5, len(result['kpi_streams']))

    def test_lift_and_charger_waits_and_charge_headroom(self):
        events = [self.event(0, 'task_released', 'T'), self.event(0, 'task_assigned', 'T', 'A'),
            self.event(0, 'segment_lift_reposition', 'T', 'A', segment_type='lift_reposition',
                       duration_sec=10, lift_id='L'),
            self.event(10, 'segment_wait_for_charger', amr='B', segment_type='wait_for_charger', duration_sec=20),
            self.event(30, 'segment_charge', amr='B', segment_type='charge', duration_sec=20, to_location='Bay'),
            self.event(60, 'task_complete', 'T', 'A'), self.event(100, 'scenario_summary')]
        result = self.build(events, [('T', 100)])
        self.assertEqual(10, self.value(result, 'Lift waiting time'))
        self.assertEqual(20, self.value(result, 'Charger wait time'))
        self.assertEqual(0, self.value(result, 'Spare capacity and headroom'))
        self.assertEqual(2, self.value(result, 'Charging infrastructure required'))

    def test_request_route_survives_multi_stop_leg_endpoint_overrides(self):
        events = [self.event(0, 'task_released', 'T'), self.event(0, 'task_assigned', 'T', 'A'),
                  self.event(100, 'task_complete', 'T', 'A')]
        journeys = pd.DataFrame([dict(task_id='T', journey_type='Delivery / other',
                                     origin_location='Actual origin', destination_location='Actual destination')])
        result = self.build(events, [('T', None)], journeys=journeys)
        self.assertEqual('Actual origin', result['kpi_routes'].iloc[0].origin)
        self.assertEqual('Actual destination', result['kpi_routes'].iloc[0].destination)

    def test_missing_load_state_does_not_claim_productive_or_empty_running(self):
        events = [self.event(0, 'task_released', 'T'), self.event(0, 'task_assigned', 'T', 'A'),
                  self.event(0, 'segment_corridor', 'T', 'A', segment_type='corridor',
                             duration_sec=10, distance_m=20), self.event(10, 'task_complete', 'T', 'A')]
        result = self.build(events, [('T', None)])
        self.assertTrue(pd.isna(self.value(result, 'Productive utilisation')))
        self.assertTrue(pd.isna(self.value(result, 'Empty running percentage')))

    def test_cancelled_and_staff_completed_exceptions_count_as_failures(self):
        events = [self.event(0, 'task_released', 'Cancel'), self.event(0, 'task_released', 'Staff'),
                  self.event(100, 'task_cancelled', 'Cancel'), self.event(200, 'task_staff_completed', 'Staff'),
                  self.event(300, 'scenario_summary')]
        result = self.build(events, [('Cancel', 50), ('Staff', 250)])
        self.assertEqual(100, self.value(result, 'Failed task percentage'))
        self.assertEqual(1, self.value(result, 'Overdue tasks'))

    def test_empty_vehicle_return_does_not_count_as_logistics_demand(self):
        events = [self.event(0, 'task_assigned', 'RETURN-A-1', 'A'),
                  self.event(100, 'task_complete', 'RETURN-A-1', 'A')]
        result = self.build(events, [('RETURN-A-1', None)], journeys=pd.DataFrame([
            dict(task_id='RETURN-A-1', journey_type='Empty AMR return')]))
        self.assertEqual(0, self.value(result, 'Task requests per hour'))
        self.assertEqual(0, self.value(result, 'Peak concurrent demand'))

    def test_reduced_logging_payload_placeholders_do_not_mean_empty_running(self):
        events = [self.event(0, 'task_released', 'T'), self.event(0, 'task_assigned', 'T', 'A'),
            self.event(0, 'segment_corridor', 'T', 'A', segment_type='corridor',
                       duration_sec=10, distance_m=20, onboard_payloads='[]'),
            self.event(10, 'task_complete', 'T', 'A'),
            self.event(20, 'scenario_impact_summary', details=json.dumps(
                {'scenario_mode': True, 'enhanced_logging': False}))]
        result = self.build(events, [('T', None)])
        self.assertTrue(pd.isna(self.value(result, 'Productive utilisation')))
        self.assertTrue(pd.isna(self.value(result, 'Empty running percentage')))

    def test_legacy_failure_without_request_event_is_preserved_and_flagged(self):
        events = [self.event(0, 'scenario_impact_summary'), self.event(100, 'task_failed', 'T'),
                  self.event(300, 'scenario_impact_summary')]
        result = self.build(events, [('T', None)])
        self.assertEqual(100, self.value(result, 'Failed task percentage'))
        self.assertEqual(1, result['kpi_observation']['request_time_fallbacks'])

    def test_charger_queue_coverage_can_establish_zero_wait(self):
        events = [self.event(0, 'initial_charge_location', amr='A'), self.event(100, 'scenario_impact_summary',
            details=json.dumps({'charger_queue_intervals_complete': True}))]
        result = self.build(events, [])
        self.assertEqual(0, self.value(result, 'Charger wait time'))

    def test_pending_request_at_cutoff_is_included_in_concurrent_demand(self):
        events = [self.event(0, 'scenario_impact_summary'), self.event(100, 'task_generated', 'T'),
                  self.event(100, 'scenario_impact_summary')]
        result = self.build(events, [('T', None)])
        self.assertEqual(1, self.value(result, 'Peak concurrent demand'))

    def test_complete_supplied_staff_hours_support_labour_cost_without_handling_logs(self):
        events = [self.event(0, 'task_released', 'T'), self.event(100, 'task_complete', 'T')]
        result = self.build(events, [('T', None)], config={'report_kpis': {
            'total_staff_hours': 2, 'costs': {'staff_hourly_rate': 15}}})
        self.assertEqual(2, self.value(result, 'Staff hours required'))
        self.assertEqual(30, self.value(result, 'Labour cost per delivery'))

    def test_fleet_dispatch_wait_reasons_are_attached_only_to_named_overdue_tasks(self):
        events = [self.event(0, 'task_released', 'T1'), self.event(0, 'task_released', 'T2'),
            self.event(10, 'task_wait', details='At start of assignment wait: T1: No AMR available; T2: No payload available'),
            self.event(100, 'scenario_impact_summary')]
        result = self.build(events, [('T1', 5), ('T2', 5)])
        reasons = result['kpi_overdue'].set_index('task_id').reason
        self.assertEqual('No AMR available', reasons['T1'])
        self.assertEqual('No payload available', reasons['T2'])


class ChargerQueueEvidenceTests(unittest.TestCase):
    def test_finite_bay_retries_preserve_start_and_resolution_records_elapsed_time(self):
        from tests.test_charger_contention import prepared
        sim = prepared()
        first, second = sim.amrs
        self.assertTrue(sim._schedule_charge_cycle(first, 0))
        self.assertFalse(sim._schedule_charge_cycle(second, 1))
        self.assertFalse(sim._schedule_charge_cycle(second, 3))
        self.assertEqual(1, sim._charger_queue_waits[second.id]['start'])
        sim._free_amr_inventory_space(first)
        self.assertTrue(sim._schedule_charge_cycle(second, 5))
        intervals = [r for r in sim.verbose_rows if r['event_type'] == 'segment_wait_for_charger']
        self.assertEqual(1, len(intervals))
        self.assertEqual(4, intervals[0]['duration_sec'])
        self.assertEqual(second.id, intervals[0]['amr_id'])

    def test_open_waits_are_recorded_without_double_counting_repeated_exports(self):
        from tests.test_charger_contention import prepared
        sim = prepared()
        self.assertTrue(sim._schedule_charge_cycle(sim.amrs[0], 0))
        self.assertFalse(sim._schedule_charge_cycle(sim.amrs[1], 1))
        for now in (10, 20, 20):
            sim.current_time = now
            sim._flush_charger_queue_waits()
        intervals = [r for r in sim.verbose_rows if r['event_type'] == 'segment_wait_for_charger']
        self.assertEqual([9, 10], [r['duration_sec'] for r in intervals])
        sim._evidence_run_status = 'cancelled'
        sim.current_time = 30
        sim._flush_charger_queue_waits()
        self.assertFalse(sim._charger_queue_waits)
        intervals = [r for r in sim.verbose_rows if r['event_type'] == 'segment_wait_for_charger']
        self.assertEqual(29, sum(r['duration_sec'] for r in intervals))


if __name__ == '__main__':
    unittest.main()
