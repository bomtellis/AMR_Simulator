"""Route-profile acceptance cases with independently specified paths and times.

The shared stem is 2 m. Clean and dirty branches are 8 m and 12 m.
An unrestricted 1 m shortcut must never substitute for a restricted loaded leg.
"""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_generation_reference import grouped_config
from visualiser.advanced_dialogs import RouteProfilesEditorV2
from visualiser.project_checks import check_project


def profile_config():
    config = reference_config()
    # Isolate routing from the legacy congestion approximation.
    config['building']['edge_slowdown_per_amr'] = 0
    config['corridors']['nodes'] = [
        dict(name=name, floor=0, x=x, y=y)
        for name, x, y in [('Shared', 1, 0), ('Clean', 3, 1), ('Dirty', 3, -1)]]
    config['corridors']['edges'] = [
        dict(zip(('from', 'to', 'distance_m'), edge), width_m=3)
        for edge in [('A', 'Shared', 2), ('Shared', 'Clean', 4), ('Clean', 'B', 4),
                     ('Shared', 'Dirty', 6), ('Dirty', 'B', 6), ('A', 'B', 1)]]
    config['route_profiles'] = {}
    for profile, branch in [('clean', 'Clean'), ('dirty', 'Dirty')]:
        pairs = [('A', 'Shared'), ('Shared', branch), (branch, 'B')]
        config['route_profiles'][profile] = {
            'allowed_edges': [list(pair) for a, b in pairs for pair in [(a, b), (b, a)]]}
    return config


