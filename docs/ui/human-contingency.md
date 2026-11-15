# Human contingency study

Open **Studies → Human contingency study…**. This is a separate saved study;
ordinary AMR simulations retain their existing behaviour and Simple/Detailed setting.

The study uses the **same Task Generation engine and project settings** as an AMR
run, plus any explicitly configured tasks. Configure demand in the existing Task
Generation interface; there is no separate contingency demand model. Category,
department and group overrides, schedules, rates, timeframes, calendars, targets,
release staggering, deferral limits, stock consumption and return dependencies
remain authoritative by default. Opt-in transport timing flexibility is described below.
Selecting services limits the work assessed by the human
study; it does not rewrite the project's generation rules. Stock balances for
unselected services are excluded from the staffing assessment.

1. Review the prefilled services. Enabled demand rules supply the permitted
   payloads and service locations, including department/group overrides and
   return payloads. Walking speed and handling come from the project staff
   settings; pickup/unloading starts from the building's load/unload time.
   The initial capacity is **two payloads per person**, editable per service.
   The initial weight allowance is the count multiplied by the heaviest permitted
   payload; this is a load estimate, not an ergonomic limit. The editable envelope
   assumes payloads in line plus 0.6 m for the person, at least 0.6 m wide and
   1.8 m high **in corridors**. Inside a lift the person and individual payloads
   are arranged separately: permitted 90° rotations and alternative positions
   are tried without overlap or stacking. The person initially occupies
   0.6 × 0.6 m of floor space and 1.8 m height, editable in each service profile.
   Shared lift trips include every person and payload in the arrangement.
   Existing boarding/alighting times apply; no additional rearrangement duration
   is assumed. Review these values for the actual carrying equipment. Changing the count
   updates derived dimensions/weight while preserving manually edited values.
2. In **Shift rules**, choose **Configure team**. The shared team and inherited
   category defaults are shown first. Select a category and enable **Use independent
   shift rules for this category** to set separate working hours, active days,
   breaks and a maximum simultaneous headcount for that team.
   Choose **Use defined start and finish times** to enter periods such as
   `06:00–14:00`, `14:00–22:00` and `22:00–06:00`, one per line. The search determines
   how many people are needed in these periods. A finish at or before the start
   means the following day; equal times describe 24 hours. Active days refer to
   the shift's starting day. An overnight period already in progress when the
   study starts is included. Full shift hours, including the portion outside the
   study boundary and breaks, are counted. Staff are assumed at their base when
   the study begins; no work before the study is inferred.
   Alternatively retain the search over allowed lengths and a start-time grid.
   Project staff patterns supply initial allowed shift lengths and active days.
   The shared base initially uses the most common service base (first service on
   a tie). Start windows, breaks and staffing limits are editable study assumptions.
   Confirm the carrying assumptions and rules. Start windows are within a
   calendar day; shifts can finish after midnight. Breaks start at the configured
   offset from each shift start. Staffed hours include breaks.
3. Review routing and the planning margin. Human routes inherit task permissions,
   doors and floor waypoints; a service can explicitly select a route-profile
   override. The corridor envelope includes its operator; lift packing counts
   the operator separately. Equipment availability
   is assumed. Lift queues and fit are evaluated across all selected services.
4. Choose **New study and run…**. Four bounded searches compare dedicated/shared
   teams with current timings and the configured walking/handling margin (20%
   initially). The same original demand calendars, physical inventory and
   consumption rules are used throughout. Staff shifts never rewrite demand.
   Dedicated teams are seeded together across active categories and simulated
   together with common lift queues. The search balances staffing additions
   across categories instead of allowing the largest task count to monopolise
   trials. Each category's staffing limit applies to that team independently;
   the shared comparison uses the shared-team limit.
5. Inspect **Results**: select a comparison, then review shifts, coverage, rounds,
   stops and unresolved work. A shared roster is counted once; round/stop records
   attribute activity to services without duplicating shared journey time.
   Dedicated results show each category's peak people and staffed hours. Combined
   peak staffing is calculated from overlapping shifts, not by adding service peaks.

## Flexible category timing

In **Services and carrying**, choose a category, then **Align flexible tasks to
staff shifts** and enter its **Maximum delay (minutes)**. All categories initially
retain original timings; 120 minutes is an editable allowance only when flexibility
is enabled. Generated scheduled tasks (including scheduled volume components)
and explicit tasks always retain their times. This protects fixed catering slots
even when another rule in the same category is flexible.

Flexible tasks use the first staffed instant after their original release and
physical dependency readiness, within the maximum delay and native department/
category opening calendar. Breaks and dedicated-team eligibility are respected.
The delivery deadline moves by the same amount, with its extension capped by
the maximum delay. No new demand or advance knowledge of random arrivals is used.
Inventory consumption, washing, exchanges and return readiness retain their
original physical dependencies. Each generated return has its own readiness
time and allowance. A dependency becoming ready too late cannot extend the
deadline beyond that allowance.

