"""Run with: python -m verification.run --output verification/latest.

Exit status is nonzero for failed tests or broken evidence links. Passing tests
never promote a partially verified feature to a fully verified feature.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from verification.inventory import ROOT, build_inventory, link_evidence, source_paths


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
        self.started = {}
        self.outcomes = {}

    def startTest(self, test):
        super().startTest(test)
        self.started[test.id()] = time.perf_counter()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.setdefault(test.id(), ("passed", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = ("failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = ("error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = ("skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcomes[test.id()] = ("expected_failure", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.outcomes[test.id()] = ("unexpected_success", "Expected failure now passes; review the test.")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            previous = self.outcomes.get(test.id(), ("failed", ""))[1]
            self.outcomes[test.id()] = ("failed", previous + self._exc_info_to_string(err, subtest))

    def stopTest(self, test):
        status, details = self.outcomes.get(test.id(), ("error", "No recorded outcome"))
        self.cases.append({"id": test.id(), "status": status, "details": details,
                           "seconds": round(time.perf_counter() - self.started[test.id()], 6)})
        super().stopTest(test)


def git(*args):
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def source_manifest():
    paths = source_paths() + list((ROOT / "tests").glob("*.py"))
    paths += list((ROOT / "verification").glob("*.py")) + list((ROOT / "verification").glob("*.json"))
    paths += list((ROOT / "verification/scenarios").glob("*.json"))
    paths += list(ROOT.glob("*.json")) + list(ROOT.glob("requirements*.txt"))
    paths += list((ROOT / "report").glob("*.mjs")) + list((ROOT / "report/assets").glob("*.xlsx"))
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(set(paths))}
    return {"files": hashes, "sha256": hashlib.sha256(
        json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ltn_audit():
    from visualiser.models import JsonStore
    from visualiser.project_checks import check_project
    start = time.perf_counter()
    path = ROOT / "ltn.json"
    raw = path.read_bytes()
    store = JsonStore.from_file(str(path))
    findings = store.validate()
    checks = check_project(json.loads(raw), base_path=path.parent)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "load_and_check_seconds": round(time.perf_counter() - start, 6),
            "locations": len(store.data.get("locations", [])),
            "nodes": len(store.data.get("corridors", {}).get("nodes", [])),
            "edges": len(store.data.get("corridors", {}).get("edges", [])),
            "findings": findings,
            "project_checks": checks.to_dict(),
            "scope": "Load, legacy editor validation and structured preflight; not a full LTN simulation or numerical validation."}


def write_junit(path, cases):
    suite = ET.Element("testsuite", name="AMR engineering verification", tests=str(len(cases)),
                       failures=str(sum(c["status"] in ("failed", "unexpected_success") for c in cases)),
                       errors=str(sum(c["status"] == "error" for c in cases)),
                       skipped=str(sum(c["status"] in ("skipped", "expected_failure") for c in cases)))
    for case in cases:
        class_name, _, name = case["id"].rpartition(".")
        node = ET.SubElement(suite, "testcase", classname=class_name, name=name, time=str(case["seconds"]))
        if case["status"] != "passed":
            tag = "skipped" if case["status"] in ("skipped", "expected_failure") else "error" if case["status"] == "error" else "failure"
            ET.SubElement(node, tag, message=case["status"]).text = case["details"]
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def write_report(path, report):
    esc = lambda value: html.escape(str(value))
    rows = []
    for feature in report["features"]:
        tests = "".join(f'<li>{esc(c["status"])} — {esc(c["id"])}</li>' for c in feature["evidence"])
        rows.append(f'<article><h2>{esc(feature["id"])} · {esc(feature["title"])}</h2>'
                    f'<p class="status">{esc(feature["status"].replace("_", " "))}</p>'
                    f'<p>{esc(feature["contract"])}</p><p><strong>Limitations:</strong> {esc(feature["limitations"])}</p>'
                    f'<details><summary>{len(feature["evidence"])} linked tests</summary><ul>{tests}</ul></details></article>')
    options = "".join(
        f'<tr><td>{esc(o["path"])}</td><td>{esc(o["disposition"])}</td><td>{esc(o["units"])}</td>'
        f'<td>{esc(o["meaning"])}<br>{esc(o["precedence"])}</td></tr>'
        for o in report["options"])
    counts = report["counts"]
    path.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AMR verification — Demand preview</title>
<style>body{{font:17px/1.5 system-ui,sans-serif;background:#f5f7fa;color:#172635;max-width:1150px;margin:auto;padding:24px}}
h1,h2{{line-height:1.2}}article,.panel{{background:white;border:1px solid #b3c2d0;border-radius:8px;padding:20px;margin:16px 0}}
.status{{font-weight:700;color:#334d65}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border:1px solid #b3c2d0;padding:8px;overflow-wrap:anywhere}}
input{{font:inherit;padding:10px;width:90%;margin:8px 0}}summary{{cursor:pointer}}a{{color:#174c94}}li{{overflow-wrap:anywhere}}
@media print{{body{{padding:0}}details{{display:block}}}}</style>
<h1>AMR engineering verification</h1><p>Demand preview review gate · {esc(report["created_utc"])}</p>
<div class="panel"><h2>{counts["passed"]} / {counts["total"]} tests passed</h2>
<p><strong>This is not full simulator validation.</strong> Verified claims apply only to the stated reference cases. Partial and unsupported features remain visible below.</p>
<p>Rollback commit: 07a059a · tested source fingerprint: <code>{esc(report["source"]["sha256"])}</code></p>
<p>{len(report["options"])} observed/documented option paths; {counts["unreviewed_options"]} require individual semantic review.</p>
<p><a href="evidence.json">Complete machine-readable evidence</a> · <a href="tests.txt">Test log</a> · <a href="options.json">Option inventory</a> · <a href="source-key-candidates.json">Additional source-key candidates</a> · <a href="source-snapshot.zip">Tested source snapshot</a></p></div>
<div class="panel"><h2>Changes to review</h2><ul>
<li>Demand preview adds a task table, hourly timetable, filters and per-rule explanations of effective settings and precedence.</li>
<li>Runtime-dependent demand remains unknown; simple fixed schedules have independent count reconciliation. Returns are not counted as fixed tasks.</li>
<li>Project checks now show searchable findings, affected objects, explanations and navigation in the editor.</li>
<li>Launcher runs block detected input errors, require warning acknowledgement, and save checks alongside the exact reviewed configuration.</li>
<li>Robot and payload width now exclude impassable corridors/doors while allowing wider alternative routes.</li>
<li>Location capacity counts actual simultaneous occupancy, using half-open time intervals.</li>
<li>Enabled groups activate generation under disabled category defaults; grouped services no longer create an extra default task.</li>
<li>PDF test dependency declared; LTN bay regression updated to its saved four-bay layout.</li></ul>
<p>LTN load/check: {esc(report["ltn"].get("load_and_check_seconds", "not measured"))} s; {len(report["ltn"].get("findings", []))} existing validation findings. Full week simulation not run at this gate.</p></div>
<div class="panel"><h2>Your review checkpoint</h2><p>Open the three JSON examples in verification/scenarios in the existing editor or simulator. Expected results: door-pass — one delivery in 9 seconds; door-blocked — one explicit failed task; door-detour — one delivery in 14 seconds via the 20 metre alternative.</p>
<p>Open Home → Project checks in the editor. Filter findings, navigate to an affected object, edit it and confirm the checks become stale. Recheck before exporting. In the launcher, review and acknowledge warnings before running, then inspect project_checks.json in the run folder.</p>
<p>Open Home → Demand preview → Build preview. Inspect Tasks, Timetable and Rules and reconciliation. Select a task for its origin and effective settings; edit the project and confirm the preview becomes stale.</p>
<p><a href="ltn-project-checks.json">LTN structured findings</a> reflects the current saved project. Previously reported references may have been corrected. Complex calendars without an independent expected count are marked not assessed. Results investigation, the remaining option audit, the unified application and new geometry remain later work.</p></div>
<label for="filter">Filter features and settings</label><input id="filter" type="search" placeholder="Try doors, charging, route profiles…">
{''.join(rows)}<h2>Configuration option inventory</h2><p>{esc(report["inventory_scope"])}</p>
<p>Source-key matches are discovery aids. Values and precedence are not guessed for unreviewed fields. See editor_defaults.json for the saved default configuration.</p>
<table><thead><tr><th>Setting</th><th>Disposition</th><th>Units</th><th>Contract</th></tr></thead><tbody>{options}</tbody></table>
<script>document.getElementById('filter').addEventListener('input',e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('article,tbody tr').forEach(n=>n.hidden=!n.textContent.toLowerCase().includes(q));}});</script></html>''', encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/latest")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.chdir(ROOT)
    fingerprint = source_manifest()
    # Preserve the actual tested code/configuration, including uncommitted
    # sources, so future edits cannot erase this evidence's reproducibility.
    with zipfile.ZipFile(output / "source-snapshot.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, expected in fingerprint["files"].items():
            data = (ROOT / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"Source changed while snapshotting: {name}")
            archive.writestr(name, data)
    inventory = build_inventory()
    started = time.perf_counter()
    with (output / "tests.txt").open("w", encoding="utf-8") as log:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=EvidenceResult).run(suite)
    cases = result.cases
    features = link_evidence(inventory["features"], cases)
    broken_links = [f'{feature["id"]}: {pattern}' for feature in features
                    for pattern in feature["unmatched_test_patterns"]]
    packages = {}
    for name in ("PySide6", "numpy", "pandas", "reportlab", "pypdf", "ezdxf"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    try:
        ltn = ltn_audit()
    except Exception as exc:
        ltn = {"findings": [f"Load/check failed: {exc}"]}
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(), "packages": packages,
        "git_commit": git("rev-parse", "HEAD"), "git_status": git("status", "--porcelain"),
        "source": fingerprint, "source_unchanged_during_tests": fingerprint == source_manifest(),
        "seconds": round(time.perf_counter() - started, 6),
        "counts": {"total": len(cases), "passed": sum(c["status"] == "passed" for c in cases),
                   "unreviewed_options": sum(o["disposition"] == "semantic_review_required" for o in inventory["options"])},
        "test_cases": cases, "features": features, "options": inventory["options"],
        "inventory_scope": inventory["scope"], "broken_evidence_links": broken_links, "ltn": ltn,
    }
    write_json(output / "evidence.json", report)
    write_json(output / 'ltn-project-checks.json', ltn.get('project_checks', {'error': 'Checks did not complete'}))
    write_json(output / "options.json", inventory["options"])
    write_json(output / "source-key-candidates.json", inventory["source_key_candidates"])
    write_json(output / "editor_defaults.json", inventory["editor_defaults"])
    write_junit(output / "junit.xml", cases)
    write_report(output / "index.html", report)
    passed = result.wasSuccessful() and not broken_links and report["source_unchanged_during_tests"]
    print(f'{report["counts"]["passed"]}/{len(cases)} tests passed; {len(broken_links)} broken evidence links.')
    print(f'Review pack: {output / "index.html"}')
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
