---
title: Configure demand and resources
nav_order: 5
has_children: true
permalink: /configure/
---
# Configure demand and resources

Start with one payload, one connected journey and a compatible robot. Confirm
that short run before introducing whole-hospital demand. Save each editor, then
save the project and rerun checks.

## Robots and payloads

Open **Configuration → Robots** to add or edit robot types. Quantity creates
individual robots of that type. Configure physical length and width in metres,
payload capacity in kilograms and carrying dimensions, speed in metres per
second, starting location, and payload compatibility.

Battery inputs include capacity in **kWh**, charge rate in **kW**, initial state
of charge and recharge threshold in **percent**, and motor power in **watts**.
Use measured or vendor-supported assumptions. A suitable payload capacity does
not establish that its physical footprint fits through a door or into a lift.

In **Configuration → Payloads**, define mass, length/width/height and allowed
carrying orientations. Review handling, inventory/tracked-item settings and
returns when used. Each task must reference an existing payload and endpoints.
For weighted lift exports, robot **Unloaded weight** is distinct from payload
capacity; unspecified robot weights remain unavailable in the export.

## Inventory, charging and washing

At one location select **Properties → Create / edit spaces…**, or right-click
and choose **Inventory spaces**. Use the canvas and Properties to place bays,
set dimensions and angles, and inspect overlap/entry clearance. Draft Undo/Redo
stays within the dialog. **Save and close** applies the edit; Cancel discards it.

The **Locations & Inventory Spaces** editor supports cross-location editing.
Choose a scope before applying bulk edits. **Detach payloads in scope** makes
payload bays flexible; robot and charging bays are skipped. Flexible bays admit
payloads fitting their dimensions, including a permitted 90-degree turn.
**Save all** applies the draft; save the project to persist it.

Charging requires reachable charging locations and compatible robot bays with
the charger option enabled. Finite bays can create charger queues. Check bay
positions rather than assuming that a charger label makes a location usable.
The building tutorial includes four example charging bays.

For a workflow needing robot washing, configure the receiving location's wash
requirement, wash location and duration in seconds. Connect the wash station and
set its capacity. Inspect washing and subsequent robot availability in Playback.

## Lifts

Open **Configuration → Lifts**. Give each lift a unique ID, served floors,
starting floor and an x/y stop position for every served floor. The position
map must match the served floors exactly; the starting floor must be served.
Connect stops to the intended corridors on each level.

Review car dimensions and capacity, door and boarding durations in seconds, and
speed in floors per second against the shared level height. Use route profiles
to restrict which lift a flow can use. Where enabled, review reliability, health,
repair and scheduled speed assumptions: these are model rules requiring
calibration, not measured equipment reliability.

To compare possible new lift locations, see
[lift planning studies](reference/lift-planning.md).

## Departments and generated demand

Use **Configuration → Departments** to set enabled departments, floor, operating
hours, active days, workflow locations, bed/turnover/staff assumptions, and waste
streams where relevant. Save the individual department and the Departments list.

In **Configuration → Demand generation**, enable automatic task generation,
then select one category and its departments/groups. Review:

| Setting | What to establish |
| --- | --- |
| Payload and endpoint role | Which item moves, and whether a department supplies pickup or dropoff. |
| Schedule/timeframe | Dates, active days, release times and any overnight windows. |
| Department/group overrides | The effective rule for each department, not only the category default. |
| Route profile | The allowed outbound path and separately configured return path. |
| Service target | A meaningful positive target and its time unit/completion rule. |
| Returns/exchanges | Payload identity, collection delay and actual return endpoint. |
| Volume/threshold | Rate, container capacity, threshold, initial stock and physical container assumptions. |
| Staff assistance | Resource pool, hours, handling time and travel policy. |

Use **Configuration → Demand preview**, choose dates/filters and **Build preview**.
Inspect Tasks, Timetable and Rules and reconciliation; investigate zero-work
explanations. A preview shows planned demand. Runtime-dependent returns and
resource-dependent timing still require simulation evidence.

Read the child pages for [manual tasks](user-guide/03-manual-task-scenario.md),
[task generation](user-guide/06-task-generation-basics.md),
[waste and volume](user-guide/07-waste-and-volume-generation.md), and
[staff-assisted handling](user-guide/08-staff-assisted-handling.md).

## Staff-assisted handling

Enable shared staff support and category/group **Requires staff** settings only
where the modelling question needs endpoint handling. Set named resource pools,
initial count, movement policy, walking speed, handling minutes and working hours.
Check the effective shift pattern and overrides in demand preview and run events.

The model can add staff when a resource pool is busy; the initial count should
not be treated as a fixed workforce ceiling. Staff handling and related travel
are not a complete porter-led transport model. Inspect actual staff waits and
assignments before treating the staff report as a workforce requirement.
