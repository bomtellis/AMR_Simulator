# Autonomous Mobile Robot Simulator

## Human contingency staffing

Use **Studies → Human contingency study…** to compare dedicated service teams and
a shared team replacing AMRs. Configure carrying profiles and shift rules, then
compare current and buffered timings. Results include shift coverage, chained
delivery rounds, unmet obligations, CSV exports and an optional PDF report section.
See [human contingency guidance](docs/ui/human-contingency.md).

## Project website (local draft)

The website source starts at [docs/index.md](docs/index.md). It contains an editable
project description, a placeholder for the future Windows package, development
setup for Windows/macOS/Linux, and the current Building flow tutorial.
See [website editing notes](docs/SITE-README.md) to fill in the description and links.

## Open the engineering workbench

From an existing environment with the project dependencies installed:

```powershell
.\.venv\Scripts\python.exe amr_app.py
.\.venv\Scripts\python.exe amr_app.py "path\to\project.amrproj"
```

The launch command also accepts JSON. Add `--without-drawings` to inspect or
repair a configuration without loading its drawing underlays. Absolute paths to
the Python executable and `amr_app.py` work from another folder. The previous
`visualiser/amr_editor_main.py` entry point remains available.

Use **File → New project** (`Ctrl+N`) to start again, with Save/Discard/Cancel for
unsaved work. New project setup opens here and when launching without a file.
Choose a floor count and height, then optionally assign a DXF or PDF per floor.
Floors start at 0; PDF assignments use the existing page, scale and alignment
settings. **Skip setup** starts an empty project for configuration through the
existing dialogs; **Cancel** keeps the current project. Created floors remain
visible in Layout even without drawings. Fresh workspaces save as compressed `.amrproj` files by default;
opened JSON configurations retain JSON saves. **Save project as** (`Ctrl+Shift+S`)
converts an imported configuration to a portable project. Simulation outputs stay
external. New projects require layout, robot and demand configuration before
**Check → Simulate → Review → Report**. Offline installation remains release work.

On **Simulate**, choose **Run storage → Memory only** to check and simulate the
current edits without saving the project or writing run files. Keep several
runs in the open document and use **Playback** or **Investigate** to compare
them. **Save run** keeps the selected run and its original inputs without
rerunning it. Save first to generate reports or export evidence. **Discard
run** frees space; closing the document discards any runs left in RAM.
Memory runs share a 1 GiB evidence and input budget. Normal editor draft
recovery is separate and remains enabled.

## Engineering verification

### Compact simulator execution

Simple and Detailed runs use an owned compact runtime dataset, immutable asset
definitions and journals of committed attribute/reservation changes. Rollback
preserves existing reservations, inventory claims and geometric occupancy;
unconverted mutable values retain the safe deep-copy fallback.

Managed runs finish with complete, hash-bound `simulation_steps.csv.sqlite`
evidence and its `.run.json` metadata. New event stores compress bounded batches
of events together, with defaults shared by event type and interned identifiers;
report state is also compressed. Investigation and Playback read this store
directly, show loading progress and offer cancellation. PDF, lift and department
report readers stream its CSV representation without writing a full event CSV
to disk. Old CSV runs and earlier SQLite formats remain readable. Detailed CSVs
are materialised only when explicitly requested through an export or compatibility
API. Exporting never reruns the model or changes its completion status. The
explicit export process has a 2 GiB RAM ceiling (capped at half of physical RAM).

An existing 238,466-event LTN store measured 388 MiB originally, 147 MiB with
per-event compression, and 53 MiB with the current batch compression: another
64% reduction, or 86% below the original, with identical decoded events,
full-precision times and playback flags. Sizes vary with the workload. Explicit
full CSV exports can still be large; existing saved evidence is not rewritten automatically.
See [output size verification](verification/OUTPUT_SIZE_REVIEW.md).

```powershell
.\.venv\Scripts\python.exe amr_app.py --export-run "path\to\run-folder" --outputs steps_csv,visualiser_csv
```

The simulator CLI now records a unique compact event store by default. `--verbose`
requests the legacy detailed event CSV; individual `--*-csv` flags or
`--exports steps_csv,transport_matrix_csv` request additional outputs. A standalone
`.sqlite` event-store file can also be passed to `amr_app.py --export-run`.

Stress workers retain immutable definitions between trials while each trial gets
fresh state, random generators and evidence. Eight-worker admission, RAM caps,
reproducible search batches and process-tree cancellation remain in effect.
See [compact execution verification](verification/COMPACT_EXECUTION.md) for
correctness checks and measured performance.

CPU execution also avoids charging-destination searches for already-stowed
robots, indexes the latest lift booking through commits and rollback, caches
department calendars and excluded timeframe allocations, and skips provably
losing Simple-mode lift alternatives. Detailed geometric checks retain their
existing evaluation. A full-week LTN comparison on 12 October 2026 took
357.5 seconds before and 160.1 seconds after, with identical normalised event,
task-record and final-state hashes. These are local single-run measurements.
See [CPU optimisation verification](verification/LTN_CPU_OPTIMISATION_20261012.txt)
for source bindings, scenario comparisons and regression results.

