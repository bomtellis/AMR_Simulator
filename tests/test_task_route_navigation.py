"""Independent graph cases for manual and effective generated route permissions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import unittest
from amr_sim_models import Task
from simulator import Simulation
from visualiser.project_checks import check_project
from tests.test_engineering_reference import reference_config
from tests.test_generation_reference import grouped_config
from amr_tutorial_assets import building_config
from pathlib import Path


class TaskRouteNavigation(unittest.TestCase):
    def report(self,c):return check_project(c,include_legacy=False)
    def generated(self,c):return [r for r in self.report(c).route_checks if r['source']=='Generated rule']
    def test_manual_profile_local_extension_and_one_way_match_runtime(self):
        c=reference_config();c['route_profiles']={'p':{'allowed_nodes':['A','Door']}}
        c['tasks']=[dict(id='T',pickup='A',dropoff='B',payload='Box',route_profile='p')]
        self.assertEqual('Blocked',self.report(c).route_checks[0]['status'])
        c['tasks'][0]['allowed_nodes']=['B']
        self.assertEqual('Reachable',self.report(c).route_checks[0]['status'])
        sim=Simulation(deepcopy(c));rules=sim._resolve_task_route_rules(Task(**c['tasks'][0]))
        self.assertIsNotNone(sim._shortest_path_same_floor(0,'A','B',rules))
        c['corridors']['edges'][0]['bidirectional']=False;c['tasks'][0].update(pickup='B',dropoff='A')
        self.assertEqual('Blocked',self.report(c).route_checks[0]['status'])
    def test_return_uses_its_own_profile_and_does_not_inherit_local_extensions(self):
        c=reference_config();c['route_profiles']={'out':{},'back':{'allowed_nodes':['A','Door']}}
        c['tasks']=[dict(id='T',pickup='A',dropoff='B',payload='Box',route_profile='out',
                         allowed_nodes=['A','B','Door'],return_enabled=True,return_payload='Box',return_route_profile='back')]
        rows=self.report(c).route_checks
        self.assertEqual([('Outbound','Reachable'),('Return','Blocked')],[(r['leg'],r['status']) for r in rows])
        self.assertTrue(any(f.code=='RETURN_UNREACHABLE' for f in self.report(c).findings))
    def test_effective_group_profile_overrides_disabled_category_and_inactive_scopes(self):
        c=grouped_config(enabled=False);category=c['task_generation']['categories']['stores']
        c['route_profiles']={'open':{},'blocked':{'allowed_nodes':['A','Door']}}
        category['route_profile']='open';category['department_groups'][0]['payload']['route_profile']='blocked'
        rows=self.generated(c)
        self.assertEqual([('blocked','Blocked','D')],[(r['profile'],r['status'],r['department']) for r in rows])
        report=self.report(c);self.assertTrue(any(f.code=='GENERATED_TASK_UNREACHABLE' and 'group' in f.path for f in report.findings))
        category['department_groups'][0]['payload']['enabled']=False
        self.assertEqual([],self.generated(c))
    def test_generated_returns_and_all_possible_pairs_are_checked_without_releases(self):
        c=grouped_config();category=c['task_generation']['categories']['stores']
        category.update(generation_mode='continuous',pickup_locations=['A','B'],dropoff_locations=['A','B'],
                        return_enabled=True,return_payload='Box',return_route_profile='back')
        c['route_profiles']={'back':{'allowed_edges':[['A','Door'],['Door','B']]}}
        rows=self.generated(c)
        self.assertEqual({('A','B'),('B','A')},{(r['pickup'],r['dropoff']) for r in rows})
        self.assertTrue(any(r['leg']=='Return' and r['status']=='Blocked' for r in rows))
    def test_unknown_effective_profile_is_an_error_not_unrestricted(self):
        c=grouped_config();c['task_generation']['categories']['stores']['department_groups'][0]['payload']['route_profile']='missing'
        report=self.report(c)
        self.assertEqual('Invalid',report.route_checks[0]['status'])
        self.assertTrue(any(f.code=='PROFILE_REFERENCE' and f.severity=='error' for f in report.findings))
    def test_tracked_payload_source_is_resolved_by_the_real_task_builder(self):
        c=grouped_config();c['payloads'][0].update(track_items=True,items={'item':{'source_location':'B','max':10}})
        c['task_generation']['categories']['stores'].update(tracked_item_exchange=True,dropoff_location='A')
        c['task_generation']['categories']['stores']['pickup_location']='B'
        # The configured pair differs from the tracked item source.
        c['locations'].append(dict(name='C',floor=0,x=0,y=1));c['corridors']['edges'].append(dict(**{'from':'C','to':'A'}))
        c['task_generation']['categories']['stores']['pickup_location']='C'
        rows=self.generated(c);self.assertEqual('B',rows[0]['pickup'])
    def test_multifloor_permissions_and_staleness_include_generated_rules(self):
        c=building_config(Path(__file__).resolve().parents[1]/'docs/building-tutorial')
        before=deepcopy(c);report=self.report(c)
        self.assertTrue(report.route_checks);self.assertTrue(all(r['status']=='Reachable' for r in report.route_checks))
        self.assertEqual(before,c)
        c['route_profiles']['clean']['allowed_lifts']=['L2']
        blocked=self.report(c);self.assertTrue(any(r['profile']=='clean' and r['status']=='Blocked' for r in blocked.route_checks))
        c['task_generation']['categories']['stores']['department_groups'][0]['payload']['route_profile']='dirty'
        self.assertIn('task_generation',report.group_states(c)['task_routes']['changed_inputs'])
        self.assertTrue(self.report(c).to_dict()['route_checks'])
    def test_autoconnect_can_make_a_generated_path_reachable(self):
        c=grouped_config();c['corridors'].update(edges=[],auto_connect=True)
        self.assertEqual('Reachable',self.generated(c)[0]['status'])
        c['corridors']['auto_connect']=False
        self.assertEqual('Blocked',self.generated(c)[0]['status'])

    def test_legacy_waste_forced_return_requires_seeded_bins(self):
        c=reference_config();c['task_generation']['enabled']=True
        c['waste_streams']=[dict(name='General',payload='Box',container_capacity_m3=1)]
        c['departments']=[dict(id='D',name='Dept',enabled=True,waste_streams=[{'name':'General'}],
                              waste={'pickup_location':'A','dropoff_location':'B','route_profile':'out'})]
        c['route_profiles']={'out':{'allowed_edges':[['A','Door'],['Door','B']]}}
        before=deepcopy(c);rows=self.report(c).route_checks
        self.assertEqual([('Outbound','Reachable')],[(r['leg'],r['status']) for r in rows])
        self.assertEqual(before,c)
        c['simulation']['seed_waste_stream_containers_at_start']=True
        self.assertEqual([('Outbound','Reachable'),('Return','Blocked')],[(r['leg'],r['status']) for r in self.report(c).route_checks])

    def test_explicit_generated_snapshot_keeps_source_and_return_leg(self):
        c=reference_config();c['tasks']=[dict(id='Frozen',pickup='B',dropoff='A',payload='Box',
                                             task_source='task_generation_return',is_return_task=True)]
        row=self.report(c).route_checks[0]
        self.assertEqual(('Generated task','Return','Reachable'),(row['source'],row['leg'],row['status']))

    def test_generated_zero_load_tasks_still_receive_profile_navigation_checks(self):
        c=grouped_config();c['route_profiles']={'p':{'allowed_nodes':['A','Door']}}
        c['task_generation']['categories']['stores'].update(payload='__empty__',route_profile='p')
        rows=self.generated(c)
        self.assertEqual(1,len(rows));self.assertEqual('Blocked',rows[0]['status'])


if __name__=='__main__':unittest.main()
