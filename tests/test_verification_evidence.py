import io
import json
import tempfile
import unittest
from pathlib import Path

from verification.inventory import (ROOT, fields, link_evidence, link_option_evidence,
                                    link_option_sources, summarize_option_audit, source_key_candidates)
from verification.run import EvidenceResult, write_junit


class VerificationEvidenceTests(unittest.TestCase):
    def test_config_paths_canonicalise_named_profiles_and_group_fields(self):
        values = dict(fields({"route_profiles": {"clean": {"allowed_nodes": ["A"]}},
                              "amrs": [{"width_m": 0.6}]}))
        self.assertIn("route_profiles.*.allowed_nodes", values)
        self.assertEqual(0.6, values["amrs[].width_m"])
        self.assertNotIn("route_profiles.clean", values)

    def test_partial_status_is_not_promoted_by_passing_tests(self):
        features = [{"id": "F", "status": "partial", "tests": ["test_a.*"]}]
        result = link_evidence(features, [{"id": "test_a.case", "status": "passed"}])[0]
        self.assertEqual("partial", result["status"])
        self.assertTrue(result["evidence_passed"])
        self.assertEqual([], result["unmatched_test_patterns"])

    def test_stale_evidence_links_are_reported(self):
        result = link_evidence([{"id": "F", "tests": ["test_missing.*"]}], [])[0]
        self.assertEqual(["test_missing.*"], result["unmatched_test_patterns"])
        self.assertFalse(result["evidence_passed"])

    def test_option_links_preserve_partial_disposition_and_report_stale_tests(self):
        options = [dict(path='corridors.auto_connect', support_status='partial',
                        tests=['test_routing.*', 'test_missing.*'])]
        result = link_option_evidence(options, [dict(id='test_routing.case', status='passed')])[0]
        self.assertEqual('partial', result['support_status'])
        self.assertEqual(['test_missing.*'], result['unmatched_test_patterns'])
        self.assertFalse(result['evidence_passed'])

    def test_reviewed_contracts_have_traceable_defaults_limits_and_acceptance(self):
        contracts = json.loads((ROOT / 'verification/field_contracts.json').read_text())
        reviewed = [contract for contract in contracts.values() if 'support_status' in contract]
        self.assertTrue(reviewed)
        for contract in reviewed:
            if contract.get('related_contract'):
                base = contracts[contract['related_contract']]
                self.assertTrue(base.get('support_status'))
                self.assertEqual('partial', contract['support_status'])
            self.assertIn(contract['support_status'], ('verified_reference_scope', 'partial', 'unsupported', 'defective'))
            for key in ('runtime_default', 'editor_behaviour', 'units', 'meaning', 'precedence',
                        'validation', 'limitations', 'source_symbols', 'tests', 'review_date'):
                self.assertTrue(contract.get(key), key)
            for reference in contract['source_symbols']:
                source, symbol = reference.split(':', 1)
                self.assertTrue((ROOT / source).is_file(), source)
        linked = link_option_sources([{'source_symbols': c['source_symbols']} for c in reviewed])
        self.assertTrue(all(e['resolved'] for row in linked for e in row['source_evidence']), linked)

    def test_source_links_resolve_qualified_definitions_not_comments_or_other_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sample.py').write_text('# Missing.fake\nclass Real:\n    def method(self): pass\nasync def work(): pass\n')
            refs = ['sample.py:Real.method', 'sample.py:work', 'sample.py:Wrong.method',
                    'sample.py:Missing.fake', 'missing.py:work']
            linked, = link_option_sources([{'source_symbols': refs}], root)
            self.assertEqual([True, True, False, False, False], [e['resolved'] for e in linked['source_evidence']])
            self.assertEqual(3, linked['source_evidence'][0]['line'])

    def test_audit_counts_keep_partial_and_unreviewed_dispositions_distinct(self):
        options = [dict(path='robot.width', disposition='reviewed_contract', support_status='partial', evidence_passed=True),
                   dict(path='robot.speed', disposition='semantic_review_required', evidence_passed=True),
                   dict(path='layout', disposition='documented_contract', evidence_passed=False)]
        audit = summarize_option_audit(options)
        self.assertEqual({'partial': 1}, audit['reviewed_statuses'])
        self.assertEqual(['layout', 'robot.speed'], [o['path'] for o in audit['backlog']])
        robot = next(r for r in audit['families'] if r['family'] == 'robot')
        self.assertEqual((2, 1, 1, 1), tuple(robot[k] for k in
            ['total', 'reviewed', 'unreviewed', 'reviewed_with_passing_evidence']))

    def test_failed_subtest_is_not_reported_as_passed(self):
        class DeliberateFailure(unittest.TestCase):
            def runTest(self):
                with self.subTest(case="expected synthetic failure"):
                    self.assertEqual(1, 2)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=EvidenceResult).run(
            unittest.TestSuite([DeliberateFailure()]))
        self.assertEqual(1, len(result.cases))
        self.assertEqual("failed", result.cases[0]["status"])
        self.assertIn("1 != 2", result.cases[0]["details"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "junit.xml"
            write_junit(path, result.cases)
            self.assertIn("<failure", path.read_text())

    def test_catalog_has_unique_ids_explicit_dispositions_and_limitations(self):
        features = json.loads((ROOT / "verification/features.json").read_text())
        self.assertEqual(len(features), len({f["id"] for f in features}))
        for feature in features:
            self.assertIn(feature["status"], ("verified_reference_scope", "partial", "unsupported", "defective"))
            self.assertTrue(feature["contract"])
            self.assertTrue(feature["limitations"])
            if feature["status"] == "verified_reference_scope":
                self.assertTrue(feature["tests"])


if __name__ == "__main__":
    unittest.main()
