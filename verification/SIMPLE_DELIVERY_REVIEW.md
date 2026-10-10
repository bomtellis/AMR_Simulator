# Simple application delivery — 9 October 2026

The Simple workflow and the three approved compact dialogs are implemented and
verified. The rebuilt offline Windows installer passed a fresh current-user
installation and the small-map workflow. No crash, data-loss or core-action
blocker was found in the checks below. This is an unsigned development build.

## Delivery files

- [Offline Windows installer](../installer/build/delivery/AMR-Simulator-Simple-Setup.exe)
- [Matching source checkpoint](../installer/build/delivery/AMR-Simulator-Simple-source.zip)
- [QA evidence bundle](../installer/build/delivery/AMR-Simulator-Simple-QA.zip)
- [Checksums and delivery manifest](../installer/build/delivery/manifest.json)
- [Findings and limitations](SIMPLE_DELIVERY_FINDINGS.md)

Run the installer normally for a per-user installation. It includes the GUI,
simulation/report worker, small-map exercise and updated guides; installation
and operation require no Python installation or network connection. Use
**Help → Guided walkthrough → Small connected map** for the demonstration.
Connect B to C before checking and running the practice map.

The archive preserves the working source, requirements, tests, build recipe,
approved layout contracts, guides and supplied portable project build input.
Rebuilding requires the dependencies and Inno Setup described in
[installer instructions](../installer/README.md). Those build prerequisites
are separate from offline installation. The checkpoint is a ZIP with a file
manifest, rather than a Git commit; existing uncommitted work was preserved.

## Package handovers

| Package | Delivered result | Focused evidence |
| --- | --- | --- |
| P1 | Preserved source baseline, original guide/installer and practice input; recorded starting HEAD `d0d5c5e79400e832e9dcf0108f28e15d119e91e5`. Updated delivery sequence in roadmap. | `latest/simple-delivery/baseline`; [roadmap](ROADMAP.md) |
| P2 | Existing project creation, configuration, connected-corridor editing, undo/redo, save/reopen and recovery retained and checked. New projects explicitly select Simple. | Project setup, storage, recovery, edit history, corridor and workspace regressions |
| P3 | Task generation Option A and Department Option A implemented. Full forms, conditional fields, draft boundaries and group/location actions retained. Checks, finding navigation, stale checks and demand preview checked. | Compact-dialog, generation, department, checks and demand-preview regressions; actual dialog screenshots |
| P4 | Simulation Option B implemented with four tabs, grouped Run period and optional complete mode details. Simple is explicit in the practice fixture. Existing frozen runs, progress, locks, cancellation and partial/failed outcomes checked. | Mode, run-control, run-store, edit-lock and partial-run regressions |
| P5 | Existing investigation, evidence reconciliation, frozen playback/report inputs, moved-run relinking, CSV evidence and PDF export checked. Review/Report remain in their existing stages. | Investigation, persistent-link, playback and report regressions; source/installed smoke |
| P6 | 560 cases across 41 isolated modules passed in 139.18 seconds. Test source unchanged. Actual widgets captured at 1024 × 768 and 1600 × 900, at 100%, 150% and 200% scale; dark/high-contrast with 18-point text. Keyboard navigation checked across all 12 dialog pages. | [Final QA](latest/simple-delivery/verified-qa/qa.json), scale/theme screenshot folders, [keyboard record](latest/simple-delivery/keyboard.json) |
| P7 | Restored the intended disconnected practice-map starting state; fixed large-text compact-window canvas area. Guide heading and title presentation corrected. Affected checks and complete selected regression suite rerun. | [Findings](SIMPLE_DELIVERY_FINDINGS.md); final QA; guide page renders |
| P8 | Rebuilt installer, verified a fresh workspace installation, checked source/installed fingerprints and guide bytes, packaged source/evidence/checksums. | [Source smoke](latest/simple-delivery/source-smoke-final/smoke.json), [installed smoke](latest/simple-delivery/installed-smoke-final/smoke.json), delivery manifest |

## GUI verification

Task generation retains the category column, compact department scope and five
focused tabs. Department retains three tabs, selected-category location controls
and a persistent reminder to Save here and then Save in Departments. Simulation
retains its four tabs and full findings behind **Show mode details**. Save/Cancel
remain outside scrolling content. Tab switching does not commit drafts.

Capture records show every dialog footer within the requested logical window.
Long forms scroll; tab overflow remains available with large text. Tab traversal
reaches every enabled footer action and each tab bar; arrow keys switch tabs and
Escape cancels. The workbench retains collapsed Properties, Focus canvas,
remembered panel proportions and appearance controls.

At 1024 × 768, the default canvas occupies 50.48% of the window. With actual
18-point appearance settings, it occupies 51.67% after the refinement. On narrow
windows with enlarged text, the existing checks summary strip collapses; the
Check stage and project tree still expose checks, and the stage tooltip carries
the current/stale summary. No permanent toolbar row or dock was added.

Representative actual screens:

- [Compact task generation](latest/simple-delivery/ui-100/task-generation-1024-tab0.png)
- [Department locations](latest/simple-delivery/ui-100/department-1024-tab2.png)
- [Simulation settings](latest/simple-delivery/ui-100/simulation-settings-1024-tab0.png)
- [High-contrast enlarged-text workbench](latest/simple-delivery/ui-high-contrast-18pt/workbench-1024.png)
- [Installed Review](latest/simple-delivery/installed-smoke-final/installed-review.png)

The PDF and Word quick-start guides each have five pages; every rendered page was
visually inspected. The illustrated compact settings and corresponding controls
reference are included in the installed guides. Word was rendered through the
installed Word application because LibreOffice was unavailable. The small-map
report has three readable pages and CSV evidence remains alongside the run.

## Acceptance evidence and boundaries

Source and fresh-installed smoke checks both recorded one completed task, zero
failed tasks, reopened project, compact Simple settings, walkthrough,
reconciled investigation, playback and Report workspace. Saved project, frozen
configuration and event CSV remained byte-identical during read-only review.
The application source SHA-256 in both runs is
`63d1f8535541febf98a6c71c517b7052ac6888bbc352d7cacb29e60e9345c4fc`.

The isolated regressions cover save/reopen/recovery, undo/redo, invalid inputs,
stale checks, successful/failed/cancelled and partial runs, frozen evidence,
relinking, reconciliation and report/CSV interfaces. Dedicated LTN tests,
workloads, benchmarks and repairs were excluded. Detailed development is
deferred; historical mode/settings preservation was checked for compatibility.

Visual checks used actual offscreen Qt widgets and a real silent Windows
installation on this host. They do not establish manual operation on another
machine or every monitor/DPI transition. The retained historical LTN exercise
and its older outcome references are outside this delivery's acceptance scope.
Other limitations are recorded separately in the findings file.
