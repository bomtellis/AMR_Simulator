"""Steering angular limits must be explicit before detailed route planning."""
import copy
import unittest

from amr_geometric_routing import geometry_input_findings
from simulator import Simulation
from tests.test_motion_dynamics_simulation import dynamics_config
from visualiser.project_checks import check_project


class AngularInputContractTests(unittest.TestCase):
    def test_nonpivoting_robots_need_both_states_angular_limits(self):
        for state in ('empty', 'loaded'):
            for field in ('rotation_speed_deg_per_sec', 'angular_acceleration_deg_per_sec2',
                          'angular_braking_deg_per_sec2'):
                with self.subTest(state=state, field=field):
                    config = dynamics_config()
                    for values in config['amrs'][0]['movement'].values():
                        values['pivot_allowed'] = False
                    del config['amrs'][0]['movement'][state][field]
                    path = f'/amrs/0/movement/{state}/{field}'
                    self.assertIn(path, [item[0] for item in geometry_input_findings(config)])
                    self.assertTrue(any(item.severity == 'error' and item.path == path
                                        for item in check_project(config).findings))
                    with self.assertRaisesRegex(ValueError, 'angular limits'):
                        Simulation(config)

    def test_legacy_and_old_geometric_inputs_do_not_claim_new_dynamics(self):
        config = dynamics_config()
        current = Simulation(config)
        self.assertIn('finite_angular_motion_v1', current._evidence_event_capabilities)
        old = copy.deepcopy(config)
        del old['amrs'][0]['movement']
        self.assertNotIn('finite_angular_motion_v1', Simulation(old)._evidence_event_capabilities)
        legacy = copy.deepcopy(config)
        legacy['simulation']['motion_model'] = 'legacy'
        self.assertNotIn('finite_angular_motion_v1', Simulation(legacy)._evidence_event_capabilities)
