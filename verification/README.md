# Engineering verification — first review gate

For current sequencing and completion criteria, use the
[revised delivery plan](ROADMAP.md), reassessed from code and tests on 2 October 2026.
Earlier checkpoint notes below are historical evidence, not the current work estimate.
The [UI design review](../design/ui-options/REVIEW.md) records the approved
graph-focused visual direction and the workflows still requiring review.

This gate establishes repeatable evidence and fixes defects reproduced by small
reference cases. It does **not** complete the feature audit or certify the simulator.
The next stage starts only after the user's review of this checkpoint.

## Review these results

The latest correction is [Timeframe allocation](TIMEFRAME_ALLOCATION_REVIEW.md):
actual release dates control pool membership across midnight; weekend import parity and
inspectable candidate-slot exclusions now accompany the reference results.
The preceding correction is [Timeframe working periods](TIMEFRAME_WINDOWS_REVIEW.md):
overnight shifts, disjoint periods and department closures now drive release spacing consistently;
Demand Preview explains out-of-hours fallback and deadline exclusions.
The preceding slice is [Generation input validation](GENERATION_INPUT_REVIEW.md):
malformed values are rejected before coercion and unsupported staff cycles have visible findings.
The preceding correction is [Staff calendar switches](STAFF_CALENDAR_REVIEW.md):
global/custom hours, runtime handling and timeframe release rules now agree in the reference cases.
The preceding correction is [Generated legacy staff hours](GENERATED_STAFF_HOURS_REVIEW.md):
omitted Stores staff choices now observe configured hours, with verified return timing.
The preceding correction is [Staff team boundaries](STAFF_SHIFT_REVIEW.md):
travel and handling are replanned with the correct roster across four-day blocks.
The preceding correction is [Staff report reconciliation](STAFF_REPORT_REVIEW.md):
recorded staffing and exchanges, separate task/busy handling time, and explicit evidence gaps.
The preceding correction is [Staff contention and batch safety](STAFF_CONTENTION_REVIEW.md):
batch sharing respects later bookings and working periods, with explicit staffing-sizing limits.
The preceding correction is [Explicit staff choice](STAFF_CHOICE_REVIEW.md):
false now suppresses legacy staff fallback while omission retains it.
The preceding slice is [Generation contracts and return import parity](GENERATION_CONTRACTS_REVIEW.md):
effective rules, completion-relative returns and preserved imported staff settings.
Earlier [Routing input validation](ROUTING_INPUT_REVIEW.md) covers:
ambiguous flags are rejected and positive widths retain their physical values.
The preceding audit is [Routing and door option contracts](ROUTING_CONTRACTS_REVIEW.md):
individual defaults, import behaviour, validation limits and acceptance links.
The latest application checkpoint is [Local routing and software evidence](LOCAL_ROUTING_REVIEW.md):
explicit local path failures, preserved endpoints, safe smoothing and broader
software fingerprints. Earlier [Effective demand settings](GENERATION_PROVENANCE_REVIEW.md) cover:
ordered rule assignments, inherited/override values and waste calculations.
[Project checks workflow](CHECK_WORKFLOW_REVIEW.md) provides
exact object/field navigation, changed-input tracking, check coverage and drawing
availability invalidation. [Route identification](ROUTE_IDENTIFICATION_REVIEW.md) provides
profile names, colours, patterns, directional access and a searchable table, shared
with frozen-run playback. [Appearance](APPEARANCE_REVIEW.md) provides
saved per-user themes, interface/map text sizes, contrast-checked colours and a
scalable or hidden layout legend. [Configuration properties](CONFIGURATION_PROPERTIES_REVIEW.md) provides
common object fields and searchable route-profile permissions in the main window.
[Layout properties](LAYOUT_PROPERTIES_REVIEW.md) provides
searchable layout objects, contextual fields, bulk previews and undoable edits.
[Project playback](PROJECT_PLAYBACK_REVIEW.md) also remains available:
saved-run playback and its timeline now stay in Review, with frozen inputs,
background loading and project-switch/pause safeguards.

