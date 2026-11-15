import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_engineering_reference import reference_config
from amr_contingency_inputs import default_settings, validate_settings, peak_people, shift_candidates
from amr_contingency_runtime import simulate_candidate, HumanSimulation
from amr_contingency_study import create_study, load_study, evaluate_study
from tests.test_generation_contracts import return_config
from tests.test_tracked_stock_reference import stock_config
from tests.test_delivery_energy_reference import lift_config
from tests.test_dropoff_zones import DropoffZoneTests


def fixture():
    config = reference_config()
    config['tasks'] = [dict(id='T1',pickup='A',dropoff='B',payload='Box',release_time=0,target_time=200,labels=['stores'])]
    settings = default_settings(config)
    settings['profiles']['stores'].update(capacity_count=2,capacity_kg=100,length_m=2,width_m=.7,height_m=2,
        base='A',empty_speed_mps=1,loaded_speed_mps=1,pickup_seconds=2,unload_seconds=2,handling_minutes=0)
    settings['shifts'].update(lengths_hours=[1],start_window=['00:00','00:00'],shared_base='A',
                              break_minutes=0,break_after_hours=0,confirmed=True,max_people=4)
    settings['trial_budget']=12
    roster=[dict(pool='shared',start=0,end=3600,breaks=[],base='A')]
    return config,settings,roster


