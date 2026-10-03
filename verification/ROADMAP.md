# Dependable AMR application — revised delivery plan

Reassessed from implementation and tests on 2 October 2026, at code baseline
`b4770ca`. This replaces the earlier progress estimate while retaining the full
original roadmap. The user resumed checkpoint 1 on 3 October 2026. Work continues
in bounded checkpoints with a user verification stop after each tested commit.

Sequencing update: the major UI rework and user tutorial follow completion of
core checkpoints 1–7. Initial concept images can be prepared now for discussion;
production UI rework requires explicit user approval of the options and workflows.
The user selected Option A and approved its graph-focused A2 refinement on
3 October 2026. This sets the visual direction; detailed workflows remain for review.
See the [stored UI options and CAD interactions](../design/ui-options/REVIEW.md).

## Assessment and evidence rules

The project has a working integrated application and substantial engineering
verification infrastructure. The remaining work combines correctness gaps,
completion of existing workflows, verified physical geometry and release material.
It is not adequately described by either test count or a single completion percentage.

A fresh `python -m unittest discover -s tests -q` run passed all 870 tests in
approximately 120 seconds. There are 66 test modules. This verifies the exercised
cases, not every option, all input combinations or physical traffic correctness.
The earlier figure of 495 unreviewed option paths is a documentation classification
produced by `inventory.py`, not a count of 495 missing or broken features. Its input
examples and literal-key discovery also do not establish an exhaustive inventory.

For each requirement, distinguish:

- **Implemented:** an executable path and user entry point exist.
- **Verified within stated scope:** independently specified acceptance evidence
  covers the behaviour and boundaries being claimed.
- **Complete:** implementation, acceptance evidence, user workflow and required
  documentation meet the entire requirement; material limitations are resolved
  or explicitly excluded from supported behaviour.

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
| Task timelines, task/payload/journey/lift distinctions, metric definitions, supporting event IDs and missing-evidence handling | `amr_results_investigation.py`, `amr_lift_evidence.py`; investigation/lifecycle/energy/lift tests | Complete report coverage and delay explanations still need auditing. Investigation currently rejects logs over 150 MiB or 250,000 events. |
| Straight door clearance and clean/dirty/shared route restrictions | Simulator routing and profile resolution; engineering-reference/profile/multi-stop tests | Shared access is defined through route profiles. Width checks do not establish swept-footprint clearance. |
| Approximate corridor concurrency and local steering/reverse-heading segments | `simulator.py`: `_corridor_lane_capacity`, `_local_manoeuvre_segments_to_inventory_space` | These are existing approximations to improve, not verified keep-right lanes or radius-constrained manoeuvres. |
| Automated engineering tests and Windows CI configuration | `tests/`, `verification/run.py`, `.github/workflows/verification.yml` | Local passing tests do not demonstrate a successful remote clean installation or a finished release. |

## Delivery sequence and human review

Work proceeds through the checkpoints below. Each checkpoint ends with a tested
commit, concise changed-result explanation, reproducible review material and a
user verification stop. Resume the next checkpoint only on the user's instruction.
Large checkpoints are delivered as reviewable slices, without changing their
completion criteria to match what happens to be implemented.

Preserve unrelated working changes, including `ltn.json`. Keep simulation outputs
external. Do not rewrite the simulator wholesale or rebuild working workspaces.
Keep technical help notes and meaningful acceptance tests alongside core changes.
Produce the final user tutorial and illustrated guide after the approved UI rework
so their instructions and screenshots match the delivered application.

### 1. Correct the concrete gaps found in the source review

**Delivery update, 3 October 2026:** fixes and acceptance coverage are recorded in
[Local routing and software evidence](LOCAL_ROUTING_REVIEW.md). User verification
is the next gate; the later geometry requirements remain open.

**Purpose:** make existing behaviour and run evidence trustworthy before extending it.

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

**Delivery:** record each issue with a reproducing acceptance test; fix individually;
trace failure propagation through callers so no movement, time or resource booking
is fabricated. Make invalid endpoint placement, geometric infeasibility and search
limits explicit where applicable. Explain changed results and compatibility with
legacy runs. Preserve legacy comparison without presenting approximations as verified.

