# Dependable AMR application — revised delivery plan

## Immediate delivery sequence — 9 October 2026

The current user-authorised delivery is a working **Simple-mode application,
matching source checkpoint and offline Windows installer by 10 October**.
This sequence supersedes the historical next-action order below for this delivery.
Detailed movement, directional passage and constrained-turn development are
deferred. LTN testing, simulations, benchmarks and repairs are explicitly excluded.
The bundled LTN archive is retained unchanged as a build asset.

| Package | Goal and saved deliverable |
| --- | --- |
| P1 Baseline | Preserve current sources and guide inputs, record identity and capture the existing GUI. |
| P2 Project editing | Complete create/open/edit/undo/save/reopen; keep the canvas prominent and Properties optional. |
| P3 Configure and check | Deliver Task generation Option A and Department Option A; retain all inputs/callbacks; demonstrate checks and demand preview. |
| P4 Simple runs | Deliver Simulation settings Option B, explicit Simple practice inputs, frozen runs, progress, cancellation and edit locks. |
| P5 Review and report | Demonstrate saved-run investigation, playback, relinking and frozen-input PDF/CSV exports. |
| P6 QA | Run the relevant isolated regression modules and compact/wide actual-widget captures at 100/150/200% scaling, without LTN workloads. |
| P7 Refine | Fix workflow/data-loss/crash/export blockers first, then clipping and confusing feedback; retain reproduction evidence. |
| P8 Handover | Build and fresh-install offline, execute the small-map GUI/run/report smoke check, and deliver source/installer hashes, guides and findings. |

Each package retains focused evidence and a short handover in
`SIMPLE_DELIVERY_REVIEW.md`. The reproducible QA/capture entry point is
`python -m verification.simple_delivery`; use `--help` for actions.
Keep advanced controls in existing tabs, menus and contextual panels. No new
permanent toolbar rows or always-open docks are part of this delivery.
Feature additions end at P5; QA, correction and packaging take the final third
of available time. Source/installer delivery is distinct from formal user release
acceptance and from the historical engineering audit below.

4 October run lifecycle checkpoint: the application freezes a saved revision,
runs it in a child process, moves the completed output folder, relinks it through
Simulate, reopens the project, loads read-only playback and exports a PDF report
from the frozen inputs. The Simulate panel now gives the short relink/playback/
report sequence. Seventy-five focused run/link/playback/report tests pass; the
combined test confirms the project archive and frozen run configuration remain
byte-identical. Other checkpoint 4 workflows and its delivery gate remain open;
see `PROJECT_WORKSPACE_REVIEW.md`.

4 October project lifecycle checkpoint: an application workflow saves two
portable revisions, closes and reopens the project, restores the earlier
revision, then simulates an atomic save failure after another edit. The last
valid archive stays byte-identical; a separate editor opens the recovery copy
and saves the unsaved edit to a new project. Project history now explains that
recovery path. Fifty-five focused storage/recovery/workbench tests pass. Other
checkpoint 4 workflows and its delivery gate remain open; see
`RECOVERY_REVIEW.md`.

4 October nested department-edit checkpoint: one UI workflow now places a
service location and a drop-off zone in the same child editor, accepts it,
saves the Departments list, undoes/redoes once, saves the portable project and
reopens it in the application. The department editor now explains the two-step
save. Forty-nine focused department/draft/project tests pass. Other named
checkpoint 4 workflows and its delivery gate remain to be audited; see
`DEPARTMENT_LOCATION_REVIEW.md`.

4 October related-record investigation checkpoint: from a selected task, the
timeline choice follows recorded payload, native journey and lift identities
across the saved run. The selected export follows that choice, including shared
records from other tasks. Thirty-nine focused investigation/quick-start tests
pass, and the bounded LTN log has related identities for all 206 tasks. The
illustrated guide and in-app reference now describe the control. See
`RESULTS_INVESTIGATION_REVIEW.md`.

4 October 2026 investigation export checkpoint: selecting a task, metric or lift
now enables an export containing its complete evidence timeline across all
500-event pages, alongside source identity and coverage. The UI states the
250,000-event / 300 MiB input limits and that larger logs are not truncated.
Sixty-nine focused investigation/lift/stock/partial-run tests pass; a real LTN
task export has exact linked event IDs. See `RESULTS_INVESTIGATION_REVIEW.md`.
File analysis remains in memory and larger-than-limit access remains open.

4 October 2026 JSON import checkpoint: a supported imported JSON file with
field issues now opens in the editor with a scrollable inline validation panel,
Recheck and a route back through File → Validate JSON. The modal validation
warning is removed; corrected fields save and reopen in `.amrproj`. Previous
version 1 archives now open unchanged and Save upgrades to version 2 with
explicit run-link metadata. A real supplied LTN archive migration preserved
configuration, five drawings, revision history and three run links. The focused
project/workspace/check/CAD group passes 104 tests. See `JSON_IMPORT_REVIEW.md`
and `ARCHIVE_MIGRATION_REVIEW.md`. The wider checkpoint 4 gate remains open.

4 October 2026 quick-start implementation: Help → Guided walkthrough now has
the two specified exercises and concise controls reference. The small-map
fixture, UI captures and matching Markdown/DOCX/PDF guide are in
`docs/quick-start/`; 88 focused workbench/run/check checks pass, and both
exported layouts were visually reviewed at four pages. See
`QUICK_START_REVIEW.md`. The current development installer bundles both
examples and all guide formats; an installed GUI check now opens all six LTN
DXF floors and the walkthrough, completes its bounded run and exports a PDF.
Physical screen/PDF-viewer review and later user testing remain open.

4 October 2026 offline package checkpoint: an Inno Setup per-user development
installer now bundles the PySide6 GUI, a console run/report worker, the exact
source fingerprint inputs and local examples/help. A first build failed at
QtCore import because PyInstaller collected an incompatible ICU DLL; the build
excludes it. Frozen DXF child processes now dispatch before app option parsing.
A fresh installed package imported Qt, launched the GUI, loaded all LTN DXF
floors, completed both example runs and exported PDFs under network-restricted
execution. See `OFFLINE_INSTALLER_REVIEW.md`. Remote CI evidence, physical
screen/PDF-viewer review and later release acceptance remain open.

4 October 2026 current LTN measurements: six drawing references / five unique
drawings (227.7 MB) plus configuration pack into a 15.1 MB project, with exact
roundtrip and unchanged source. Save/reopen take 2.080 / 0.317 seconds. Two
bounded six-hour saved-project runs produce identical 150 completed / 15 failed /
0 pending outcomes in 10.634 / 10.717 seconds; all outcome counts reconcile.
Failures point to graph entries inside other inventory-bay obstacle bounds at
seven drop-off zones. Navigable Project checks warnings now flag that bounded
risk; see `LOCAL_BAY_ENTRY_REVIEW.md` and `LTN_CURRENT_REVIEW.md`.
This does not close successful seven-day LTN runs,
interactive drawing performance or the wider release gates.

## Delivery and testing phases

The current roadmap phase is implementation and delivery of the listed features,
workflows, documentation and release materials. A feature is delivered when its
specified controls, data flow, user entry point and documented behaviour are
implemented to the scope stated here. Implementation checkpoints may use focused
checks to confirm that the delivered path runs and produces reviewable evidence.

Simulator design errors, unexpected results and engineering-model disagreements
found while implementing or demonstrating a feature are recorded as test-phase
findings. They do not block completion of the planned implementation deliverables.
Do not expand implementation scope to redesign simulator behaviour or resolve
those findings during this phase. Preserve the reproduction, observed result,
expected result and relevant run/configuration so the user can pick it up during
the testing phase after roadmap deliverables are complete.

After delivery, the user testing phase reviews the completed workflows and
simulator outcomes against the agreed requirements. That phase triages findings
and authorises any required simulator corrections. Release acceptance follows
that review. Keep delivery status, test findings and release acceptance distinct
throughout this roadmap.

4 October 2026 controlled scale delivery: two explicit constant-lift-health
runs complete all 7,000 tasks at 10 floors / 60 robots / 1,000 tasks/day / seven
days. The benchmark deliverable and retained evidence are complete. Input and
outcome hashes match between runs, and execution plus exports take 100.274 /
100.751 seconds. Only lift wear is overridden; the default-wear reference and its
resource constraints remain intact. This completes the controlled simple-mode
scale benchmark deliverable. LTN, detailed traffic, UI responsiveness and release
acceptance are separate roadmap/testing items.
See `WORKLOAD_SCALE_REVIEW.md` and the two constant-health evidence summaries.

4 October 2026 scale performance deliverable: a conservative pickup-floor check
avoids route estimates when no lift serving the two floors meets minimum health.
Temporary outages/repairs and same-floor work retain normal estimation; five
new cases and 269 focused regressions pass. Full unchanged workload runtime falls
from 544.498 to 213.406 seconds with an identical outcome hash. All 7,000 tasks
now reconcile as completed (6,455), failed (457) or explicitly pending (88).
The 88 pending tasks and retained resource constraints are test-phase findings.
See `WORKLOAD_SCALE_REVIEW.md`; full regression refresh and wider roadmap
deliverables remain open.

4 October 2026 pending-state investigation: new runs record each live pending
task at stop, reconcile those IDs with the bound summary, and expose a
"pending at stop" filter plus snapshot explanation in Results investigation.
Cancellation preserves partial coverage; absent reasons and older logs remain
explicitly unknown rather than inferred. The pending-state implementation is
delivered, with 129 focused checks recorded; scale outcomes remain test-phase
findings.
Before this addition, the scheduler baseline passed 2,049/2,049 isolated tests
in 441.532938 seconds at `84284b4`, with unchanged source and zero broken links:
`latest/scheduler-window-verified/index.html`. That full baseline does not include
the new pending-state feature. Preserved local LTN/simulator edits remain part of
the tested worktree. A refreshed full regression baseline and wider roadmap
deliverables remain open.

4 October 2026 charging-estimate checkpoint: repeated empty charger approaches
are reused within a single selection pass, with fresh dispatch checks and
task-specific onward feasibility. 228 focused tests pass. The full workload's
corrected outcome hash is unchanged; 544.498 seconds versus 550.802 is only one
timing sample. Final-state evidence explains the 88 floor-5 pending tasks: local
robots cannot reach compatible chargers after lift wear, and floor-5 robots are
elsewhere. Expose explicit final pending evidence in Results investigation next;
refresh the full regression baseline. Performance and scale acceptance remain
open. See `WORKLOAD_SCALE_REVIEW.md` and `workload-evidence/charge-cache.json`.

4 October 2026 scale-run defect fixed: an infeasible candidate window no longer
hides feasible tasks later in the pending queue. Route estimates remain batched;
226 focused regressions pass. The unchanged seven-day workload completes 402
additional tasks (6,455 completed, 457 failed, 88 pending), with reconciled event
counts. Runtime rises to 550.802 seconds. Explain the remaining pending work and
optimise repeated infeasible estimates next, retaining the corrected behaviour.
See `WORKLOAD_SCALE_REVIEW.md`; full workload acceptance and a refreshed full
isolated regression baseline remain open.

