"""Independent physical-instance and service-handoff reference cases."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from amr_results_investigation import load_investigation
from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def service_config():
    config = reference_config()
    config['building']['edge_slowdown_per_amr'] = 0
    config['locations'][1]['inventory_spaces'] = [
        dict(name='Finite bin bay', length_m=2, width_m=2, height_m=2,
             flexible=True, payload_slots=[dict(payload='Box')])]
    config['mass_collections'] = [dict(id='Rotation', location='B', payloads=['Box'],
                                       scheduled_times=[], capacity_trigger_count=0)]
    return config


def seeded_service_config():
    config = service_config()
    config['simulation']['seed_waste_stream_containers_at_start'] = True
    config['waste_streams'] = [dict(name='Clinical', payload='Box', container_capacity_m3=1,
                                   full_threshold_fraction=1)]
    config['departments'] = [dict(id='D', enabled=True, waste_pickup_locations=['A'],
                                  waste_streams=[dict(name='Clinical', initial_container_present=True)])]
    config['task_generation'] = dict(enabled=True, update_interval_sec=60, categories={
        'service': dict(enabled=True, generation_mode='scheduled', scheduled_times=['00:01'],
                        pickup_location='A', dropoff_location='B', payload='Box', waste_stream='Clinical',
                        staff_handling_minutes=0, staff_collection_delay_minutes=0)})
    return config


class PayloadConservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / 'simulation_steps.csv'

    def run_cycle(self, delay_minutes=0, *, rotation=True):
        config = service_config()
        if not rotation:
            config['mass_collections'] = []
            config['locations'][1].pop('inventory_spaces')
        sim = Simulation(config, verbose=True, verbose_csv_path=str(self.log))
        # One independently specified department bin, separate from the finite
        # store's seeded exchange stock. No expected ID is taken from output.
        sim.payload_instance_store.store('A', 'Box', 'BIN-1', metadata={'container_state': 'empty'})
        sim._log_payload_location_event('location_payload_enter', 'A', 'Box', 'BIN-1')
        task = Task('COLLECT', 'A', 'B', 'Box', payload_instance_id='BIN-1',
                    waste_stream='Clinical', return_enabled=True, return_payload='Box',
                    return_delay_minutes=delay_minutes)
        task.requires_existing_payload_instance = True
        task.return_same_payload_instance = True
        sim.schedule_task_release(task)
        initial_store_ids = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        with self.log.open(encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        return sim, rows, initial_store_ids

    def test_same_bin_service_cycle_has_two_transfers_and_no_tracking_conflict(self):
        sim, rows, _initial = self.run_cycle()
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual([9, 9], [r['duration_sec'] for r in sim.completed_task_records])
        movement = [r for r in rows if r['payload_instance_id'] == 'BIN-1' and
                    r['event_type'] in {'location_payload_enter', 'location_payload_exit', 'payload_service_arrival'}]
        self.assertEqual([
            ('location_payload_enter', 'A', 0),
            ('location_payload_exit', 'A', 2),
            ('payload_service_arrival', 'B', 9),
            ('location_payload_exit', 'B', 11),
            ('location_payload_enter', 'A', 18),
        ], [(r['event_type'], r['to_location'], float(r['sim_time_sec'])) for r in movement])
        report = load_investigation(self.log)
        metrics = {m['key']: m for m in report['metrics']}
        self.assertEqual(2, metrics['payload_moves']['value'])
        self.assertEqual('full bound log', metrics['payload_moves']['coverage'])
        self.assertEqual(0, metrics['payload_tracking_conflicts']['observed_count'])
        self.assertEqual(0, metrics['payload_unpaired_exits']['observed_count'])
        self.assertEqual(1, metrics['payload_service_arrivals']['value'])
        self.assertEqual([movement[2]['event_id']], metrics['payload_service_arrivals']['event_ids'])

    def test_service_arrival_never_adds_the_bin_to_finite_storage(self):
        sim, rows, initial_store_ids = self.run_cycle(delay_minutes=1)
        self.assertEqual(1, len(initial_store_ids))
        self.assertEqual(initial_store_ids, {r.instance_id for r in sim.payload_instance_store.records_at('B')})
        self.assertEqual(['BIN-1'], [r.instance_id for r in sim.payload_instance_store.records_at('A')])
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))
        self.assertEqual({'Box': 2}, sim.payload_instance_store.counts_by_payload())
        arrivals = [r for r in rows if r['event_type'] == 'payload_service_arrival']
        self.assertEqual(1, len(arrivals))
        self.assertEqual('', arrivals[0]['inventory_space'])
        self.assertEqual('payload_handling', arrivals[0]['status'])
        self.assertIn('not stored', arrivals[0]['details'])
        self.assertFalse(any(r['event_type'] == 'location_payload_enter' and
                             r['payload_instance_id'] == 'BIN-1' and r['to_location'] == 'B' for r in rows))

    def test_regular_dropoff_keeps_ordinary_storage_events(self):
        sim, rows, _initial = self.run_cycle(rotation=False)
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertFalse(any(r['event_type'] == 'payload_service_arrival' for r in rows))
        self.assertTrue(any(r['event_type'] == 'location_payload_enter' and r['to_location'] == 'B' for r in rows))
        report = load_investigation(self.log)
        self.assertEqual(2, next(m['value'] for m in report['metrics'] if m['key'] == 'payload_moves'))
        self.assertEqual(0, next(m['value'] for m in report['metrics'] if m['key'] == 'payload_service_arrivals'))

    def test_legacy_log_without_service_capability_does_not_claim_zero_service_arrivals(self):
        self.log.write_text('event_type,sim_time_sec,task_id\ntask_complete,9,T\n', encoding='utf-8')
        report = load_investigation(self.log)
        metric = next(m for m in report['metrics'] if m['key'] == 'payload_service_arrivals')
        self.assertIsNone(metric['value'])
        self.assertEqual('partial or unknown coverage', metric['coverage'])

    def test_service_arrival_retained_in_playback_without_becoming_storage(self):
        sim, rows, _initial = self.run_cycle()
        playback = Path(self.temp.name) / 'playback.csv'
        with contextlib.redirect_stdout(io.StringIO()):
            sim.write_visualiser_csv(str(playback))
        with playback.open(encoding='utf-8') as stream:
            arrivals = [r for r in csv.DictReader(stream) if r['event_type'] == 'payload_service_arrival']
        self.assertEqual(1, len(arrivals))
        self.assertEqual(next(r['event_id'] for r in rows if r['event_type'] == 'payload_service_arrival'),
                         arrivals[0]['event_id'])
        self.assertEqual('', arrivals[0]['inventory_space'])

    def test_playback_does_not_treat_service_arrival_as_inventory_pickup_or_dropoff(self):
        from visualiser.amr_sim_visualiser_pyside6 import SimulationVisualizer
        row = dict(event_type='payload_service_arrival', status='payload_handling', payload='Box')
        self.assertEqual('', SimulationVisualizer._inventory_physical_payload_event_kind(None, row))

    def test_reduced_scenario_logging_keeps_service_evidence_omitted(self):
        config = service_config()
        config['scenario_testing'] = dict(enabled=True, active_scenario='Quiet', enhanced_logging=False,
                                           scenarios=[dict(name='Quiet', events=[])])
        sim = Simulation(config, verbose=True)
        self.assertTrue(sim.scenario_mode)
        sim._log_payload_service_arrival(Task('T', 'A', 'B', 'Box', payload_instance_id='BIN-1'), 9)
        self.assertFalse(any(r['event_type'] == 'payload_service_arrival' for r in sim.verbose_rows))

    def test_generated_seeded_service_cycle_conserves_original_bin_and_stock(self):
        scenario = Path(__file__).resolve().parents[1] / 'verification/scenarios/payload-service-return.json'
        sim = Simulation(json.loads(scenario.read_text(encoding='utf-8')), verbose=True, verbose_csv_path=str(self.log))
        original = {r.instance_id for r in sim.payload_instance_store.records_at('A')}
        stock = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        self.assertEqual((1, 1), (len(original), len(stock)))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual([9, 9], [r['duration_sec'] for r in sim.completed_task_records])
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        self.assertEqual(stock, {r.instance_id for r in sim.payload_instance_store.records_at('B')})
        self.assertEqual(original | stock, set(sim.payload_instance_store._known_instances))
        report = load_investigation(self.log)
        self.assertEqual(2, next(m['value'] for m in report['metrics'] if m['key'] == 'payload_moves'))

    def test_review_example_survives_editor_normalisation_and_preflight(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/payload-service-return.json'
        config = JsonStore(json.loads(path.read_text(encoding='utf-8'))).data
        report = check_project(config)
        self.assertEqual([], [f.message for f in report.findings if f.severity == 'error'])
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual([9, 9], [r['duration_sec'] for r in sim.completed_task_records])
        self.assertEqual([69, 78], [r['sim_time_sec'] for r in sim.verbose_rows if r['event_type'] == 'task_complete'])

    def test_multi_stop_service_arrivals_are_recorded_for_each_physical_bin(self):
        config = service_config()
        slot = dict(payload_capacity_kg=100, payload_length_capacity_m=2,
                    payload_width_capacity_m=2, payload_height_capacity_m=2)
        config['amrs'][0]['payload_slots'] = [dict(slot, name='One'), dict(slot, name='Two')]
        config['amrs'][0]['multi_stop_enabled'] = True
        sim = Simulation(config, verbose=True, verbose_csv_path=str(self.log))
        for index in (1, 2):
            instance_id = f'BIN-{index}'
            sim.payload_instance_store.store('A', 'Box', instance_id, metadata={'container_state': 'empty'})
            sim._log_payload_location_event('location_payload_enter', 'A', 'Box', instance_id)
            task = Task(f'COLLECT-{index}', 'A', 'B', 'Box', payload_instance_id=instance_id,
                        waste_stream='Clinical', task_source='task_generation',
                        return_enabled=True, return_payload='Box')
            task.requires_existing_payload_instance = True
            task.return_same_payload_instance = True
            sim.schedule_task_release(task)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        self.assertEqual(set(), sim.failed_task_ids)
        with self.log.open(encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(2, sum(r['event_type'] == 'multi_stop_task_assigned' for r in rows))
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual({'BIN-1', 'BIN-2'}, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        self.assertEqual({'BIN-1', 'BIN-2'}, {r['payload_instance_id'] for r in rows if r['event_type'] == 'payload_service_arrival'})
        report = load_investigation(self.log)
        self.assertEqual(4, next(m['value'] for m in report['metrics'] if m['key'] == 'payload_moves'))


if __name__ == '__main__':
    unittest.main()
