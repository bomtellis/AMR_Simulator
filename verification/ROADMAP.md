# Dependable AMR application — revised delivery plan

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
| Task timelines, task/payload/journey/lift distinctions, metric definitions, supporting event IDs and missing-evidence handling | `amr_results_investigation.py`, `amr_lift_evidence.py`; investigation/lifecycle/energy/lift tests | Complete report coverage and delay explanations still need auditing. Investigation currently rejects logs over 300 MiB or 250,000 events. |
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

### 8. User-approved UI and CAD workflow rework — current priority

**Updated entry conditions:** the latest user request explicitly brings UI and
interactions ahead of the remaining core work. The graph-focused A2 workbench and
the confirmed selection/properties conventions are authorised for implementation.
Additional material workflows retain their user review gate. Stored images are
design concepts, not evidence of implemented controls or geometry.

The first production interaction checkpoint is described in
[CAD workspace review](CAD_WORKSPACE_REVIEW.md): compact commands, collapsed
properties, directional selection and typed continuous drawing. It does not close
the full UI or core-feature gate.

The following [A2 implementation checkpoint](A2_IMPLEMENTATION_REVIEW.md) applies
the approved visual shell in production: workflow menus/bar, illustrated CAD
tools, light/dark/high-contrast map, Properties side tab and checks strip. Direct
Door placement preserves topology and references. Full CAD geometry commands,
run editing locks, dense labels and final human acceptance remain open.

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
- Supply editable guide sources in both Word and Markdown. Deliver the tutorial
  as an in-application guided walkthrough, with the compact reference and LTN example.
- Check the tutorial and guide against the delivered application. User completion
  of the tutorial is explicitly excluded from release acceptance (3 October Q&A).
  Design-concept images are not final guide screenshots, and checkpoint notes do
  not substitute for this deliverable.

**Gate:** a new engineering modeller can reproduce the expected reference outcome
and follow the LTN example using only the delivered tutorial and guide. Documents
match the released UI version and all files are retained with editable sources.

### 10. Final release validation

Automated tests and engineering evidence run throughout development. User release
acceptance follows the core and approved UI gates and excludes the tutorial.
Tutorial/help/guide delivery and document quality checks remain required work.

- Execute Windows clean-install and launch/run/report checks from the actual
  installer, without administrator access and with networking unavailable.
  Installation, normal operation, help and reporting must all work offline.
  Retain executed CI evidence.
- Run the complete normal/boundary/invalid/interaction acceptance matrix and
  independent invariant checks. Reconcile demand, event records and report totals.
- Confirm repeatability and agreed project-size, save/load, memory and LTN runtime
  thresholds with reproducible inputs and the released software fingerprint.
- Publish the general engineering verification pack: requirements/dispositions,
  independent calculations, test inputs/results, defects and unresolved limitations.
- Verify the contextual help, tutorial, LTN example and illustrated guide from
  checkpoint 9 against the final installed application.
- Have the user complete this agreed acceptance workflow: open/create a project,
  edit geometry and configuration, check inputs, simulate, investigate results or
  a blockage, compare runs and export reports. Resolve review findings before
  declaring the complete plan delivered. Do not add tutorial completion to this gate.

**Final gate:** every original requirement has inspectable implementation,
acceptance evidence and its required user-facing deliverable. An unresolved or
unverified requirement keeps its gate open; successful narrow tests cannot close it.

## Retained decisions

Windows desktop first; PySide6 and existing command-line tools retained;
engineering modellers as primary users; general engineering verification rather
than certification; revision restore rather than a tamper-proof audit;
compressed `.amrproj` with deduplicated drawings and external simulation outputs;
explicit migrations and legacy comparison; sequential user verification checkpoints.

## Confirmed Q&A decisions — 3 October 2026

These requirements refine the earlier roadmap and take precedence where wording
conflicts. They are agreed target behaviour, not claims of implemented or verified
functionality. The user explicitly resumed implementation after the Q&A and
authorised multiple subagents on 3 October 2026. Complete core features sequentially, then
the approved UI workflows, and finish the tutorial and illustrated guide at the end.
Keep engineering test evidence current throughout.

