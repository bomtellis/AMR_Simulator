import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import random,tempfile,unittest
from unittest.mock import patch

from amr_contingency_study import coverage_scores,create_study,evaluate_study,load_study,structural_findings
from amr_contingency_packing import pack_lift,lift_rectangles
from amr_contingency_runtime import HumanSimulation,simulate_candidate
from amr_sim_task_generation import (_department_is_open_at_datetime,_department_active_seconds_between,
    _next_department_open_datetime)
from tests.test_human_contingency import fixture
from tests.test_delivery_energy_reference import lift_config


class ContingencyPerformanceTests(unittest.TestCase):
    def test_coverage_sweep_matches_brute_force_including_late_releases(self):
        rng=random.Random(1)
        work=[dict(service=rng.choice(['a','b','stock']),release=rng.randrange(60),deadline=rng.randrange(60)) for _ in range(200)]
        candidates=[dict(pool=pool,start=start,end=start+12) for pool in ('a','b','shared') for start in range(60)]
        expected=[sum((c['pool']=='shared' or c['pool']==t['service']) and c['start']<=t['deadline'] and c['end']>t['release'] for t in work) for c in candidates]
        self.assertEqual(expected,coverage_scores(candidates,work))

    def test_calendar_cache_tracks_input_edits_and_timezone(self):
        dept=dict(operating_start_time='22:00',operating_end_time='06:00',days_active=['mon'])
        t=datetime(2026,1,6,2)
        self.assertTrue(_department_is_open_at_datetime(dept,t))
        self.assertEqual(4*3600,_department_active_seconds_between(dept,t,t+timedelta(hours=8)))
        dept['days_active']=['tue']
        self.assertFalse(_department_is_open_at_datetime(dept,t))
        self.assertEqual(t.replace(hour=22),_next_department_open_datetime(dept,t))
        a=datetime(2026,1,5,23,tzinfo=timezone.utc)
        b=a.astimezone(timezone(timedelta(hours=2)))
        dept=dict(operating_start_time='22:00',operating_end_time='24:00',days_active=['mon'])
        self.assertTrue(_department_is_open_at_datetime(dept,a))
        self.assertFalse(_department_is_open_at_datetime(dept,b))
        self.assertTrue(_department_is_open_at_datetime(dict(operating_start_time=0),t))
        with self.assertRaises(ValueError):
            _department_is_open_at_datetime(dict(operating_start_time=False),t)

    def test_empty_baseline_runs_once_and_progress_is_available_inside_trial(self):
        c,s,r=fixture();s['trial_budget']=1
        messages=[]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.json';create_study(c,s,path)
            with patch('amr_contingency_study.simulate_candidate',wraps=simulate_candidate) as call:
                state=evaluate_study(path,progress=messages.append)
            self.assertEqual(1,call.call_count)
            self.assertTrue(any(v.get('phase')=='simulating' for v in messages))
            self.assertEqual('budget_exhausted',state['status'])
            self.assertEqual(state['variants'],load_study(path)['variants'])

    def test_single_payload_impossible_fit_stops_search(self):
        _,s,r=fixture();c=lift_config();c['tasks']=fixture()[0]['tasks']
        c['lifts'][0]['capacity_width_m']=.5
        s['trial_budget']=20
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.json';create_study(c,s,path)
            state=evaluate_study(path)
        self.assertEqual('infeasible',state['status'])
        for result in state['variants'].values():
            self.assertEqual(1,result['trials'])
            self.assertIn('permitted rotations',result['diagnostics'][0])


class LiftPackingTests(unittest.TestCase):
    def assert_valid_packing(self,length,width,rectangles,packing):
        self.assertIsNotNone(packing)
        self.assertEqual(len(rectangles),len(packing))
        for index,x,y,l,w,turned in packing:
            self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+l,length+1e-9);self.assertLessEqual(y+w,width+1e-9)
            if turned:self.assertTrue(rectangles[index][3])
        for i,a in enumerate(packing):
            for b in packing[i+1:]:
                _,x,y,l,w,_=a;_,px,py,pl,pw,_=b
                self.assertFalse(x<px+pl-1e-9 and x+l>px+1e-9 and y<py+pw-1e-9 and y+w>py+1e-9)

    def test_two_trolleys_and_person_rearrange_to_fit_ltn_lift(self):
        rectangles=((.6,.6,1.8,True,'Person'),(1.4,.8,1.6,True,'Trolley'),(1.4,.8,1.6,True,'Trolley'))
        packing=pack_lift(2.8,1.8,2.1,rectangles)
        self.assert_valid_packing(2.8,1.8,rectangles,packing)
        self.assertGreater(1.4*2+.6,2.8)  # The former fixed in-line test rejected it.

    def test_rotation_and_prohibited_orientation(self):
        rectangles=((.6,.6,1.8,True,'Person'),(1.8,.5,1,True,'Box'))
        packing=pack_lift(1.2,2,2.1,rectangles)
        self.assert_valid_packing(1.2,2,rectangles,packing)
        self.assertTrue(next(v[-1] for v in packing if v[0]==1))
        self.assertIsNone(pack_lift(1.2,2,2.1,(rectangles[0],(1.8,.5,1,False,'Box'))))

    def test_person_space_height_and_shared_loads_count(self):
        box=(1,.7,1,True,'Box');person=(.6,.6,1.8,True,'Person')
        self.assertIsNotNone(pack_lift(1.8,.8,2.1,(person,box)))
        self.assertIsNone(pack_lift(1.8,.8,2.1,(person,box,person,box)))
        self.assertIsNone(pack_lift(1.8,.8,1.7,(person,box)))

    def test_study_does_not_reject_long_corridor_envelope(self):
        _,s,r=fixture();c=lift_config();c['tasks']=fixture()[0]['tasks']
        s['profiles']['stores']['length_m']=9
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual([],structural_findings(c,s,result))
        self.assertTrue(any(stop.get('lift_arrangement') for stop in result['stops']))

    def test_cached_route_preview_observes_changed_lift_reservations(self):
        _,s,r=fixture();c=lift_config();c['tasks']=fixture()[0]['tasks']
        sim=HumanSimulation(c,s,r)
        try:
            router=sim.human_router;task=next(iter(sim.human_tasks.values()))
            args=('A','B',0,s['profiles']['stores'],[task],1,router.bookings)
            first=router.route(*args)
            self.assertIs(first,router.route(*args))
            lift=sim.lifts[0]
            sim.lift_reservations[lift.id].append((0,1000,0,0))
            later=router.route(*args)
            self.assertGreater(later[0],first[0])
            self.assertGreaterEqual(later[0],1000)
        finally:
            if sim.routing_executor:sim.routing_executor.shutdown(wait=True)
            if sim.event_store and not sim.event_store.closed:sim.event_store.close()


if __name__=='__main__':unittest.main()