All simulations and automated stress tests use the CPU simulator. Older projects
with a GPU computation setting run on CPU; saving them removes the retired
setting. Historical run evidence remains readable.

In **Layout**, choose **Edge** on the drawing toolbar and click two existing graph
points to connect them. **Escape** cancels the current chain; **Undo/Redo** applies
to each completed edge. Set **Bidirectional edges** and **Chain edge creation** in
**More tools → Edit → Drawing behaviour**. Use **Corridor** to draw routes that
also create new nodes.

Choose **Department** on the Layout drawing toolbar to place a department marker
on the current floor or edit one by clicking it. Its drop-down menu opens
**Manage departments…** to add, edit or remove departments and configure their
workflow locations. The full editor is also available under **Configuration → Departments**.

The bottom-right **Object snap** controls let you enable **End** (graph points),
**Mid** (corridor midpoints), **Perp** (perpendicular from the current anchor),
and **Cross** (intersections) together. **Near** provides nearest-point/edge
snapping when no enabled specific target is nearby. Targets compete by distance;
exact coincidences still reuse existing graph geometry. Turn **Object snap** off
to suspend attraction while keeping your chosen targets. **Grid snap** is
independent. Drawing previews, commits and transform reference picking use the
same enabled targets; the full tool tabs retain single-target presets.

To change the level height after setup, open **Configuration → Building settings**,
edit **Level height**, and choose **Save**. This shared distance between adjacent
floors applies to all levels. The edit preserves effective lift speeds in metres
per second and recalculates floors per second, so vertical travel times reflect
the new height. It supports Undo/Redo; save the project to persist the change and
rerun Project checks before simulating.

Saved-run **Review → Playback** uses horizontal controls above the full-width
map. **Display** contains visibility options and the optional legend; **Inspect**
opens task, lift and payload monitors. Drag the divider above the timeline to
resize it. Timeline backgrounds are cached for the visible area, and drag-to-seek
updates are coalesced while retaining the final position on release. The run name
and metadata replace the standalone viewer's loaded-file panel.

Generated reports include the eight operational KPI groups for demand, service,
capacity, efficiency, bottlenecks, reliability, resources and cost/sustainability.
See [report KPI definitions and optional inputs](docs/report-kpis.md) for evidence
limits, calculation rules and the accompanying CSV exports.
Reports include a title page, linked contents and numbered headings. The
[report structure and PDF insertion guide](docs/report-structure.md) explains
SLA category assignments and adding selected or prepared sections to existing PDFs.

The editor now opens compressed `.amrproj` files containing configuration,
deduplicated drawings and saved revisions. See the
[project storage review guide](verification/PROJECT_STORAGE_REVIEW.md).
Export JSON for the existing simulator and launcher; results remain external.
Unsaved-work safeguards and automatic recovery copies are described in the
[recovery review guide](verification/RECOVERY_REVIEW.md).
Use **Edit → Undo / Redo** for completed changes; see the
[undo and redo review guide](verification/UNDO_REDO_REVIEW.md) for scope and limits.
**Home → Project runs** can save, check and simulate a project revision, then open
its results in the editor. See the [project runs review guide](verification/PROJECT_RUNS_REVIEW.md).

The first verification checkpoint provides independently calculated routing,
door-width, service-time, reservation and task-generation reference cases, plus
a searchable evidence pack and an inventory of settings still requiring review.
See [verification/README.md](verification/README.md) for the three review projects,
known limitations and commands to reproduce the results. This is verification of
specific model behaviour, not a claim of full simulator validation.

***Project licensed under AGPL.***

This script simulates paths taken by autonomous mobile robots around a facility to deliver payloads to destinations.

This uses a graph per floor level and lifts to naviagte the internals of a building.

The graph nodes and edges are ***explictly*** defined in the json file.

# Getting Started

```
    python simulator.py --write-example your_file_name.json
    python simulator.py --config your_file_name.json --verbose --interactive

    ^C to quit and save evidence; --verbose also writes "simulation_steps.csv"
    Use --verbose-csv path_to_file.csv to name file
```

## Local manoeuvre override

In **Simulation settings → Initial conditions → Inventory and container state**,
**Ignore invalid local manoeuvres** optionally replaces a failed local inventory-bay
path with direct movement. It defaults to off. Distance and travel time remain
included, and movement event details record `unverified_direct_fallback` plus the
original failure reason. Project checks warn when it is enabled. This option
does not bypass corridor, door, traffic or malformed-coordinate checks.

## Limiting task deferral

In **Simulation settings → Run period**, set **Maximum task deferral** in minutes
and save the configuration. The JSON field is `simulation.max_task_deferral_minutes`;
for example, `30` allows up to 30 minutes from a task's scheduled release to AMR
assignment. The shared default for normal runs and stress trials is `60` minutes.
`0` (displayed as **Unlimited**) explicitly disables the limit. Stress trials use
the project's saved setting, including any explicit override.