**Gate:** both geometry probes have explicit correct outcomes; unchanged valid
reference routes still pass; changes to every covered source dependency invalidate
prepared-run compatibility; older evidence remains readable with its limits shown.
Review the small references and representative LTN behaviour before continuing.

### 2. Finish verification of existing configuration and simulation behaviour

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

**Purpose:** close the first release's engineering evidence requirement.

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
- Decide and document intended waste behaviour before changing it: fallback
  thresholds currently use global stream capacity/fraction, and department stream
  values can override the restored category policy. Separate bug fixes from explicit
  policy changes and provide migration/result explanations where required.
- Establish a representative LTN regression matrix and baseline runtime, memory,
  project size and save/load measurements. Agree measurable acceptance thresholds
  before declaring performance satisfactory.
- Surface unsupported settings and material limitations in the application.

**Gate:** every inventoried option has a reviewed disposition; every supported
feature has passing acceptance evidence within an explicit contract; calculations,
results, defects and limitations are traceable in the verification pack. Remaining
unsupported behaviour is visible rather than silently accepted as supported.

### 3. Complete the three correctness workspaces

**Project checks:** extend coverage to resolved generation inputs and all relevant
references, dimensions, schedules, connectivity, profiles and resource compatibility.
Keep invalid inputs distinct from warnings and intentional constraint studies.
Finish affected-object navigation. Preserve stale-check tracking, warning review
and run-bound findings/acknowledgements.

**Demand preview:** complete task-specific values, global staff settings, implicit
defaults, inactive rules and every zero-work explanation. Reconcile configured
fixed demand independently across supported schedules and department calendars.
Retain department/category/payload/date/profile filters and timetable accounting.
State conditional and runtime-dependent work without inventing fixed totals.

**Results investigation:** retain the implemented task/payload/journey/lift separation
and missing-evidence handling. Complete assignment delay, resource wait, restriction
and failure explanations; link each supported metric and report total to contributing
records. Use frozen inputs and recorded events. Add scalable loading/access for
representative large logs while preserving older-log compatibility.

**Gate:** reference scenarios can be followed from configured demand through
preview, checks, simulated events and final reports with reconciled totals and
explanations. Missing evidence remains distinguishable from zero activity.

**First-release gate:** checkpoints 1–3 plus applicable release checks below.

### 4. Finish project and editor hardening

**Purpose:** complete the second release using the existing integrated application.
This checkpoint supplies reliable core editing commands and necessary controls.
The broad screen redesign and final user workflows are deferred to checkpoint 8;
do not choose a new navigation layout or interaction scheme on the user's behalf.

- Finish frequent nested configuration editing, rule editing and create/rename/delete
  workflows with reference-safe updates, inline properties and bulk previews.
- Audit all persistent edits for coherent undo/redo, atomic saving, recovery and
  revision comparison/restore. Retain command grouping and pending-draft protection.
- Define explicit import/archive migrations with fixtures and failure behaviour.
  Finish revision/asset retention and large-project save/load responsiveness.
- Retain revision/input/software-bound external runs, relinking and JSON interchange.
- Finish snapping controls, intentional crossing/junction creation and corridor
  operations that preserve applicable attributes/references in one undo step.
- Preserve functional keyboard access, readable controls and user preferences
  while hardening the core. Finish playback underlay functionality. Full navigation,
  dialog, typography and dense-map presentation rework is reviewed at checkpoint 8.
  Route identification must continue to use labels/patterns alongside colour.

**Gate:** representative users can create, edit, check, save, close, reopen, recover,
simulate, investigate and report a project without losing references or history.
Large-text and keyboard workflows, moved results, failed saves, migrations and
performance meet the agreed acceptance criteria.

**Second-release gate:** checkpoint 4 plus continued first-release regression and
applicable release checks below.

### 5. Verify door geometry and profile interactions

- Define explicit modelled corridor, opening, junction and obstacle geometry;
  drawings remain underlays, not inferred collision boundaries.
- Introduce explicit robot manoeuvring/clearance parameters with unit validation.
- Verify loaded robot/payload footprints through openings and along trajectories.
- Keep clean/dirty/shared access in **route profiles**. Shared sections are allowed
  by each relevant profile. Finish loaded, return, batch and empty-journey policy
  interactions without adding a competing classification system.
