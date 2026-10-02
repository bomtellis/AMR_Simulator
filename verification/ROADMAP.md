# Dependable AMR application — completion ledger

This retains the full agreed plan. A working foundation or passing narrow test
does not close a whole requirement. Human review checkpoints accompany the
implementation; no national-body certification claim is made.

## 1. Verify and explain existing behaviour — gate OPEN

| Requirement | Current evidence and remaining work |
| --- | --- |
| Reproducible baseline preserving local changes | Rollback commit `07a059a`; subsequent commits and source snapshots. The user's LTN edit remains separate. |
| Inventory every option, behaviour, units, defaults, precedence and limitation | `features.json`, `field_contracts.json`, generated inventory. Hundreds of option paths still require individual semantic review; source-key discovery is not a complete dataflow audit. |
| Explicit feature dispositions and unsupported options surfaced | Feature inventory and project-check scope findings exist. Complete option-level unsupported/defective presentation remains. |
| Independent reference calculations | Door, graph, profile, scheduled demand, capacity and payload-service cases exist. Generation boundaries, returns/staff, contention, energy, lifts, scenarios and interactions remain incomplete. |
| Individual defect reproduction and changed-result explanations | D001–D053 recorded in README, with reference failures and changed-result explanations. Continue identifying defects rather than equating green tests with complete verification. |
| LTN realistic regression and performance | Repeatable bounded six-hour windows; full representative operational and performance matrix remains. |
| Completion gate | NOT MET: every supported feature needs acceptance evidence, every inventoried option needs disposition, and unresolved limits must remain visible. |

## 2. Make correctness visible — foundations delivered, completion OPEN

| Workspace | Remaining requirements |
| --- | --- |
| Project checks | Complete reference/dimension/schedule/connectivity/profile/resource checks, check-specific staleness and navigation. Existing findings, warning acknowledgements and malformed-input blocking must cover all effective inputs. |
| Demand preview | Complete searchable table/timetable filters, effective-rule provenance and inherited/override values for every supported mode; reconcile configured demand and explain all zero-work rules. Runtime-dependent totals must remain unknown where appropriate. |
| Results investigation | Lift floor continuity, overlap and booking/log count checks now expose per-lift coverage and supporting events; see LIFT_EVIDENCE_REVIEW.md. Complete assignment/resource/route/failure explanations, task/payload/AMR/lift distinctions, all metric-to-record links, missing-evidence handling and large-log access remain. Existing frozen input/event IDs and legacy adapters are foundations. |

## 3. Dependable editing and unified project — completion OPEN

- Seven stages now share a persistent workflow tree and central workspace:
  Project, Layout, Configuration, Check, Simulate, Review and Report. Report
  generation uses selected runs' frozen inputs and external outputs. See
  PROJECT_WORKSPACE_REVIEW.md. Revision-bound playback now sits under Review with
  an embedded timeline and local monitors; see PROJECT_PLAYBACK_REVIEW.md.
  Layout objects now have a searchable tree and contextual properties with bulk
  previews, undo and draft safeguards; see LAYOUT_PROPERTIES_REVIEW.md.
  Configuration-object properties, broader identity/floor editing and replacement
  of other frequent dialogs remain unfinished. Playback underlays and large-log
  scaling remain open.
- Centralised state and undoable editing: snapshot undo/redo exists; finish
  command coverage and frequent editing outside modal dialogs.
- `.amrproj` compressed storage, deduplicated drawings, atomic saves, recovery,
  revision comparison/restore and JSON export exist. Finish explicit migration
  coverage, retention/cleanup and responsiveness for large projects.
- Results stay external. Immutable run inputs/revision/software binding and
  persistent run references/custom locations now survive reopening. Moved runs
  retain missing entries and relink by identity; Save As rebases paths. See
  PERSISTENT_RUN_LINKS_REVIEW.md. The workflow tree now includes floors; fuller
  configuration-object tree integration remains open; layout objects are listed.
- Explicit corridor splitting and subdivision now preserve edge attributes,
  routing/resource references and grouped undo; see CORRIDOR_EDITING_REVIEW.md.
  Continuous drawing now places and connects successive nodes, snaps to points
  and explicit edges, previews the next click, and supports per-step undo; see
  CORRIDOR_DRAWING_REVIEW.md. Broader snapping controls and crossing-junction
  editing remain open. Added sections can change reservation and people timing.
- Complete shared accessible themes, font/colour controls, keyboard navigation,
  dialog consistency and bulk-edit previews. Route identification must combine
  labels and line patterns with colour.

## 4. Verified geometric traffic — completion OPEN

1. Straight door-width filtering exists; complete loaded swept-footprint passage
   against modelled geometry, with drawings used only as underlays.
2. Clean/dirty/shared access uses the existing **route profiles**. Shared sections
   belong to each applicable profile; complete all interaction tests and explicit
   empty-journey policy support. Do not add a competing classification system.