The timer includes both waiting for a preceding return pickup and waiting for an
available AMR. Releasing a deferred task or retrying assignment does not restart
it. A task still unassigned at the deadline fails and is removed from the waiting
queue, with its waiting time and failure reason recorded in the existing failure
logs and exports. Assigned journeys continue normally. Collection/return tasks
have their own timer from their release time; automatic idle parking trips are
excluded.

## Managing inventory spaces across locations

For one location, select it and choose **Properties > Create / edit spaces…**, or
right-click it and choose **Inventory spaces**. The inventory editor opens maximized
with a central CAD canvas, a spaces list, an explicit Properties panel, a metre grid,
zoom/pan, multi-selection, drag movement and numeric centre/rotation fields. The toolbar
and **Edit tools** menu retain payload/AMR creation, arrays, copy/paste, deletion,
alignment, capacity arrangement and charger controls. Draft Undo/Redo stays inside
the dialog; **Save and close** applies one project edit, while **Cancel** discards it.
Part 4, Action 2 shows bay dimensions and labelled placement previews and can create
four correctly positioned tutorial charging bays before robot types are configured.

Open **Locations & Inventory Spaces** in the editor. The left list includes every
location and drop-off zone; the right table edits its spaces and previews the layout.
Changes remain in a draft while navigating. **Save all** updates the editor's
configuration; **Cancel** discards the draft. Save the JSON normally to persist it to disk.

- Select payload bays and choose **Detach payloads in scope** to remove their
  payload template and make them flexible. Any payload fitting length, width and
  height may use them, including a 90-degree turn. AMR/charger bays are skipped.
- Edit flexible length/width, height, name and bay angle directly in the table.
  **Attach payload to selected** restores a fixed template. Add, duplicate and
  delete spaces here, or add AMR bays and toggle their charger checkbox.
- Choose **Selected spaces**, **Current location**, **Selected locations**, or
  **All locations**, then apply the length/width fields. Only flexible payload bays
  are resized; detach fixed payload templates first. Centres and angles are kept.
  Review the preview for clearance/overlap after resizing; bays are not repacked.
- **Select similar locations** matches the current location's payload-space count
  and bay orientations, allowing the displayed angle tolerance (default 5 degrees).
  It ignores AMR bays, position, payload type and dimensions. Headings differing by
  180 degrees match. The matching locations are selected and become the bulk scope.

## Exporting journey flows for a lift engineer

For lift travel alone, choose **Lift travel CSV** in the report dialog and tick
**Export lift travel CSV only (skip PDF)**. The command-line equivalent is:

```powershell
python report/amr_report_main.py ltn_full_20260910.csv --lift-csv-only --lift-travel-csv output/lift_travel.csv
```

The CSV contains one row per lift transfer or empty lift reposition: lift ID,
origin/destination levels, start/finish time, duration in seconds,
travel distance in metres, direction, AMR and task IDs, and whether the AMR is
onboard. For repositioning, the AMR/task identify the request served; the AMR is
waiting rather than travelling. Lift node endpoints take precedence over the
robot's logged floor, which can remain unchanged during repositioning. Missing
endpoints are marked `Unknown`. Multiple tasks sharing a movement stay on one row.
The `origin_location` and `destination_location` columns contain level labels only
(for example, `L00` and `L02`), matching `origin_level` and `destination_level`.

`payload_weight_kg` and `amr_weight_kg` are populated only on AMR-carrying lift
transfers; empty lift reposition rows leave both blank. Supply `--config-json`
(or select the matching JSON in the dialog) to resolve weights. Payload weight
sums the actual onboard payload instances, so approach travel before pickup has
zero payload weight even when the task names a future load. Unknown/suppressed
loads remain blank. Explicit logged weights take precedence over configuration.

Set each AMR type's **Unloaded weight** in its editor's physical settings. This
saves `weight_kg` in its JSON entry; the report maps it to individual robots
(for example, `AMR-C` to `AMR-C-1`, `AMR-C-2`, etc.). Payload capacity is not robot
self-weight. Unspecified AMR weights remain blank. For a weighted CSV:

```powershell
python report/amr_report_main.py ltn_full_20260910.csv --config-json ltn.json --lift-csv-only --lift-travel-csv output/lift_travel.csv
```

Normal report generation also writes this CSV automatically. Set its output with
`--lift-movements-csv` (alias `--lift-travel-csv`), or leave it blank to save
`<report>_lift_movements.csv` beside the PDF. CSV-only mode does not need a JSON config.

The report tool includes **Journey origins, destinations and returns** in the
report section selector (`journey_flows` on the command line). For example:

```powershell
python report/amr_report_main.py ltn_full_20260910.csv --config-json ltn.json --output output/pdf/vertical_transport.pdf --report-sections journey_flows --omit-drawings
```

Every report run, including the report dialog, writes three CSVs beside its PDF:

- `<report>_journeys.csv`: one row per recorded task request, with origin and
  destination locations, levels and departments, payload, requesting department,
  status, release/assignment/completion times and the parent task ID for identifiable
  payload returns. Empty AMR return tasks are labelled separately.