4 October 2026 operating-scale evidence: two controlled 10-floor, 60-robot,
7,000-task runs reproduce identical outcomes in approximately 172 seconds each.
Both have 6,053 completed, 457 failed and 490 pending tasks; lift health declines
below its operational threshold on day six. Completed/failed event reconciliation
passes, but full workload completion does not. See `WORKLOAD_SCALE_REVIEW.md`
and retained `workload-evidence` summaries. Investigate pending classification
and resource availability next; realistic LTN, detailed traffic, GUI performance
and the broader release gates remain open.

4 October 2026 integrated CAD verification baseline: **2,040/2,040 tests passed**
across **183 isolated modules** in 434.957137 seconds at `51a0a3a`. The evidence
has zero broken links and unchanged tested source. This includes layer styling,
canvas Move/Copy/Rotate, shared transform snaps and corridor endpoint trim/extend.
Review `latest/cad-transforms-verified/index.html`; JUnit, per-module logs, source
snapshot and evidence JSON are retained beside it. Preserved local simulator/LTN
changes are included, so this is not a clean-install result. The 267 unreviewed
option paths, representative workload and LTN performance measurements, remaining
core/CAD requirements, offline packaging, human approval and learning materials
retain their open gates. Passing regression tests do not close those requirements.

4 October 2026 corridor endpoint trim/extend: select one corridor and use Edit or
its context menu → Trim / extend corridor. Choose a free corridor-node endpoint
and select/pick a boundary; a ghost preview shows the proposed connected graph.
Apply moves the existing node and subdivides the boundary around that identity.
Source distance overrides scale proportionally; boundary distances and supported
route/resource references use the established subdivision rules. One-way records,
widths and door properties are retained, with one undo step. Automatic corridors,
junction/location/lift relocation, endpoint merging and occupied intersections are
rejected. Other crossings remain unchanged and physical clearance still requires
checks. All 98 related tests pass, including an independent simulator 16 m / 8 s
connection with retained one-way and door restrictions. Actual normal/large-text
captures are in `latest/cad-control-preview/corridor-endpoint*.png`. This is a
bounded graph-editing feature; general trimming and the wider roadmap remain open.

4 October 2026 shared transform snaps: Move, Copy and Rotate now use the selected
nearest, endpoint, midpoint, perpendicular or intersection snap mode. Perpendicular
uses the picked base point/rotation centre; before that anchor exists, the first
pick uses the grid/free coordinate. Visible corridor lines remain reference targets
even when endpoint markers are hidden. Hidden lines and other floors do not attract
picks. Intersection picking is read-only and never subdivides/connects graph edges.
Both snap resolution and geometry previews are coalesced; final clicks discard any
pending cursor position and resolve their own coordinates. All 73 related tests
pass, including independent coordinates, unchanged topology, hidden layers,
perpendicular movement and a 50-pointer-event/one-resolution check. Polar direction
constraints and clipboard operations remain open; this does not close the wider
CAD or release gates.

4 October 2026 canvas move/copy: both numerical transform bars now offer Pick
destination. Pick a base point and destination with grid/visible-point snapping;
coalesced previews show the result before the second click commits one undoable
edit. Numerical Move now also has a graphical preview. Copies retain their existing
new-identity, empty-bay-default and conflict-rejection rules. Selection stays intact
during picking; right-click/Escape, floor/stage changes and reopening a command
cancel the draft. Tests independently check preview/result equality, original-copy
preservation, collision rejection, zero offsets, locks and undo/redo. Broader snap
modes, clipboard operations and physical-clearance acceptance remain open.
The 100 related transform, layer, selection, layout, lock, lifecycle and evidence
tests pass. Actual normal Move and enlarged Copy captures were visually checked;
the full-suite baseline predates this increment.

4 October 2026 canvas rotation: Edit → Rotate selected now includes Pick rotation.
Click a centre, a reference direction and a target direction to commit one undoable
rotation using the existing transform model. Pointer motion previews the geometry
and reference/target rays; events are coalesced at 33 ms. Grid and visible graph-point
snaps apply to these picks. Zero-length directions are rejected; Escape/right-click,
floor changes and workspace changes cancel without mutation. Typed rotation remains
available. Edge/midpoint/intersection snaps and polar angle constraints for this
gesture remain open. Actual captures include normal mouse guides and large-text
controls in `latest/cad-control-preview`. All 79 related interaction, layer, layout,
transaction and workspace tests pass; the full baseline predates this increment.

4 October 2026 layer-line styling: the optional line-style section offers theme
colour or explicit #RRGGBB, five line patterns and cosmetic widths from 0.5–6 px.
Styles affect explicit corridor lines and location outlines, preserving semantic
point symbols, selection highlights and route-profile overlays. Style changes
are undoable, persist in project metadata, survive layer rename/current-layer
changes and can reset to the theme. Custom colours remain fixed across themes;
users must choose suitable contrast. The normal-size actual UI capture is
`latest/cad-control-preview/layer-styles.png`. Node-symbol styling, per-object
overrides, plot/export style propagation and combined layer management remain open.
Focused verification passed 92 layer, route-display, selection, map-style,
transaction and evidence tests; the full baseline below predates this increment.

4 October 2026 corrected model-layer verification baseline: **2,015/2,015 tests**
passed across **180 isolated modules** in 422.865603 seconds at `f0e33cc`, with
zero broken evidence links and unchanged tested source. MODEL-LAYERS-01 links all
19 layer acceptance cases. See `latest/model-layers-corrected/index.html`, its
evidence JSON, JUnit, module logs and frozen source archive. This supersedes the
failed layer regression run below. Preserved local simulator/LTN changes remain
included; this is not a clean-install result. The 267 unreviewed option paths,
representative workload benchmark, remaining core/CAD features, offline release
packaging, human acceptance and learning materials retain their open gates.

4 October 2026 integrated-layer regression audit: the isolated pack at `37153ba`
ran 2,014 tests in 420.735 seconds with unchanged source and zero broken evidence
links. 2,013 passed; the object-label fixture selected a corridor it had never
created. The fixture now creates that corridor. Layer visibility cleanup also
moves before drawing so hidden selected corridors cannot leave endpoint labels
for one frame; a new regression covers this. The failed full-run evidence is
retained in `latest/model-layers-verified` despite that directory's name. A new
full pass is still required after these changes. The run includes preserved local
LTN and simulator edits and is not clean-install or release acceptance evidence.
The corrected fixture and redraw ordering pass 99 focused label, layer, selection,
history, route-display and workspace-preference tests. MODEL-LAYERS-01 now links
the delivered layer contract to its acceptance cases in the feature inventory.

4 October 2026 model-layer checkpoint: View → Model layers provides project-owned
layer definitions, selected-object assignment, visibility and editing locks.
Locations, corridor nodes, lift stops, departments and explicit corridors can be
assigned. Locked corridors protect their endpoint positions and reciprocal edge
records. Layer edits participate in undo/redo and project archive storage; hidden
objects leave selection and proximity picking. These controls do not change
route-profile permissions or simulation topology. The optional dock respects
Focus canvas and workspace switching. Acceptance tests are in
`tests/test_model_layers.py`; actual UI capture is retained under
`verification/latest/cad-control-preview/model-layers.png`.

4 October 2026 layer-management follow-up: rename and move-contents/remove are
available inline. Removal previews the record count and destination; no graph
objects are deleted. Default is retained, duplicate names are rejected, and
locked source/destination layers must be unlocked. Each operation is one undo
entry. Four additional acceptance tests cover preservation, rejection and undo;
131 related tests pass. The actual panel was rendered and checked.

4 October 2026 current-layer drawing follow-up: choose a visible, unlocked layer
with Use for new drawing. New locations, nodes and explicit corridor connections
use this project-owned setting. It survives archive save/load, rename and removal,
and is undoable. Hiding or locking the current layer blocks new drawing with an
explanation; it does not silently fall back to Default. Copies retain source
layers and split nodes inherit an unambiguous parent layer. Four additional
acceptance tests cover authoring, blocked creation, persistence and UI undo.

Remaining layer work: broader styling and a combined drawing/model layer manager.
Legacy projects draw on Default. Hidden topology still participates
in model-aware drawing snaps. Locks protect editor transactions, not external
file edits. Broader release gates and human UI acceptance remain open.

Reassessed from implementation and tests on 2 October 2026, at code baseline
`b4770ca`. This replaces the earlier progress estimate while retaining the full
original roadmap. The user resumed checkpoint 1 on 3 October 2026. Work continues
in bounded checkpoints with a user verification stop after each tested commit.

Latest priority update — 3 October 2026: the user has made UI features and user
interactions the main goal and explicitly requested these next. The production
CAD interaction work now takes priority over the previous core-first sequence.
Unfinished core requirements retain their open gates; this does not mark them
complete. The tutorial and illustrated guide still follow the delivered UI.
The user selected Option A and approved its graph-focused A2 refinement on
3 October 2026. Confirmed Q&A also specifies directional window/crossing selection,
Shift selection changes, Escape cancellation and explicitly opened properties.
Implement these agreed interactions and present the working UI for review;
additional material workflows retain their review gate.
See the [stored UI options and CAD interactions](../design/ui-options/REVIEW.md).

## Assessment and evidence rules

4 October 2026 failed-edit transaction checkpoint: the shared undoable wrapper
now restores configuration, selected identities and history when an outer edit
or history commit raises. Nested edits roll back together; failed drag release
restores the pre-drag configuration. Pending earlier edits and redo branches are
preserved, transient gestures are cleared, unchanged drawing caches survive and
secondary refresh failures do not replace the original exception. This replaces
the earlier behaviour of retaining partial failed edits for manual undo and is
a prerequisite for safe model-layer rejection; model-layer locking remains open.
Six new failure cases and the full isolated suite pass: 1,996/1,996 tests across
179 modules in 414.274 seconds, no broken evidence links, source unchanged.
Pack: `latest/atomic-editor-verified/index.html`, with logs and source snapshot.
The tested tree is HEAD `31f537d` plus this transaction patch and preserved local
simulator/LTN changes; it is not a clean-install result. The 267-option semantic
review backlog, human acceptance and remaining roadmap gates stay open.

4 October 2026 DXF-layer visibility checkpoint: supported imported entities retain
their layer names, with layer-zero inheritance for existing supported block
contents. View → DXF layers opens an optional searchable dock with checkbox,
show/hide-all and isolate controls. Layer paths stay batched; visibility reuses
existing graphics without drawing I/O, model changes or undo entries. Choices
persist per drawing path on this computer. The dock hides outside Layout and in
Focus canvas, restores on return and respects explicit closure. Eight new
acceptance cases and related drawing/workspace regressions pass (62 tests), with
actual UI capture retained. Imported layers retain the existing all-visible
default; source off/frozen flags, further DXF entity support, custom model layers,
locking and line styling remain open. This is not a geometric-wall implementation.

