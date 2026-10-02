# Dependable AMR application — revised delivery plan

Reassessed from implementation and tests on 2 October 2026, at code baseline
`b4770ca`. This replaces the earlier progress estimate while retaining the full
original roadmap. Implementation remains paused pending the user's instruction
to resume. Updating this plan does not authorise restarting implementation.

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
Add contextual help and meaningful acceptance tests alongside each completed feature.

### 1. Correct the concrete gaps found in the source review

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

- Finish frequent nested configuration editing, rule editing and create/rename/delete
  workflows with reference-safe updates, inline properties and bulk previews.
- Audit all persistent edits for coherent undo/redo, atomic saving, recovery and
  revision comparison/restore. Retain command grouping and pending-draft protection.
- Define explicit import/archive migrations with fixtures and failure behaviour.
  Finish revision/asset retention and large-project save/load responsiveness.
- Retain revision/input/software-bound external runs, relinking and JSON interchange.
- Finish snapping controls, intentional crossing/junction creation and corridor
  operations that preserve applicable attributes/references in one undo step.
- Complete keyboard navigation, consistent dialogs, scalable custom rendering,
  font/colour accessibility, playback underlays and dense route label placement.
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

### 8. Release validation and learning materials

This work runs alongside development; the final gate closes it rather than
starting all documentation at the end.

- Execute Windows clean-install and launch/run/report checks from the actual
  distributable or supported installation procedure. Retain executed CI evidence.
- Run the complete normal/boundary/invalid/interaction acceptance matrix and
  independent invariant checks. Reconcile demand, event records and report totals.
- Confirm repeatability and agreed project-size, save/load, memory and LTN runtime
  thresholds with reproducible inputs and the released software fingerprint.
- Publish the general engineering verification pack: requirements/dispositions,
  independent calculations, test inputs/results, defects and unresolved limitations.
- Deliver contextual help, a compact guided tutorial, the LTN worked example and
  a separate illustrated PDF user guide with editable source. Cover all supported
  options and relevant dialogs; existing checkpoint guides are supporting material.
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

Begin checkpoint 1 with the blocked local-manoeuvre reproduction and an endpoint
preservation test. Then repair software fingerprint coverage. Do not start the
larger geometric traffic model before those existing correctness gaps are closed.