- `<report>_journey_flows.csv`: task counts by journey type, origin/destination
  level and department, and outcome. Failed/incomplete requests remain separate.
- `<report>_lift_movements.csv`: one row per logged lift transfer or empty lift
  reposition, with lift, AMR, task IDs, start/finish times and levels. Multi-stop
  tasks sharing a lift movement do not create extra movement rows.

Use the matching simulation JSON for department and location metadata. Logged
endpoint floors take precedence, with JSON floors as a fallback. Numeric floor 0
is displayed as L00; missing metadata is `Unknown`. Shared endpoint departments
are listed together; `task_department` identifies the requesting department.
No L00 origin/destination or reverse route is assumed. Return pickups can differ
from the original delivery endpoint because of staff transfers to drop-off zones.
Assignment time is dispatch time, not payload pickup time. CSV times include dates
when the source does, otherwise elapsed seconds. Counts span the entire source log.

Journey counts represent tasks, not AMR or lift trips. Use lift movements for
vertical transport demand, including empty AMR travel and lift repositioning;
use task IDs to join to journey endpoints. Movements without task IDs (for example,
some charging travel) cannot be linked to delivery tasks. A return's parent ID is
blank when the log does not establish a link. Legacy logs without request events
cannot supply a complete journey table. Department mappings reflect the supplied
configuration, so use the configuration saved for the simulation run.

## Defining the simulation parameters
```
"simulation": {
    "start_datetime": "2026-01-01T08:00:00", # start time of the simulation
    "tick_rate": 120.0 # does nothing currently for future when GUI is implemented
  },
```

## Defining the building

```
  "building": {
    "load_unload_time_sec": 20.0, # how long it takes to drop a payload off
    "floor_height_m": 4.0, # how tall is each floor
    "charge_location": "Stores" # where do you charge the robots up must be a defined location
  },
```

## Defining Locations

`X` is distance from datum in metres

`Y` is distance from datum in metres

```
"locations": [
    ...
    {
      "name": "Stores",
      "floor": 0,
      "x": 0,
      "y": 0
    },
    ...
]
```

## Defining Nodes and Edges

Nodes on the floor are defined as `Cx_y` where `x` is the level number and `y` is the node letter.

Lift edges are defined as `Lift-x-Fy` where `x` is the lift number and `y` is the floor level.

```
{
    "corridors": {
        "nodes": [],
        "edges": [],
        "auto_connect": false
    }
}
```

Nodes must have the four keys to operate

```
"nodes": [
    ...
    {
        "name": "C0-A",
        "floor": 0,
        "x": 4,
        "y": 0
    },
    ...
]
```
Edges must have these two keys to operate. Do not make a circular reference e.g. `C0-C --> C0-B --> C0-B --> C0-C` as this will confuse the pathfinding function

```
"edges": [
    ...
    {
        "from": "C0-C",
        "to": "Pharmacy"
    },
    {
        "from": "Lift-2-F0",
        "to": "C0-C"
    },
    ...
]
```

## Defining payloads

The name used in the definition is used in the task.

```
{
    "name": "food_trolley",
    "weight_kg": 120
    "size_units": 1.0
}
```

## Defining AMRs

AMRs are the robots that move around a facility to transport goods.

```
"amrs": [
    {
      "id": "AMR-A", # unique per type of AMR
      "quantity": 2, # how many do you have, this gets incremented automatically e.g. AMR-A-1..2..3
      "payload_capacity_kg": 150, # total weight bearing capacity, payload > capacity = no go
      "payload_size_capacity": 1.0, # related to payload size factor 
      "speed_m_per_sec": 1.2, # how quick can this thing move
      "motor_power_w": 900, # motor power
      "battery_capacity_kwh": 6.5, # how big are the batteries
      "battery_charge_rate_kw": 2.2, # how quick do they recharge
      "recharge_threshold_percent": 20.0, # when do you want to retire this unit to recharge %
      "battery_soc_percent": 100.0, # inital state %
      "start_location": "Stores" # where does it begin in the simulation
    }
],
```

## Defining Lifts
```
"lifts": [
    {
      "id": "Lift-1", # name of the lift
      "served_floors": [ # how many levels can this lift get to
        0,
        1,
        2,
        3
      ],
      "speed_floors_per_sec": 0.5, # how fast floors per sec linked to distance between floors e.g 4m between floors * 0.5 = 2m/s
      "door_time_sec": 4, # how long does it take for the doors to open
      "boarding_time_sec": 6, # how quickly can the amr get into the lift
      "capacity_size_units": 1.0, # linked to payload size
      "start_floor": 0, # where does the lift start in the simulation
      "floor_locations": { # where is the lift in each level, useful for offsets if plans do not line up.
        "0": {
          "x": 5,
          "y": 2
        },
        "1": {
          "x": 5,
          "y": 2
        },
        "2": {
          "x": 5,
          "y": 2
        },
        "3": {
          "x": 5,
          "y": 2
        }
      }
    },
    ...
  ],
```