4 October 2026 layout-copy checkpoint: Edit/context menus copy selected locations
and corridor nodes by an exact displacement, including selected-edge endpoints
and all explicit edges within the selection. Unique names, dashed previews,
profile membership, local/absolute owned geometry, internal wash references and
one-step undo/redo are implemented. Bays start empty unless Copy occupied bays is
enabled. Operational demand, people schedules, scenario events, initial fleet
and geometry are separate inputs. Automatic corridors must first be explicit;
departments/lifts use their dedicated editors. Seven copy acceptance cases plus
related CAD, profile, inventory and project regressions pass (107 tests), including
independent copied clean/dirty path lengths of 10/14 metres and project round trips.
Actual compact large-text rendering is retained. Clipboard placement, department/
lift duplication, trim/extend/offset, layers and human workflow acceptance remain open.

4 October 2026 selection-rotation checkpoint: Edit and selection context menus
now expose rotation about editable absolute X,Y with counterclockwise degrees.
A dashed graph preview shows transformed points, affected edges, boundaries,
bay outlines and the pivot before Apply. Selected-edge endpoints join the
selection; attached local/legacy geometry and bay/slot headings rotate together.
References retain identity, inferred bay dimensions become explicit to preserve
capacity, and the operation is atomic with undo/redo. Separately authored floor
geometry and initial robot headings remain fixed; users must recheck routes and
poses. Eight new acceptance cases plus related CAD/storage/lock tests pass
(101 tests). Compact large-text rendering is retained in the control preview
artifacts. Mouse-driven rotation, copy/trim/extend/offset and layers remain open.

4 October 2026 accumulated-UI regression baseline: the full isolated suite at
`53591f46410c6c4b9c20667b69d26d769d854d11` passed 1,967/1,967 tests across 175 modules
in 401.285 seconds, with zero broken evidence links and unchanged source during
testing. Evidence: `latest/boundary-ui-verified/index.html`, `evidence.json`,
JUnit results, individual module logs and `source-snapshot.zip`. This includes
the preserved local `simulator.py`, `ltn.json` and LTN handoff regression changes;
it is evidence for that captured working tree, not a clean checkout. The installed
environment also passed `python -m pip check`; this is not a clean-install test.
The inventory still has 267 options requiring semantic review. Full operating
workload benchmarking, human UI acceptance and remaining feature gates stay open.

4 October 2026 exact polygon-entry checkpoint: location boundary drafts now offer
inline absolute/relative/polar coordinates, last-point removal and explicit
Finish/Cancel controls. Mouse and keyboard input share a draft and final history
entry. Forty-eight focused tests pass, including large-font compact layout,
stale input and interaction locks; the actual UI capture is recorded in
`CAD_WORKSPACE_REVIEW.md`. General copy/rotation, layers and full release gates
remain open.

4 October 2026 boundary-editing checkpoint: polygon drafts now support Escape
cancellation, reversible corner drags, cancellation on floor/tool/workspace
changes and rejection of stale location edits. Invalid inputs remain editable
without changing the saved boundary. Seven new focused checks and related UI
regressions pass (88 tests); the remaining roadmap deliverables are listed below.
Any observed model issue is logged for the user testing phase. See
`tests/test_location_boundary_draft.py` and `CAD_WORKSPACE_REVIEW.md`.

The project has a working integrated application and substantial implementation
evidence. Remaining work covers specified workflows, model controls, documentation
and release materials. Simulator behaviour findings are tracked separately for
the user testing phase. Progress is not adequately described by a single test
count or completion percentage.

A fresh `python -m unittest discover -s tests -q` run passed all 870 tests in
approximately 120 seconds. There are 66 test modules. This verifies the exercised
cases, not every option, all input combinations or physical traffic correctness.
The earlier figure of 495 unreviewed option paths is a documentation classification
produced by `inventory.py`, not a count of 495 missing or broken features. Its input
examples and literal-key discovery also do not establish an exhaustive inventory.

For delivery tracking, distinguish:

- **Implemented:** an executable path and user entry point exist.
- **Delivery complete:** the specified implementation, user entry point, workflow
  and required documentation are present. Focused checks may confirm the path is
  runnable; they do not certify simulator design or engineering correctness.
- **Test-phase finding:** an observed error, questionable result, unsupported
  interaction or disagreement with expected simulator behaviour, recorded with a
  reproduction for review after roadmap deliverables are complete.
- **Release accepted:** the user has completed the later testing and acceptance
  phase and accepted the resulting behaviour and documented limitations.

No original release gate is declared complete by this reassessment.

## Capabilities already present — retain and harden

These are supported by code and tests, rather than progress-note claims.

| Capability | Implementation and acceptance evidence | Boundary to retain in the plan |
| --- | --- | --- |
| Integrated Project → Layout → Configuration → Check → Simulate → Review → Report | `visualiser/project_workspace.py`; `tests/test_project_workspace.py` | Advanced settings still use dialogs; integration does not mean every editing workflow is finished. |
| Compressed single-file project, deduplicated drawings, atomic saving, revisions, restore, JSON interchange and recovery | `amr_project.py`, `amr_recovery.py`; storage/recovery tests | Current archive version is supported; unsupported versions are rejected rather than migrated. Large-project retention and performance need acceptance gates. |
| External runs bound to saved inputs and revision; moved-run relinking; frozen-input playback/reporting | `amr_project_runs.py`, `amr_run_review.py`, `amr_project_report.py`; run/link/playback/workspace tests | Software fingerprint coverage needs correction. Simulation outcomes are not established merely by a valid binding. |
| Undo/redo across many editor operations, common contextual properties and bulk previews | `visualiser/edit_history.py`, properties modules and editor callbacks; edit-history/properties tests | Audit command coverage and finish common nested/create/rename/delete operations. Preserve existing draft and recovery safeguards. |
| Continuous corridor drawing, point/edge snapping, linking, splitting and subdivision | `visualiser/corridor_editing.py`, editor drawing callbacks; corridor tests | Crossings do not automatically create junctions. More explicit snapping/junction controls remain. |
| Themes, font/colour preferences, route names, patterns and directional overlays | Appearance and route-display modules and tests | Full keyboard/dialog/custom-rendering accessibility and dense-map label placement remain. |
| Structured project checks, acknowledgements, precise navigation and stale-input tracking | `visualiser/project_checks.py`, check panels/dependencies/navigation; check tests | These are selected checks, not a complete configuration schema or effective-rule validator. |
| Demand filters, timetable, rule reconciliation and dynamic-setting histories | `amr_demand_preview.py`, generation provenance and preview panel; demand/provenance tests | Independent expected counts cover a restricted schedule contract. Runtime demand stays unknown; some effective fields and no-work explanations are incomplete. |
| Task timelines, task/payload/journey/lift distinctions, metric definitions, supporting event IDs and missing-evidence handling | `amr_results_investigation.py`, `amr_lift_evidence.py`; investigation/lifecycle/energy/lift tests | Complete report coverage and delay explanations still need auditing. Investigation currently rejects logs over 300 MiB or 250,000 events. |
| Straight door clearance and clean/dirty/shared route restrictions | Simulator routing and profile resolution; engineering-reference/profile/multi-stop tests | Shared access is defined through route profiles. Width checks do not establish swept-footprint clearance. |
| Approximate corridor concurrency and local steering/reverse-heading segments | `simulator.py`: `_corridor_lane_capacity`, `_local_manoeuvre_segments_to_inventory_space` | These are existing approximations to improve, not verified keep-right lanes or radius-constrained manoeuvres. |
| Automated engineering tests and Windows CI configuration | `tests/`, `verification/run.py`, `.github/workflows/verification.yml` | Local passing tests do not demonstrate a successful remote clean installation or a finished release. |

## Delivery sequence and human review

Work proceeds through the checkpoints below. Each checkpoint ends with an
implementation summary and reviewable delivery material. Preserve focused checks
as evidence that the implemented path runs. Record simulator behaviour concerns
as test-phase findings; a user verification stop is for workflow/design review
where specified, not a requirement to diagnose simulator correctness during
implementation. Resume the next checkpoint only on the user's instruction.
Large checkpoints are delivered as reviewable slices, without changing their
completion criteria to match what happens to be implemented.

Preserve unrelated working changes, including `ltn.json`. Keep simulation outputs
external. Do not rewrite the simulator wholesale or rebuild working workspaces.
Keep technical help notes and meaningful acceptance tests alongside core changes.
Produce the final user tutorial and illustrated guide after the approved UI rework
so their instructions and screenshots match the delivered application.

### 1. Implement the concrete source-review deliverables

**Delivery update, 3 October 2026:** implementation and focused evidence are
recorded in [Local routing and software evidence](LOCAL_ROUTING_REVIEW.md).
Any simulator design review is part of the later testing phase; subsequent
geometry deliverables remain open.

**Purpose:** deliver the scoped route-failure handling and software fingerprint
changes. Record any simulator outcome concerns for later user testing.

1. Local manoeuvre failure must not silently return a blocked straight path.
   A read-only probe requested `(0, 0)` → `(4, 0)` with four rectangular walls
   enclosing the start. Both endpoints were outside obstacle interiors. The
   planner returned the direct path although its own segment check found it blocked.
   Rectangle bounds `(min_x, min_y, max_x, max_y)` were `(-1, -1, 1, -0.8)`,
   `(-1, 0.8, 1, 1)`, `(-1, -1, -0.8, 1)` and `(0.8, -1, 1, 1)`.
   Source: `simulator.py`, `_local_manoeuvre_waypoints`, direct-return fallbacks.
2. Preserve requested route endpoints or reject the request explicitly. Another
   probe placed both endpoints inside a blocking rectangle. Candidate filtering
   removed them, but the search still treated candidate indices 0 and 1 as the
   endpoints and returned an unrelated segment between obstacle corners.
   Inputs were `(0, 0)` → `(2, 0)` with rectangle `(-1, -1, 3, 1)`; returned
   endpoints were `(-1.35, -1.35)` and `(-1.35, 1.35)`.
3. Complete the run software fingerprint. `software_snapshot()` omits imported
   modules including `amr_route_reservations.py` and `amr_generation_provenance.py`;
   project/check dependencies are omitted too. Define and fingerprint the full
   relevant source dependency set. Preserve honest interpretation of older runs.

**Delivery:** implement each scoped item and retain its reproducing scenario, focused
checks and changed-result notes. Make the requested failure outcomes and fingerprint
behaviour available in the product. Record any suspected simulator-design error or
unexpected result for the later testing phase; resolving it is not a prerequisite
for completing this implementation checkpoint.