class HumanContingencyTests(unittest.TestCase):
    def test_hand_calculated_round(self):
        c,s,r=fixture()
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(14,result['tasks'][0]['completed'])
        self.assertEqual(24,result['rounds'][0]['end'])
        self.assertEqual(20,result['distance_m'])

    def test_fixed_roster_no_people(self):
        c,s,r=fixture()
        result=simulate_candidate(c,s,[])
        self.assertFalse(result['passed'])
        self.assertEqual(0,result['peak_people'])
        self.assertEqual(1,len(result['unresolved']))

    def test_batch_two_payloads(self):
        c,s,r=fixture()
        c['tasks'].append(dict(c['tasks'][0],id='T2'))
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(1,result['trips'])
        self.assertEqual(20,result['distance_m'])
        self.assertEqual(2,result['completed'])

    def test_capacity_one_forces_separate_trips(self):
        c,s,r=fixture();s['profiles']['stores']['capacity_count']=1
        c['tasks'].append(dict(c['tasks'][0],id='T2'))
        result=simulate_candidate(c,s,r)
        # Interleaving can deliver first, reload, then deliver second in one round.
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(40,result['distance_m'])

    def test_missing_route_is_not_zero_time(self):
        c,s,r=fixture(); c['corridors']['edges']=[]
        result=simulate_candidate(c,s,r)
        self.assertFalse(result['passed'])
        self.assertIn('route',result['unresolved'][0]['reason'])

    def test_break_and_shift_end(self):
        c,s,r=fixture();r[0]['end']=20
        self.assertFalse(simulate_candidate(c,s,r)['passed'])
        r[0]['end']=3600;r[0]['breaks']=[[0,180]]
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(194,result['tasks'][0]['completed'])

    def test_buffer_and_input_preservation(self):
        c,s,r=fixture();before=copy.deepcopy(c)
        a=simulate_candidate(c,s,r);b=simulate_candidate(c,s,r,buffered=True)
        self.assertAlmostEqual(28.8,b['rounds'][0]['end'])
        self.assertEqual(a['obligations'],b['obligations']);self.assertEqual(c,before)

    def test_unchanged_workload_and_replay(self):
        c,s,r=fixture()
        self.assertEqual(simulate_candidate(c,s,r),simulate_candidate(c,s,r))

    def test_validation_requires_capacity_and_confirmed_rules(self):
        c,s,r=fixture();validate_settings(c,s)
        with self.assertRaises(ValueError):validate_settings(c,default_settings(c))

    def test_generated_return_identity_and_passive_wait(self):
        _,s,r=fixture();c=return_config()
        s['profiles']['stores']['handling_minutes']=.1
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        out,back=result['tasks']
        self.assertEqual(out['payload_instance_id'],back['payload_instance_id'])
        self.assertAlmostEqual(54,back['release']-out['completed'])
        self.assertLess(result['active_hours']*3600,back['completed']-out['release'])

    def test_full_exchange_returns_previous_physical_container(self):
        c,s,r=fixture();c['tasks']=[]
        s['profiles']['stores']['capacity_count']=1
        c['locations'][1]['inventory_spaces']=[dict(name='Single bay',length_m=2,width_m=2,height_m=2,
                                                   flexible=True,payload_slots=[dict(payload='Box')])]
        sim=HumanSimulation(c,s,r)
        sim.payload_instance_store.store('B','Box','PREVIOUS')
        sim.inventory_spaces_by_location['B'][0].update(occupied=True,payload='Box',payload_instance_id='PREVIOUS')
        from amr_sim_models import Task
        task=Task('EXCHANGE','A','B','Box',labels=['stores'],return_enabled=True,return_payload='Box',
                  tracked_item_exchange=True,exchange_mode='full_exchange',staff_handoff_only=True)
        sim.schedule_task_release(task)
        result=sim.evaluate()
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual('PREVIOUS',result['tasks'][1]['payload_instance_id'])
        self.assertNotEqual('PREVIOUS',result['tasks'][0]['payload_instance_id'])
        self.assertEqual('A',next(v['location'] for v in result['inventory'] if v['instance_id']=='PREVIOUS'))
        self.assertEqual(1,result['trips'])
        self.assertEqual(1,len(sim.payload_instance_store.records_at('B')))

    def test_inventory_robot_references_survive_zero_operating_robots(self):
        c,s,r=fixture()
        c['locations'][0]['inventory_spaces']=[dict(name='Robot bay',length_m=2,width_m=2,height_m=2,
            payload_slots=[dict(slot_type='amr',amr_type='R-1')],amr_type='R')]
        sim=HumanSimulation(c,s,r)
        self.assertEqual([],sim.amrs)
        result=sim.evaluate()
        self.assertTrue(result['passed'],result['unresolved'])

    def test_wash_duration_reserves_person_before_next_work(self):
        c,s,r=fixture();c['locations'][1].update(wash_cycle_required=True,wash_cycle_duration_sec=30)
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(54,result['rounds'][0]['end'])
        self.assertAlmostEqual(30/3600,result['washing_hours'])

    def test_generated_stock_balance_and_shortfall(self):
        _,s,r=fixture();c=stock_config();s['shifts']['lengths_hours']=[8];r[0]['end']=28800
        good=simulate_candidate(c,s,r);bad=simulate_candidate(c,s,[])
        self.assertTrue(good['passed'],good['unresolved'])
        self.assertEqual(16,good['balances']['tracked'][0]['consumed'])
        self.assertEqual(0,good['balances']['tracked'][0]['difference'])
        self.assertFalse(bad['passed'])
        self.assertTrue(any(t['service']=='stock' for t in bad['unresolved']))

    def test_direct_department_delivery_does_not_stage_at_zone(self):
        _,s,r=fixture();c=DropoffZoneTests._config()
        rule=c['task_generation']['categories']['stores']['departments']['D1']
        rule.update(return_payload='Trolley',return_enabled=True)
        s['profiles']['stores'].update(payloads=['Trolley'],base='Store',width_m=.7,handling_minutes=1)
        s['shifts']['shared_base']='Store';r[0]['base']='Store'
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual('Ward',result['tasks'][0]['dropoff'])
        self.assertTrue(all(v['location']!='Zone' for v in result['inventory']))

    def test_missing_return_stock_does_not_create_empty_equivalent(self):
        _,s,r=fixture();c=DropoffZoneTests._config()
        s['profiles']['stores'].update(payloads=['Trolley','Empty Trolley'],base='Store')
        s['shifts']['shared_base']='Store';r[0]['base']='Store'
        result=simulate_candidate(c,s,r)
        self.assertFalse(result['passed'])
        self.assertEqual(1,result['completed'])

    def test_dedicated_services_compete_for_lift_and_shared_count_not_summed(self):
        _,s,r=fixture();c=lift_config()
        c['lifts'][0]['capacity_width_m']=.8
        c['lifts'][0]['capacity_length_m']=1.8  # One person + box fits; two do not.
        c['tasks']=[dict(id='S',pickup='A',dropoff='B',payload='Box',labels=['stores'],target_time=200),
                    dict(id='L',pickup='A',dropoff='B',payload='Box',labels=['linen'],target_time=200)]
        s['services'].append('linen');s['profiles']['linen']=copy.deepcopy(s['profiles']['stores'])
        r=[dict(r[0],pool='stores'),dict(r[0],pool='linen')]
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertGreater(result['lift_wait_hours'],0)
        self.assertEqual(2,result['peak_people'])
        self.assertEqual(2,result['trips'])
        self.assertEqual({'stores','linen'},set(result['services']))

    def test_lift_load_too_large(self):
        _,s,r=fixture();c=lift_config();c['lifts'][0]['capacity_width_m']=.5
        c['tasks']=fixture()[0]['tasks']
        result=simulate_candidate(c,s,r)
        self.assertFalse(result['passed'])

    def test_urgent_task_served_before_looser_deadline(self):
        c,s,r=fixture();c['tasks'].append(dict(c['tasks'][0],id='urgent',target_time=14))
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual('urgent',next(v['task_id'] for v in result['stops'] if v['action']=='deliver'))

    def test_incompatible_payload_and_route_permissions(self):
        c,s,r=fixture();s['profiles']['stores']['capacity_kg']=5
        self.assertFalse(simulate_candidate(c,s,r)['passed'])
        c,s,r=fixture();c['tasks'][0]['allowed_edges']=[['A','Door']]
        self.assertFalse(simulate_candidate(c,s,r)['passed'])

    def test_overnight_shift_and_late_demand(self):
        c,s,r=fixture();c['simulation'].update(start_datetime='2026-01-05T23:00:00',end_datetime='2026-01-06T01:00:00')
        s['shifts'].update(start_window=['23:00','23:00'],lengths_hours=[4])
        c['tasks'][0]['release_time']=7200;r[0].update(end=14400)
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved'])
        self.assertEqual(7214,result['tasks'][0]['completed'])

    def test_different_services_use_separate_rounds_on_shared_person(self):
        c,s,r=fixture();s['services'].append('linen');s['profiles']['linen']=copy.deepcopy(s['profiles']['stores'])
        c['tasks'].append(dict(c['tasks'][0],id='linen',labels=['linen']))
        result=simulate_candidate(c,s,r)
        self.assertTrue(result['passed'],result['unresolved']);self.assertEqual(2,result['trips'])
        self.assertEqual(1,result['peak_people'])

    def test_cancelled_search_and_uninterrupted_search_match(self):
        c,s,r=fixture()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';q=Path(d)/'b.json';create_study(c,s,p);create_study(c,s,q)
            state={'stop':False}
            evaluate_study(p,cancelled=lambda:state['stop'],progress=lambda _:state.update(stop=True))
            a=evaluate_study(p);b=evaluate_study(q)
            self.assertEqual(a['variants'],b['variants'])

    def test_budget_exhaustion_never_claims_search_complete(self):
        c,s,r=fixture();s['trial_budget']=1
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.json';create_study(c,s,path);state=evaluate_study(path)
            self.assertEqual('budget_exhausted',state['status'])
            self.assertTrue(all(v['best'] is None for v in state['variants'].values()))

    def test_study_search_binding_and_resume(self):
        c,s,r=fixture()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'study.json';create_study(c,s,path)
            first=evaluate_study(path,cancelled=lambda:True)
            self.assertEqual('cancelled',first['status'])
            state=evaluate_study(path)
            for variant in state['variants'].values():
                self.assertTrue(variant['best']['passed'])
                self.assertEqual(1,variant['best']['peak_people'])
            load_study(path,c)
            changed=copy.deepcopy(c);changed['tasks'][0]['target_time']=1
            with self.assertRaises(ValueError):load_study(path,changed)


if __name__ == '__main__':unittest.main()