## Defining Tasks
```
"tasks": [
    {
      "id": "T1", # can be anything as long as its unique
      "pickup": "Stores", # location as defined earlier
      "dropoff": "Ward-1A", # same as above
      "payload": "food_trolley", # what is it carrying, defined in payloads
      "release_datetime": "2026-01-01T08:00:00", # when does this task get added to the queue
      "priority": 10 # how desparately does this need to be done
    },
]
```

## Department service review exports

In the reporting dialog, select the simulation event CSV and matching configuration
JSON, enable **Export category reviews**, and choose **PDF and Excel (.xlsx)**,
**PDF only**, or **Excel (.xlsx) only**. Use **Reviews only** to skip the main report
and lift exports. The review folder receives a separate file for every configured
category, including a clearly empty review for inactive categories.

```powershell
python report/amr_report_main.py simulation_steps.csv --config-json hospital.json --department-review-only --department-review-dir department_reviews --department-review-formats both
```

Each category review includes a directory of configured departments, effective
generation rules (including department groups and waste streams), Monday-Sunday
delivery/collection counts, payload routes, and a timetable separating configured
release/fill times from actual deliveries and collections. The PDF gives the
category timetable with exact times and department IDs; Excel also provides a
department-by-department timetable and the full generated-task audit. Excel's
amber current-service and owner-comment fields are blank for department review.
The **Difference** column calculates simulated total minus the entered current total.

PDF export also writes `<category>_executive_summary.pdf`, a single portrait A4
page with key service statements and a timeline of configuration schedules,
generated tasks, actual deliveries and actual collections. The same executive
page opens the full review. Up to eight calendar dates are shown individually;
longer intervals overlay all events by weekday, explicitly labelled on the page.

Counts use completed tasks with service times in the configuration's half-open
simulation interval. Delivery time is the staff final arrival where logged,
otherwise AMR drop-off completion. Collection time is AMR pickup completion at the
department or shared zone. Return container deliveries count as deliveries; staff
return legs and robot accommodation trips do not count again. Weekdays are calendar
days; coverage hours make partial days explicit. Late/incomplete/unclassified
tasks remain in the audit. The supplied configuration's hash is recorded because
the log itself cannot establish that the supplied JSON matches the simulated run.

PDF uses the reporting tool's existing ReportLab dependency. Excel export uses
Node.js and `@oai/artifact-tool`; the bundled Codex runtime is detected automatically.
For another installation, set `AMR_REPORT_NODE` to the Node executable and
`AMR_REPORT_NODE_MODULES` to its `node_modules` directory containing that package.
PDF-only exports do not require Node. The retained Analytics Dashboard reference
in `report/assets/department_review_template.xlsx` supplies the workbook template;
its synthetic marketing content is replaced with category service data.

## Department drop-off zones

A department category can associate its normal pickup/drop-off locations with one
or more intermediate drop-off zones. The normal locations remain the final human
destinations; the AMR stages the payload at a zone, department staff complete the
last leg, and return the configured empty/equivalent payload to that zone for the
AMR return journey.

```json
{
  "id": "D1",
  "name": "Ward 1",
  "task_generation_locations": {
    "catering": {
      "pickup_dropoff_locations": ["Ward-1A"],
      "dropoff_zone_locations": ["Ward-1-Drop-Zone"]
    }
  }
}
```

Drop-off zones are ordinary placed locations. Configure their existing
`inventory_spaces` as **Flexible payload spaces** to let different payload types
use any space whose maximum length, width and height they fit. Payloads may rotate
90 degrees in plan. The simulator assigns the smallest available compatible space
first, preserving larger spaces for larger payloads. New and existing department
drop-off-zone spaces default to flexible; other inventory spaces can opt in from
the Inventory Spaces editor. Multiple spaces provide the zone's simultaneous
holding capacity.

In the Department editor, use **New drop-off zone → Create and assign** to name
and place a zone, then assign that one location to any number of selected task
categories in the same operation.

For a generated delivery using a zone:

- `Task.dropoff` and `Task.dropoff_zone` are the AMR staging location.
- `Task.final_destination` is the associated department location.
- staff and a return task are enabled automatically;
- `return_payload` selects the empty/equivalent type, falling back to the outbound
  payload type when it is blank;
- `staff_collection_delay_minutes` adds a configurable response delay between AMR
  drop-off and staff collection;
- staff handling occurs within the configured `return_delay_minutes` window at
  the final destination. The longer of `staff_handling_minutes` and
  `return_delay_minutes` determines the destination dwell, matching the original
  direct-delivery return timing; calculated walking time from the zone and back
  remains additional;
- `dropoff_zone_capacity_policy` can either wait for a compatible free space or
  allow temporary overflow. This setting is category-wide: all departments in
  the category use the same policy, and legacy department override values are
  ignored. Overflow applies only when the payload fits a configured zone space,
  keeps generated tasks from failing during a temporary occupancy peak, and
  remains visible in zone utilisation/shortfall reporting;
- `release_next_after_return_pickup` optionally serialises lower-priority
  workflows that share a drop-off zone. The next checked task is held until the
  preceding return collects its payload and frees the zone inventory space.
  Unchecked priority categories continue to release normally.