Open `latest/index.html` in a browser. It contains the test results, feature
contracts, limitations and searchable option inventory. `latest/evidence.json`
contains individual outcomes, source hashes, environment versions and test links.
`latest/source-snapshot.zip` preserves the tested code and configurations, including
uncommitted files. The rollback commit before this work is `07a059a`.
Generated `latest/` bundles are ignored by Git and retained locally or uploaded as
CI artifacts; regenerate them with the commands below after cloning. The compact
review record is versioned in `REVIEW_STATUS.md`.

The current inventory distinguishes:

- **Verified reference scope:** specific stated behaviour has independent small-case tests.
- **Partial:** implemented behaviour has gaps in coverage, definitions or functionality.
- **Unsupported:** planned behaviour has not been delivered.
- **Semantic review required:** a setting was discovered but its full contract is not yet reviewed.

The inventory searches editor defaults, the built-in example, `example*.json` and
LTN. A separate literal-key source index helps find additional settings, but those
matches also include output/runtime dictionaries. It is not a complete dataflow
analysis and must not be used to claim every source key is a supported input.
Container paths and leaf settings both appear in the option count.

## Three examples for your verification

Use copies of the JSON projects in `verification/scenarios` with the existing
editor/simulator. All start at A, carry one box to B, travel at 2 m/s, and take
2 seconds each to load and unload. A–Door and Door–B each measure 5 m by the
3–4–5 triangle; the door opening is 0.8 m.

| Project | Expected result | Independent calculation |
| --- | --- | --- |
| `door-pass.json` | One completed task, 9 seconds | 0.7 m box fits; 2 + (5 + 5) / 2 + 2 |
| `door-blocked.json` | One failed task, no completed task | 0.9 m box cannot pass through a 0.8 m opening |
| `door-detour.json` | One completed task, 14 seconds | Use the explicit 20 m alternative; 2 + 20 / 2 + 2 |

In the detour example the explicit edge distance overrides its straight drawing
distance, intentionally exercising the existing distance override feature.
This checks straight passage only: door opening time, safety clearance, turn
radius, height and the swept payload envelope remain outside this claim.

Also review the generation rules: enabled groups run even when category defaults
are disabled; groups do not add an extra category-level task; multiple groups can
deliberately request separate services; category-wide zone capacity policy wins.
Legacy route profiles still union their allow-lists with task allowances, and an
empty list means unrestricted. Clean, dirty and shared access is defined by route
profiles: include shared sections in every applicable profile. See
`ROUTE_PROFILES_REVIEW.md` for the verified scope and empty/return journey policies.

## Reproduce the evidence

