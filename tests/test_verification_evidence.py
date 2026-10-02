import io
import json
import tempfile
import unittest
from pathlib import Path

from verification.inventory import ROOT, fields, link_evidence, source_key_candidates
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