**Delivery gate:** the two probe scenarios, software fingerprint behaviour and
legacy-evidence presentation are implemented and documented with focused evidence.
Any disagreement between expected and observed simulator outcomes is recorded for
the user's testing phase. It does not block moving to the next delivery checkpoint.

### 2. Finish verification of existing configuration and simulation behaviour

**Bounded delivery scope:** finish configuration reference pages for the current
supported inputs; provide one inventory file with a row for each discovered
setting and its default, unit, editor path, runtime consumer, and known limitation;
complete the named reference workflows in slices 2A–2AN; and retain one runnable
LTN benchmark with input/output hashes and runtime/memory/project-size fields.
Do not treat exhaustive proof of every option combination as a delivery condition.
Record simulator discrepancies for user testing.

**Slice 2A, 3 October 2026:** sixteen routing/door option contracts now have
individual source/default/validation/acceptance traceability. See
[Routing contracts review](ROUTING_CONTRACTS_REVIEW.md).
**Slice 2B:** [Routing input validation](ROUTING_INPUT_REVIEW.md) rejects ambiguous
flags and invalid widths before import/simulation, and preserves positive widths
below 0.1 m. Wider schema coverage and interactive width-entry consistency remain
open, as do the full inventory and checkpoint 2 gate.
**Slice 2C:** [Generation contracts and return import parity](GENERATION_CONTRACTS_REVIEW.md)
adds 22 generation-field contracts and corrects the two imported staff defaults
that changed the reference return timing. Full import parity, staff semantics,
runtime waste/return interactions and the remainder of the inventory stay open.
**Slice 2D:** [Explicit staff choice](STAFF_CHOICE_REVIEW.md) makes false suppress
legacy Stores staffing while omission preserves the fallback across editor
roundtrips. Staff capacity/queue semantics and wider scalar validation remain open.
**Slice 2E:** [Staff contention and batch safety](STAFF_CONTENTION_REVIEW.md)
verifies the existing staffing-sizing rules and fixes three unsafe batch-sharing
cases. Six staff option contracts and dialog help clarify automatic growth.
Staff report reconciliation, shift boundaries and wider input validation remain open.
**Slice 2F:** [Staff report reconciliation](STAFF_REPORT_REVIEW.md) corrects
omitted exchanges, overridden recorded counts and reclassified Linen assignments;
adds recorded busy handling and evidence notes. Boundary review found that travel
deferred into a new four-day block can retain the previous team. Its reproduction
is recorded for the next simulator fix; full staff utilisation remains open.
**Slice 2G:** [Staff team boundaries](STAFF_SHIFT_REVIEW.md) fixes travel and
overnight bookings crossing into the wrong four-day roster; rejected candidates
do not alter outgoing reservations. Nine reference tests and two pattern contracts
cover the bounded scope. Generated legacy Stores tasks still bypass global hours
when the staff requirement is omitted; that reproduction is next.
**Slice 2H:** [Generated legacy staff hours](GENERATED_STAFF_HOURS_REVIEW.md)
attaches effective hours independently of staff choice, preserving omission/false
and required zone handoffs. Eight acceptance tests verify hours and return timing;
three global pattern fields gain traced contracts. Global staff switches and
timeframe release-spreading still need a consistent, verified contract.
**Slice 2I:** [Staff calendar switches](STAFF_CALENDAR_REVIEW.md) aligns global
pattern disablement and custom-hour precedence across generation/runtime; shared
staff-choice resolution includes legacy omissions in timeframe spreading. Nine
reference tests and two switch contracts cover the declared scope. Broader
calendar interactions and generation input validation remain open.
**Slice 2J:** [Generation input validation](GENERATION_INPUT_REVIEW.md) adds shared
raw checks before import/runtime, precise structured errors and acknowledgeable
unsupported-cycle findings. Ten tests cover rejection, non-mutation, retained
legacy forms and stale acknowledgements. Complete schema and calendar/mode
acceptance remain open.
**Slice 2K:** [Timeframe working periods](TIMEFRAME_WINDOWS_REVIEW.md) corrects
overnight carry-in, disjoint available periods and previous-day department group
sizing. Twelve references cover release arithmetic and visible fallback/deadline
explanations. Heterogeneous pooled calendars and category active-day boundaries
remain open; release spacing does not prove staffing capacity.
**Slice 2L:** [Timeframe allocation](TIMEFRAME_ALLOCATION_REVIEW.md) corrects
active-day/fortnight pool membership across midnight and preserves unrestricted
imported category/department weekdays. Twelve references cover differing
department windows, excluded slots and dialog display. Preview slot accounting
explains outcomes without claiming an independent expectation or staff capacity.
**Slice 2M:** [Accumulated demand](ACCUMULATION_REVIEW.md) fixes lost demand at
closed-time polls, inactive-date overcounting and decimal threshold/event boundaries.
Twelve references and eight option contracts cover dynamic single-pair accumulation.
Shared/legacy waste pools and tracked-item consumption remain open.
**Slice 2N:** [Waste thresholds and conservation](WASTE_CONSERVATION_REVIEW.md)
corrects effective threshold derivation, legacy closed-poll/invalid-route losses
and plain-import legacy settings. Twelve references and ten option contracts cover
the declared scope. Shared physical collection/return lifecycle and conflicting
group definitions remain open.

**Slice 2O:** [Shared-bin lifecycle](SHARED_BIN_REVIEW.md) fixes seeded payload
precedence, wrong-group reservations, discarded return settings and missing returns
after delayed assignment. Fifteen references cover identity, exact timing,
failure conservation and structured rejection of incompatible active shared rules.
Raw seed/resolved-rule parity, multi-location groups and failed collection volume
reconciliation remain open.

**Slice 2P:** [Resolved initial bins](WASTE_SEED_REVIEW.md) shares the existing
modern Waste resolver with initial seeding. Eleven references cover inherited
pickup/group/presence settings, disabled contributors, full automatic shared
multi-pickup cycles and unavailable inventory space. Legacy/custom seeding remains
an explicit compatibility adapter; threshold failure-volume reconciliation is next.

**Slice 2Q:** [Accumulated waste balance](WASTE_BALANCE_REVIEW.md) fixes duplicated
threshold volume across route pairs and lost allocations after pre-pickup failure.
Thirteen references cover pending/completed/restored/unconfirmed balances, shared
and scheduled fill, and recorded Results Investigation reconciliation. Legacy,
ordinary scheduled/sporadic and tracked-item accounting remain outside this balance.

**Slice 2R:** [Tracked stock](TRACKED_STOCK_REVIEW.md) fixes generation-time refills,
lost/overcounted calendar consumption and threshold rounding. Seventeen references
cover top-up, full content exchange, replace-empty, pending/failed supply, scheduled
orders, confirmed handoffs and persisted item/request evidence. Dedicated recorded
stock reconciliation and distinct physical content-handling workflows remain open.

**Slice 2S:** [Tracked-stock results evidence](TRACKED_STOCK_EVIDENCE_REVIEW.md)
adds per-item Results Investigation balances, explicit delivery/handoff receipts,
physical-arrival and request reconciliation, and missing-evidence handling. Ten
references cover saved runs, corrupt/incomplete records and metric navigation.
This closes the dedicated stock metrics gap from 2R within recorded-accounting
scope; independent interval recalculation and physical handling limits remain.

**Slice 2T:** [Legacy waste outcomes](LEGACY_WASTE_BALANCE_REVIEW.md) closes lost
fill after pre-pickup collection failure. Ten references cover allocation,
restoration/retry, unconfirmed post-pickup failures, duplicate/return callbacks,
saved results and old-log compatibility. Version 2 accumulated-waste evidence
includes dynamic and legacy generators; version 1 retains its narrower scope.
Ordinary scheduled/sporadic accounting and mixed-service inventory remain open.

**Slice 2U:** [Sporadic planning](SPORADIC_PREVIEW_REVIEW.md) adds deterministic
sporadic and scheduled-sporadic releases to Demand Preview, with event fractions,
mode explanations and independent bounded rate counts. Events with no valid route
pair are retained. Thirteen references plus a provenance check cover calendars,
poll boundaries, route multiplicity, saved simulation parity and limits. Hybrid
interactions, completed-volume outcomes for these modes and mixed inventory remain open.

**Slice 2V:** [Hybrid demand](HYBRID_DEMAND_REVIEW.md) fixes discrete event volume
being both dispatched directly and added to the threshold pool. Twelve references
cover the two components, retained volume, closing polls, threshold compatibility,
full transport and four editor paths. Shared mode help explains the result change;
active threshold inputs are exposed. Separate direct-event outcome accounting and
mixed-service inventory remain open.

**Slice 2W:** [Direct-event volume outcomes](DIRECT_EVENT_VOLUME_REVIEW.md) adds
separate accounting for generated scheduled-waste and sporadic task volumes,
including hybrid discrete events. Thirteen references cover outcomes, physical
pickup failure evidence, pool separation, old logs and corrupt/incomplete records.
Results Investigation links the new metrics to contributing events. This does
not prove disposal/staff handoff or complete mixed-service inventory accounting.

**Slice 2X:** [Configuration audit consolidation](CONFIG_AUDIT_REVIEW.md) records
31 group/department bindings to reviewed generation contracts, retaining partial
dispositions and shared-resolution exceptions. Representative layer tests cover
rates, returns, stock, disable flags, invalid inputs and category capacity policy.
Source links now resolve qualified definitions; the pack publishes an exact
remaining audit by family. Neither passing tests nor a reviewed partial contract
closes the feature or release gate.

**Slice 2Y:** [Lift contracts](LIFT_CONTRACT_REVIEW.md) records 19 partial scalar
contracts and unsupported legacy size-unit capacity. Fourteen references cover
independent service timing, exact cabin bounds, exclusive reservations, entry-point
validation and editor behaviour. Displays follow effective runtime speed; saves
retain unit-conversion precision and use runtime boarding/cabin defaults. Floor
identities, served-floor/coordinate structure and all precision round trips remain
open, as do the stated physical and reliability limitations.

**Slice 2Z:** [Lift floor definitions](LIFT_STRUCTURE_REVIEW.md) adds shared
identity, served-floor, starting-floor and coordinate checks, with twelve
references including negative-floor timing, atomic invalid edits and rename
collision protection. Eight structural contracts retain partial status. Floor-map
labels are canonicalised in the inventory. Valid rename/floor-removal migration,
editor precision and physical shaft/clearance claims remain open.

**Slice 2AA:** [Robot and slot contracts](ROBOT_CONTRACT_REVIEW.md) unifies raw and
editor capacity/orientation resolution, preserving legacy dimensional fallbacks
and rejecting empty or unknown permissions. Fifteen references cover exact bounds,
flags, unit balances and import parity, with 29 explicit dispositions. Combined
deck packing, aggregate structural mass, physical payload input checks beyond
orientation and complete editor precision preservation remain open.

