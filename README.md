# Autonomous Mobile Robot Simulator

## Engineering verification

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

    ^C to quit and save .csv default name = "simulation_steps.csv"
    Use --verbose-csv path_to_file.csv to name file
```

## Limiting task deferral

In **Simulation settings → Run period**, set **Maximum task deferral** in minutes
and save the configuration. The JSON field is `simulation.max_task_deferral_minutes`;
for example, `30` allows up to 30 minutes from a task's scheduled release to AMR
assignment. `0` (the default, displayed as **Unlimited**) disables the limit.

The timer includes both waiting for a preceding return pickup and waiting for an
available AMR. Releasing a deferred task or retrying assignment does not restart
it. A task still unassigned at the deadline fails and is removed from the waiting
queue, with its waiting time and failure reason recorded in the existing failure
logs and exports. Assigned journeys continue normally. Collection/return tasks
have their own timer from their release time; automatic idle parking trips are
excluded.

## Managing inventory spaces across locations

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
