"""Configuration evidence, deliberately separating observed keys from contracts.

Source-key matches are discovery aids, not proof a setting is supported. Unknown
or unreviewed semantics remain explicit rather than inferred from a passing test.
"""
from __future__ import annotations

import ast
import fnmatch
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATHS = {
    "route_profiles", "task_generation.categories",
    "task_generation.categories.*.departments",
    "departments[].task_generation_locations", "departments[].task_generation_location_suffixes", "payloads[].items",
    "task_generation.staff_config.shift_patterns",
    "lifts[].floor_locations",
}


def fields(value, path=""):
    """Yield option paths, using [] for list elements and * for named maps."""
    if isinstance(value, dict):
        for key, child in value.items():
            name = "*" if path in MAP_PATHS else key
            child_path = f"{path}.{name}" if path else name
            yield child_path, child
            yield from fields(child, child_path)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                yield from fields(child, path + "[]")


def source_key_candidates(paths):
    """Index literal dict reads without claiming receiver/dataflow semantics."""
    result = defaultdict(list)
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            key = default = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("get", "setdefault") and node.args:
                    key = node.args[0]
                    default = ast.unparse(node.args[1]) if len(node.args) > 1 else "None"
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                result[key.value].append({
                    "source": f"{path.relative_to(ROOT).as_posix()}:{node.lineno}",
                    "default_expression": default,
                })
    return dict(sorted(result.items()))


def source_paths():
    paths = list(ROOT.glob("*.py"))
    for directory in ("visualiser", "report"):
        paths.extend((ROOT / directory).glob("*.py"))
    return sorted(paths)


def build_inventory():
    from visualiser.models import JsonStore
    from simulator import EXAMPLE_CONFIG

    features = json.loads((ROOT / "verification/features.json").read_text(encoding="utf-8"))
    contracts = json.loads((ROOT / "verification/field_contracts.json").read_text(encoding="utf-8"))
    observations = defaultdict(dict)
    inputs = {"editor_defaults": JsonStore().data, "simulator_example": EXAMPLE_CONFIG}
    # All checked-in-style example files, plus the realistic project. Do not
    # inspect arbitrary result JSON or alter the user's project through save().
    for path in sorted({*ROOT.glob("example*.json"), ROOT / "ltn.json"}):
        if path.exists():
            inputs[path.name] = json.loads(path.read_text(encoding="utf-8-sig"))
    for label, config in inputs.items():
        for path, value in fields(config):
            observations[path].setdefault(label, value)
    for path in contracts:
        observations.setdefault(path, {})
    candidates = source_key_candidates(source_paths())
    options = []
    for path, seen in sorted(observations.items()):
        contract = contracts.get(path, {})
        feature_ids = []
        for feature in features:
            if any(path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[]")
                   for prefix in feature["config"]):
                feature_ids.append(feature["id"])
        default_known = "editor_defaults" in seen
        sample = next(iter(seen.values()), None)
        options.append({
            "path": path,
            "disposition": ("reviewed_contract" if contract.get("support_status") else
                            "documented_contract" if contract else "semantic_review_required"),
            "support_status": contract.get("support_status", "not_individually_reviewed"),
            "runtime_default": contract.get("runtime_default", "not individually reviewed"),
            "editor_behaviour": contract.get("editor_behaviour", "not individually reviewed"),
            "validation": contract.get("validation", "not individually reviewed"),
            "limitations": contract.get("limitations", "not individually reviewed"),
            "source_symbols": contract.get("source_symbols", []),
            "tests": contract.get("tests", []),
            "review_date": contract.get("review_date"),
            "related_contract": contract.get("related_contract"),
            "feature_ids": feature_ids,
            "observed_in": sorted(seen),
            "observed_type": type(sample).__name__ if seen else "not_observed",
            "editor_default_present": default_known,
            # Container defaults are not duplicated into every row.
            "editor_default": seen.get("editor_defaults") if not isinstance(seen.get("editor_defaults"), (dict, list)) else "See editor_defaults.json",
            "units": contract.get("units", "not reviewed"),
            "meaning": contract.get("meaning", "Not individually reviewed; inspect source references."),
            "precedence": contract.get("precedence", "not reviewed"),
            "candidate_source_reads": candidates.get(path.rsplit(".", 1)[-1], []),
        })
    return {"features": features, "options": options,
            "source_key_candidates": candidates, "editor_defaults": inputs["editor_defaults"],
            "scope": "Observed fields in editor defaults, built-in example, example*.json and ltn.json; additional literal source keys are candidates, not certified configuration fields."}