Global staff settings provide the walking speed, lift allowance and default
payload-handling time used by every drop-off-zone handoff. A category/department
handling value of `0` uses that global default. The global short-exchange threshold
can hold the delivering AMR at the zone until the returned payload is ready,
preventing it from accepting intervening work during a quick exchange.

Set `staff_department_fallback_enabled` on a category or department override to
let an untracked department team complete the zone-to-department-to-zone handoff
when the primary staff team cannot finish it within its current working period.
`staff_department_fallback_resource_name` controls the label used in event logs.
Fallback assignments are auditable but do not enter the primary staff pool,
consume central staffing capacity, retain movement history, or delay another
department fallback. Once the return payload reaches the zone, its AMR return
task is released and collection is autonomous.

`staff_handoff_only` removes destination dwell for movement-only workflows such
as Linen: the person delivers the incoming trolley, takes the previous return
trolley immediately, and places it in the zone for autonomous AMR collection.
Where a department category has several destination locations, the simulator
orders them by staff graph-route distance from the zone and selects the nearest
available location; an occupied or reserved location causes it to try the next
candidate.

Tracked exchange deliveries leave the newly delivered full payload at the final
destination and bring the previous empty/equivalent payload back to the zone as a
different physical instance. This supports Linen-style full-for-empty swaps while
keeping destination and zone populations stable across repeated visits.
When the same tracked payload is assigned to several department destination
locations, `consumption_per_day` remains the department's total demand. The
simulator divides that demand evenly between the physical resources, tracks each
container's balance independently, and targets replenishment at the resource that
reaches its threshold.

The simulation visualiser shows this handoff when **Show drop-off-zone staff
handoffs** is enabled: the assigned person carries the delivered payload to the
final destination, handles it there, and returns the configured empty/equivalent
payload to the zone. Exchange tasks additionally show the person manoeuvring the
full/empty payload swap, while a held AMR remains visible at the zone. Right-click
a location and select **Payloads → Find maximum
space utilisation** to inspect its peak occupied-space count, peak timestamp, and
the utilisation history of every configured space. The PDF report includes a **Drop-off zone peak occupancy**
section with each zone's maximum occupied spaces and the true simultaneous
maximum across all configured zones.

Static tasks can opt into the same workflow by supplying both `dropoff_zone` and
`final_destination`; the simulator routes their AMR leg to `dropoff_zone`.

### Unattended engineering verification

For unattended engineering verification, run
`python -m verification.run --isolated --output verification/latest/isolated`.
Each test module runs in a fresh process with a 180-second limit, preventing Qt
state retained by earlier modules from slowing later UI tests. Module logs,
stack snapshots and per-test evidence remain under the output folder. Crashes,
timeouts and missing results fail verification explicitly. Omit `--isolated` to
retain the shared-process suite for integration diagnostics.

### Payload supply at depleted sources

Simulation settings > Initial conditions > **Spawn payloads when pickup stock is exhausted**
(`simulation.spawn_payloads_when_empty`, default false) reuses eligible unreserved stock
first, then supplies a unique payload at actual pickup. Route estimates create no stock.
Exact IDs, same-container returns, staged recovery and reserved empty-bin exchanges
still require physical stock. Ordinary outbound creation rules are unchanged.

Verbose evidence records `payload_source_spawned` with task, source, time and identity.
Population summaries include `payload_source_additions` alongside peak active population.
Counts remain available as `Simulation.source_payload_additions` without verbose logging.
These are scenario supply requirements, not proof of a globally minimum container fleet.
# Simple application delivery

New-project setup and the shipped small-map practice input select Simple mode.
Existing imported modes and historical projects keep their settings.
Task generation uses focused tabs and a Department actions menu. Department
settings use Details, Hours & waste, and Task locations & zones; save the child
editor, then save the Departments list. Simulation settings keep four tabs;
Show mode details reveals the full readiness findings without expanding the
default form. Properties and advanced drawing tools remain optional.

The current delivery excludes LTN tests and workloads. Reproduce the focused
workflow QA with `.venv\Scripts\python.exe -m verification.simple_delivery qa
--output verification/latest/simple-delivery/qa`. See
[the delivery review](verification/SIMPLE_DELIVERY_REVIEW.md) for the source,
installer, checks and known limits.

### Automated scenario stress testing

