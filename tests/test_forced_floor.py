"""Optional all-journey floor policy, physical routes and legacy equivalence."""
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
import random
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from amr_bed_lifts import boarding_wait
from amr_floor_routing import lift_plan_journeys, lift_plan_segments, lift_policy_key
from amr_forced_floor import _search_forced_lift_plan, requires_lift_route
from amr_routing_inputs import validate_routing_inputs
from amr_run_exports import encode
from amr_sim_models import Task
from simulator import Simulation
from tests.test_floor_waypoints import floor_config
from tests.test_lift_integration import two_lifts
from visualiser.project_checks import check_project


def configured(transfer=False, speed_based=False):
    cfg = floor_config(transfer=transfer)
    cfg['building'].update(force_via_floor_enabled=True, force_via_floor=2)
    for name, floor in [('C0', 0), ('C2', 2)]:
        cfg['locations'].append(dict(name=name, floor=floor, x=8, y=0))
        cfg['corridors']['edges'].append(dict(**{'from': 'A' if floor == 0 else 'B2', 'to': name},
            width_m=3, distance_m=8))
    if speed_based:
        cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.3, lift_exit_speed_m_per_sec=.5)
        for lift in cfg['lifts']:
            lift['transfer_timing_mode'] = 'speed_based'
    return cfg


def connected_network():
    cfg = configured()
    cfg['lifts'] = []
    cfg['corridors']['edges'] = []
    for index, (name, floors) in enumerate([('A', [0, 1]), ('B', [1, 2]),
                                          ('C', [1, 3]), ('D', [3, 5]), ('E', [2, 5])]):
        cfg['lifts'].append(dict(id=name, served_floors=floors, start_floor=floors[0],
            speed_floors_per_sec=1, door_time_sec=1, boarding_time_sec=1,
            capacity_length_m=5, capacity_width_m=5, capacity_height_m=5,
            health_loss_per_journey_percent=0, mean_time_between_failures_hours=0,
            floor_locations={str(f): dict(x=2+4*index, y=0) for f in floors}))
        for floor in floors:
            endpoint = 'A' if floor == 0 else f'B{floor}'
            distance = 1 if name == 'D' and floor == 5 else 30 if name == 'E' and floor == 5 else 2
            cfg['corridors']['edges'].append(dict(**{'from': endpoint, 'to': f'{name}-F{floor}'},
                width_m=3, distance_m=distance))
    return cfg


def plan(sim, origin='A', destination='B5', rules=None, collect=True):
    return sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations[origin], sim.locations[destination],
        sim.payloads['Box'], rules, 'lengthways', collect)


def rides(value):
    return [(leg['origin_lift'].floor, leg['destination_lift'].floor) for leg in lift_plan_journeys(value)]


def state(sim):
    return encode(dict(amrs=sim.amrs, lifts=sim.lifts, lift_reservations=sim.lift_reservations,
        edge_reservations=sim.edge_reservations, node_reservations=sim.node_reservations,
        location_reservations=sim.location_reservations, inventory=sim.inventory_spaces_by_location))