### Simulation modes and geometry

- Provide a Simple/Detailed simulation behaviour toggle, not a UI-complexity toggle.
  Simple preserves existing graph/capacity behaviour, including door-width and
  route-profile restrictions. Detailed adds physical trajectories and traffic
  interactions. Record the selected mode with each frozen run.
- Corridor width is measured between walls. Normally provide two keep-right lanes;
  use single-file operation when the loaded footprints and required clearances
  cannot accommodate two lanes. Physical openings/obstructions still use explicit
  model geometry; drawings remain underlays.
- Wall clearance and robot-to-robot minimum separation are separate user settings,
  with project defaults and optional robot-type overrides. Enforce the larger
  robot-to-robot requirement when two robot types differ. The earlier 100 mm
  discussion does not establish a compulsory or universal default.
- Users may draw no-queuing areas, but these are optional for simulation. Protect
  modelled doors/openings and junction connecting paths automatically even without
  custom areas. Check the complete loaded footprint when deciding whether a stop
  obstructs protected space.

### Yielding, queuing and blockage handling

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

### Robot movement and load model

- Provide steering, pivoting and omnidirectional presets. Define movement capability
  per robot type, with independently selectable stationary pivot and lateral motion.
  Reversing, minimum-radius turns and multi-point manoeuvres must use those capabilities.
- Use one empty and one loaded settings set per robot type, not a separate movement
  configuration for every robot/payload combination. Loaded settings may change
  movement permissions, speeds and turning radius.
- Configure forward, reverse, sideways and rotation speeds separately, exposing
  the relevant values for each type. Loaded reverse, lateral and rotation speeds
  are independently configurable from their empty equivalents.
- Detailed mode models acceleration and braking explicitly, with separate empty
  and loaded values and angular acceleration/braking. These affect journey time,
  stopping distance and safe traffic behaviour.
- Turning speed must satisfy both a configured maximum turning speed and a
  configured lateral-acceleration limit; use the lower permitted speed.
- The turning reference point is configurable per robot using longitudinal/lateral
  offsets from its geometric centre in millimetres, and is displayed on its footprint.
  Do not silently interpret an entered turning radius as a centre-based radius.
- Payloads are centred, rigidly carried loads. Offset load placement and articulated
  towing are outside this agreed scope; centred loads can still extend beyond the
  robot body and their complete footprint must be checked.

### CAD and project workflow

- Support both centreline-plus-width corridor drawing with automatic nodes/links,
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
  the dependencies/assets needed for fully offline installation, help and reporting.

### Reports, comparisons and learning materials

- Default report sections, individually selectable: inputs/assumptions/software
  version/project revision; demand and completed/failed/pending outcomes with
  explanations; delivery times/waits/queues/resource utilisation; energy/charging/
  fleet performance; route restrictions/geometric failures/deadlocks; verification
  findings and known limitations.
- Export PDF, supporting CSV records and an Excel workbook.
- Integrate comparison of multiple runs, displaying input differences alongside
  results. Support runs from different project files as well as revisions of the
  same project, including alternative layouts and fleet sizes.
- Deliver an in-app guided walkthrough, illustrated PDF guide and editable Word
  and Markdown sources, covering the compact reference followed by LTN. Finish
  these against the delivered UI after core and approved UI work.
- User release acceptance is the workflow listed in checkpoint 10. Tutorial
  completion is excluded from that acceptance; the tutorial remains a deliverable.

## Next action when resumed

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

CAD footprint checkpoint, 4 October 2026: locations now support two-corner
rectangular boundary drawing with live dimensions, nonmutating preview, explicit
cancellation and atomic undo/redo. Existing polygon editing remains available;
boundaries retain location-relative storage. 123 focused tests pass. Rotated and
numerically dimensioned footprint authoring remain open alongside later geometry
and human-acceptance requirements.

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
