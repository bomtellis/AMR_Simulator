"""Independent route evidence, policy, comparison and saved-run contracts."""
import contextlib
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from amr_route_analysis import (load_analysis, compare_runs, Filters, export_comparison,
    SATISFIED, VIOLATION, UNKNOWN, DISABLED, CONFIRMED, PLANNED)
from amr_run_evidence import config_hash, file_hash
from simulator import Simulation
from tests.test_engineering_reference import reference_config


def analysis_config(forced=True):
    config = reference_config()
    config['building'].update(force_via_floor_enabled=forced, force_via_floor=2)
    config['locations'] = [dict(name=n, x=x, y=0, floor=f) for n,x,f in [('A',0,0),('B',10,0),('C',0,2),('D',10,3)]]
    config['lifts'] = [dict(id='L', transfer_timing_mode='fixed', boarding_time_sec=2,
        served_floors=[0,2,3], floor_locations={str(f):dict(x=5,y=0) for f in (0,2,3)})]
    config['corridors'] = dict(nodes=[], edges=[])
    return config


def segment(kind, origin, destination, start, duration=1, *, id=None, task='T', journey='J', amr='R', floor=0, to_floor=None, **detail):
    detail = dict(type=kind, **{'from':origin,'to':destination}, **detail)
    return dict(event_type='segment_'+kind, segment_type=kind, event_id=id or f'e{start}:{kind}',
                run_id='run', task_id=task, journey_id=journey, amr_id=amr, sim_time_sec=start,
                duration_sec=duration, distance_m=10 if kind in ('corridor','lift_transfer') else 0,
                start_node=origin, end_node=destination, from_location=origin,to_location=destination,
                start_x=0,start_y=0,start_floor=floor,end_x=10,end_y=0,end_floor=floor if to_floor is None else to_floor,
                payload='Box', lift_id='L' if kind.startswith('lift_') else '', details=json.dumps(detail), status='completed')


def complete(time, task='T', journey='J'):
    return dict(event_type='task_complete',event_id=f'complete{time}',run_id='run',task_id=task,
                journey_id=journey,amr_id='R',sim_time_sec=time,to_location='B')


def forced_rows():
    return [segment('corridor','A','L-F0',0),
            segment('lift_transfer','L-F0','L-F2',1,floor=0,to_floor=2,exit_time_sec=2,required_floor=2,required_floor_visited=True),
            segment('lift_transfer','L-F2','L-F0',2,floor=2,to_floor=0,exit_time_sec=2,required_floor=2,required_floor_visited=True),
            segment('corridor','L-F0','B',3), complete(5)]


class RouteAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def log(self, rows, config=None, name='events.csv', verified=True, full=True):
        path = self.root / name
        fields = sorted(set().union(*(r.keys() for r in rows)))
        with path.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields)
            writer.writeheader();writer.writerows(rows)
        if verified:
            config = config or analysis_config()
            evidence = dict(schema_version=1,run_id='run',log_sha256=file_hash(path),frozen_inputs=config,
                config_sha256=config_hash(config),run_status='finished',logging_enabled=True,reduced_logging=not full,log_kind='full')
            Path(str(path)+'.run.json').write_text(json.dumps(evidence),encoding='utf-8')
        return path

    def read(self, rows, **kwargs):
        return load_analysis(self.log(rows,**kwargs),drawings=False)

    def test_normal_routes_are_available_with_policy_disabled(self):
        run=self.read([segment('corridor','A','B',0),complete(2)],config=analysis_config(False))
        self.assertEqual(1,len(run.legs))
        leg=run.legs[0]
        self.assertEqual(('A','B',10,DISABLED,CONFIRMED),(leg.origin,leg.destination,leg.distance,leg.compliance,leg.evidence))

    def test_same_floor_detour_has_independent_visits_and_confirmed_outcome(self):
        run=self.read(forced_rows())
        self.assertEqual(1,len(run.legs))
        self.assertEqual(SATISFIED,run.legs[0].compliance)
        self.assertEqual(CONFIRMED,run.legs[0].evidence)
        self.assertEqual(2,len(run.movements))

    def test_policy_violation_does_not_become_pass_from_annotation(self):
        rows=[segment('corridor','A','L-F0',0),segment('lift_transfer','L-F0','L-F3',1,to_floor=3,exit_time_sec=1),
              segment('corridor','L-F3','D',2,floor=3),complete(4)]
        self.assertEqual(VIOLATION,self.read(rows).legs[0].compliance)
        rows[1]['details']=json.dumps(dict(type='lift_transfer',**{'from':'L-F0','to':'L-F3'},required_floor=2,required_floor_visited=True,exit_time_sec=1))
        self.assertEqual(UNKNOWN,self.read(rows).legs[0].compliance)

    def test_passing_through_required_floor_is_not_alighting(self):
        rows=[segment('corridor','A','L-F0',0),segment('lift_transfer','L-F0','L-F3',1,to_floor=3,exit_time_sec=1),
              segment('corridor','L-F3','D',2,floor=3),complete(4)]
        self.assertEqual(VIOLATION,self.read(rows).legs[0].compliance)

    def test_missing_exit_evidence_is_unknown(self):
        cfg=analysis_config();cfg['lifts'][0].update(transfer_timing_mode='speed_based')
        rows=forced_rows();d=json.loads(rows[1]['details']);d.pop('exit_time_sec');d.pop('required_floor_visited');rows[1]['details']=json.dumps(d)
        d=json.loads(rows[2]['details']);d.pop('required_floor_visited');rows[2]['details']=json.dumps(d)
        self.assertEqual(UNKNOWN,self.read(rows,config=cfg).legs[0].compliance)

    def test_starting_required_floor_satisfies_local_route(self):
        cfg=analysis_config();cfg['locations'][1]['floor']=2
        run=self.read([segment('corridor','C','B',0,floor=2),complete(2)],config=cfg)
        self.assertEqual(SATISFIED,run.legs[0].compliance)

    def test_ending_required_floor_requires_arrival_exit(self):
        rows=[segment('corridor','A','L-F0',0),segment('lift_transfer','L-F0','L-F2',1,to_floor=2,exit_time_sec=1),
              segment('corridor','L-F2','C',2,floor=2),complete(4)]
        self.assertEqual(SATISFIED,self.read(rows).legs[0].compliance)

    def test_each_multistop_leg_is_checked_separately(self):
        rows=forced_rows()[:-1]
        rows += [segment('dropoff','B','B',4),segment('corridor','B','A',5),complete(7)]
        run=self.read(rows)
        self.assertEqual([SATISFIED,VIOLATION],[leg.compliance for leg in run.legs])

    def test_local_manoeuvres_do_not_create_extra_legs(self):
        rows=[segment('local_manoeuvre','A::local::0','A',0,purpose='amr_unstow'),
              segment('corridor','A','B',1),segment('local_manoeuvre','B','B::local::0',2,purpose='amr_stow'),complete(4)]
        self.assertEqual(1,len(self.read(rows).legs))

    def test_empty_lift_reposition_is_not_an_amr_visit_or_distance(self):
        rows=[segment('corridor','A','B',0),segment('lift_reposition','L-F0','L-F2',1,to_floor=2),complete(3)]
        run=self.read(rows)
        self.assertEqual(VIOLATION,run.legs[0].compliance)
        self.assertEqual(10,run.legs[0].distance)
        self.assertEqual(1,len(run.movements))

    def test_duplicate_shared_movements_count_once(self):
        rows=forced_rows()
        for row in rows:row['task_id']='T1,T2'
        rows.insert(1,dict(rows[0]))
        run=self.read(rows)
        self.assertEqual(1,len(run.legs))
        self.assertEqual(2,len(run.movements))
        self.assertEqual(('T1','T2'),run.legs[0].tasks)

    def test_conflicting_duplicate_is_rejected(self):
        rows=forced_rows();rows.append(dict(rows[0],distance_m=999))
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            self.read(rows)

    def test_missing_middle_segment_and_legacy_input_are_unknown(self):
        rows=forced_rows();rows.pop(1)
        self.assertEqual(UNKNOWN,self.read(rows).legs[0].compliance)
        self.assertTrue(all(l.compliance==UNKNOWN for l in self.read(forced_rows(),name='legacy.csv',verified=False).legs))

    def test_reduced_log_does_not_prove_absence_of_visit(self):
        run=self.read([segment('corridor','A','B',0),complete(2)],full=False)
        self.assertEqual(UNKNOWN,run.legs[0].compliance)

    def test_status_completed_on_plan_is_not_outcome_confirmation(self):
        run=self.read(forced_rows()[:-1])
        self.assertEqual(PLANNED,run.legs[0].evidence)
        summary=compare_runs(run)['sides'][0]
        self.assertIsNone(summary['metrics']['Mean confirmed journey time (s)'])
        self.assertEqual(1,summary['metrics']['Excluded from journey duration'])

    def test_stationary_action_is_not_a_forced_floor_journey(self):
        row=segment('corridor','A','A',0);row['distance_m']=0
        self.assertEqual([],self.read([row,complete(2)]).legs)

    def test_charging_travel_uses_arrival_confirmation(self):
        rows=[segment('corridor','A','B',0,task='',journey=''),
              segment('charge','B','B',1,task='',journey=''),
              dict(event_type='charge_cycle_arrive',event_id='arrive',run_id='run',amr_id='R',sim_time_sec=1,to_location='B')]
        leg=self.read(rows,config=analysis_config(False)).legs[0]
        self.assertEqual(('Charging travel',CONFIRMED),(leg.purpose,leg.evidence))

    def test_legacy_empty_payload_alias_is_an_empty_approach(self):
        row=segment('corridor','A','B',0);row['payload']='-'
        self.assertEqual('Empty approach',self.read([row,complete(2)]).legs[0].purpose)

    def test_reposition_filter_belongs_to_one_leg_not_entire_multistop(self):
        rows=forced_rows()[:-1]
        rows += [segment('dropoff','B','B',4),segment('lift_reposition','L-F0','L-F2',5,to_floor=2),segment('corridor','B','A',6),complete(8)]
        run=self.read(rows)
        result=compare_runs(run,filters=Filters(origin='A'))
        self.assertEqual(0,result['sides'][0]['metrics']['Empty lift repositioning'])

    def test_explicit_window_keeps_both_run_denominators_equal(self):
        a=self.read(forced_rows());b=deepcopy(a);b.duration=10
        result=compare_runs(a,b,Filters(end=500))
        self.assertEqual([10,10],[s['end'] for s in result['sides']])

    def test_cancel_export_leaves_no_partial_folder(self):
        (self.root/'source').mkdir()
        run=self.read(forced_rows(),name='source/events.csv');target=self.root/'cancelled'
        with self.assertRaises(InterruptedError):
            export_comparison(compare_runs(run),target,cancel=lambda:True)
        self.assertFalse(target.exists())

    def test_common_window_differences_and_zero_denominator(self):
        a=self.read([segment('corridor','A','B',0),complete(2)],config=analysis_config(False))
        cfg=analysis_config(False);cfg['simulation']['end_datetime']='2026-01-05T00:05:00'
        b=self.read([segment('corridor','A','B',0),complete(2),segment('corridor','A','B',400,task='T2',journey='J2'),complete(402,'T2','J2')],config=cfg,name='b.csv')
        comparison=compare_runs(a,b)
        self.assertEqual(300,comparison['filters'].end)
        self.assertEqual(0,next(r['delta'] for r in comparison['metrics'] if r['metric']=='Recorded AMR legs'))
        self.assertIsNone(next(r['percent'] for r in comparison['metrics'] if r['metric']=='Lift transfers'))

    def test_busy_time_clips_and_duration_excludes_cross_boundary(self):
        run=self.read(forced_rows())
        result=compare_runs(run,filters=Filters(start=1.5,end=3.5))['sides'][0]
        self.assertEqual(1.5,result['metrics']['Lift busy time in window (s)'])
        self.assertEqual(1,result['metrics']['Lift transfers'])
        result=compare_runs(run,filters=Filters(end=3.5))['sides'][0]
        self.assertEqual(1,result['metrics']['Excluded from journey duration'])

    def test_cancel_and_changed_file_reject_incomplete_results(self):
        path=self.log(forced_rows())
        with self.assertRaises(InterruptedError):load_analysis(path,cancel=lambda:True)
        def progress(message):
            if message.startswith('Reconstructing'):
                with path.open('a') as stream:stream.write('\n')
        with self.assertRaisesRegex(ValueError,'changed during'):
            load_analysis(path,progress=progress,drawings=False)

    def test_tampered_sidecar_inputs_are_rejected(self):
        path=self.log(forced_rows());side=Path(str(path)+'.run.json');data=json.loads(side.read_text());data['frozen_inputs']['building']['force_via_floor']=3;side.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'differs'):
            load_analysis(path,drawings=False)

    def test_filters_groups_and_unmatched_routes(self):
        a=self.read(forced_rows());b=self.read([segment('corridor','B','A',0),complete(2)],name='b.csv')
        result=compare_runs(a,b)
        self.assertEqual(2,len(result['groups']))
        filtered=compare_runs(a,b,Filters(lift='L'))
        self.assertEqual(1,len(filtered['sides'][0]['legs']))
        self.assertEqual(0,len(filtered['sides'][1]['legs']))

    def test_export_contains_all_filtered_evidence_and_does_not_touch_runs(self):
        source_dir=self.root/'source';source_dir.mkdir()
        path=self.log(forced_rows(),name='source/events.csv')
        run=load_analysis(path,drawings=False);before=path.read_bytes()
        target=export_comparison(compare_runs(run),self.root/'export')
        self.assertEqual(before,path.read_bytes())
        with (target/'journey-evidence.csv').open(encoding='utf-8-sig') as stream:
            self.assertEqual(4,len(list(csv.DictReader(stream))))
        self.assertTrue((target/'provenance.json').is_file())
        with (target/'route-comparison.csv').open(encoding='utf-8-sig') as stream:
            groups=list(csv.DictReader(stream))
        self.assertEqual('1',groups[0]['a_count'])
        self.assertTrue((target/'route-variants.csv').is_file())
        with self.assertRaises(ValueError):export_comparison(compare_runs(run),source_dir/'bad')

    def test_real_simulator_normal_and_forced_csv(self):
        from tests.test_forced_floor import configured
        for forced in (False,True):
            cfg=configured(speed_based=True)
            cfg['building']['force_via_floor_enabled']=forced
            cfg['tasks']=[dict(id='T',pickup='A',dropoff='C0',payload='Box')]
            path=self.root/f'actual-{forced}.csv'
            with contextlib.redirect_stdout(io.StringIO()):
                sim=Simulation(cfg,verbose=True,verbose_csv_path=str(path));sim.run();sim.write_verbose_csv()
            run=load_analysis(path,drawings=False)
            self.assertTrue(run.complete)
            self.assertTrue(run.legs)
            self.assertTrue(all(l.compliance==(SATISFIED if forced else DISABLED) for l in run.legs),[(l.origin,l.destination,l.reason) for l in run.legs])
            expected=sim._evidence_inputs['building']['force_via_floor_enabled']
            self.assertEqual(forced,expected)
            self.assertEqual(2 if forced else 0,len(run.movements))