**Slice 2AB:** [Physical payloads and storage envelopes](PAYLOAD_CONTRACT_REVIEW.md)
adds shared physical input checks and corrects bay height inference from legacy
payload dimensions. Import preserves inferred precision and dimension/flexibility
aliases. Thirteen references and 18 dispositions cover the stated cases. Full bay
input/reference validation, zero-as-inference policy, missing-template height and
swept geometry remain open.

**Slice 2AC:** [Storage bay inputs and preservation](INVENTORY_INPUT_REVIEW.md)
blocks unknown bay payload/AMR references at run time and rejects malformed
inputs and duplicate resolved names before coercion. Bay edits retain dimension-only
storage, legacy short outlines, precision and occupancy metadata. Twelve references
and 13 new partial dispositions cover the stated input and preservation cases.
Initial occupancy is explicitly distinguished from seeded stock. Location inputs,
mixed bay classification, legacy slot aliases, zero-dimension policy and full
physical geometry remain open.

**Slice 2AD:** [Location inputs and wash capacity](LOCATION_CONTRACT_REVIEW.md)
checks location scalars and wash references, reserves wash-service capacity,
preserves wash settings in the editor and updates wash references on rename.
Sixteen new tests include independent 21/27-second journeys with delivery at 9
seconds; nine dispositions expose the unused location people classification.
Physical wash efficacy, queue geometry, local-service timing alignment, general
rename/delete coverage and the complete location model remain open.

**Slice 2AE:** [Bay classification and dimension policy](INVENTORY_CLASSIFICATION_REVIEW.md)
unifies AMR markers, legacy aliases and restriction unions across runtime/editor
storage and charging. Numeric/string zero bay dimensions share inference and pass
the same preflight policy; unresolved extents, unbounded height and mixed markers
have explicit warnings. Thirteen tests and five additional partial dispositions
cover the stated cases. Fleet-to-bay matching, instance-specific charger allocation
and complete physical geometry remain open.

**Slice 2AF:** [Initial fleet and charger allocation](FLEET_ALLOCATION_REVIEW.md)
maximises distinct compatible initial charger occupancy, then parking. Shared
and instance-restricted bays are counted globally, shortages are explicit
acknowledgeable constraints, and malformed charging references block running.
Fifteen tests include 4,096 exhaustive small-graph/charger cases. Two charging
option dispositions and shared location resolution cover list/CSV/legacy inputs.
Physical parking, live fleet rematching and charging throughput remain open.

**Slice 2AG:** [Location outline coordinates and model scope](LOCATION_OUTLINE_REVIEW.md)
fixes editor rounding, large-origin area cancellation, legacy absolute playback
offsets and mixed-coordinate report measurements. Twelve tests cover coordinate
contracts, independent area/timing references, JSON/project persistence and
boundary undo/redo/cancel. Nonempty outlines expose their drawing/arrangement-only
scope in Project Checks. Physical wall containment and polygon validity remain
open for the geometry phase; these measurements are not swept-clearance proof.

**Slice 2AH:** [Storage report reconciliation](STORAGE_REPORT_REVIEW.md)
aligns payload-bay counts, AMR classification, alias/zero dimensions, payload
defaults and nominal compatible capacity with simulation. Mixed absolute/local
bay envelopes now resolve at the parent origin across runtime, editor, fleet
checks and reports. Twelve tests include independent dimensional, capacity and
overflow references. Count-only capacity comparisons are explicitly labelled;
full event coverage, live availability and physical access remain open.

**Slice 2AI:** [Department schedules and demographic inputs](DEPARTMENT_CONTRACT_REVIEW.md)
fixes shortened overnight/full-day legacy imports, the subhour waste denominator,
fractional-value truncation and loss of legacy coefficients on dialog acceptance.
Shared checks reject malformed department clocks/days/enablement, negative or
nonfinite demographic inputs and overflowing combined waste rates. Twelve tests
cover independent intervals, waste arithmetic, atomic rejection and dialog
preservation. Identity/reference/floor/coordinate and complete editing remain open.

**Slice 2AJ:** [Department identity and reference editing](DEPARTMENT_IDENTITY_REVIEW.md)
replaces edited identities atomically while retaining group/override/static-task
references and one-task demand. List cancellation preserves nested project data,
successive renames track the original ID and canvas rename supports undo/redo.
Fifteen tests cover malformed/duplicate identities, coordinate precision, name
fallback, incomplete drafts, protected deletion and graph-label collisions.
Category-location aliases, modal staleness and separate placement transactions
remain open alongside broader workspace and report coverage.

**Slice 2AK:** [Department location contracts and provisional placement](DEPARTMENT_LOCATION_REVIEW.md)
unifies service/zone aliases across generation, editing and reports. Explicit empty
modern assignments remain authoritative after clearing/deletion. Malformed values
reject; effective missing destinations block managed preflight. Placement remains
provisional through child OK, commits atomically with department Save and supports
one-step undo/redo. Fifteen tests cover these contracts and nested cancellation,
retry and reopening. General stale edits, provisional-owner sharing/deletion and
broader workspace/report acceptance remain open.

**Slice 2AL:** [Shared provisional locations and stale department drafts](DEPARTMENT_DRAFT_REVIEW.md)
transfers pending point creation to a surviving user when its originating draft is
deleted, discards unused provisional points and rejects conflicting placements.
Department dialogs retain their input and reject stale project/parent-list state,
including a replacement project with identical contents. Ten tests cover those
cases. General modal recovery, merge workflows and final CAD preview remain outside
this checkpoint.

**Slice 2AM:** [Preserve department waste-stream overrides](DEPARTMENT_WASTE_REVIEW.md)
prevents no-op department/stream edits from replacing inherited demand with zero
rates or dropping payload/capacity/extension fields. Single controls expose
inheritance; bulk edits apply only changed fields. Fourteen tests include independent
one-hour volume/count expectations, schedule/empty precedence, sparse patches and
malformed-input rejection. Legacy pickup/seeding references and remaining option
dispositions remain open alongside the broader workspace/report gates.

**Slice 2AN:** [Legacy waste stock, references and location naming](LEGACY_WASTE_SEED_REVIEW.md)
aligns active legacy bin type, initial-presence policy and group identity with its
collection tasks while preserving extra/custom stock inputs. Sixteen tests include
independent two-minute collection/return/physical-ID outcomes, shared definitions,
scalar references, deletion and suffix assignment. Managed findings explain unused
legacy overrides and routing-list scope. Suffix category keys are canonicalised in
the inventory. Wider custom/mixed-service stock and report reconciliation remain open.

**Purpose:** close the first release's engineering evidence requirement.

This checkpoint delivers the inventory and traceability materials. Runtime
findings discovered during inventory are recorded for the later user testing
phase; they do not require simulator fixes to complete this deliverable.

- Inventory actual user inputs across configuration, editor, generator and simulator
  consumption paths. Record units, defaults, precedence, validation, limitations,
  supported/partial/defective/unsupported disposition and acceptance links.
- Treat literal-key searches and example-derived option lists as discovery tools.
  Audit runtime data flow and reconcile renamed, inherited and derived settings.
- Prioritise routing/profile restrictions, doors, generation precedence and calendars,
  return/staff flows, physical payload conservation, inventory/resource contention,
  charging/energy, lifts, scenario failures and their interactions.
- Extend existing independent reference tests; do not replace useful passing tests.
  Cover normal, boundary, invalid and interacting inputs. Test outcome consistency,
  payload conservation and resource capacity, including unsuccessful route commits.
- Preserve reviewed effective waste threshold derivation. Department stream values
  can still override the restored category capacity policy; decide and document
  intended behaviour before changing that exception. Separate bug fixes from explicit
  policy changes and provide migration/result explanations where required.
- Establish a representative LTN regression matrix and baseline runtime, memory,
  project size and save/load measurements. Agree measurable acceptance thresholds
  before declaring performance satisfactory.
- Surface unsupported settings and material limitations in the application.

**Delivery gate:** the inventory file contains one row for each discovered setting
with unit, default, editor path, runtime consumer, disposition and known limit;
the LTN benchmark summary contains input/output hashes, elapsed time, memory and
project size; the help links each unsupported setting to its current limitation.
Suspected implementation issues remain in the separate test-phase findings log.

### 3. Complete three named project workflows

**Workflow A — Prepare and check a project:** open an editable project, change a
generation rule, run Project checks, review a finding, navigate to its object, and
acknowledge an allowed warning. Deliver the resolved-input checks, affected-object
navigation and stale-check indicator.

**Workflow B — Preview demand:** select a date range and department/category,
inspect generated task rows and the weekly timetable, and see why a rule produces
zero tasks. Deliver values/defaults and inactive-rule explanations supported by
the existing generator.

**Workflow C — Investigate a run:** open a saved run, filter to a task, follow its
task/payload/journey/lift records, inspect pending/failure/resource-wait reasons,
and export the selected evidence. Deliver paged access for the current 250,000
event/300 MiB log limits and explain those limits in the UI.

**Delivery gate:** the workspaces expose the specified inputs, previews, checks,
investigation views and report explanations. Record any simulator-result mismatch
or unresolved engineering question as a test-phase finding with its reproduction;
it does not hold the workspace implementation deliverable open.

**First-release delivery gate:** workflow 2 plus the project workflows in checkpoint
3 and their listed artifacts are present. Simulator findings remain separate.

### 4. Finish project and editor hardening

**Purpose:** complete the named editor and project workflows using the existing
integrated application. The approved screen design and remaining CAD actions are
specified in checkpoint 8.

- Complete one nested-edit workflow: add a department location and drop-off zone,
  save the parent dialog, undo/redo, and verify the project after reopen.
- Complete one project lifecycle workflow: save, close, reopen, restore a revision,
  and recover after a simulated failed save without losing the last valid project.
- Complete one run lifecycle workflow: freeze inputs, run, relink a moved output
  folder, reopen the read-only run and export its report.
- Complete one import workflow: import a supported JSON project, show validation
  errors inline, save as `.amrproj`, reopen and retain supported fields.
- Support migration from the immediately previous archive version; unsupported
  versions show an actionable message.
- Complete one corridor edit workflow: snap, split at a junction, preserve edge
  attributes/profile references, undo/redo and save/reopen.
- Keep keyboard access for these workflows and preserve existing user preferences.

**Delivery gate:** the five named workflows above are available in the application,
produce the described saved state, and have concise user instructions. Any observed
failure is recorded for later user testing and does not expand this implementation
scope.

This is a delivery milestone for the listed editing and project workflows. Any
behaviour findings are retained for later testing and do not hold implementation
delivery open.

**Second-release delivery gate:** all five checkpoint 4 workflows are documented
and produce the named saved project/run state. Simulator findings remain separate.

### 5. Detailed movement workflow — bounded first delivery

Add a Detailed mode choice to Simulation settings and freeze the mode in each run.
Add robot-type fields for footprint length/width, wall clearance, forward/reverse/
rotation speed, turning radius, and reverse/pivot permissions. The first delivery
supports forward travel, reverse travel and a single minimum-radius turn using one
shared trajectory for simulation, playback and event evidence. Reject unsupported
manoeuvres with a named reason and retain the run up to the failure.