- Establish the trajectory representation shared by simulation and visualisation,
  collision checks, failure outcomes and an explicit legacy migration/comparison mode.

**Gate:** independently specified just-fit, just-fail, orientation, load and
profile-intersection cases agree between simulation, display and recorded evidence.
No failed geometry request silently becomes straight-line movement.

### 6. Implement verified directional traffic

- Replace approximate width-based concurrency where the geometric mode applies
  with keep-right directional lanes, narrow-section reservations and junction
  conflict handling.
- Account for loaded footprints, direction, occupancy and safe release of claims.
- Distinguish infeasible routes, deadlocks and exhausted search limits. Provide
  understandable diagnostics and evidence for the affected geometry/resources.

**Gate:** opposing traffic, narrow passages, junction crossings, queues, contention
and recovery cases satisfy capacity/collision invariants with repeatable outcomes.
The displayed and simulated trajectories are the same.

### 7. Implement constrained manoeuvres in successive checkpoints

Deliver and review in this order:

1. Minimum-radius turns and explicitly permitted pivots.
2. Reversing with explicit robot capability and motion constraints.
3. Multi-point manoeuvres with bounded search and meaningful failure reporting.

Replace footprint-derived visual steering heuristics only through an explicit
model choice/migration. Check swept loaded footprints over every manoeuvre and
use the same trajectories for timing, movement evidence and visualisation.
Provide editor controls for drawing and adjusting these paths, with visible
turning radii, permitted manoeuvres and clearance/infeasibility feedback.

**Gate for each:** independent feasible/infeasible geometry cases, minimum-radius
and clearance boundaries, resource interactions, deterministic replay and explicit
search-limit/deadlock outcomes. Legacy comparisons identify changed assumptions.

**Third-release gate:** checkpoints 5–7 plus continued earlier-release regression
and the final release requirements below.

## Core-feature completion gate

Core checkpoints 1–7 must meet their acceptance gates before production UI rework
starts: supported engineering behaviour is verified, project/run operations are
reliable, and the specified geometric model is implemented with explicit failure
outcomes. Unresolved supported-feature defects keep this gate open. Preparing
concept images is design work and does not satisfy this gate. Visual selection
does not establish implemented functionality.

### 8. User-approved UI and CAD workflow rework — after core features

**Entry conditions:** core-feature gate met, plus explicit user approval of the
proposed UI configuration and workflows. The graph-focused A2 workbench is the
approved visual direction; detailed interaction workflows remain pending. Stored
images are design concepts, not evidence of implemented controls or geometry.

**8A — design and workflow approval**

- Retain the selected A2 project-tree workbench as the visual target. The graph
  occupies the majority of the main workspace. Side and bottom panels provide
  additional information and must not overcrowd the graph. Keep drawing controls
  compact, with properties and checks collapsed in the default drawing view.
- Retain A, B and C alternatives for comparison. Review panel expansion, docking,
  resizing, remembered state and a focus-canvas action before implementation;
  frequent selection must not unexpectedly shrink the drawing area. Keep important
  check/status information discoverable when its full panel is collapsed.
- Review creation/drawing, selection/properties, configuration, checks, simulation,
  investigation and reporting flows. Show save/recovery, invalid input, stale
  checks, warnings, progress/cancellation and representative dialog states.
- Obtain explicit approval of navigation, panels, tool grouping, visual hierarchy,
  drawing gestures, keyboard mappings and the distinction between current projects
  and read-only saved runs. Elapsed time or an unattended machine is not approval.
- Confirm the selected design with a reviewable prototype before completing the
  production rework. Any material workflow change returns for user approval.

**8B — familiar CAD interaction requirements**

- Draw lines, connected polylines, arcs/fillets where supported, corridor nodes,
  doors and labelled location footprints directly on the canvas. Locations have
  clear connection points and editable size, position and rotation.
- Provide crosshair/dynamic input, typed coordinates/lengths/angles with visible
  units, grid and object snaps (endpoint, midpoint, intersection and perpendicular),
  orthogonal/polar constraints and clear snap/preview feedback.
- Support familiar selection, additive selection and window/crossing selection;
  editable grips; move, copy, rotate, trim, extend, offset, split and join operations
  where meaningful. Model topology and routing references must remain correct.