class ManagedAnalysisTests(unittest.TestCase):
    from tests.test_project_runs import ProjectRunTests
    setUp = ProjectRunTests.setUp
    prepare = ProjectRunTests.prepare
    run_reference = ProjectRunTests.run_reference

    def test_managed_sqlite_load_does_not_expand_or_mutate(self):
        from amr_project_runs import execute
        directory=self.prepare()
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        before={p.name:p.stat().st_mtime_ns for p in directory.iterdir() if p.is_file()}
        run=load_analysis(directory,drawings=False)
        self.assertTrue(run.complete)
        self.assertTrue(run.source.endswith('.sqlite'))
        self.assertEqual(CONFIRMED,run.legs[0].evidence)
        self.assertEqual(before,{p.name:p.stat().st_mtime_ns for p in directory.iterdir() if p.is_file()})


class PartialAnalysisTests(unittest.TestCase):
    from tests.test_partial_playback import PartialPlaybackTests
    setUp = PartialPlaybackTests.setUp
    prepare = PartialPlaybackTests.prepare
    partial_run = PartialPlaybackTests.partial_run

    def test_stopped_run_never_confirms_planned_future_segment(self):
        run=load_analysis(self.partial_run(),drawings=False)
        self.assertEqual(3,run.stop)
        self.assertFalse(run.complete)
        self.assertTrue(run.legs)
        self.assertTrue(all(leg.evidence==PLANNED for leg in run.legs))
        self.assertIsNone(compare_runs(run)['sides'][0]['metrics']['Mean confirmed journey time (s)'])