**Explicitly deferred:** lateral motion, acceleration/braking, configurable turning
reference offsets, multi-point search, payload offset/articulated loads, automatic
recovery/deadlock proofs, optional passing/no-queuing areas and user-drawn obstacle
geometry. Existing drawings remain underlays. These are follow-on proposals, not
implicit parts of this bounded delivery.

**Workflow:** choose Detailed; set robot footprint and movement fields; prepare a
project with a straight corridor, one opening and one 90-degree route; save and run;
open playback and see the same recorded path and any explicit failure reason.
Delivery ends when those controls, frozen input fields, playback path and reason
display are available. Outcome concerns are recorded for user testing.

### 6. Directional passage workflow — bounded first delivery

Use explicit corridor width and robot width to choose single-file or two-lane
operation. Reserve a single-file section before entry, queue opposing robots at
its ends, and release the reservation when the robot exits or its run stops.
Provide a visible reservation/wait reason in playback and investigation.

**Explicitly deferred:** drawn passing places/no-queuing regions, mid-corridor
yielding, urgency preemption, multi-section reverse retreat and general deadlock
proof. The initial workflow covers one narrow section and two opposing robots.

**Workflow:** configure one narrow and one passable corridor; release two robots
from opposite ends; review reservation ownership, waiting reason and release in
the run. Delivery means the controls, queued state, reason and event evidence are
available. Unexpected movement outcomes are testing findings.

### 7. Constrained-turn workflow — bounded first delivery

Deliver one turn planner using the robot's configured minimum turning radius and
reverse permission. Expose steering/pivot/reverse capabilities in robot settings;
the initial planner uses steering and reverse, with pivot as an explicit opt-in.
Show the planned path before run and retain the same path in playback.

**Explicitly deferred:** multi-point manoeuvres, lateral travel, advanced search,
per-payload movement profiles and user-drawn trajectory editing.

**Workflow:** set a robot radius and permissions; use a right-angle corridor and
one constrained bay approach; inspect the planned route, save, run and inspect
playback. An unavailable turn has a named outcome for later user testing.

Delivery checkpoints 5–7 end when the named controls and workflows are present,
their run inputs are frozen, and the route/wait/failure evidence is reviewable.
The detailed simulator test phase follows after roadmap implementation deliverables.

## Core-feature delivery gate

Core checkpoints 1–7 describe implementation deliverables and can proceed alongside
the approved UI work. Their completion means the specified engineering controls,
model paths and failure reporting have been implemented. Simulator design errors
or unexpected outcomes are recorded for the later user testing phase and do not
block implementation delivery. Preparing concept images alone does not satisfy an
implementation deliverable.

### 8. User-approved UI and CAD workflow rework — current priority

**Updated entry conditions:** the latest user request explicitly brings UI and
interactions ahead of the remaining core work. The graph-focused A2 workbench and
the confirmed selection/properties conventions are authorised for implementation.
Additional material workflows outside the named checkpoints below remain deferred.
Stored images are design concepts, not evidence of implemented controls.

The production interaction checkpoint is described in
[CAD workspace review](CAD_WORKSPACE_REVIEW.md): compact commands, collapsed
properties, directional selection and typed continuous drawing. This roadmap now
limits additional CAD delivery to the workflows below.

The following [A2 implementation checkpoint](A2_IMPLEMENTATION_REVIEW.md) applies
the approved visual shell in production: workflow menus/bar, illustrated CAD
tools, light/dark/high-contrast map, Properties side tab and checks strip. Direct
Door placement preserves topology and references. Full CAD geometry commands,
run editing locks, dense labels and final human acceptance remain open.

**8A — A2 shell and session preferences**

Keep the existing graph-dominant shell, project tree, compact toolbar, collapsed
Properties tab and checks strip. Deliver three explicit session workflows: switch
Layout/Configuration/Check/Simulate/Review/Report; hide and restore panels with
Focus canvas; resize Layout and Configuration panes and retain their proportions
across restart. The existing code already supplies much of this scope; remaining
work is gaps listed in CAD_WORKSPACE_REVIEW.md. Do not reopen A/B/C navigation
selection or add docking as a requirement for this release.

**8B — drawing and selection**

Deliver three entry-to-save workflows: (1) draw a connected corridor using mouse
or typed `X,Y` / `@distance<angle`, then finish or cancel; (2) create a junction
at an existing/interior crossing and undo it; (3) select by click/window/crossing,
open Properties explicitly, edit one field, undo/redo and save/reopen. Retain the
already implemented snaps, directional window rules and CAD conventions.

**8C — graph editing**

Deliver four workflows: move selected graph objects by typed displacement or picked
destination; copy a selected subgraph with new identities and empty bays by default;
rotate a selection by typed centre/angle or picked directions; trim/extend one free
corridor endpoint to a selected boundary. Each previews before Apply, produces one
undoable change, and saves/reopens through the project archive. Defer clipboard
integration, department/lift duplication, general offset and arbitrary multi-edge
trimming.

**8D — model and drawing layers**

Deliver layer create/rename, assign selected objects, change visibility/lock, set
new-drawing layer, and set explicit line colour/pattern/width. Keep route-profile
permissions independent from visual styling. Defer per-object overrides, node
symbol styling, custom DXF source flags and export-style propagation.

**8E — presentation and edit safety**

Deliver persistent normal/dark/high-contrast themes, adjustable text size, object
name filtering, zoom-to-selection, simulation-time project edit lock, and cancellation
of active drafts on Escape or workspace/floor changes. Defers are full accessibility
certification, arbitrary docking, collision-aware label placement and all-platform
screen-size tuning.

**Delivery gate:** each numbered workflow above can be performed in the application,
shows a preview where specified, has a defined finish/cancel path, and saves through
the project file. Record simulator findings for later user testing. Human testing
is a later phase and does not block this delivery gate.

### 9. Quick-start and reference guide — after UI delivery

Deliver one in-app walkthrough and one illustrated guide (PDF plus editable DOCX
and Markdown). The walkthrough has exactly two exercises: a small connected map
with two robot types, and the supplied LTN project. Each exercise lists the actions,
expected UI state, how to save a run, where to inspect results, and how to export a
report. Include a concise reference for project checks, demand preview, snaps,
selection, undo, layers, run investigation and report export. Use captures from the
delivered UI. Do not build a general training course or duplicate the full option
inventory in the guide.

**Delivery gate:** both exercises can be followed using only the shipped help;
PDF/DOCX/Markdown files agree on steps and controls and match the delivered UI.
Simulator-result concerns are recorded for user testing.

### 10. Final release validation

Automated checks and implementation evidence run throughout development. The user
testing phase follows roadmap delivery and reviews simulator behaviour; release
acceptance follows that phase and excludes the tutorial.
Tutorial/help/guide delivery and document quality checks remain required work.

- Execute Windows clean-install and launch/run/report checks from the actual
  installer, without administrator access and with networking unavailable.
  Installation, normal operation, help and reporting must all work offline.
  Retain executed CI evidence.
- Prepare and run the complete normal/boundary/invalid/interaction test matrix and
  independent invariant checks during the user testing phase. Reconcile demand,
  event records and report totals; log findings for user triage.
- Record project size, save/load, peak memory and LTN runtime for the named
  reference workloads. No numeric pass threshold is implied until the user sets one.
- Publish one delivery pack containing feature-to-workflow mapping, run inputs,
  implementation checks, known scope limits and a separate test-phase findings log.
- Verify the contextual help, tutorial, LTN example and illustrated guide from
  checkpoint 9 against the final installed application.
- After implementation delivery, have the user review this workflow in the testing
  phase: open/create a project,
  edit geometry and configuration, check inputs, simulate, investigate results or
  a blockage, compare runs and export reports. Resolve or disposition findings under
  the user's direction before release acceptance. Do not add tutorial completion
  to this gate.

**Roadmap delivery gate:** workflows 2A–2C, 5–9 and offline packaging can be
performed from the named inputs and produce the listed saved artifacts. The
delivery pack links each workflow to its controls and scope. Simulator findings
are kept for the later user testing phase. Release acceptance follows that phase.

## Retained decisions

Windows desktop first; PySide6 and existing command-line tools retained;
engineering modellers as primary users; general engineering verification rather
than certification; revision restore rather than a tamper-proof audit;
compressed `.amrproj` with deduplicated drawings and external simulation outputs;
explicit migrations and legacy comparison; sequential user verification checkpoints.

## Confirmed Q&A decisions — 3 October 2026

These notes record the user's decisions. The bounded delivery is defined by
checkpoints 5–9; items marked deferred are future scope, not hidden acceptance
conditions for this delivery. Simulator outcomes are reviewed in the later user
testing phase.

### Simulation modes and geometry — bounded in checkpoint 5

- Provide a Simple/Detailed simulation behaviour toggle, not a UI-complexity toggle.
  Simple preserves existing graph/capacity behaviour, including door-width and
  route-profile restrictions. Detailed adds physical trajectories and traffic
  interactions. Record the selected mode with each frozen run.
- **Deferred:** Corridor width is measured between walls. Normally provide two keep-right lanes;
  use single-file operation when the loaded footprints and required clearances
  cannot accommodate two lanes. Physical openings/obstructions still use explicit
  model geometry; drawings remain underlays.
- **Deferred:** Wall clearance and robot-to-robot minimum separation are separate user settings,
  with project defaults and optional robot-type overrides. Enforce the larger
  robot-to-robot requirement when two robot types differ. The earlier 100 mm
  discussion does not establish a compulsory or universal default.
- **Deferred:** Users may draw no-queuing areas, but these are optional for simulation. Protect
  modelled doors/openings and junction connecting paths automatically even without
  custom areas. Check the complete loaded footprint when deciding whether a stop
  obstructs protected space.

### Yielding, queuing and blockage handling — deferred beyond checkpoint 6

- Robots can queue in corridors if they do not obstruct doors, junctions or drawn
  no-queuing areas. In a corridor wide enough for passing, the yielding robot may
  stop where it is if the other can physically pass with the required separation.
- Users draw passing places as usable areas; assess fit geometrically, not through
  a manually declared capacity alone. They are not mandatory for every simulation.
  Choose the nearest reachable passing place that fits when one is required.
- Task urgency is fixed and numerical. Urgency determines access priority but must
  not displace a robot already traversing a narrow section. Reserve passage before
  entry; opposing robots wait outside until the section clears, including when no
  passing places are marked.
- Reversing is allowed. A yielding robot may retreat across several corridor
  sections to a valid stopping/passing place if its complete movement is clear and
  complies with robot movement constraints. Never invent free space or a retreat.
