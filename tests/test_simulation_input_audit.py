import json
import unittest

from verification.simulation_audit import HERE, build_simulation_audit, resolve_path


class SimulationInputAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = build_simulation_audit()
        cls.rows = {row['path']: row for row in cls.audit['rows']
                    if row['scope'] == 'historical_fixture_path'}

    def test_every_original_fixture_path_has_one_review_and_resolved_sources(self):
        frozen = json.loads((HERE / 'simulation_audit_scope.json').read_text(encoding='utf-8'))
        self.assertEqual(len(frozen['paths']), 480)
        self.assertEqual(set(self.rows), set(frozen['paths']))
        self.assertEqual(self.audit['unclassified'], [])
        self.assertEqual(self.audit['broken_links'], [])
        for row in self.audit['rows']:
            for key in ('source_symbols', 'runtime_default', 'precedence', 'validation', 'units', 'modes', 'meaning'):
                with self.subTest(path=row['path'], key=key):
                    self.assertTrue(row.get(key))
        for path, row in self.rows.items():
            with self.subTest(path=path):
                self.assertEqual(row['observed_in'], frozen['paths'][path])
                self.assertTrue(set(row['observed_in']) <= set(frozen['fixtures']))
                self.assertTrue(row['meaning'])

    def test_known_fixture_shapes_resolve_to_scoped_contracts(self):
        self.assertEqual(self.rows['departments[].task_generation_locations.linen.locations[]']['contract_path'],
                         'departments[].task_generation_locations.*.locations')
        self.assertEqual(self.rows['task_generation.staff_config.*.four_on_four_off_12h.start_time']['contract_path'],
                         'task_generation.staff_config.shift_patterns.*.start_time')
        shift = self.rows['task_generation.categories.*.departments.*.staff_working_hours.sat.start_time']
        self.assertEqual(shift['contract_path'], 'task_generation.categories.*.staff_working_hours.*.start_time')
        self.assertIn('overlays the category default', shift['precedence'])
        scoped_schedule = self.rows['task_generation.categories.*.department_groups[].payload.scheduled_times[]']
        self.assertEqual(scoped_schedule['contract_path'],
                         'task_generation.categories.*.department_groups[].payload.scheduled_times')

    def test_retained_zone_overrides_and_unwired_pool_are_distinguished(self):
        for suffix in ('departments.*.', 'department_groups[].payload.'):
            prefix = 'task_generation.categories.*.' + suffix
            self.assertEqual(self.rows[prefix + 'dropoff_zone_capacity_policy']['classification'], 'compatibility')
            self.assertEqual(self.rows[prefix + 'reusable_return_pool_enabled']['classification'], 'defective')
        self.assertEqual(self.rows['simulation.task_release_stagger_sec']['classification'], 'alias')
        self.assertEqual(self.rows['floor_dxf_files[].filepath']['classification'], 'presentation')

    def test_unknown_child_does_not_inherit_an_entire_container_contract(self):
        contracts = {'task_generation.categories.*': {'classification': 'structural'}}
        self.assertIsNone(resolve_path('task_generation.categories.*.departments.*.unknown_value', contracts))

    def test_passing_linked_test_does_not_promote_classification(self):
        outcome = {'id': 'test_simulation_run_controls.SimulationRunControlTests.test_import_preserves_release_spacing_alias',
                   'status': 'passed'}
        report = build_simulation_audit([outcome])
        alias = next(row for row in report['rows'] if row['path'] == 'simulation.task_release_stagger_sec')
        self.assertTrue(alias['evidence_passed'])
        self.assertEqual(alias['classification'], 'alias')