If there is no suitable staffed release, the obligation remains visible with
its original deadline; it is not discarded. Release alignment does not promise
that an entire round fits in the remaining shift. The simulation still rejects
late deliveries, insufficient stock, break conflicts and overtime. Native task
deferral timeouts allow the authorised release delay, then retain their existing
assignment limit. A flexible policy cannot erase unmet stock consumption.

**Results → Task timing** and task CSVs show original/revised releases and deadlines,
the latest allowed release, delay durations and reasons. PDF summaries identify
flexible categories, allowed delays and how many tasks were retimed. The result
view reads task rows on demand to avoid creating a widget for every cell in a
week's workload. Comparison inputs share the same demand and timing policy;
realised release/deadline times may differ with the chosen rosters. Editing these
rules invalidates previous results and requires a new study.

Each setup form scrolls independently. Validation messages have their own bounded,
copyable scrolling area; the action buttons remain visible. Previously saved
blank profiles are filled from the project when reopening the dialog; completed
profiles retain their edits. Saved studies always retain their original inputs.

Every round serves one service and returns to the service base, then the shared
base if different. Routes can deliver, pick up again and collect available
returns, checking capacity after every stop. Passive return dwell does not reserve
a person; department handling does. All scheduled rounds must finish before a
break or shift end. Source stock and returned container identities are retained.
Missing return stock is an unmet obligation, never an invented empty trolley.

The result is the **lowest staffed-hours passing roster found**, not a proof of
the global minimum. Ranking uses staffed hours, peak simultaneous people, trips,
then travel distance. Search is bounded by the displayed trial budget. No passing
roster means no recommendation was established, not proof that no roster exists.
The configured maximum staffing and permitted shift starts may need revision.
An empty workload does not establish a staffing recommendation.

The trial budget applies to each of the four comparisons. The first trial is a
no-staff baseline, so a budget of one cannot produce a staffed recommendation.
The baseline is simulated once and reused, while staffed trials simulate the
whole demand period. Progress reports the current trial, simulated hours,
completed obligations and elapsed time during the trial. Static corridor paths
and calendar calculations are cached; lift queues and inventory still advance
for each candidate. Checkpoints use compact JSON with the same integrity checks.
If an actual individual obligation and its operator cannot fit any lift, even
with permitted rotations, the study reports that setup limitation rather than
trying more staff. A packing-search limit is not treated as proof of impossibility.
Lift arrangements are inspectable in Stops and its CSV export.

The study horizon bounds new demand. Fixed task deadlines remain authoritative;
flexible deadlines use the explicit bounded policy above.
Work without a target, and required returns, must finish by the latest permitted
candidate shift end. Tasks dependent on stock/return cycles retain those dependencies;
their realized release times can differ across rosters even though demand rules
and consumption remain identical. Inspect tracked-stock shortfalls as well as
transport failures.

**Stop** checkpoints completed trials. Open the saved study and choose **Run /
resume** to continue an interrupted search. Edited project inputs or changed
application source require a new study; old evidence remains viewable/exportable.
Trial-budget exhaustion remains explicitly labelled. Save settings saves a
project draft; use the usual project Save action to persist it.

Export detailed CSVs or a standalone PDF from the study. In the normal project
report panel, **Select human contingency study for PDF…** adds the optional
**Human contingency staffing** section. Evidence must match that report run's
frozen project configuration.

Command-line evaluation uses the same operations as the interface:

```powershell
.\.venv\Scripts\python.exe amr_app.py --human-contingency-study "study.json"
```

Python callers can use `default_settings`, `validate_settings`, `create_study`,
`simulate_candidate`, `evaluate_study`, `load_study`, `export_csvs` and `export_pdf`
from the `amr_contingency_*` modules. Optional project settings live under
`human_contingency` with versioned study settings, separate from `simulation.mode`.
Study files bind their complete inputs and results to SHA-256 hashes and source
identity. These hashes detect accidental changes; they are not digital signatures.

This version sizes shift coverage only. It does not model recruitment establishment,
absence cover, limited equipment inventory, multi-person carrying, mixed-service
rounds or a mid-run AMR takeover. Additional lift passenger demand is not inferred.

## Integration and acceptance

The existing workbench controller owns settings/undo, the native QProcess pattern
owns execution, and the existing report pipeline hosts the optional PDF section.
The human dispatcher reuses the simulator's task-generation and physical payload
operations but never calls its automatically expanding staff-booking algorithm.
Existing project files need no migration. Ordinary simulation defaults and default
PDF sections are unchanged.

Automated acceptance covers hand-calculated trips, interleaved loads, urgent work,
capacity/route failures, physical returns, department destinations, stock shortages,
lift contention, breaks, overnight coverage, deterministic resume, project binding,
UI execution/edit locks and settings undo. Visual evidence is generated separately
with normal/enlarged text and PDF rendering. Production staffing conclusions require
reviewed carrying and shift inputs for the actual project.