- Distinguish ordinary waiting, genuine deadlock and exhausted search limits.
  Establish deadlock only when no permitted movement or future scheduled release
  can resolve the blockage. Stop the simulation on deadlock, retain partial results
  and evidence, and highlight the robots, blocked routes and conflicting areas.
  An exhausted search is a distinct explicit error, not proof of deadlock or passage.

### Robot movement and load model — partial delivery in checkpoint 5

- **Deferred:** Provide steering, pivoting and omnidirectional presets. Define movement capability
  per robot type, with independently selectable stationary pivot and lateral motion.
  Reversing, minimum-radius turns and multi-point manoeuvres must use those capabilities.
- **Deferred:** Use one empty and one loaded settings set per robot type, not a separate movement
  configuration for every robot/payload combination. Loaded settings may change
  movement permissions, speeds and turning radius.
- Checkpoint 5 specifies forward, reverse and rotation speeds. **Deferred:** configure sideways speed separately, exposing
  the relevant values for each type. Loaded reverse, lateral and rotation speeds
  are independently configurable from their empty equivalents.
- **Deferred:** Detailed mode models acceleration and braking explicitly, with separate empty
  and loaded values and angular acceleration/braking. These affect journey time,
  stopping distance and safe traffic behaviour.
- **Deferred:** Turning speed must satisfy both a configured maximum turning speed and a
  configured lateral-acceleration limit; use the lower permitted speed.
- **Deferred:** The turning reference point is configurable per robot using longitudinal/lateral
  offsets from its geometric centre in millimetres, and is displayed on its footprint.
  Do not silently interpret an entered turning radius as a centre-based radius.
- **Deferred:** Payloads are centred, rigidly carried loads. Offset load placement and articulated
  towing are outside this agreed scope; centred loads can still extend beyond the
  robot body and their complete footprint must be checked.

### CAD and project workflow — bounded in checkpoints 4 and 8

- **Deferred:** Support both centreline-plus-width corridor drawing with automatic nodes/links,
  and explicit boundary drawing from which the route is derived.
- Use CAD window/crossing selection: left-to-right selects fully enclosed objects;
  right-to-left selects objects touched by the selection area. Support Shift
  selection changes and Escape cancellation as proposed in the approved convention.
- Selection highlights objects; users explicitly open contextual properties.
  Preserve the approved A2 graph-dominant layout with compact, collapsible panels.
- Lock project editing while its simulation runs. Frozen inputs, revision binding
  and read-only saved-run investigation remain required.
- The representative operating workload is 10 floors, 60 robots, 1,000 tasks per
  day and seven simulated days. Benchmark this workload; do not impose these values
  as hard software limits or invent an agreed runtime threshold.
- Deliver a Windows installer that does not require administrator access. Bundle
  the dependencies/assets needed for the checkpoint 9 walkthrough and PDF/CSV reports.

### Reports, comparisons and learning materials — bounded in checkpoints 9–10

- Deliver PDF/CSV export in the report workflow. **Deferred:** individually selectable report sections for inputs/assumptions/software
  version/project revision; demand and completed/failed/pending outcomes with
  explanations; delivery times/waits/queues/resource utilisation; energy/charging/
  fleet performance; route restrictions/geometric failures/deadlocks; verification
  findings and known limitations.
- Export PDF and supporting CSV records. **Deferred:** Excel workbook and multi-run comparison, displaying input differences alongside
  results. Support runs from different project files as well as revisions of the
  same project, including alternative layouts and fleet sizes.
- Deliver an in-app guided walkthrough, illustrated PDF guide and editable Word
  and Markdown sources, covering the compact reference followed by LTN. Finish
  these against the delivered UI after core and approved UI work.
- User release acceptance is the workflow listed in checkpoint 10. Tutorial
  completion is excluded from that acceptance; the tutorial remains a deliverable.

## Next action when resumed

Continue with CAD workflows 8A–8E, then the bounded project and simulator workflows
in checkpoints 2–7, followed by the quick-start materials and offline package.
Each workflow names its user action and saved result. Keep simulator design concerns
in the test-phase findings log for the user's later review.

## Historical implementation notes

The dated implementation notes that follow preserve prior progress and evidence.
They are a development history, not additional scope or completion gates. The
bounded workflows in checkpoints 2–10 above define this delivery. If a historical
note describes a broader simulator feature, mark it as existing work or deferred
follow-up; do not infer that its full engineering validation is part of delivery.

The next correction adds the user-confirmed opt-in direct fallback for failed
local inventory-bay manoeuvres. The default remains rejection; non-finite
coordinates and corridor/traffic errors are not bypassed. Fallback segments retain
distance/time and an explicit unverified flag and failure reason in event details;
Project checks record an enabled-option warning. The independent reference run
completes in 11 seconds (nine seconds transport/handling plus two seconds direct
bay travel). Playback retains the original robot body and heading display, with
the added oversized reference cross removed. The focused 63-test run passed;
see `verification/latest/local-manoeuvre-option-tests.txt`. Full release
verification and the existing geometric-traffic limitations remain open.

The subsequent CAD correction retains drawing caches on ordinary undo/redo,
reuses unchanged DXF graphics on scene refresh and coalesces drag redraws while
preserving the final model position. Graph tools bypass native DXF hover picking;
PDF alignment retains native interaction. Delete operates on canvas selections
through the keyboard, Edit menu and right-click menu with a single undo step.
Demand generation is directly accessible under Configuration in the project tree.
Acceptance is in `tests/test_cad_delete_and_drawing_history.py`. This
checkpoint passed 105 focused regression tests; the full pack was not rerun.
Results are in `verification/latest/cad-interaction-regression.txt`. The
30,000-line drawing benchmark measured median scene refresh at 6.9 ms when
rebuilding DXF graphics and 0.2 ms when retaining them. This is an offscreen
microbenchmark, not an LTN frame-rate or full interactive performance guarantee.

The operational UI checkpoint adds a standalone workbench entry point with
optional project/JSON loading, File New with unsaved-work protection, portable
first saves and standard Save As. Opening another document clears drawing and
selection state; running simulations/reports still block document switching.
Acceptance is in `tests/test_workbench_lifecycle.py`, alongside recovery, undo,
workspace and child-process run regressions. On 3 October 2026, 116 focused tests
passed, including native startup from another working directory; the separate
verification-evidence checks also passed. Logs are in
`verification/latest/workbench-operational-tests.txt` and
`verification/latest/workbench-evidence-tests.txt`. The full pack was not rerun
for this checkpoint. This does not complete the installer,
editing locks, broader traffic model or final human workflow acceptance.

The user's latest priority on 3 October 2026 is production UI features and user
interactions. Continue the graph-dominant CAD UI next; the tutorial and illustrated
guide follow the delivered UI. Do not resume the exhaustive option audit or core
manoeuvre search as the default next task. Existing unresolved verification and
core requirements remain open release requirements.

The run-control correction and initial shared trajectory/workbench checkpoint are
implemented; see [the checkpoint](GEOMETRY_WORKBENCH_REVIEW.md). Subsequent commits
`6f4020c` and `c360a9a` added geometric timing/energy/playback integration and an
opt-in keep-right moving-traffic model. The subsequent core checkpoints add
separate clearances, motion dynamics, urgency and complete committed moving/
stationary occupancy with validated initial placements. These do not complete
detailed traffic. Verified taskless yielding now supports parked empty blockers,
reverse and permitted lateral graph paths, nearest fitting graph anchors in drawn
passing places, and ordinary safe graph anchors when places are absent. Shared
joint-plan occupancy validation now supports atomic runtime admission of one
requester and one parked empty blocker, including cases needing both old tails
to be replaced. Failed admission restores both robots and resource claims before
any events or streamed evidence are published. General multi-robot negotiation,
moving/loaded yielding, multi-point manoeuvres and proven
deadlock detection remain open. Explicit blocked/search-limit stops now preserve
verified partial runs, elapsed geometric activity and bounded playback. These
stops do not establish deadlock; complete partial stock/battery reconciliation
and partial report exports remain open. Curved motion now applies configured
angular speed, acceleration and braking, including non-pivoting robots. Existing
circular paths stop without dwell at curvature discontinuities; unchanged-curvature
subdivisions preserve timing. This does not model steering-actuator time, jerk or
continuous-curvature transitions. Explicit turning-reference offsets now drive
forward/reverse geometry, selected pivot axis, lane transitions and continuous
loaded-footprint checks while preserving body-centre endpoints. Saved schema-3
evidence and partial results distinguish reference translation from body travel;
zero offsets preserve legacy geometry. Workbench controls and playback markers
expose the point. Additional connector and multi-point searches remain open,
including some reference-axis initial heading corrections and reversals.
Movement schema 2 now requires explicit empty/loaded reverse permissions, enforced
by trajectory planning, timing and recovery search. Legacy omissions keep their
previous reverse permission; explicit migration preserves numerical inputs.
Steering, pivoting and omnidirectional permission presets are available in the
robot editor for existing detailed settings. Each state remains independently
editable; presets supply no physical parameters. The editor preserves detailed
movement/manoeuvring settings and extensions when other robot fields change.
Simple/Detailed mode selection now changes the model fields explicitly in one
undoable edit and preserves dormant inputs. Detailed requires complete explicit
movement, separate clearances, turning reference and initial placement inputs;
incomplete selections remain editable but cannot run. Historical geometric
studies remain a separately identified comparison mode. Frozen run manifests and
evidence record and verify the resolved mode; saved-run review displays it.
Complete numerical authoring and general manoeuvre search remain open. Mode
selection does not remove the existing restrictions on geometric lifts, bays,
people, scenarios, batching or general recovery/deadlock detection.
The full application guide is
also unfinished.
Continue with:

Panel-sizing checkpoint, 4 October 2026: user-resized Layout and Configuration
splitter proportions/property widths persist independently in per-user settings.
Focus canvas does not overwrite them; earlier visibility-only records remain
compatible. 46 focused workspace/preference/layout tests pass. Window geometry,
docking, configurable layers and human workflow acceptance remain open.

Workspace preference checkpoint, 4 October 2026: panel visibility and object-name
choices now persist across windows/restarts in versioned per-user settings without
changing project data/history. Focus canvas stays temporary. Malformed records and
write failures are handled explicitly. 59 focused tests pass. Persisting panel
sizes/window geometry, full layer controls and human acceptance remain open.

Compact input-layout checkpoint, 4 October 2026: actual Qt review exposed a narrow
rectangle feedback column at large text sizes. Rectangle, corridor and move bars
now place feedback beneath inputs across the full width. The 1024×768/18-point
rectangle graph viewport gains 82 pixels of height; real captures are saved under
`verification/latest/cad-control-preview/`. 69 focused layout/interaction tests
pass. This is not human UI approval or exhaustive DPI/accessibility verification.

