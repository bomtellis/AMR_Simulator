import io
import json
import tempfile
import unittest
from pathlib import Path

from verification.inventory import ROOT, fields, link_evidence, link_option_evidence, source_key_candidates
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
            self.assertIn(contract['support_status'], ('verified_reference_scope', 'partial', 'unsupported', 'defective'))
            for key in ('runtime_default', 'editor_behaviour', 'units', 'meaning', 'precedence',
                        'validation', 'limitations', 'source_symbols', 'tests', 'review_date'):
                self.assertTrue(contract.get(key), key)
            for reference in contract['source_symbols']:
                source, symbol = reference.split(':', 1)
                self.assertTrue((ROOT / source).is_file(), source)
                self.assertTrue(symbol.split('.')[-1] in (ROOT / source).read_text(encoding='utf-8-sig'), reference)

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