def link_evidence(features, cases):
    linked = []
    for feature in features:
        item = dict(feature)
        item["evidence"] = [case for case in cases if any(
            fnmatch.fnmatchcase(case["id"], pattern) for pattern in feature["tests"])]
        item["unmatched_test_patterns"] = [pattern for pattern in feature["tests"] if not any(
            fnmatch.fnmatchcase(case["id"], pattern) for case in cases)]
        item["evidence_passed"] = bool(item["evidence"]) and not item["unmatched_test_patterns"] and all(
            case["status"] == "passed" for case in item["evidence"])
        linked.append(item)
    return linked


def link_option_evidence(options, cases):
    """Attach real test outcomes without promoting a reviewed support disposition."""
    return link_evidence(options, cases)


def link_option_sources(options, root=ROOT):
    """Resolve qualified Python definitions, not matching words in source text."""
    cache = {}
    result = []
    root = Path(root).resolve()
    for option in options:
        item = dict(option)
        item['source_evidence'] = []
        for reference in option.get('source_symbols', []):
            source, separator, symbol = reference.partition(':')
            path = (root / source).resolve()
            if path not in cache:
                definitions = {}
                if path.is_relative_to(root) and path.suffix == '.py' and path.is_file():
                    try:
                        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                        class Definitions(ast.NodeVisitor):
                            def __init__(self):
                                self.scope = []

                            def visit_definition(self, node):
                                self.scope.append(node.name)
                                definitions['.'.join(self.scope)] = node.lineno
                                self.generic_visit(node)
                                self.scope.pop()

                            visit_ClassDef = visit_definition
                            visit_FunctionDef = visit_definition
                            visit_AsyncFunctionDef = visit_definition
                        Definitions().visit(tree)
                    except (OSError, SyntaxError, UnicodeError):
                        pass
                cache[path] = definitions
            line = cache[path].get(symbol) if separator else None
            item['source_evidence'].append({'reference': reference, 'resolved': line is not None, 'line': line})
        result.append(item)
    return result


def summarize_option_audit(options):
    """Expose remaining review work without equating linked tests with support."""
    families = {}
    backlog = []
    reviewed_statuses = Counter()
    for option in options:
        family = option['path'].split('.')[0].removesuffix('[]')
        row = families.setdefault(family, {'family': family, 'total': 0, 'reviewed': 0,
            'unreviewed': 0, 'reviewed_with_passing_evidence': 0, 'broken_source_links': 0})
        row['total'] += 1
        row['broken_source_links'] += sum(not s['resolved'] for s in option.get('source_evidence', []))
        if option['disposition'] == 'reviewed_contract':
            row['reviewed'] += 1
            reviewed_statuses[option['support_status']] += 1
            row['reviewed_with_passing_evidence'] += bool(option.get('evidence_passed'))
        else:
            row['unreviewed'] += 1
            backlog.append({'path': option['path'], 'disposition': option['disposition'],
                'observed_type': option.get('observed_type'), 'feature_ids': option.get('feature_ids', [])})
    return {'scope': 'Observed/documented options only; passing linked tests never promote a support disposition or establish a release gate.',
            'reviewed_statuses': dict(sorted(reviewed_statuses.items())),
            'families': sorted(families.values(), key=lambda row: (-row['unreviewed'], row['family'])),
            'backlog': sorted(backlog, key=lambda row: row['path'])}