Open **Scenario testing → Automated stress test** in the workbench. Manual
scenarios remain available. Choose eligible assets, timing and duration choices,
availability/speed percentages, simultaneous event count and a trial budget.
Assets are grouped into lifts, corridors, AMRs and doors. Select multiple rows
with Ctrl/Shift, then use **Include selected**, **Exclude selected**, a selected
checkbox or Space to toggle them together. Category checkboxes toggle a whole group.
Fresh setups start with no assets checked; newly added assets remain unchecked.
The tree header shows the included asset count, including collapsed categories.
Use **Clear all** to reset saved choices before ticking a smaller subset, or
**Include all** to explicitly include every asset.
Choose **New study and run…** and a study filename to run a normal baseline,
full-period blockages of the checked physical corridors, and a reproducible
search of disruption combinations. **Individual corridor blockage tests** can
be changed to **All project corridors** for an explicit full sweep. Older saved
studies retain their original full-sweep scope.
Replacing an existing filename uses the file picker's overwrite confirmation.
The previous study is retained beside it as a dated `*.previous-*.stress.json`
backup, with its original trial evidence intact. A running study cannot be
replaced or run by a second coordinator. **Open study…** and **Run / resume study**
continue an interrupted study; **Restore study settings** resets edited controls
to its saved setup. Worker and RAM limits can change when resuming. **Save settings**
updates the project in memory; save the project to retain those choices after closing.
The live plan separates the baseline, corridor tests and combined trials.
Baseline and corridor runs are additional to the default cap of 100 combined
trials. Unticking AMRs or lifts changes the combinations but can leave their
count at that cap; unticked corridors are excluded from the default sweep.
If the source project already has a completed normal-operation simulation with
matching design inputs, drawing contents, simulation software and full service evidence,
the study reuses it as its baseline. Linked runs and runs in the project's
results location are checked, including when resuming. Progress and baseline
details identify the reused run; investigation and playback use its original
evidence. Changed, incomplete or incompatible runs trigger a fresh baseline.
Changes confined to the stress search, coordinator or stress dialog do not
invalidate a normal-operation baseline. Changes to any other application
source still require a fresh baseline.
Lift-only trials retain the normal cached floor routes and apply disruptions
in lift planning. Corridor, door and AMR disruptions use time-dependent floor
route searches. Each trial still runs the full configured demand period.
Normal runs now record the precise service evidence needed for reuse; older
runs without that evidence require a fresh baseline.

A passing trial must finish every required service obligation, including
configured returns, with no failed or pending tasks. The configured end bounds
new demand; released work and its required returns may finish afterwards.
Both normal runs and stress trials apply the same saved assignment deferral
limit (60 minutes by default) from each task's scheduled release. This limits
waiting for assignment, not the duration of an assigned journey. Tasks finishing
after demand ends are shown for information and do not fail a trial.
Missing baseline requests count as unmet work even when a disruption suppresses
later inventory-dependent generation. Passing trials are ranked by total additional task
completion delay relative to normal operation. Results show the **worst passing
scenario found**, the number of tested grid candidates, and whether coverage was
exhaustive. A bounded search does not prove the global worst case.

Select a critical corridor to highlight and zoom to it on the design. Select a
trial to investigate its complete saved evidence or play it back. **Save as
scenario** copies dated events into a uniquely named manual scenario without
enabling it automatically. Dated event windows can be edited or changed to daily
recurring events in the normal event editor.

Evaluation uses up to **eight concurrent CPU workers** by default after the
baseline, with a configurable **16 GiB study RAM limit** and **8 GiB free-RAM
reserve**. Automatic admission also preserves at least 20% of physical RAM,
subject to a half-RAM cap on smaller machines, and uses measured trial peak memory
with a 50% allowance. Fixed refinement batches preserve the search across worker
counts and interrupted runs. Startup phases, active trials, elapsed/estimated
time, task counts and live RAM usage appear in Progress. A separate active-run
bar shows baseline simulation progress even when the overall study remains below
1%. A fresh baseline runs with one worker to check feasibility and measure memory;
parallel disruption trials start only after it passes. A failed baseline opens
Results with the unmet, late, failed and pending counts and its investigation link.
Windows process groups
enforce the memory ceiling and stop all children on cancellation or coordinator
termination. A memory-pressure stop retains completed evidence for resume.
See [the concurrency and C++ assessment](verification/STRESS_PARALLEL_REVIEW.md).

Stop retains completed trial evidence;
open the study and choose **Run / resume study** to continue. Resume requires
unchanged design inputs, frozen drawing contents, search settings and software.
New trials are separate project-bound runs under the study's results directory;
the source design and its demand/inventory settings are preserved.

In stress-test **Setup → Saved data**, select **Reduced data (differences from
normal operation)** to share one full baseline across the study. Unchanged event
fields and report data are read from that baseline; changed and additional data
are saved with each trial. Playback, investigation, service metrics and explicit
CSV exports reconstruct the full evidence. Full data remains the default for
independent trial files. The storage choice is frozen when the study is created.
Keep the baseline with the study: its checksum is checked when reduced data is
opened, and missing or modified baseline files are rejected. References are
relative when possible, so the study and its baseline can be moved together.
This mode applies to new studies; existing evidence is retained as saved.

**Previous studies** lists saved studies, statuses, recorded trial counts, data
modes, dates and locations. It discovers adjacent study files and previous-version
backups, and remembers studies created or opened elsewhere in a project-local
`.stress-history.json` index. Select a row and **Open selected study** to review
results or resume compatible work. Missing files are shown explicitly. Older
studies remain visible after model or software changes; running again requires
a new study when the saved inputs or software no longer match.