class ForcedFloorTests(unittest.TestCase):
    def test_every_origin_and_same_floor_visit_required_stop(self):
        sim = Simulation(configured())
        for origin, destination, expected in [('A','B5',[(0,2),(2,5)]),
            ('B1','B5',[(1,2),(2,5)]), ('B5','A',[(5,2),(2,0)]),
            ('A','C0',[(0,2),(2,0)]), ('B2','B5',[(2,5)]), ('B1','B2',[(1,2)])]:
            with self.subTest(origin=origin, destination=destination):
                self.assertEqual(expected, rides(plan(sim, origin, destination)))

    def test_same_floor_required_and_stationary_actions_do_not_detour(self):
        sim = Simulation(configured())
        for a,b in [('B2','C2'),('A','A')]:
            self.assertFalse(requires_lift_route(sim.config,sim.locations[a],sim.locations[b]))
            self.assertTrue(sim._route_possible_between_locations(sim.amrs[0],sim.locations[a],sim.locations[b],sim.payloads['Box']))
        result=sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','A','Box'),reserve=True)
        self.assertFalse([s for s in result['segments'] if s['type']=='lift_transfer'])

    def test_same_floor_required_stays_local_in_preflight_and_execution(self):
        cfg=configured();other=deepcopy(cfg['lifts'][0]);other['id']='Other'
        cfg['lifts'].append(other)
        cfg['corridors']['edges']=[e for e in cfg['corridors']['edges'] if e['to']!='C2']
        cfg['corridors']['edges'] += [dict(**{'from':a,'to':b},width_m=3,distance_m=2)
            for a,b in [('C2','Other-F2'),('B3','Other-F3')]]
        cfg['tasks']=[dict(id='T',pickup='B2',dropoff='C2',payload='Box')]
        sim=Simulation(cfg)
        self.assertFalse(sim._route_possible_between_locations(sim.amrs[0],sim.locations['B2'],sim.locations['C2'],sim.payloads['Box']))
        self.assertEqual('Blocked',check_project(cfg).route_checks[0]['status'])

    def test_multiple_connections_and_floor_revisit_use_nearest_final_stop(self):
        sim = Simulation(connected_network())
        before=state(sim)
        result=plan(sim)
        self.assertEqual([(0,1),(1,2),(2,1),(1,3),(3,5)],rides(result))
        self.assertEqual('D',lift_plan_journeys(result)[-1]['lift'].id)
        self.assertEqual(before,state(sim),'estimate changed reservations or assets')
        self.assertTrue(sim._route_possible_between_locations(sim.amrs[0],sim.locations['A'],sim.locations['B5'],sim.payloads['Box']))
        _,_,_,_,_=lift_plan_segments(sim,result,sim.amrs[0],sim.payloads['Box'],0,reserve=True)
        self.assertEqual(2,len(sim.lift_reservations['B']))
        bookings=sorted(sim.lift_reservations['B'])
        self.assertLessEqual(bookings[0][1],bookings[1][0])

    def test_nearest_busy_car_is_still_selected(self):
        sim=Simulation(connected_network());sim.lifts[3].available_time=500
        result=plan(sim)
        self.assertEqual('D',lift_plan_journeys(result)[-1]['lift'].id)
        self.assertGreaterEqual(lift_plan_journeys(result)[-1]['lift_start'],500)

    def test_fallback_checks_multi_floor_route_that_revisits_a_floor(self):
        cfg = connected_network()
        cfg['lifts'][3].update(usage_mode='bed_fallback',
                               amr_access_windows=[dict(start='00:00', end='24:00')])
        sim = Simulation(cfg)
        sim.lifts[4].available_time = 600
        before = state(sim)
        result = plan(sim)
        self.assertEqual([(0, 1), (1, 2), (2, 1), (1, 3), (3, 5)], rides(result))
        self.assertEqual(['D'], result['bed_fallback_lift_ids'])
        self.assertEqual(before, state(sim))

    def test_fallback_deadline_excludes_late_lifts_and_late_routes(self):
        cfg = configured()
        cfg['simulation']['end_datetime'] = '2026-01-06T00:00:00'
        cfg['building']['bed_lift_fallback_wait_sec'] = 180
        late = deepcopy(cfg['lifts'][0])
        late.update(id='Late', usage_mode='bed_fallback',
                    amr_access_windows=[dict(start='23:00', end='24:00')])
        slow = deepcopy(cfg['lifts'][0])
        slow.update(id='Slow', usage_mode='bed_fallback', speed_floors_per_sec=.1,
                    amr_access_windows=[dict(start='00:00', end='24:00')])
        cfg['lifts'] += [late, slow]
        for edge in list(cfg['corridors']['edges']):
            if edge['to'].startswith('L-F'):
                cfg['corridors']['edges'].append(dict(edge, to=edge['to'].replace('L-', 'Late-')))
                # The slow lift has a long approach but no queue.
                cfg['corridors']['edges'].append(dict(edge, to=edge['to'].replace('L-', 'Slow-'),
                                                     distance_m=3000))
        sim = Simulation(cfg)
        sim.lifts[0].available_time = 240
        primary = plan(sim, rules={'allowed_lifts': {'L'}})
        slow_only = plan(sim, rules={'allowed_lifts': {'Slow'}})
        self.assertLess(sum(map(boarding_wait, lift_plan_journeys(slow_only))),
                        sum(map(boarding_wait, lift_plan_journeys(primary))))
        self.assertGreater(slow_only['final_finish'], primary['final_finish'])
        with patch.object(sim, '_direct_lift_plan', wraps=sim._direct_lift_plan) as direct:
            result = plan(sim)
        self.assertEqual(primary['final_finish'], result['final_finish'])
        self.assertTrue(any(call.kwargs.get('only_lift') == 'Slow' for call in direct.call_args_list))
        self.assertFalse(any(call.kwargs.get('only_lift') == 'Late' for call in direct.call_args_list))

    def test_fallback_ranks_wait_ahead_of_arrival_within_deadline(self):
        cfg = configured()
        cfg['building']['bed_lift_fallback_wait_sec'] = 180
        for lift_id in ('Fast', 'LessWait'):
            lift = deepcopy(cfg['lifts'][0])
            lift.update(id=lift_id, usage_mode='bed_fallback',
                        amr_access_windows=[dict(start='00:00', end='24:00')])
            cfg['lifts'].append(lift)
            for edge in list(cfg['corridors']['edges']):
                if edge['to'].startswith('L-F'):
                    distance = 100 if lift_id == 'LessWait' and edge['from'] == 'B2' else 4
                    cfg['corridors']['edges'].append(dict(edge, to=edge['to'].replace('L-', lift_id + '-'),
                                                         distance_m=distance))
        sim = Simulation(cfg)
        sim.lifts[0].available_time = 240
        sim.lifts[1].available_time = 20
        fast = plan(sim, origin='B2', destination='B3', rules={'allowed_lifts': {'Fast'}})
        result = plan(sim, origin='B2', destination='B3')
        primary = plan(sim, origin='B2', destination='B3', rules={'allowed_lifts': {'L'}})
        self.assertEqual(['LessWait'], result['bed_fallback_lift_ids'])
        self.assertLess(sum(map(boarding_wait, lift_plan_journeys(result))),
                        sum(map(boarding_wait, lift_plan_journeys(fast))))
        self.assertLess(fast['final_finish'], result['final_finish'])
        self.assertLess(result['final_finish'], primary['final_finish'])

    def test_fallback_continues_feasibility_search_beyond_quick_budget(self):
        cfg = connected_network()
        cfg['lifts'][3].update(usage_mode='bed_fallback',
                               amr_access_windows=[dict(start='00:00', end='24:00')])
        sim = Simulation(cfg)
        rules = {'allowed_lifts': {'A', 'B', 'C', 'D'}}
        with patch('amr_forced_floor.FALLBACK_SEARCH_STATES', 1), patch(
                'amr_forced_floor._search_forced_lift_plan', wraps=_search_forced_lift_plan) as search:
            result = plan(sim, rules=rules)
        self.assertEqual([(0, 1), (1, 2), (2, 1), (1, 3), (3, 5)], rides(result))
        self.assertEqual('no_usable_fm_route', result['bed_fallback_reason'])
        self.assertTrue(any(call.kwargs.get('first_feasible') for call in search.call_args_list))

    def test_candidate_batch_reuses_lift_legs_without_sharing_result_segments(self):
        sim = Simulation(configured())
        robot = sim.amrs[0]
        other = deepcopy(robot)
        other.id = 'Other'
        start, finish, payload = sim.locations['A'], sim.locations['B5'], sim.payloads['Box']

        def estimate(amr, mark):
            result = sim._nearest_compatible_lift_plan(0, amr, start, finish, payload)
            segment = lift_plan_journeys(result)[0]['to_lift_segments'][0]
            if mark:
                segment['energy_kwh'] = 42
            else:
                self.assertNotIn('energy_kwh', segment)
            return result['final_finish']

        before = state(sim)
        with patch.object(sim, '_direct_lift_plan', wraps=sim._direct_lift_plan) as direct:
            results = sim._estimate_candidate_jobs([
                {'fn': estimate, 'args': (robot, True)},
                {'fn': estimate, 'args': (other, False)},
            ])
            self.assertEqual(2, direct.call_count)
            self.assertEqual(results[0][1], results[1][1])
            self.assertIsNotNone(results[0][1])
            sim.lifts[0].available_time = 100
            later = sim._estimate_candidate_jobs([{'fn': estimate, 'args': (other, False)}])
            self.assertGreater(later[0][1], results[1][1])
        self.assertIsNone(sim._forced_lift_estimate_batch)
        sim.lifts[0].available_time = 0
        self.assertEqual(before, state(sim))

    def test_timed_lift_bound_cache_distinguishes_opening_times(self):
        from amr_floor_routing import optimistic_remaining_times
        sim = Simulation(configured())
        lift = sim.lifts[0]
        args = sim, sim.amrs[0], sim.locations['B5'], 2, lift, 2
        open_now = optimistic_remaining_times(*args, finish_by=100, lift_openings={'L': 0})
        too_late = optimistic_remaining_times(*args, finish_by=100, lift_openings={'L': 100})
        self.assertIn(('A', False), open_now)
        self.assertNotIn(('A', False), too_late)
        self.assertIs(open_now, optimistic_remaining_times(*args, finish_by=100, lift_openings={'L': 0}))

    def test_shared_destination_bound_matches_the_best_individual_car_bound(self):
        from amr_floor_routing import optimistic_remaining_times
        cfg = connected_network()
        sim = Simulation(cfg)
        args = sim, sim.amrs[0], sim.locations['B5'], 2
        options = ((sim.lifts[3], 1), (sim.lifts[4], 30))
        openings = dict.fromkeys((lift.id for lift in sim.lifts), 0)
        openings['D'] = 500
        for deadline in (None, 150, 1000):
            kwargs = {'finish_by': deadline, 'lift_openings': openings}
            shared = optimistic_remaining_times(*args, final_options=options, **kwargs)
            individual = [optimistic_remaining_times(*args, lift, distance, **kwargs)
                          for lift, distance in options]
            self.assertEqual(set(shared), set().union(*individual))
            for state, bound in shared.items():
                self.assertAlmostEqual(bound, min(values.get(state, float('inf')) for values in individual))

    def test_wait_node_uses_sorted_reservations_and_preserves_overlap_rules(self):
        sim = Simulation(configured())
        amr = sim.amrs[0]
        path = [{'type': 'corridor', 'from': 'A'}, {'type': 'corridor', 'from': 'Near'}]
        for tick in range(100):
            sim._reserve_node('Near', tick, tick + 1, 'Other')
        sim._reserve_node('Near', 200, 220, 'Other')
        self.assertEqual('A', sim._lift_wait_node_for_plan(path, 'L-F0', 210, 215, amr))
        self.assertEqual('Near', sim._lift_wait_node_for_plan(path, 'L-F0', 230, 235, amr))

    def test_reusing_a_car_respects_projected_wear_and_repairs(self):
        cfg=configured();cfg['lifts'][0].update(health_loss_per_journey_percent=1,
            mean_time_between_failures_hours=1/3600,mean_time_to_repair_hours=10/3600)
        sim=Simulation(cfg);before=state(sim)
        result=plan(sim,destination='C0');first,second=lift_plan_journeys(result)
        self.assertEqual(before,state(sim))
        self.assertGreaterEqual(second['lift_start'],first['lift_finish']+10)
        lift_plan_segments(sim,result,sim.amrs[0],sim.payloads['Box'],0,reserve=True)
        self.assertEqual(98,sim.lifts[0].health_percent)
        self.assertEqual(2,sim.lifts[0].failures_count)

    def test_permissions_width_and_load_can_exclude_nearest_car(self):
        for kind in ('permission','width','load'):
            cfg=connected_network();rules=None
            if kind=='permission':rules=dict(allowed_lifts={'A','B','E'})
            if kind=='load':cfg['lifts'][3]['capacity_width_m']=.1
            if kind=='width':
                for edge in cfg['corridors']['edges']:
                    if edge['to']=='D-F5':edge['width_m']=.1
            sim=Simulation(cfg)
            with self.subTest(kind=kind):
                self.assertEqual('E',lift_plan_journeys(plan(sim,rules=rules))[-1]['lift'].id)

    def test_equal_distance_uses_completion_then_lift_id(self):
        cfg=connected_network()
        for edge in cfg['corridors']['edges']:
            if edge['to']=='E-F5':edge['distance_m']=1
        self.assertEqual('E',lift_plan_journeys(plan(Simulation(cfg)))[-1]['lift'].id)
        cfg=two_lifts();cfg['building'].update(force_via_floor_enabled=True,force_via_floor=2)
        for edge in cfg['corridors']['edges']:edge['distance_m']=1
        self.assertEqual('NearDestination',lift_plan_journeys(plan(Simulation(cfg)))[-1]['lift'].id)

    def test_different_endpoints_select_different_final_lifts(self):
        cfg=two_lifts();cfg['building'].update(force_via_floor_enabled=True,force_via_floor=2)
        cfg['locations'].append(dict(name='Other',floor=5,x=20,y=0))
        for lift in cfg['lifts']:
            cfg['corridors']['edges'].append(dict(**{'from':f"{lift['id']}-F5",'to':'Other'},width_m=3,
                distance_m=1 if lift['id']=='NearOrigin' else 20))
        sim=Simulation(cfg)
        self.assertEqual('NearDestination',lift_plan_journeys(plan(sim))[-1]['lift'].id)
        self.assertEqual('NearOrigin',lift_plan_journeys(plan(sim,destination='Other'))[-1]['lift'].id)

    def test_unavailable_required_floor_blocks_direct_and_same_floor_routes(self):
        cfg=configured()
        cfg['lifts'][0]['served_floors'].remove(2)
        cfg['lifts'][0]['floor_locations'].pop('2')
        cfg['corridors']['edges']=[e for e in cfg['corridors']['edges'] if e['to']!='L-F2']
        sim=Simulation(cfg)
        for endpoint in ('B5','C0'):
            self.assertIsNone(plan(sim,destination=endpoint))
            self.assertFalse(sim._route_possible_between_locations(sim.amrs[0],sim.locations['A'],sim.locations[endpoint],sim.payloads['Box']))
        self.assertFalse(any(sim.lift_reservations.values()))

    def test_project_check_matches_actual_connections_and_same_floor_detour(self):
        for cfg,endpoint in ((connected_network(),'B5'),(configured(),'C0')):
            cfg['tasks']=[dict(id='T',pickup='A',dropoff=endpoint,payload='Box')]
            report=check_project(cfg)
            self.assertEqual('Reachable',report.route_checks[0]['status'])
            self.assertIn('floor 2',report.route_checks[0]['reason'])
            cfg['route_profiles']={'no_lift':dict(allowed_lifts=['A'] if endpoint=='B5' else [])}
            if endpoint=='B5':
                cfg['tasks'][0]['route_profile']='no_lift'
                self.assertEqual('Blocked',check_project(cfg).route_checks[0]['status'])

    def test_estimates_empty_approach_loaded_return_and_idle_return(self):
        cfg=configured();sim=Simulation(cfg);sim.amrs[0].location_name='B1'
        estimate=sim._estimate_route_seconds(sim.amrs[0],sim.locations['A'],sim.locations['C0'],sim.payloads['Box'],start_time_value=0)
        self.assertGreater(estimate,4)
        result=sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','C0','Box'),reserve=True)
        self.assertEqual([(1,2),(2,0),(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in result['segments'] if s['type']=='lift_transfer'])
        for idle in (False,True):
            sim=Simulation(cfg);sim.amrs[0].location_name='C0'
            task=Task('Return','C0','A','Box',is_return_task=not idle)
            task.is_idle_return=idle
            if idle:
                task.amr_id=sim.amrs[0].id
                task.payload='empty'
            else:
                sim.payload_instance_store.store('C0','Box','RETURN-BOX')
                task.payload_instance_id='RETURN-BOX'
            result=sim._estimate_task_for_amr(sim.amrs[0],task,reserve=False)
            self.assertEqual([(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in result['segments'] if s['type']=='lift_transfer'])

    def test_charging_and_batch_movements_use_required_floor(self):
        cfg=configured();cfg['building']['charge_location']='C0'
        sim=Simulation(cfg)
        self.assertEqual('C0',sim._select_charge_location_for_amr(sim.amrs[0],sim.locations['A'],0).name)
        charge=sim._plan_return_to_charge(sim.amrs[0],sim.locations['A'],0,reserve=True)
        self.assertEqual([(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in charge['segments'] if s['type']=='lift_transfer'])
        slot=dict(payload_capacity_kg=100,payload_length_capacity_m=2,payload_width_capacity_m=2,payload_height_capacity_m=2)
        cfg['amrs'][0].update(multi_stop_enabled=True,payload_slots=[dict(slot,name='One'),dict(slot,name='Two')])
        sim=Simulation(cfg)
        result=sim._estimate_multi_stop_for_amr(sim.amrs[0],[Task('T1','A','C0','Box'),Task('T2','A','C0','Box')],reserve=True)
        self.assertEqual([(0,2),(2,0),(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in result['segments'] if s['type']=='lift_transfer'])

    def test_rollback_restores_empty_approach_bookings_when_loaded_leg_is_blocked(self):
        cfg=configured();cfg['route_profiles']={'blocked':dict(allowed_nodes=['A','C0'])}
        sim=Simulation(cfg);sim.amrs[0].location_name='B1';before=state(sim)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','C0','Box',route_profile='blocked'),reserve=True))
        self.assertEqual(before,state(sim))

    def test_speed_timing_energy_and_saved_stop_evidence(self):
        cfg=configured(speed_based=True);cfg['tasks']=[dict(id='T',pickup='A',dropoff='C0',payload='Box')]
        with contextlib.redirect_stdout(io.StringIO()):
            sim=Simulation(cfg,verbose=True);sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(1,len(sim.completed_task_records))
        transfers=[json.loads(r['details']) for r in sim.event_store.iter_rows() if r['event_type']=='segment_lift_transfer']
        self.assertEqual([(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in transfers])
        self.assertEqual([True,True],[s['required_floor_visited'] for s in transfers])
        for segment in transfers:
            self.assertEqual(2,segment['required_floor'])
            self.assertEqual(segment['entry_edge']['distance_m']/.3,segment['entry_time_sec'])
            self.assertEqual(segment['exit_edge']['distance_m']/.5,segment['exit_time_sec'])
        self.assertEqual('nearest_reachable_destination_stop',transfers[-1]['lift_selection_reason'])

    def test_policy_cache_keys_and_cancellation(self):
        cfg=configured();sim=Simulation(cfg)
        old=lift_policy_key(cfg);cfg['building']['force_via_floor_enabled']=False
        self.assertNotEqual(old,lift_policy_key(cfg))
        task=Task('T','A','C0','Box')
        active=sim._route_estimate_cache_key(sim.amrs[0],task)
        sim.config['building']['force_via_floor_enabled']=False
        self.assertNotEqual(active,sim._route_estimate_cache_key(sim.amrs[0],task))
        sim.config['building']['force_via_floor_enabled']=True
        sim.stop_requested=True
        self.assertIsNone(plan(sim))

    def test_cancellation_rolls_back_and_leaves_work_pending(self):
        sim=Simulation(configured());before=state(sim)
        original=sim._direct_lift_plan
        def cancel(*args,**kwargs):
            result=original(*args,**kwargs)
            sim.stop_requested=True
            return result
        with patch.object(sim,'_direct_lift_plan',side_effect=cancel):
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','C0','Box'),reserve=True))
        self.assertEqual(before,state(sim))
        cfg=configured();cfg['tasks']=[dict(id='T',pickup='A',dropoff='C0',payload='Box')]
        sim=Simulation(cfg)
        def stop(*args,**kwargs):sim.stop_requested=True;return None
        with contextlib.redirect_stdout(io.StringIO()),patch('amr_forced_floor.forced_lift_plan',side_effect=stop):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertTrue(any(task.id=='T' for _,_,_,task in sim.pending_tasks))

    def test_configurable_floor_other_than_two(self):
        cfg=configured();cfg['building'].update(force_via_floor=4,mandatory_floor_waypoints=[])
        self.assertEqual([(0,4),(4,0)],rides(plan(Simulation(cfg),destination='C0')))

    def test_bounded_search_matches_unbounded_scores_and_bound_is_admissible(self):
        from amr_floor_routing import optimistic_remaining_times
        for seed in range(30):
            rng=random.Random(seed)
            cfg=two_lifts();cfg['building'].update(force_via_floor_enabled=True,force_via_floor=2)
            for lift in cfg['lifts']:
                lift['served_floors']=[0,1,2]
                lift['floor_locations']={k:v for k,v in lift['floor_locations'].items() if int(k)<3}
                lift.update(speed_floors_per_sec=rng.choice([.5,1,2]),
                    door_time_sec=rng.choice([0,1,2]),boarding_time_sec=rng.choice([0,1,2]),
                    health_percent=rng.choice([40,80,100]),health_loss_per_journey_percent=rng.choice([0,1]))
            cfg['corridors']['edges']=[e for e in cfg['corridors']['edges'] if int(e['to'].rsplit('-F',1)[1])<3]
            for edge in cfg['corridors']['edges']:edge['distance_m']=rng.choice([0,1,3,8])
            sim=Simulation(cfg)
            for lift in sim.lifts:lift.available_time=rng.choice([0,10,100])
            bounded=plan(sim,destination='B1')
            with patch('amr_floor_routing.optimistic_remaining_times',return_value=None):
                exhaustive=plan(sim,destination='B1')
            with self.subTest(seed=seed):
                self.assertEqual(bounded['final_finish'],exhaustive['final_finish'])
                final=lift_plan_journeys(bounded)[-1]
                self.assertEqual(final['lift'].id,lift_plan_journeys(exhaustive)[-1]['lift'].id)
                bounds=optimistic_remaining_times(sim,sim.amrs[0],sim.locations['B1'],2,
                    final['lift'],final['destination_walking_distance_m'])
                self.assertLessEqual(bounds[('A',False)],bounded['final_finish']+1e-8)

    def test_scenario_mode_keeps_required_physical_stop_and_geometric_restriction_is_preserved(self):
        from tests.test_scenario_study import scenario,event
        configurations=[scenario(configured(),[event('A -> L-F0',start=0,end=5,availability=0)])]
        geometric=configured()
        geometric['simulation']['motion_model']='geometric_v1'
        geometric['amrs'][0]['manoeuvring']=dict(minimum_radius_m=.2,pivot_allowed=True,pivot_speed_deg_per_sec=90,clearance_m=.05)
        geometric['geometry']=dict(schema_version=1,floors=[dict(floor=f,bounds=[-20,-20,30,20],obstacles=[]) for f in range(6)])
        # The application currently rejects every lift/geometric combination.
        # A routing toggle must not bypass that physical-model restriction.
        with self.assertRaisesRegex(ValueError,'lifts interaction with geometric motion'):
            Simulation(geometric)
        for cfg in configurations:
            with self.subTest(mode=cfg['simulation'].get('motion_model')):
                sim=Simulation(cfg)
                result=sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','C0','Box'),reserve=True)
                self.assertIsNotNone(result)
                self.assertEqual([(0,2),(2,0)],[(s['from_floor'],s['to_floor']) for s in result['segments'] if s['type']=='lift_transfer'])


class ForcedFloorInputTests(unittest.TestCase):
    def test_invalid_settings_and_conflicting_rules_fail(self):
        for changes in (dict(force_via_floor_enabled='true'),dict(force_via_floor=True),
                        dict(force_via_floor=9),dict(force_via_floor=None),dict(force_via_floor=2.0)):
            cfg=configured();cfg['building'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_routing_inputs(cfg)
        cfg=configured();cfg['building']['mandatory_floor_waypoints'][0]['via_floor']=3
        with self.assertRaisesRegex(ValueError,'conflicts'):validate_routing_inputs(cfg)
        cfg['building']['force_via_floor_enabled']=False
        validate_routing_inputs(cfg)


def original_simulation():
    root=Path(__file__).resolve().parents[1]/'verification/force-floor-20261109'
    loaded=[]
    for name in ('amr_floor_routing','simulator'):
        spec=importlib.util.spec_from_file_location('forced_original_'+name,root/('original_'+name+'.py'))
        value=importlib.util.module_from_spec(spec);sys.modules[spec.name]=value;spec.loader.exec_module(value)
        loaded.append(value)
    loaded[1].connecting_lift_plan=loaded[0].connecting_lift_plan
    return loaded[1].Simulation


class ForcedFloorDisabledParityTests(unittest.TestCase):
    def test_disabled_complete_runs_exactly_match_original(self):
        original=original_simulation()
        for explicit in (False,True):
            cfg=configured();cfg['building'].pop('force_via_floor_enabled');cfg['building'].pop('force_via_floor')
            if explicit:cfg['building'].update(force_via_floor_enabled=False,force_via_floor=3)
            cfg['tasks']=[dict(id=f'T{i}',pickup='A' if i%2==0 else 'B5',
                dropoff='B5' if i%2==0 else 'C0',payload='Box',release_time=i*25) for i in range(12)]
            with contextlib.redirect_stdout(io.StringIO()):
                old=original(deepcopy(cfg),verbose=True);new=Simulation(deepcopy(cfg),verbose=True)
                old.run();new.run()
            self.assertEqual(old.current_time,new.current_time)
            self.assertEqual(encode(old.completed_task_records),encode(new.completed_task_records))
            self.assertEqual(state(old),state(new))
            def rows(sim):
                return [{k:str(v).replace(sim.run_id,'<run>') if isinstance(v,str) else v for k,v in row.items()}
                        for row in sim.event_store.iter_rows()]
            self.assertEqual(rows(old),rows(new))


if __name__=='__main__':unittest.main()