class RouteProfileAcceptanceTests(unittest.TestCase):
    def run_case(self, config):
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        return sim

    def test_saved_review_scenarios_match_expected_outcomes(self):
        folder = Path(__file__).resolve().parents[1] / 'verification/scenarios'
        for variant, durations, failures in [('clean', [9], 0), ('dirty', [11], 0),
                                              ('return', [9, 11], 0), ('blocked', [], 1)]:
            with self.subTest(variant=variant):
                config = json.loads((folder / f'profiles-{variant}.json').read_text(encoding='utf-8'))
                sim = self.run_case(config)
                self.assertEqual(durations, [r['duration_sec'] for r in sim.completed_task_records])
                self.assertEqual(failures, len(sim.failed_task_ids))

    def test_shared_stem_and_separate_branches_in_both_directions_and_cache(self):
        sim = Simulation(profile_config())
        for profile, branch, distance in [('clean', 'Clean', 10), ('dirty', 'Dirty', 14),
                                           ('clean', 'Clean', 10)]:
            rules = sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile=profile))
            for start, end, expected in [('A', 'B', ['A', 'Shared', branch, 'B']),
                                          ('B', 'A', ['B', branch, 'Shared', 'A'])]:
                with self.subTest(profile=profile, start=start):
                    route = sim._shortest_path_same_floor(0, start, end, rules)
                    self.assertEqual(distance, route['distance_m'])
                    self.assertEqual(expected, [start] + [e['to'] for e in route['edges']])

    def test_executed_clean_and_dirty_deliveries_match_hand_calculations(self):
        for fast in (True, False):
            for profile, seconds in [('clean', 9), ('dirty', 11)]:
                with self.subTest(fast=fast, profile=profile):
                    config = profile_config()
                    config['simulation']['fast_assignment_estimates'] = fast
                    config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile=profile)]
                    sim = self.run_case(config)
                    self.assertEqual(set(), sim.failed_task_ids)
                    self.assertEqual(1, len(sim.completed_task_records))
                    self.assertAlmostEqual(seconds, sim.completed_task_records[0]['duration_sec'])

    def test_empty_approach_is_unrestricted_but_loaded_leg_uses_profile(self):
        config = profile_config()
        config['building']['charge_location'] = 'B'
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        sim = self.run_case(config)
        # Empty B->A = 1/2 s; loaded A->B = 10/2 s; service = 4 s.
        self.assertAlmostEqual(9.5, sim.completed_task_records[0]['duration_sec'])

    def test_return_uses_explicit_profile_and_blank_does_not_inherit_outbound(self):
        for return_profile, seconds in [('dirty', 11), ('', 4.5)]:
            with self.subTest(return_profile=return_profile):
                config = profile_config()
                config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean',
                                        return_enabled=True, return_payload='Box', return_route_profile=return_profile)]
                sim = self.run_case(config)
                self.assertEqual(set(), sim.failed_task_ids)
                self.assertEqual(2, len(sim.completed_task_records))
                self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])
                self.assertAlmostEqual(seconds, sim.completed_task_records[1]['duration_sec'])

    def test_dirty_label_fallback_is_retained_by_return_and_explicit_profile_wins(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', labels=['dirty'],
                                route_profile='clean', return_enabled=True, return_payload='Box')]
        sim = self.run_case(config)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual([9, 11], [r['duration_sec'] for r in sim.completed_task_records])

    def test_removed_profile_edge_fails_without_using_unrestricted_shortcut(self):
        config = profile_config()
        config['route_profiles']['clean']['allowed_edges'].remove(['Clean', 'B'])
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        sim = self.run_case(config)
        self.assertEqual({'T'}, sim.failed_task_ids)
        self.assertEqual([], sim.completed_task_records)
        self.assertIn('route restrictions', sim.failed_tasks[0]['reason'])

    def test_unknown_explicit_and_implicit_profiles_reject_static_tasks(self):
        for fields in [dict(route_profile='typo'), dict(labels=['dirty'])]:
            with self.subTest(fields=fields):
                config = reference_config()
                config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', **fields)]
                with self.assertRaisesRegex(ValueError, "[Rr]oute profile.*(typo|dirty)"):
                    Simulation(config)

    def test_unknown_profile_cannot_be_resolved_as_unrestricted(self):
        sim = Simulation(reference_config())
        with self.assertRaisesRegex(ValueError, "[Rr]oute profile.*typo"):
            sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile='typo'))

    def test_malformed_profile_object_is_rejected(self):
        config = reference_config()
        config['route_profiles'] = {'clean': []}
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        with self.assertRaisesRegex(ValueError, "Route profile.*clean.*object"):
            Simulation(config)

    def test_task_edges_extend_profile_and_can_explicitly_permit_shortcut(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean',
                                allowed_edges=[['A', 'B']])]
        sim = self.run_case(config)
        self.assertAlmostEqual(4.5, sim.completed_task_records[0]['duration_sec'])

    def test_unreachable_return_does_not_fall_back_to_outbound_or_shortcut(self):
        config = profile_config()
        config['route_profiles']['dirty']['allowed_edges'].remove(['B', 'Dirty'])
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean',
                                return_enabled=True, return_payload='Box', return_route_profile='dirty')]
        sim = self.run_case(config)
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual('T', sim.completed_task_records[0]['task_id'])
        self.assertEqual(1, len(sim.failed_task_ids))
        self.assertTrue(next(iter(sim.failed_task_ids)).startswith('RETURN-T-'))

    def test_missing_implicit_return_profile_rejected_even_with_valid_outbound(self):
        config = profile_config()
        del config['route_profiles']['dirty']
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean',
                                labels=['dirty'], return_enabled=True, return_payload='Box')]
        with self.assertRaisesRegex(ValueError, "Route profile.*dirty"):
            Simulation(config)

    def test_unknown_runtime_task_profile_is_rejected_before_assignment(self):
        sim = Simulation(reference_config())
        with self.assertRaisesRegex(ValueError, "[Rr]oute profile.*typo"):
            sim.add_runtime_task(dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='typo'))
        self.assertEqual([], sim.completed_task_records)
        self.assertEqual([], sim.pending_tasks)

    def test_unknown_enabled_return_profile_rejects_outbound_before_movement(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean',
                                return_enabled=True, return_route_profile='typo')]
        with self.assertRaisesRegex(ValueError, "[Rr]oute profile.*typo"):
            Simulation(config)

    def test_effective_generated_profile_is_checked_after_group_override(self):
        for effective, valid in [('clean', True), ('typo', False)]:
            with self.subTest(effective=effective):
                config = grouped_config()
                config['task_generation']['update_interval_sec'] = 60
                config['route_profiles'] = {'clean': {'allowed_nodes': ['A', 'Door', 'B']}}
                category = config['task_generation']['categories']['stores']
                category['route_profile'] = 'overridden-missing-profile'
                category['department_groups'][0]['payload']['route_profile'] = effective
                if valid:
                    sim = self.run_case(config)
                    self.assertEqual(1, len(sim.completed_task_records))
                    self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])
                else:
                    with self.assertRaisesRegex(ValueError, "[Rr]oute profile.*typo"):
                        self.run_case(config)

    def test_implicit_missing_dirty_profile_blocks_project_checks(self):
        config = reference_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', labels=['dirty'])]
        report = check_project(config, include_legacy=False)
        report.acknowledge_warnings()
        self.assertFalse(report.can_run(config))
        finding = next(f for f in report.findings if f.code == 'PROFILE_REFERENCE')
        self.assertEqual(('error', 'tasks', 'T'), (finding.severity, finding.section, finding.target))

    def test_shared_profiles_are_explained_as_supported_and_empty_policy_is_visible(self):
        report = check_project(profile_config(), include_legacy=False)
        self.assertNotIn('PROFILE_SEPARATION', {f.code for f in report.findings})
        finding = next(f for f in report.findings if f.code == 'PROFILE_POLICY')
        self.assertIn('shared', finding.message.lower())
        self.assertIn('empty', finding.consequence.lower())


class RouteProfileEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selected_nodes_generate_both_directions_only_for_two_way_corridors(self):
        edges = [dict(zip(('from', 'to'), pair), **extra) for pair, extra in [
            (('A', 'Shared'), {}), (('Shared', 'B'), {'bidirectional': False}),
            (('A', 'Shared'), {}), (('B', 'Other'), {})]]
        dialog = RouteProfilesEditorV2(None, {'clean': {'allowed_nodes': ['A', 'Shared', 'B']}},
                                      ['A', 'Shared', 'B', 'Other'], [], edges, lambda _p: None)
        try:
            dialog.fill_edges_from_nodes()
            pairs = json.loads(dialog.edges_text.toPlainText())
            self.assertEqual([['A', 'Shared'], ['Shared', 'A'], ['Shared', 'B']], pairs)
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()
