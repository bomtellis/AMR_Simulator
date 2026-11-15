"""Hand-calculated release windows and independent category shift periods."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest

from amr_contingency_inputs import validate_settings, shift_candidates, roster_within_limits
from amr_contingency_runtime import HumanSimulation, simulate_candidate
from amr_contingency_study import create_study, evaluate_study, coverage_scores, neighbours
from amr_contingency_timing import staffed_intervals, aligned_release
from amr_contingency_report import export_csvs, export_pdf
from amr_sim_models import Task
from tests.test_human_contingency import fixture
from tests.test_generation_reference import grouped_config
from tests.test_tracked_stock_reference import stock_config


def flexible_fixture():
    _, settings, roster = fixture()
    config = grouped_config()
    config['task_generation']['categories']['stores'].update(generation_mode='timeframe',
        timeframe_start='00:02', timeframe_end='00:08', timeframe_payload_multiple=1,
        target_time=3600, requires_staff=False)
    settings['profiles']['stores']['release_policy'].update(mode='staff_aligned', max_delay_minutes=20)
    roster[0]['start'] = 600
    return config, settings, roster


class ContingencyTimingTests(unittest.TestCase):
    def test_release_and_deadline_move_by_same_bounded_amount(self):
        c, s, r = flexible_fixture();before = copy.deepcopy(c)
        result = simulate_candidate(c, s, r)
        self.assertTrue(result['passed'], result['unresolved'])
        task = result['tasks'][0]
        self.assertEqual((120, 600, 480, 960),
                         tuple(task[k] for k in ('original_release','release','original_deadline','deadline')))
        self.assertEqual(614, task['completed'])
        self.assertEqual(480, task['release_delay_seconds'])
        self.assertEqual(480, task['deadline_delay_seconds'])
        self.assertEqual(1, result['retimed_tasks'])
        self.assertEqual(c, before)

    def test_fixed_scheduled_and_explicit_tasks_are_protected(self):
        for scheduled in (False, True):
            c, s, r = fixture()
            if scheduled:
                c = grouped_config()
                c['task_generation']['categories']['stores'].update(target_time=200,requires_staff=False)
            s['profiles']['stores']['release_policy']['mode']='staff_aligned'
            r[0]['start']=600
            result=simulate_candidate(c,s,r)
            task=result['tasks'][0]
            self.assertEqual(task['original_release'],task['release'])
            self.assertEqual(task['original_deadline'],task['deadline'])
            self.assertIn('Fixed',task['timing_reason'])
            self.assertFalse(result['passed'])

    def test_no_staff_or_staff_after_limit_does_not_extend_or_drop_obligation(self):
        c,s,r=flexible_fixture();s['profiles']['stores']['release_policy']['max_delay_minutes']=1
        for roster in ([],r):
            result=simulate_candidate(c,s,roster)
            self.assertFalse(result['passed']);self.assertEqual(1,result['obligations'])
            task=result['tasks'][0]
            self.assertEqual((120,480,180),(task['release'],task['deadline'],task['latest_allowed_release']))
            self.assertIn('No staffed release',task['timing_reason'])
            issue=result['unresolved'][0]
            self.assertEqual((120,540),(issue['planning_release'],issue['planning_deadline']))

    def test_break_end_and_dedicated_service_eligibility(self):
        c,s,r=flexible_fixture()
        r[0].update(start=0,breaks=[[100,600]],pool='stores')
        r.append(dict(r[0],pool='linen',breaks=[]))
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(600,result['tasks'][0]['release'])
        self.assertEqual('P1',result['rounds'][0]['person'])

    def test_short_native_deferral_limit_starts_after_authorized_release_delay(self):
        c,s,r=flexible_fixture();c['simulation']['max_task_deferral_minutes']=.1
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(614,result['tasks'][0]['completed'])

    def test_department_calendar_prevents_alignment_outside_open_hours(self):
        c,s,r=flexible_fixture()
        c['departments'][0]['operating_end_time']='00:09'
        result=simulate_candidate(c,s,r)
        self.assertFalse(result['passed'])
        task=result['tasks'][0]
        self.assertEqual(120,task['release'])
        self.assertIn('opening hours',task['timing_reason'])

    def test_return_near_shift_end_cannot_claim_overtime_or_free_deadline_extension(self):
        c,s,r=flexible_fixture()
        c['task_generation']['categories']['stores'].update(return_enabled=True,return_payload='Box',
            return_delay_minutes=1,return_target_time=200)
        r[0].update(start=0,end=200)
        r.append(dict(pool='shared',start=600,end=3600,breaks=[],base='A'))
        result=simulate_candidate(c,s,r)
        self.assertFalse(result['passed'])
        outbound,returned=result['tasks']
        self.assertEqual(134,outbound['completed'])
        # Readiness at 194 is still in the first shift, even though the round
        # cannot fit. It is not postponed by inspecting future task completion.
        self.assertEqual(194,returned['original_release'])
        self.assertEqual(outbound['payload_instance_id'],returned['payload_instance_id'])
        self.assertEqual(200,returned['original_deadline']-returned['original_release'])

    def test_return_ready_between_shifts_aligns_and_preserves_identity(self):
        c,s,r=flexible_fixture()
        c['task_generation']['categories']['stores'].update(return_enabled=True,return_payload='Box',
            return_delay_minutes=2,return_target_time=200)
        r[0].update(start=0,end=200)
        r.append(dict(pool='shared',start=600,end=3600,breaks=[],base='A'))
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        outbound,returned=result['tasks']
        self.assertEqual((254,600,454,800),tuple(returned[k] for k in
            ('original_release','release','original_deadline','deadline')))
        self.assertEqual(outbound['payload_instance_id'],returned['payload_instance_id'])
        self.assertEqual('A',next(v['location'] for v in result['inventory'] if v['instance_id']==returned['payload_instance_id']))

    def test_dependency_delay_cannot_extend_deadline_beyond_allowance(self):
        c,s,r=fixture();c['tasks']=[]
        s['profiles']['stores']['release_policy'].update(mode='staff_aligned',max_delay_minutes=1)
        sim=HumanSimulation(c,s,r)
        task=Task('dependent','A','B','Box',release_time=100,target_time=50,labels=['stores'],created_during_runtime=True)
        sim._human_prepare(task)
        task.release_time=300
        sim.schedule_task_release(task)
        result=sim.evaluate();task=result['tasks'][0]
        self.assertEqual(210,task['deadline'])
        self.assertEqual(300,task['release'])
        self.assertIn('Dependency',task['timing_reason'])
        self.assertFalse(result['passed'])

    def test_native_stock_shortfalls_remain_failures(self):
        _,s,_=flexible_fixture();c=stock_config();s['shifts']['lengths_hours']=[8]
        result=simulate_candidate(c,s,[])
        self.assertFalse(result['passed'])
        self.assertTrue(any(t['service']=='stock' for t in result['unresolved']))
        self.assertTrue(any(row['unmet']>0 for row in result['balances']['tracked']))

    def test_all_comparisons_share_original_demand_and_timing_policy(self):
        c,s,r=flexible_fixture();expected=None
        for pool in ('shared','stores'):
            for buffered in (False,True):
                result=simulate_candidate(c,s,[dict(r[0],pool=pool)],buffered=buffered)
                values=[tuple(t[k] for k in ('id','payload','quantity','original_release','original_deadline','release','deadline'))
                        for t in result['tasks']]
                if expected is None:expected=values
                self.assertEqual(expected,values)
                self.assertTrue(result['passed'],result['unresolved'])

    def test_coverage_search_considers_original_window_not_only_shifted_release(self):
        self.assertEqual([1],coverage_scores([dict(pool='stores',start=120,end=300)],
            [dict(service='stores',release=600,deadline=960,planning_release=120,planning_deadline=1680)]))

    def test_old_settings_default_fixed_and_invalid_limits_rejected(self):
        c,s,r=fixture();del s['profiles']['stores']['release_policy']
        self.assertTrue(simulate_candidate(c,validate_settings(c,s),r)['passed'])
        for policy in (None,dict(version=2,mode='fixed'),dict(version=1,mode='staff_aligned',max_delay_minutes=0),
                       dict(version=1,mode='staff_aligned',max_delay_minutes=float('nan'))):
            s['profiles']['stores']['release_policy']=policy
            with self.assertRaises(ValueError):validate_settings(c,s)


class IndependentShiftTests(unittest.TestCase):
    def two_services(self):
        c,s,r=fixture();s['services'].append('linen');s['profiles']['linen']=copy.deepcopy(s['profiles']['stores'])
        c['tasks'].append(dict(c['tasks'][0],id='L',labels=['linen']))
        return c,s,r

    def test_exact_periods_overnight_days_and_breaks(self):
        c,s,_=fixture();c['simulation']['end_datetime']='2026-01-06T23:59:00'
        s['shifts'].update(periods=[dict(start='22:00',end='06:00')],days=['mon'],break_minutes=30,break_after_hours=4)
        candidates=shift_candidates(c,validate_settings(c,s),'dedicated')
        self.assertEqual(1,len(candidates));p=candidates[0]
        self.assertEqual((79200,108000,[[93600,95400]]),(p['start'],p['end'],p['breaks']))

    def test_category_periods_and_people_limits_are_independent(self):
        c,s,_=self.two_services();c['simulation']['end_datetime']='2026-01-05T23:59:00'
        s['shifts'].update(periods=[dict(start='06:00',end='14:00')],max_people=1)
        s['profiles']['linen']['shift_rules']=dict(periods=[dict(start='10:00',end='18:00')],max_people=2)
        candidates=shift_candidates(c,validate_settings(c,s),'dedicated')
        self.assertEqual([('stores',21600,50400),('linen',36000,64800)],
            [(r['pool'],r['start'],r['end']) for r in candidates])
        self.assertTrue(roster_within_limits(candidates+[candidates[1]],s))
        self.assertFalse(roster_within_limits(candidates+[candidates[0]],s))
        self.assertEqual(['shared'],[r['pool'] for r in shift_candidates(c,s,'shared')])

    def test_dedicated_search_seeds_both_categories_and_reports_both(self):
        c,s,_=self.two_services();s['shifts']['max_people']=1
        baseline=simulate_candidate(c,s,[])
        seed=next(neighbours(c,s,'dedicated',baseline))
        self.assertEqual({'stores','linen'},{r['pool'] for r in seed})
        result=simulate_candidate(c,s,seed)
        self.assertTrue(result['passed'],result['unresolved']);self.assertEqual(2,result['peak_people'])
        self.assertEqual([1,1],[result['services'][p]['peak_people'] for p in s['services']])
        self.assertEqual([1,1],[result['services'][p]['staffed_hours'] for p in s['services']])

    def test_invalid_periods_and_breaks_fail_validation(self):
        c,s,_=fixture()
        for periods in ([dict(start='25:00',end='06:00')],[dict(start='24:00',end='06:00')],
                        [dict(start='22:00')],['22:00-06:00'],'wrong'):
            s['shifts']['periods']=periods
            with self.assertRaises(ValueError):validate_settings(c,s)
        s['shifts'].update(periods=[dict(start='06:00',end='07:00')],break_minutes=30,break_after_hours=1)
        with self.assertRaises(ValueError):validate_settings(c,s)

    def test_overnight_period_already_on_duty_at_study_start(self):
        c,s,_=fixture()
        s['shifts'].update(periods=[dict(start='22:00',end='06:00')],days=['sun'],max_people=1)
        roster=shift_candidates(c,validate_settings(c,s),'dedicated')
        self.assertEqual([(-7200,21600)],[(r['start'],r['end']) for r in roster])
        result=simulate_candidate(c,s,roster)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(8,result['staffed_hours'])
        self.assertEqual(14,result['tasks'][0]['completed'])

    def test_interval_union_and_overnight_staff_alignment(self):
        roster=[dict(pool='stores',start=79200,end=108000,breaks=[[93000,94800]])]
        intervals=staffed_intervals(roster,'stores')
        self.assertEqual(94800,aligned_release(93600,96000,intervals))
        self.assertIsNone(aligned_release(93600,94000,intervals))
        self.assertIsNone(aligned_release(93600,96000,staffed_intervals(roster,'linen')))

    def test_export_and_replay_of_flexible_exact_period_study(self):
        from pypdf import PdfReader
        c,s,_=flexible_fixture()
        s['shifts']['periods']=[dict(start='00:10',end='01:10')]
        s['trial_budget']=5
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'study.json';create_study(c,s,path)
            state=evaluate_study(path)
            self.assertTrue(all(v['best'] and v['best']['passed'] for v in state['variants'].values()))
            self.assertEqual(state['variants'],evaluate_study(path)['variants'])
            export_csvs(path,Path(folder)/'csv')
            with (Path(folder)/'csv/shared_current_tasks.csv').open(encoding='utf-8-sig',newline='') as stream:
                row=next(csv.DictReader(stream))
            self.assertEqual('2026-01-05 00:02:00',row['original_release'])
            self.assertEqual('2026-01-05 00:10:00',row['release'])
            self.assertEqual('2026-01-05 00:16:00',row['deadline'])
            pdf=Path(folder)/'study.pdf';export_pdf(path,pdf)
            text=' '.join(p.extract_text() or '' for p in PdfReader(pdf).pages)
            self.assertIn('flexible transport releases',text)
            self.assertIn('Independent category team',text)

    def test_cancelled_multi_category_period_search_resumes_deterministically(self):
        c,s,_=self.two_services()
        s['shifts']['periods']=[dict(start='00:00',end='01:00')]
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.json';b=Path(folder)/'b.json'
            create_study(c,s,a);create_study(c,s,b)
            stop={'value':False}
            paused=evaluate_study(a,cancelled=lambda:stop['value'],progress=lambda value:
                stop.update(value=True) if value.get('trials',0)>=2 else None)
            self.assertEqual('cancelled',paused['status'])
            resumed=evaluate_study(a);full=evaluate_study(b)
            self.assertEqual(resumed['variants'],full['variants'])


if __name__=='__main__':unittest.main()