3. Implement keep-right directional lanes, narrow-section reservations and
   junction conflicts. Current width-based concurrent capacity is approximate.
4. Implement radius-constrained turns and permitted pivots.
5. Implement reversing and multi-point manoeuvres.

All geometric stages require shared simulation/visualisation trajectories,
explicit manoeuvring parameters, swept collision checks, distinct infeasible,
deadlock and exhausted-search results, no silent straight-line fallback, and
explicit legacy comparison/migration.

## 5. Release discipline and learning — completion OPEN

- Execute automated tests and clean-install checks for Windows releases;
  configured CI is not evidence of an executed remote clean installation.
- Complete normal/boundary/invalid/interaction reference coverage, payload
  conservation, resource-capacity and consistent-task-outcome invariants.
- Reconcile demand, event records and all report totals.
- Measure repeatability, project size, save/load time and representative LTN
  runtime, with reproducible inputs and acceptance thresholds.
- Finish the engineering verification pack: requirements, independent
  calculations, results, defects and limitations with traceable evidence.
- Deliver contextual help, compact guided tutorial, LTN worked example and an
  illustrated PDF user guide with editable source. Existing checkpoint guides
  do not substitute for these deliverables.

## Retained decisions

Windows desktop first; PySide6 and existing command-line tools retained;
engineering modellers as primary users; general engineering verification rather
than certification; revision restore rather than a tamper-proof audit;
simulation results outside the project file. The simulator is extended
incrementally, not replaced wholesale.

## Next source-review investigations

Final partial-interval generation coverage is fixed in D013. D014 adds exact
calendar dispatch for scheduled and timeframe releases, with 22 reference cases
including overnight, department opening, staff spacing and physical-bin fills.
D015/D016 now verify onboard per-leg restrictions and straight clearance in
multi-stop routing. D017–D019 add distinct storage claims, rejected multi-stop
commit rollback and temporary capacity waiting. Review STORAGE_RESERVATIONS_REVIEW.md.
D020/D021 extend rollback to individual, idle-return and charging-route plans;
see SINGLE_CHARGE_ROLLBACK_REVIEW.md. D022–D024 verify charging travel capacity,
motor/lift energy and handled recharge events; see CHARGING_TRAVEL_REVIEW.md.
D025 verifies distinct empty-bin exchange claims and reference-cycle conservation;
see EXCHANGE_CLAIMS_REVIEW.md. D026/D027 apply physical actions at pickup/dropoff,
retain exchange stock until arrival, and preserve empties on no-return deliveries;
see PAYLOAD_ACTION_TIMING_REVIEW.md. D028 claims distinct sources for tasks requiring
existing stock; see SOURCE_PAYLOAD_CLAIMS_REVIEW.md. D029 verifies explicit-ID creation
and ordinary reuse; see EXPLICIT_PAYLOAD_IDENTITY_REVIEW.md. D030/D031 record physical
lifecycle states, staged recovery needs and evidence-based population/task counts;
see PAYLOAD_LIFECYCLE_REVIEW.md. Explicit staged recovery now has location, route,
robot and capacity checks, editor controls and outcome evidence; D032 fixes task
editing compatibility. See STAGED_RECOVERY_REVIEW.md. Staging geometry/capacity
remains open. D033 corrects delivery traction, lift-supply attribution and actual
battery feasibility; see DELIVERY_ENERGY_REVIEW.md. D034/D035 add in-place
individual-route charging retries and correct physical-event charging timestamps;
see ROUTE_CHARGE_REPLANNING_REVIEW.md. D036/D037 add required-charge dispatch
from other locations and pure charger availability checks; see
REQUIRED_CHARGE_DISPATCH_REVIEW.md. D038 separates shared task/journey energy
and adds source-attributed investigation/report reconciliation; see
SHARED_ENERGY_REVIEW.md. D039 records charging input and reconciles model battery
balances; see BATTERY_BALANCE_REVIEW.md. D040 adds direct batch charging and onward
batch feasibility for detours; see BATCH_CHARGING_REVIEW.md. D041–D043 verify charger
arrival/capacity, reject invalid credits and protect newer reservations; see
CHARGER_CONTENTION_REVIEW.md. D044–D047 verify scheduled robot/lift admission and
recovery, structural failure checks and overnight windows; see SCENARIO_RECOVERY_REVIEW.md.
D048 samples lift speeds at planned service phases and adds independent wear/repair
references; see LIFT_REPAIR_REVIEW.md. D049/D050 preserve lift floor continuity and
chronological wear/repair by protecting committed bookings; see
LIFT_RESERVATION_ORDER_REVIEW.md. Next audit mid-journey outages, multiple-lift
interactions and wider failure/recovery behaviour,
alongside the wider generation-mode matrix.
These are concrete next checks, not replacements for the full requirements above.
