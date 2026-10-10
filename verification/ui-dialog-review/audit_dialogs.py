"""Inventory dialog layout risks without executing application constructors.

Run from the repository root: python verification/ui-dialog-review/audit_dialogs.py
The review is structural; image review is recorded separately in README.md.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "visualiser"
OUTPUT = Path(__file__).resolve().parent


def source_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def calls_in(method: ast.FunctionDef) -> list[str]:
    return [source_name(node.func) for node in ast.walk(method) if isinstance(node, ast.Call)]


def find_dialogs() -> list[dict]:
    rows = []
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            if not any(source_name(base) == "QDialog" for base in cls.bases):
                continue
            methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)]
            init = next((node for node in methods if node.name == "__init__"), None)
            if init is None:
                continue
            calls = calls_in(init)
            full_calls = [ast.unparse(node.func) for node in ast.walk(init) if isinstance(node, ast.Call)]
            text = ast.get_source_segment(path.read_text(encoding="utf-8"), init) or ""
            fixed = sum(name in calls for name in ("setFixedWidth", "setFixedHeight", "setFixedSize"))
            minimum = sum(name in calls for name in ("setMinimumWidth", "setMinimumHeight", "setMinimumSize"))
            horizontal = calls.count("QHBoxLayout") + calls.count("QSplitter")
            scroll = "QScrollArea" in calls
            tabs = "QTabWidget" in calls
            polished = any("polish_dialog" in name for name in full_calls)
            long_labels = sum(len(node.value) >= 180 for node in ast.walk(init)
                              if isinstance(node, ast.Constant) and isinstance(node.value, str))
            risks = []
            if fixed:
                risks.append("fixed-width control")
            if minimum:
                risks.append("minimum size")
            if horizontal >= 3 and not tabs:
                risks.append("dense horizontal layout")
            if long_labels:
                risks.append("long explanatory copy")
            if not scroll and (minimum or horizontal >= 3 or long_labels):
                risks.append("no local scroll")
            if not polished:
                risks.append("theme only on show")
            rows.append({
                "dialog": cls.name,
                "source": str(path.relative_to(ROOT)).replace("\\", "/"),
                "line": cls.lineno,
                "fixed_controls": fixed,
                "minimum_sizes": minimum,
                "horizontal_layouts": horizontal,
                "local_scroll": scroll,
                "tabs": tabs,
                "long_copy_blocks": long_labels,
                "polish_in_constructor": polished,
                "risks": risks,
                "priority": "high" if len(risks) >= 3 else ("medium" if risks else "low"),
            })
    return rows


def main() -> None:
    rows = find_dialogs()
    (OUTPUT / "dialog-inventory.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Dialog structural assessment",
        "",
        "Each direct `QDialog` subclass in `visualiser` is listed. This is source inspection,",
        "not a visual claim for every possible data-dependent state. The revision images",
        "and measured runtime captures in this directory supplement the inventory.",
        "",
        "| Dialog | Priority | Layout observations |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        link = f"[{row['dialog']}](../../{row['source']}#L{row['line']})"
        traits = ", ".join(row["risks"]) or "No static crowding flag"
        if row["tabs"]:
            traits += "; tabs"
        if row["local_scroll"]:
            traits += "; local scroll"
        lines.append(f"| {link} | {row['priority']} | {traits} |")
    lines.extend(["", f"Total: {len(rows)} dialogs; " +
                  ", ".join(f"{sum(row['priority'] == p for row in rows)} {p}" for p in ("high", "medium", "low")) + ".", ""])
    (OUTPUT / "dialog-inventory.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