Feature-inventory reconciliation, 4 October 2026: the project, investigation and
editing entries now match implemented controls and link their current acceptance
modules; dedicated CAD input/view entries expose their remaining limitations.
All five affected entries remain partial. The scoped isolated audit passes
449/449 tests with all references resolved and unchanged source, retained under
`verification/latest/cad-inventory-audit/`. Nine inventory-integrity tests also
pass. This corrects stale feature descriptions; it does not close the separate
267-option semantic backlog or full release/human acceptance.

Automatic crossing checkpoint, 4 October 2026: the default-off Connect crossings
while drawing corridors option previews junction positions and creates them along
the new segment in one atomic undo step. Existing door identities, directed
attributes and applicable references are retained; failed later crossings roll
back the entire edit, and collinear overlaps are explicitly rejected. 87 focused
CAD tests pass. Human acceptance and geometric/traffic validation of junctions
remain separate open requirements.

Selection navigation checkpoint, 4 October 2026: Zoom to selection is available
from View and the Select context menu. It fits active-floor points, selected
corridor endpoints and location boundaries without including/reloading underlays
or rebuilding the scene. It remains usable during simulation and leaves edits and
history untouched. 65 focused CAD tests pass; human navigation acceptance remains.

Dense-label checkpoint, 4 October 2026: View → Object names now filters to key
locations/doors or selected objects, or hides names without removing graph symbols.
Selected corridor endpoints are identified, and route labels retain their separate
control. These session view preferences remain usable during simulation locks and
do not affect project inputs/history. 87 focused tests pass. Collision-aware labels,
full layer controls, persisted filters and human acceptance remain open.

Simulation editing-lock checkpoint, 4 October 2026: managed runs now block layout
and configuration commands, property application, history edits, save/save-as,
revision restore and run-link/results-root changes. A persistent message explains
the lock. Native PDF dragging is also guarded. Pan, zoom, floor/workflow navigation,
saved-run investigation and Stop remain available. All 131 focused lifecycle/CAD
tests pass, including unlock on success, cancellation and failed startup. This
closes the identified simulation-time application editing gap within those paths;
it does not imply filesystem locking or full release/human acceptance.

Full regression checkpoint, 4 October 2026: the isolated pack at
`verification/latest/cad-snaps-verified/index.html` passes 1,927/1,927 tests across
167 modules, with zero broken evidence links and unchanged tested source
(380.095 seconds). Snapshot HEAD is `aa0a82a`, including preserved local
simulator/LTN changes and local LTN regression tests. The inventory still records
267 options awaiting semantic review. This does not close release acceptance or
the representative operating-workload benchmark. Next implement the agreed
simulation-time project editing lock; current code blocks document switching but
does not consistently block layout/configuration mutation during a running job.

Intersection-snap checkpoint, 4 October 2026: explicit intersection snapping now
creates one shared junction across intersecting corridors, including multi-way
and T-junctions, with existing identity reuse and atomic undo. Default crossing
behaviour is unchanged. 118 focused CAD tests pass, including profile/distance
preservation and filtering distant corridors before pair search. Automatic junction
insertion along a newly drawn route, human acceptance and full release verification
remain open.

CAD object-snap checkpoint, 4 October 2026: the drawing behaviour controls now
offer nearest, endpoints/graph points and corridor midpoint targets for corridors,
nodes and doors. Preview and placement share resolution; exact overlaps retain
topology and constraints reject off-direction attraction. 98 focused CAD tests
pass. Perpendicular/intersection snapping, automatic crossing insertion and human
workflow acceptance remain open.

Perpendicular snap checkpoint, 4 October 2026: route drawing can snap to the
perpendicular foot from its current endpoint onto a finite corridor. Preview and
placement share the anchor, preserve endpoint identities, split interior targets
atomically and respect active direction constraints. 101 focused CAD tests pass.
Intersection snapping and automatic crossing insertion remain open; human workflow
acceptance and the broader release gate are not closed by these tests.

CAD footprint checkpoint, 4 October 2026: locations now support two-corner
rectangular boundary drawing with live dimensions, nonmutating preview, explicit
cancellation and atomic undo/redo. Existing polygon editing remains available;
boundaries retain location-relative storage. The inline bar additionally accepts
exact width/height and optional rotation, previews the location-centred rectangle,
and applies it as one undoable edit. 127 focused tests pass, including independent
rotated geometry expectations. General multi-object rotation, later geometry
requirements and human acceptance remain open.

CAD existing-junction checkpoint, 4 October 2026: the crossing command now reuses
a unique existing point and supports T-junctions, preserving door restrictions
and the untouched branch. Ambiguous identities, department markers and near misses
are rejected without mutation. Eighty-eight focused tests pass, including actual
door routing and undo/redo. Automatic crossing insertion remains open.

CAD crossing checkpoint, 4 October 2026: an explicit two-corridor junction command
now joins same-floor interior crossings in one undoable operation. Split directions,
widths, distance overrides and route/resource references are retained. Eighty-four
focused tests pass, including clean/dirty branch restrictions. Automatic crossing
insertion and junctions at existing points remain open; no new full-pack claim is
made for this increment. See `CAD_WORKSPACE_REVIEW.md` for the user workflow.

Unattended verification checkpoint, 4 October 2026: `verification.run --isolated`
runs each test module in a fresh process with a 180-second limit and preserves
module logs, stack snapshots and per-test outcomes. Crashes, missing evidence,
empty discovery, fixture errors and timeouts fail explicitly; stale result files
are removed before each module starts. The in-process runner remains available
for cross-module diagnostics. CI now selects isolated execution. The first full
isolated pack ran 1,891 cases with one payload-settings import-path dependency;
the fixture now supplies the same visualiser path as the desktop entry point and
passes independently. The clean rerun passed **1,891/1,891 tests**, with zero
broken evidence links and an unchanged tested-source fingerprint. Review
`latest/isolated-verified/index.html`; per-module logs, JUnit, frozen source and
the full evidence JSON are retained beside it. This establishes the exercised
regression scope, not completion of unimplemented roadmap or human-acceptance
requirements. The shared-process diagnostic ran 1,887 tests with only the
already-repaired tree-search assertion failing, then waited during native shutdown;
its final process was interrupted after its test summary and stack were retained.

Regression diagnosis, 4 October 2026: the full-suite stall was traced to the
layout-property save test passing a JSON filename to the new-project `.amrproj`
save workflow and waiting in its error dialog. The test now reopens the saved
project to inspect the draft; a separate imported-JSON test retains that contract.
The tree-search assertion now distinguishes permanent workflow stages from the
filterable Demand generation child. All 36 focused property/evidence tests pass.
The verification runner now retains periodic stack snapshots in `test-stacks.txt`;
CI bounds the verification step at 20 minutes while retaining available artifacts.
Snapshots are diagnostic, not automatic failure verdicts. Full-suite rerun is
still in progress, with later delays traced to Qt global stylesheet restoration;
do not report a full pass until its terminal result is inspected.

CAD numerical move checkpoint, 4 October 2026: Edit/context-menu/Ctrl+M opens an
inline displacement preview, supporting exact Cartesian or polar offsets for
active-floor selections. Apply is atomic and undoable; cancellation is nonmutating.
Ninety-two focused tests pass. A broader discovery run was interrupted without a
result after it stopped showing observable progress; diagnose this before claiming
full-suite acceptance. Rotation/copying/scaling and human workflow review remain open.

CAD group-move checkpoint, 4 October 2026: selected points and corridor endpoints
now translate together on the active floor, retaining identities, shape offsets
and selection. Each drag is one undoable edit; Escape/mode/floor changes restore
the original state. Seventy focused tests pass. Rotation, copying, scaling and
typed displacement remain open; see `CAD_WORKSPACE_REVIEW.md`.

CAD direction checkpoint, 4 October 2026: the corridor input bar now supports
orthogonal and 15/30/45-degree mouse constraints. Typed coordinates explicitly
override them; snapping cannot deflect the selected direction. Ninety-three
focused CAD tests pass, including independent geometry and undo/preview checks.
This closes the basic orthogonal/polar drawing-control implementation, while
human acceptance, richer snap types, crossings, footprints and arcs remain open.

CAD snapping checkpoint, 4 October 2026: separate grid/object toggles and an
adjustable metre spacing now govern corridor, node and door placement. Typed
preview and commit share settings; exact overlaps preserve topology. Ninety
focused CAD tests pass. See `CAD_WORKSPACE_REVIEW.md` for scope and remaining
snap types and crossing-junction work.

Investigation UI checkpoint, 4 October 2026: timeline tables render 500 events per
page with previous/next and direct navigation, retaining every contributing record
for review/export. Filtering and load failures clear stale event details. The 62
focused regression tests pass; file analysis remains in-memory with the existing
300 MiB / 250,000-event limits. This advances large-run usability but does not
close overall performance, report coverage or remaining CAD acceptance gates.

1. Current priority: deliver the confirmed A2 CAD interactions and present the
   working production UI for review. The first checkpoint adds compact controls,
   explicitly opened properties, directional selection and typed route drawing;
   see [CAD workspace review](CAD_WORKSPACE_REVIEW.md). Continue with creation,
   snapping and property workflows, editing-lock rules, map accessibility and
   remaining material workflow approvals.
2. Complete geometric traffic occupancy, optional drawn passing/no-queuing areas,
   automatic door/junction protection, urgency-aware access and deadlock evidence
   against the confirmed Q&A requirements. Retain explicit model choice and legacy
   comparison; moving-route-only tests cannot close the full traffic gate.
3. Complete configurable turning reference points, movement presets, empty/loaded
   settings, reversing/lateral/multi-point manoeuvres and acceleration/braking.
   Integrate the same trajectories into timing, reservations and playback, without
   fallback paths. The full core-feature gate remains required before release.
   Complete cross-project run comparison, report exports and offline distribution.
4. Complete the in-app tutorial, illustrated guide, editable Word/Markdown sources
   and LTN example using the delivered UI. Execute final validation and the agreed
   user acceptance workflow, which explicitly excludes tutorial completion.

Retain the other requirements above, including report/stock reconciliation,
calendars, staffing, project reliability and final release validation. Return to
those audits when needed by these workflows and before final release. Preserve
the user's uncommitted LTN edits and the explicit UI workflow approval checkpoint.

- Optional depleted-source supply: default off; unique objects supplied at pickup, with addition events and counts. Exact identities and reserved empty exchanges retain stock requirements. Tests: `test_source_payload_replenishment`.

## Subsequent building-flow increment

The approved T1–T7 sequence is implemented separately from the preserved Simple
delivery: reproducible assets and interface inventory; checked tutorial engine
with a live-control bubble; twelve-chapter core course; frozen scenario evidence;
confirmed DXF interpretation; service-protected two-lift proposals; integrated QA,
illustrated guide and offline package. See `BUILDING_TUTORIAL_REVIEW.md` for the
package handovers and practical limits. Main instruction delivery is a small
anchored bubble; the larger walkthrough is an optional reference. Detailed
development and LTN testing, workloads, benchmarks and repairs remain deferred.