- Inserting a node on an edge splits/reconnects it atomically. Crossing a route
  must explicitly distinguish a connected junction from a geometric crossing.
- Provide layers, visibility/locking, line type, line weight, colour and labels.
  These control presentation, not routing permissions. Clean/dirty/shared access
  remains defined by route profiles; shared means membership in applicable profiles.
- Provide wheel zoom around the cursor, pan, zoom extents/selection, consistent
  Esc cancel and Enter finish behaviour, repeat command and per-operation undo/redo.
  Final keyboard/mouse mappings require user approval and discoverable tooltips.
- Show widths, turning radii and swept-clearance feedback using the verified core
  model. Invalid geometry must be explained rather than merely drawn as successful.
- Complete resizable/dockable workspaces, contextual properties, bulk-edit previews,
  consistent dialogs, large text, keyboard access, contrast and custom-rendering
  accessibility. Labels and patterns accompany route colours.

**Gate:** the user approves the design and workflows, then verifies the implemented
CAD operations on reference and LTN projects. Drawing, cancellation, selection,
topology preservation, undo/redo, save/reopen, accessibility and saved-run isolation
pass acceptance tests. Image approval alone does not prove working interactions.

### 9. User tutorial and illustrated guide — after approved UI delivery

- Deliver a compact guided tutorial taking a new user from a blank project through
  drawing corridors, placing nodes/locations/doors, assigning profiles, configuring
  robots/payloads/demand, checking, simulating, investigating and reporting.
- Include explicit step-by-step actions, expected screen states, independently
  verified expected results, common mistakes and recovery. Cover CAD snapping,
  dimensions, line types/layers, selection and undo as practical exercises.
- Follow with an LTN worked example and contextual help in the final application.
- Deliver a separate illustrated PDF user guide with editable source, an option
  reference and screenshots of the approved UI and relevant dialogs. Distinguish
  display settings from engineering model settings and explain limitations.
- Have the user complete and approve the tutorial workflow; fix unclear instructions
  and UI problems before final release. Design-concept images are not final guide
  screenshots, and checkpoint notes do not substitute for this deliverable.

**Gate:** a new engineering modeller can reproduce the expected reference outcome
and follow the LTN example using only the delivered tutorial and guide. Documents
match the released UI version and all files are retained with editable sources.

### 10. Final release validation

Automated tests and engineering evidence run throughout development. This final
gate follows the core, approved UI and tutorial gates.

- Execute Windows clean-install and launch/run/report checks from the actual
  distributable or supported installation procedure. Retain executed CI evidence.
- Run the complete normal/boundary/invalid/interaction acceptance matrix and
  independent invariant checks. Reconcile demand, event records and report totals.
- Confirm repeatability and agreed project-size, save/load, memory and LTN runtime
  thresholds with reproducible inputs and the released software fingerprint.
- Publish the general engineering verification pack: requirements/dispositions,
  independent calculations, test inputs/results, defects and unresolved limitations.
- Verify the contextual help, tutorial, LTN example and illustrated guide from
  checkpoint 9 against the final installed application.
- Have the user complete the tutorial and representative project workflow and
  resolve review findings before declaring the complete plan delivered.

**Final gate:** every original requirement has inspectable implementation,
acceptance evidence and its required user-facing deliverable. An unresolved or
unverified requirement keeps its gate open; successful narrow tests cannot close it.

## Retained decisions

Windows desktop first; PySide6 and existing command-line tools retained;
engineering modellers as primary users; general engineering verification rather
than certification; revision restore rather than a tamper-proof audit;
compressed `.amrproj` with deduplicated drawings and external simulation outputs;
explicit migrations and legacy comparison; sequential user verification checkpoints.

## Next action when resumed

Review slice 2N's waste corrections, then verify shared-bin collection and return
lifecycle, failed pickup, unreturned bins and conflicting group definitions.
Reconcile accrued demand with physical movements and remaining stock.
Retain explicit limits on staffing capacity and broader calendar combinations.
Continue the configuration inventory and independent acceptance audit through
generation precedence, schedules, returns and resource contention. Keep the larger
geometry and UI work in their planned order.
