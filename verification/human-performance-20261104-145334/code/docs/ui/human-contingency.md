# Human contingency study

Open **Studies → Human contingency study…**. This is a separate saved study;
ordinary AMR simulations retain their existing behaviour and Simple/Detailed setting.

The study uses the **same Task Generation engine and project settings** as an AMR
run, plus any explicitly configured tasks. Configure demand in the existing Task
Generation interface; there is no separate contingency demand model. Category,
department and group overrides, schedules, rates, timeframes, calendars, targets,
release staggering, deferral limits, stock consumption and return dependencies
remain authoritative. Selecting services limits the work assessed by the human
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
   1.8 m high. Review it for the actual carrying equipment. Changing the count
   updates derived dimensions/weight while preserving manually edited values.
2. Review shift lengths, start windows, active days, breaks, shared-team base and
   maximum simultaneous staffing. Project staff patterns supply initial allowed
   shift lengths and active days; the search calculates staffing and start times.
   The shared base initially uses the most common service base (first service on
   a tie). Start windows, breaks and staffing limits are editable study assumptions.
   Confirm the carrying assumptions and rules. Start windows are within a
   calendar day; shifts can finish after midnight. Breaks start at the configured
   offset from each shift start. Staffed hours include breaks.
3. Review routing and the planning margin. Human routes inherit task permissions,
   doors and floor waypoints; a service can explicitly select a route-profile
   override. The trolley envelope includes its operator. Equipment availability
   is assumed. Lift queues and fit are evaluated across all selected services.
4. Choose **New study and run…**. Four bounded searches compare dedicated/shared
   teams with current timings and the configured walking/handling margin (20%
   initially). The same original demand calendars, targets, physical inventory
   and consumption rules are used throughout. Staff shifts never rewrite demand.
5. Inspect **Results**: select a comparison, then review shifts, coverage, rounds,
   stops and unresolved work. A shared roster is counted once; round/stop records
   attribute activity to services without duplicating shared journey time.

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

The study horizon bounds new demand. Existing task deadlines remain authoritative;
work without a target, and required returns, must finish by the latest permitted
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