From the repository root, using Python 3.13 on Windows:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m verification.run --output verification/latest
.venv/Scripts/python.exe -m verification.smoke --config ltn.json --minutes 360 --output verification/latest/ltn-six-hour
```

The first command declares the previously missing `pypdf` test dependency.
The verification command exits nonzero on a failed test, a broken evidence link
or source changes during the test run. JUnit XML is available for CI consumers.
The smoke command runs the same copied LTN input twice and compares completed,
failed and pending outcomes exactly. It changes only the copy's end datetime;
the original project is checked for changes afterward. Its shorter demand horizon
does not prevent the current simulator from finishing assigned work afterward.
These are repeatability checks, not independently validated LTN results.

The Windows CI workflow installs dependencies in a clean runner and retains the
evidence even on failure. The workflow itself has not yet run on GitHub at this gate.

## Defect record and remaining work

| ID | Finding | Resolution / effect |
| --- | --- | --- |
| D001 | Oversized robot/payload could traverse narrow doors/corridors | Width now participates in shortest-path search and its cache. Wider alternatives remain usable. Impossible tasks fail with width-limit context. |
| D002 | Location capacity counted successive reservations as simultaneous | Sweep simultaneous occupancy over half-open intervals; this can reduce previously artificial waits. |
| D003 | Enabled groups ignored under disabled category defaults | Group activation now follows the same independent enable semantics as department overrides. |
| D004 | Grouped service could also generate a category-level task | Category-only fallback suppressed when groups exist; dynamic waste groups also suppress the legacy waste generator. |
| D005 | Two PDF tests could not import pypdf | Added pinned verification dependency. |
| D006 | LTN regression assumed three bays after the project acquired a fourth | Assert the actual four named bays; no LTN data was changed. |
| D007 | Fast assignment and charging estimates could still use a route rejected by door-width checks | Apply the same oriented robot/payload width to preliminary travel, energy and fast assignment queries. Three regression cases verify detour time, impossible passage and both charging-estimate legs. |
| D008 | LTN has two exits for one clinical-waste instance before its next recorded entry | Resolved: same-bin service bypassed storage and also omitted its physical arrival event. Record a distinct service arrival, reconcile it as a transfer endpoint, and retain storage counts. The bounded LTN run now has 190 paired transfers, no tracking conflicts and the same detailed task outcomes. Old logs retain their missing evidence. See PAYLOAD_SERVICE_REVIEW.md. |
| D009 | Sorting configuration keys in project, undo and recovery snapshots changed generation category iteration order | Preserve configuration key order in persisted/restored snapshots. Ordered-category acceptance tests reproduce the defect. The project-bound six-hour LTN run now matches the original detailed outcome fingerprint exactly. Previously sorted snapshots cannot reconstruct discarded order; reimport the original JSON for baseline comparisons. |
| D010 | Missing route profiles silently became unrestricted, including generated tasks and implicit dirty-label selection | Reject unknown effective profiles before scheduling. Validate active return profiles too. Static checks now detect missing implicit dirty profiles; effective generation overrides are checked by the engine. Runs using invalid names must be corrected rather than compared as valid routing results. |
| D011 | Generating profile edges from selected nodes omitted reverse directions of two-way corridors | Generate both permitted directions and remove duplicates. One-way corridors remain one-way. Existing manually authored or saved edge lists remain unchanged until deliberately regenerated. |
| D012 | Editor normalisation and the task-generation dialog discarded update_interval_sec | Preserve the explicit interval through open, save, reopen and dialog acceptance. A 60-second interval in the short reference run previously reverted to 900 seconds and produced no scheduled work. Three independent regression tests cover persistence and engine outcomes. |
| D013 | Generation skipped the final partial update interval | Schedule one final update at the inclusive demand horizon. Six reference cases cover short, partial, exact, disabled and zero-duration boundaries. Newly recovered work may complete after the demand horizon. This fixes coverage, not exact-time dispatch. |
| D014 | Scheduled work between updates is discovered and assigned late; midnight can discard demand | Resolved for clock schedules and timeframe slots: plan exact calendar events without precreating tasks or advancing accumulation polls. Retain schedules deferred to another day's opening. Effective releases before the simulation start are excluded instead of replayed at zero. This intentionally changes legacy catch-up and dispatch results. Twenty-two reference tests cover timing, recurrence, opening hours, staff slots, physical-bin fill thresholds and preview agreement. See SCHEDULED_DISPATCH_REVIEW.md. |
| D015 | Multi-stop tours used only the first task's route restrictions throughout the journey | Intersect effective node, edge and lift permissions for the payloads currently on board. An empty intersection is forbidden, distinct from an unrestricted empty input list, including in route caches. Remove restrictions after delivery; apply new ones at pickup. Incompatible batches can run as separate valid journeys. See MULTI_STOP_ROUTING_REVIEW.md. |
| D016 | Multi-stop ordering ignored loaded width, while committed legs kept the whole batch's footprint before pickup and after delivery | Use the current onboard oriented envelope in ordering and committed route checks. A delivered wide payload no longer blocks a later narrow corridor, and an uncollected wide payload does not block its approach. Geometry remains the existing straight-passage approximation. |
| D017 | Multi-stop estimates could allocate one free bay to multiple deliveries, and stale assignment names could overwrite active claims | Match strict deliveries to distinct compatible bays before commitment; retain other tasks' claims and give strict deliveries priority over optional overflow. See STORAGE_RESERVATIONS_REVIEW.md. |
| D018 | Rejected multi-stop commits leaked route/storage reservations, lift operational state or energy | Journal touched entries and restore them on rejection or exception, including late battery failure and lift wear/failure state. Successful commits retain their reservations. Single-task and charging paths remain separate audits. |
| D019 | Temporarily full storage caused immediate task failure even when a later return would release capacity | Wait under the original deferral deadline; unlimited waits can remain pending. Physically incompatible bays still fail immediately. Wait records retain the reason observed at the start of the wait. |
| D020 | Rejected individual delivery or idle-return plans left reservations, task targets, lift state, energy or charge records behind | Extend the serial route transaction to individual and idle-return commits. Restore robot state and appended charging records as well as reservations. See SINGLE_CHARGE_ROLLBACK_REVIEW.md. |
| D021 | Failed charging routes released departure occupancy or retained target/lift mutations; estimates changed the target charger | Release the departure bay inside the charging-route transaction, restore touched state on rejection/exception, and keep target selection in committed plans. Successful plans retain the destination claim. |
| D022 | Charging trips did not reserve corridor capacity, including lift approaches and exits | Reserve corridor and node intervals for committed charging travel. Two single-capacity reference trips now finish at 5 and 10 seconds instead of both at 5 seconds. See CHARGING_TRAVEL_REVIEW.md. |
| D023 | Charging travel omitted motor/battery and lift-supply energy, allowing unreachable trips and understating recharge duration | Account for empty motor travel, record lift supply separately, select energy-reachable chargers and recharge from arrival energy. Explicit waits have zero traction consumption under the retained approximate model. |
| D024 | Legacy recharge helper emitted events without handlers, leaving the battery unchanged | Delegate to the handled charge-cycle scheduler. An end-to-end reference verifies travel, charging records, completion and full battery. |
| D025 | Multiple delivery plans could depend on one physical empty bin at a finite exchange store | Match distinct existing empty instances, reserve them on commitment, consume the owning task's claim, and release unconsumed claims on rejection or failure. Same-bin service retains separate exchange stock. See EXCHANGE_CLAIMS_REVIEW.md. |
| D026 | Physical pickup and drop-off were usually applied at journey completion with backdated logs | Schedule idempotent stock actions at their planned times, including early batch drops and post-delivery wash. Stage exchange stock at arrival. Record unconfirmed arrival after an in-transit failure and prevent failed batch members completing. See PAYLOAD_ACTION_TIMING_REVIEW.md. |
| D027 | Full-bin deliveries without returns removed empty bins unnecessarily | Consume exchange stock only for an enabled equivalent-bin return. Other deliveries require ordinary free capacity; preserve empty stock when waiting or timing out. |
| D028 | Existing-source checks could promise the same container to competing robots or multiple batch pickups | Match distinct sources and exchange empties, claim at commit, restore claims and bindings on rejection, and retain the original waiting deadline. Delivered stock remains reusable. See SOURCE_PAYLOAD_CLAIMS_REVIEW.md. D029 extends this to ordinary outbound ID creation/reuse. |
| D029 | Ordinary outbound tasks could create the same explicit ID twice or recreate it while stored elsewhere/in transit | Distinguish planned registration, exclusive creation claims and physically issued IDs. Issued IDs require source stock for ordinary reuse; failed pre-pickup plans release creation rights, while transit failures do not recreate stock. Avoid generated-ID collisions and flag conflicting payload types in project checks. See EXPLICIT_PAYLOAD_IDENTITY_REVIEW.md. |
| D030 | Population peaks excluded carried/staged containers, while known totals included unissued planned IDs | Track planned, stored, in-transit, staged, unconfirmed and removed states; count active issued identities and publish final identity evidence. Failed returns retain staged containers and flag recovery needs. Actual recovery commands and staging geometry remain open. See PAYLOAD_LIFECYCLE_REVIEW.md. |
| D031 | Report deduplication erased tasks reusing a container; missing evidence became invented counts, and initial inventory was counted as transported | Count tasks independently of physical IDs; pair departures with stored/service arrivals, excluding seeded stock. Keep unknown population and transported counts missing in older logs. State the basis of per-type peaks and separate cumulative issued counts. See PAYLOAD_LIFECYCLE_REVIEW.md. |
| D032 | The task form emitted manual flags the simulator constructor rejected, and editing replaced unexposed task settings | Accept the editor's manual-task fields and preserve seed settings, including explicit identities and restrictions. The form now exposes staged-recovery tasks. See STAGED_RECOVERY_REVIEW.md. |
| D033 | Delivery energy charged lift supply and queued time to the AMR, retained delivered batch weight, omitted boarding standby, and allowed cross-floor battery overdraw | Calculate traction per movement using onboard payloads, record lift supply once, and reject commits below reserve with rollback. See DELIVERY_ENERGY_REVIEW.md and the independent before/after cases. |
| D034 | A cross-floor or local-manoeuvre battery shortfall left individual work pending even while the robot was at a charger | Retry after a full charge, rollback the first attempt and reconstruct resource times. Full-battery excess has an explicit pending reason. See ROUTE_CHARGE_REPLANNING_REVIEW.md. |
| D035 | Pre-task charging appeared twice in movement and physical-payload timestamps | Start the segment timeline at charging start, retaining the actual charge end separately. Independent same-floor and cross-floor cases verify pickup, arrival, completion and busy duration. |
| D036 | Idle robots above reserve could strand tasks requiring more route energy, despite reachable chargers | Use explicit scheduler charge requests, check compatible reachable chargers and onward feasibility, retain pending work, and commit charging separately. See REQUIRED_CHARGE_DISPATCH_REVIEW.md. |
| D037 | Read-only charger availability checks cleared stale bay occupancy/reservations | Make inspection pure and defer stale-marker cleanup to serial reservation/arrival operations. Live occupants remain protected; failed commits retain transaction rollback. |
| D038 | Shared journey energy was repeated per task and added again in the transport matrix; legacy missing lift energy appeared as zero | Leave per-task shared energy unallocated, retain explicitly scoped journey totals, and use one source-attributed movement ledger for investigation and report totals. Missing attribution remains unknown. See SHARED_ENERGY_REVIEW.md. |
| D039 | An in-place pre-task charge added battery energy but its exported charge segment recorded zero input | Record its planned input, log applied charge credits separately, and reconcile each robot's initial, credited, traction and final energy. Cancelled or legacy evidence cannot establish a full balance. See BATTERY_BALANCE_REVIEW.md. |
| D040 | A multi-stop batch needing charge was rejected even at a usable charger, forcing individual delivery fallback | Replan batches after in-place charging; check reachable chargers against the full onward batch, with serial rechecks and rollback. Feasible deliveries precede charging detours. See BATCH_CHARGING_REVIEW.md. |
| D041 | Charger occupancy began before arrival; rejected bay claims could still credit charging, and unavailable chargers polluted delivery failures | Add arrival/completion phase and cycle checks, separate operational wait/failure evidence and validate bay ownership before battery credit. See CHARGER_CONTENTION_REVIEW.md. |
| D042 | An older delivery completion could clear a newly assigned charger reservation at the same timestamp | Skip obsolete stow actions once newer work or charging owns the robot. The reproduced two-robot case now uses one charger serially. See CHARGER_CONTENTION_REVIEW.md. |
| D043 | An identical local start/end pose generated an alignment loop, consuming time and battery | Return zero local movement when both position and heading match. See CHARGER_CONTENTION_REVIEW.md. |
| D044 | Valid work could remain asleep after a temporary robot outage | Schedule scenario start/end checks that invalidate estimates and retry pending work. See SCENARIO_RECOVERY_REVIEW.md. |
| D045 | A temporary lift outage could permanently fail a structurally valid delivery | Separate allowed graph/lift/width feasibility from current availability; retain original task deadlines. See SCENARIO_RECOVERY_REVIEW.md. |
| D046 | Multi-stop assignment bypassed robot outage admission | Apply robot availability to batch and separate charging admission. See SCENARIO_RECOVERY_REVIEW.md. |
| D047 | Overnight scenario weekdays were interpreted as the current day, losing the after-midnight portion | Anchor half-open intervals to their start day and preserve fractional boundary comparisons. See SCENARIO_RECOVERY_REVIEW.md. |
| D048 | Lift service delayed by repair used scenario speed at planning time | Sample reposition, loaded and reset movement speed at their planned phase start; reject non-finite future candidates. See LIFT_REPAIR_REVIEW.md. |
| D049 | Earlier lift gap insertion allowed a reset movement that was never recorded or reserved | Permit gaps only when the recorded journey restores the next booking's original starting floor. See LIFT_RESERVATION_ORDER_REVIEW.md. |
| D050 | Earlier gap insertion used future wear state and could place its repair after a later booked journey | Keep wear/failure-enabled journeys in chronological commitment order; preserve committed routes and expose the scheduling assumption in Project Checks. See LIFT_RESERVATION_ORDER_REVIEW.md. |
| D051 | Investigation exports and header replaced the event-log path with `lift_supply` | Keep the energy-source loop variable separate from the original log source path. See LIFT_EVIDENCE_REVIEW.md. |
| D052 | Unchecking Bidirectional edges still created a link the simulator could traverse both ways | Connect and continuous-drawing tools now write the selected direction explicitly. Existing links retain their directions. See CORRIDOR_DRAWING_REVIEW.md and baseline/corridor-direction-before-fix.txt. |
| D053 | Reading absent drawing lists silently edited the project and caused a false unsaved indicator | Drawing queries no longer insert configuration fields; explicit mapping edits still create lists. See PROJECT_WORKSPACE_REVIEW.md and baseline/drawing-read-before-fix.txt. |
| D054 | An edge finding selected its start node instead of its corridor record | Resolve exact finding paths before human-readable targets, then focus supported properties. See CHECK_WORKFLOW_REVIEW.md and baseline/check-navigation-and-drawing-before-fix.txt. |
| D055 | Adding or removing a referenced drawing left checks current when JSON was unchanged | Track the availability tested by drawing checks and invalidate run readiness when it changes. See CHECK_WORKFLOW_REVIEW.md and baseline/check-navigation-and-drawing-before-fix.txt. |

The original 115-test baseline and before-fix reference failures are in `baseline/`.
Continue individual option contracts and independent cases for other generation
modes, lifts, energy, resource contention and reports. Structured findings are now
available at the Project checks checkpoint described below. The project container,
unified UI, lanes, swept turns, tutorials and illustrated guide remain later stages.
Broader route-profile interactions, time-boundary semantics and approximate lane
capacity remain outstanding. Shared sections use the existing route profiles;
there is no separate clean/dirty classification system.

## Project checks checkpoint

In the editor, use **Home → Project checks**. The dock stays open while editing.
Filter by severity or search for an object. Select a finding for its explanation,
consequence, setting path and next action. **Go to affected settings** selects a
graph point or opens the relevant settings editor. Older validator findings that
do not identify a section retain their explanation without precise navigation.
Severity is written in text; it does not depend on colour.

Any configuration edit makes the report stale (checked every 750 ms and again
before actions). Rerunning checks resets warning acknowledgement. Export saves a
JSON record containing findings, stable finding IDs and the configuration hash.

Launcher runs now review the raw configuration before normalisation. Detected
malformed input errors block a run. Warnings describe operational constraints,
missing drawings or unresolved rule references and require acknowledgement.
Each run saves the exact reviewed input bytes as `config.json` and saves findings
and acknowledged warning IDs in `project_checks.json`. The manifest contains
both a file hash and a canonical configuration hash. An external configuration
edit during review prevents launch unless its parsed values still match.
Direct command-line simulation retains its existing behaviour.

Manual review before the next stage:

1. Open LTN without drawings and open Project checks. Its stored linen group
   references to `D26-LINEN` should appear as warnings. Department assignments can
   replace group destinations, so these are not a claim that LTN demand fails.
2. Search for `D26`, select a warning and open its task-generation settings.
3. Edit a setting on a disposable copy. Confirm the checks become stale and
   export/navigation are disabled until checks are rerun.
4. In the launcher, try a copy with robot speed zero: the error must prevent a run.
   Restore a valid speed, recheck, review warnings and run. Inspect its saved checks.
5. Confirm the dock and run dialog are readable with your display scaling and
   keyboard navigation. Automated Qt checks and a local render do not replace this.

This is incremental preflight, not a complete schema or acceptance of every
configuration field. Static directed connectivity and profile allowance unions
are checked; loaded door passage, lift compatibility, dynamic generation
precedence, capacity contention and swept geometry are not proved by preflight.
Existing reference simulation tests still supply those narrower verified claims.
Drawing file availability is checked on recheck, not watched continuously.
All checks become stale together; dependency-specific invalidation is deferred.
Demand preview is now available at the checkpoint described below.

## Demand preview checkpoint

Use **Home → Demand preview → Build preview**. Inspect the task table, hourly
timetable and rule reconciliation; filter by department, category, payload, date
or route profile. Selecting tasks and rules shows their origins, effective settings
and precedence. Unknown runtime-dependent totals remain distinct from zero work.
Edits invalidate the preview and disable export until it is rebuilt.

Follow [the review guide](DEMAND_PREVIEW_REVIEW.md) before the Results investigation
stage. It describes count definitions, the independent count checks, known
limitations and the LTN evidence. To export without opening the editor:

```powershell
.venv/Scripts/python.exe -m amr_demand_preview --config ltn.json --output verification/latest/ltn-demand-preview.json
```

Exports contain the frozen project configuration, so treat them as project data.

## Results investigation checkpoint

The latest checkpoint is [Project-bound simulation](PROJECT_RUNS_REVIEW.md):
save, check and simulate within the editor, frozen revision-bound external runs,
moved-run matching and Results investigation. Persistent run links and the full
project tree remain outstanding.

[Undo and redo](UNDO_REDO_REVIEW.md) provides shared completed-edit
history, keyboard shortcuts, save-aware dirty state and protection against stale
editing windows. Saved revisions remain the cross-session restore mechanism.

[Recovery and unsaved work](RECOVERY_REVIEW.md) provides
30-second recovery copies, Save / Discard / Cancel safeguards and recovery to a
new unsaved document.

[Portable project storage](PROJECT_STORAGE_REVIEW.md) provides
compressed `.amrproj`, deduplicated drawings, atomic saves and revision restore.
Use **Home → Save project as** and **Project revisions**. Results stay external;
use **Export JSON** for the existing launcher and command-line tools.

Use **Home → Results investigation**, or **Investigate Results** in the launcher.
Select the saved run folder or full event CSV. Task timelines distinguish recorded
outcomes from planned route segments. Metric selection opens contributing events;
missing evidence remains explicit, including partial payload-transfer coverage.

New logs have stable event/journey identities and `.csv.run.json` evidence sidecars.
Move the CSV and its sidecar together. Older logs remain readable with weaker,
explicitly labelled evidence. See the [review guide](RESULTS_INVESTIGATION_REVIEW.md)
for definitions, test results and the next user verification gate.

```powershell
.venv/Scripts/python.exe -m amr_results_investigation verification/latest/ltn-investigation --output verification/latest/investigation.json
```
