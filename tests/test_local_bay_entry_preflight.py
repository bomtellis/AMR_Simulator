"""Reference checks for graph entries overlapping another drawn bay."""
import copy
import json
import unittest
from pathlib import Path

from visualiser.check_navigation import destination
from visualiser.project_checks import _entry_overlapping_bay_bounds, check_project


ROOT = Path(__file__).resolve().parents[1]


class LocalBayEntryPreflightTests(unittest.TestCase):
    def test_expanded_bounds_and_other_bay_condition(self):
        location = {
            'name': 'Drop', 'x': 10, 'y': 20,
            'inventory_spaces': [
                {'name': 'Near', 'points': [
                    {'dx': .15, 'dy': -.3}, {'dx': .8, 'dy': -.3},
                    {'dx': .8, 'dy': .3}, {'dx': .15, 'dy': .3}]},
                {'name': 'Target', 'points': [
                    {'dx': 2, 'dy': 0}, {'dx': 3, 'dy': 0},
                    {'dx': 3, 'dy': 1}, {'dx': 2, 'dy': 1}]},
            ],
        }
        self.assertEqual([(0, 'Near')], _entry_overlapping_bay_bounds(location))
        # The parent entry and bay move together. Only their relative outline
        # determines this risk, so an absolute relocation cannot clear it.
        location['x'] += 5
        self.assertEqual([(0, 'Near')], _entry_overlapping_bay_bounds(location))
        for point in location['inventory_spaces'][0]['points']:
            point['dx'] += .001
        self.assertEqual([], _entry_overlapping_bay_bounds(location))
        location['inventory_spaces'].pop()
        self.assertEqual([], _entry_overlapping_bay_bounds(location))

    def test_current_ltn_findings_are_navigable_and_nonmutating(self):
        config = json.loads((ROOT / 'ltn.json').read_text(encoding='utf-8'))
        original = copy.deepcopy(config)
        report = check_project(config)
        findings = [f for f in report.findings if f.code == 'LOCAL_BAY_ENTRY_OVERLAP']
        by_location = {f.object_name: f for f in findings}
        expected = {
            'D29-DROP-ZONE', 'D32-DROP-ZONE', 'D33-DROP-ZONE',
            'D35-DROP-ZONE', 'D38-DROP-ZONE', 'D39-DROP-ZONE',
            'D41-DROP-ZONE',
        }
        self.assertTrue(expected <= by_location.keys())
        for name in expected:
            finding = by_location[name]
            self.assertEqual('warning', finding.severity)
            self.assertEqual('locations', finding.section)
            target = destination(config, finding)
            self.assertEqual(('point', name), (target.kind, target.key))
            self.assertIn('axis-aligned bay-bound risk', finding.consequence)
        self.assertEqual(original, config)
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(config))
        location = next(row for row in config['locations'] if row['name'] == 'D29-DROP-ZONE')
        location['inventory_spaces'][1]['points'][0]['dx'] += .01
        self.assertIn('locations', report.changed_inputs(by_location['D29-DROP-ZONE'], config))
        self.assertFalse(report.can_run(config))


if __name__ == '__main__':
    unittest.main()