To include multiple stress tests in the final PDF, choose **Report stress tests…**
on the stress-test **Results** tab, or open a simulation run's report panel and
choose **Select stress tests for PDF…**. Tick individual trials or tick a study
to include all its saved trials. Use **Add study files…** for studies saved
elsewhere; selections can span multiple studies. The selector displays affected
assets, outcomes and added delay, with disruption windows in the asset tooltip.
Confirming the selection enables the **Stress-test comparison** report section.
Keep any other desired report sections checked, then choose **Generate report**.

Each selected study includes its own normal-operation baseline, a comparison
table, configured disruption windows and availability/speed, service failures,
unmet obligations and added completion delay. Studies with different design
inputs are labelled separately. Old saved evidence can be reported without
resuming its simulations. Results are verified against event evidence before
generation and checked for changes afterwards; missing or changed baseline data
is rejected. Both full and reduced data are supported without expanding event
CSVs. The report manifest records the selected trials and evidence checksums,
and `stress_test_comparison.json` retains the compact comparison snapshot.

The PDF now starts each study with a **Worst-case impact summary**, separating
service failures from the largest delays among passing trials. For simultaneous
full lift shutdowns with the same start/end time, it includes single-lift
rankings, failing-pair counts, mean delay across passing pairs, and a combination
matrix (up to 10 lifts). Select all trials in the lift study to compare every
saved combination. Missing selections are labelled, not treated as zero impact;
different shutdown windows are compared separately. Delay hours are cumulative
across service obligations, not additional elapsed simulation time. Failed
tasks and unmet obligations can describe the same incident. Single/pair results
do not establish the worst case for three or more simultaneous shutdowns.

To find how slowly the whole AMR fleet can operate, choose **All-AMR speed sweep
(5% steps)** in the stress-test **Test type** selector. Choose **New study and
run…** to save and start it. The sweep uses a 100% normal-operation baseline,
then runs 95%, 90%, 85%, and every further five-percentage-point level down to
5%, one at a time. All AMR configurations and their quantity instances slow
together. The limit remains active through completion of work after demand
ends; lift speeds and handling times are unchanged. Reduced data is selected
by default, and normal baseline reuse, cancellation, resume and history work
as for other studies. This is 20 runs including the baseline, not a search
over individual AMR combinations.

Results list speed levels in descending order and identify the lowest tested
passing percentage and the first failing level. The sweep continues after a
failure because model outcomes need not be monotonic. Passing means all service
obligations are met and no tasks are failed or pending under the project's
assignment-deferral limit; completion after demand ends remains allowed. An
incomplete sweep is labelled provisional. Select its trials for the PDF to
include the speed-sweep summary and results table; partial report selections
are assessed only against the levels selected.

To add the comparison to an existing final document, select **Existing PDF** and
an insertion page (or **Append to end**). The combined PDF is saved as a new
report, preserving the original. Untick the other report sections to produce
only the stress-test supplement, with its own title and linked contents.

This feature currently requires **Simple mode**. Scenario routing compares
permitted detours with waiting through closures or slowdowns, including
overlapping events. Already committed journeys keep their existing behavior;
mid-journey interruption and Detailed-mode scenario support are not included.

### Building-flow tutorial

The subsequent building-flow increment adds a live-control instruction bubble
under Help > Building flow tutorial. It supplies three aligned 800 m² floors,
checkpoints and dedicated/shared lift reference projects. Configuration > Plan
lift locations requires reviewed DXF interpretation, proposes aligned sites and
compares frozen scenarios with protected service to every floor/flow. Separate
variants preserve the original design; explicit application supports undo.
See [the illustrated guide](docs/building-tutorial/Building-Flow-Tutorial.pdf)
and [increment review](verification/BUILDING_TUTORIAL_REVIEW.md). Its handover
is under `installer/build/building-delivery`. The current source adds Number of
floors to Building settings, and tutorial Next/Resume locates the relevant
workspace. The bubble avoids panes/controls and can be dragged. Circulation
uses numbered click markers, route previews and checked progression; missing
links or incorrect properties are highlighted before Next is enabled.
Facility placement also shows the next location's name, floor and coordinates,
including while its naming dialog is open. Insertion tools share contextual
coordinate feedback. All tutorial stages validate automatically; use Next when
ready, and Details for full corrections. The bubble is an independent nonmodal
dialog owned by the application, so temporary editors cannot close or delete it.
Progress saves automatically beside the project as chapters, actions and practice
change. The first save and Save as preserve it; Resume restores the saved position
and skips completed chapters and verified actions. Shared transition instructions
explicitly create the middle node at (3,10) on each floor before connecting lanes.
Transition and Lift have distinct drawing toolbar icons: Transition places a
node for corridor junctions on the current floor; Lift connects stops across floors.
With enlarged text in a compact window, drawing tools show icons and keep their
names in accessible labels and tooltips so both controls remain visible.
Help > Restart tutorial bubble (also in its More menu) reopens the bubble at
the current step without resetting project edits or checked progress.
Installer work for these corrections is excluded at the user's request;
the earlier building and Simple deliveries are preserved.
