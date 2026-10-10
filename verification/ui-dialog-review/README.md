# Dialog design review — one dialog at a time

The source inventory covers 57 direct `QDialog` definitions in `visualiser` (56
unique class names; an earlier `LocationInventoryPayloadDialog` definition is
shadowed by a later definition in the same module). The structural pass flags
fixed sizes, dense horizontal layouts, long copy, local scrolling and whether
the shared dialog polish is called in the constructor. It is a triage aid, not a
claim that every data-dependent dialog state has been visually accepted.

Review each dialog in sequence: capture the current UI at compact and wide sizes,
agree a revision image, map every current control and explanation to the revised
layout, then implement and verify at representative display scales. Approval of a
layout concept does not authorise removal of existing inputs or behaviour.

## 1. Task generation parameters — Option A selected

The user selected Option A on 4 October 2026. Preserve the full field-placement
contract below. Implemented on 9 October 2026; see the
[Simple delivery review](../SIMPLE_DELIVERY_REVIEW.md) for functional and screen evidence.

Current capture: [Task generation](captures/task-generation.png). At the current
display scale the dialog is 1068 × 815 logical pixels, with a 1707 × 1019 logical
desktop available. The buttons are visible, but two fixed selection columns and a
long form compete for horizontal space. Department group actions take most of the
left column. The large schedule/Waste explanation sits above the save controls and
adds visual density. The form itself scrolls; the selection columns do not adapt.

Revision images at 1024 × 768 logical pixels:

- [Option A — selection plus focused tabs](revisions/task-generation-A-1024.png)
- [Option B — full-width sections](revisions/task-generation-B-1024.png)

Wide comparisons: [A at 1600](revisions/task-generation-A-1600.png),
[B at 1600](revisions/task-generation-B-1600.png). These are layout concepts, not
screens of implemented controls. The images show a representative subset of the
current form so the hierarchy and spacing can be compared. The complete field
mapping below is required for implementation.

**Option A** retains a persistent category list, moves department selection and
group operations into a compact scope area, and divides the form into focused tabs.
It reduces simultaneous density but users switch tabs to compare distant settings.

**Option B** places category and department selection above one full-width scrolling
form with numbered sections. It keeps related settings visible in one sequence,
but a long form requires scrolling and category switching becomes a dropdown.

In either option, Save/Cancel/Export stay visible; the full current explanation
belongs in a Notes & help tab or Reference and assumptions section, using the
original wording. Contextual tooltips and applicability/disabled-state behaviour
must remain. The visuals do not imply new simulation settings.

### Complete field placement contract

The current dialog has 41 form rows plus global controls and category/department
operations. Preserve them as follows:

| Group | Current form rows and operations | A | B |
| --- | --- | --- | --- |
| Scope and global | Enable automatic task generation; global staff summary/configuration; category list/Add/Delete; department list; Configure multiple, Edit/Delete/Clear configured group, Clear all department settings | Selection column and top summary | Editing scope and group menu; global summary in Timing and staff |
| Basics | Category enabled; Display name; Generation mode; Priority; Notes | Basics; Notes in Notes & help | 1 · Basics; Notes in Reference and assumptions |
| Locations and route | Department location role; Pickup/source location; Drop-off destinations; Payload; Route profile | Locations & routing | 2 · Locations, payload and route |
| Returns and inventory | Tracked item exchange; Exchange mode; Return task; Return payload; Return delay; Shared-zone release spacing; Reusable return pool; Pool multiplier; Pool hard cap | Returns & stock | 4 · Returns and stock |
| Staff | Staff handling; Collection response delay; Handling time; Handoff timing; Category-wide drop-off-zone capacity; Initial staff count; Staff resource name; Out-of-hours fallback; Fallback resource name; Staff movement; Shift pattern; Working hours by day | Schedule & staff | 3 · Timing and staff |
| Timing and volume | Days active; Fortnightly recurrence; Scheduled times; Frequency per day; Volume per event; Threshold volume; Base daily volume; Timeframe start/end; Payload multiple | Schedule & staff | 3 · Timing and staff |
| Guidance | Waste-specific scope explanation; schedule/timeframe, destination compatibility and configured-group guidance | Notes & help | Reference and assumptions |

Whichever option is chosen, the build must retain all listed controls, values,
validation, conditional enabling, group actions and save/export behaviour. The
selected revision should be checked at 1024 × 768 and 1600 × 900 logical window
sizes and at 100%, 150% and 200% display scaling, with no clipped controls.

## 2. Simulation settings — Option B selected

The user selected Option B on 4 October 2026. Retain the existing four tabs,
organise the Run period rows into groups, and make full mode findings available
through an explicit details control. Implemented on 9 October 2026; see the
[Simple delivery review](../SIMPLE_DELIVERY_REVIEW.md) for verification.

Current capture: [Simulation settings](captures/simulation-settings.png). The
dialog already has four useful tabs and a fixed Save/Cancel footer. On Run period,
the always-visible mode findings box consumes much of the page even when it says
only that there are no changes. Several field labels wrap onto two lines while
the tab uses one long undifferentiated form. The run-period page scrolls, but
other pages rely on the outer dialog size.

Revision images at 1024 × 768 logical pixels:

- [Option A — section navigator](revisions/simulation-settings-A-1024.png)
- [Option B — compact tabs](revisions/simulation-settings-B-1024.png)

Wide comparisons: [A at 1600](revisions/simulation-settings-A-1600.png),
[B at 1600](revisions/simulation-settings-B-1600.png). These are nonfunctional
layout concepts showing Run period. The other sections must carry the complete
existing controls and wording listed below.

**Option A** uses a persistent left navigation list and a mode/demand summary.
The selected section scrolls on the right. It keeps section identity visible,
but uses some horizontal space.

**Option B** keeps the current tabs and groups the run-period controls into Mode,
Demand window, and Release and deferral. It preserves familiar navigation and
maximises form width, but the active section is less prominent.

Both options replace the permanently expanded mode-finding box with a visible
readiness line and an explicit detail control. That control must show the entire
existing finding text, including errors and source-representation information;
the mockup does not remove or summarise it in saved data.

| Existing tab | Controls and guidance to preserve |
| --- | --- |
| Run period | Simulation mode; readiness status and complete mode-change/finding details; start time; fixed-end toggle and end time; legacy rate metadata; same-time release spacing; maximum task deferral; duration/end precedence guidance |
| Performance | Route precomputation toggle and pair limit; multi-stop and single-task candidate limits; assignments per cycle; simulated continuation delay; workload guidance |
| Charging | Opportunity charging toggle; inactive-before-charging duration; battery-reserve guidance |
| Initial conditions | Seed waste containers; ignore inventory-space capacity; ignore invalid local manoeuvres with unverified evidence; spawn payloads when pickup stock is exhausted; capacity-planning guidance |

The implementation must keep exact validation, enabled states, imported-value
precision preservation and Save/Cancel semantics. Check 1024 × 768 and 1600 × 900
logical windows at 100%, 150% and 200% display scaling.

## 3. Department — Option A selected

The user selected Option A on 4 October 2026. Use the Details, Hours & waste,
and Task locations & zones tabs, with the two-step save reminder always visible.
Implemented on 9 October 2026; see the
[Simple delivery review](../SIMPLE_DELIVERY_REVIEW.md) for verification.

Current populated capture: [Department](captures/department.png). With three task
categories at 1024 × 768 logical pixels, one flat form scrolls from identity
through hours and waste to category locations, drop-off zones and map position.
The compact default opening (503 × 474 in the first capture) showed only the
top rows. Category rows combine summary, Select, suffix and Place in one line;
the zone selection and provisional-save instructions are much farther down.

Revision images at 1024 × 768 logical pixels:

- [Option A — focused tabs, Details](revisions/department-A-1024.png)
- [Option A — Task locations and zones](revisions/department-A-locations-1024.png)
- [Option B — grouped continuous form](revisions/department-B-1024.png)

Wide comparisons: [A at 1600](revisions/department-A-1600.png),
[B at 1600](revisions/department-B-1600.png). The images are nonfunctional
layout concepts. Option A separates Details, Hours & waste, and Task locations
& zones; the category list stays visible while each category's service location
and zone controls take the full remaining width. Option B keeps one scrollable
page with inline expandable cards; it shows an overview of all categories at
once but requires expansion to edit fields.

In both designs, the existing two-step save instruction remains visible above
the fixed Save/Cancel footer. Inline expansion in B must not introduce another
save boundary. Neither option changes the provisional location/zone lifecycle.

| Current content | Placement in A | Placement in B |
| --- | --- | --- |
| ID, name, read-only floor, enabled, bed count, patient turnover, staff count, X/Y | Details | Identity/activity and Map position cards |
| Operating start/end, calculated hours, seven active-day toggles | Hours & waste | Hours/waste card, expandable inline |
| Assigned waste streams and Waste-generation guidance | Hours & waste | Hours/waste and Guidance cards |
| For each configured task category: service-location summary and selector, new-location suffix, Place action, drop-off-zone summary and selector | Task locations & zones, category selection on the left | Task locations & zones, one expandable inline card per category |
| Shared drop-off-zone Select or create action and placement guidance | Task locations & zones | Task locations & zones and Guidance cards |
| Provisional placement instructions and Save/Cancel | Persistent footer | Persistent footer |

Every current validation rule, category-dependent row, selection/placement
callback, hidden draft and parent-list save behaviour must survive the revision.

## 4. Corridors, doors and people use — Option B selected

The user selected Option B on 4 October 2026. Retain the full-width comparison
tables and group the bulk-edit controls beneath them. The production dialog has
not been changed yet.

Current captures: [Corridors](captures/corridors.png) and
[Door openings](captures/corridors-doors.png). At 1220 × 720 logical pixels the
seven-column corridor table and four-column door table leave a large blank area
with the current two-row sample. The bulk-edit controls run across the full
dialog width. The two tabs, table selection, map selection, filter, guidance,
Apply action and Save/Cancel are all required.

Revision images at 1024 × 768 logical pixels:

- [Option A — corridor list and selected-asset inspector](revisions/corridors-A-1024.png)
- [Option A — door-opening view](revisions/corridors-A-doors-1024.png)
- [Option B — full-width table and edit drawer](revisions/corridors-B-1024.png)
- [Option B — door-opening view](revisions/corridors-B-doors-1024.png)

Wide comparisons: [A corridors](revisions/corridors-A-1600.png),
[A doors](revisions/corridors-A-doors-1600.png),
[B corridors](revisions/corridors-B-1600.png),
[B doors](revisions/corridors-B-doors-1600.png). These are nonfunctional layout
concepts with representative data.

**Option A** places a compact route or node list beside a selected-asset
inspector and a stacked edit panel. A selected route's complete values are
shown below the list. It gives the controls more vertical room, but comparing
many corridors requires selecting them in turn.

**Option B** retains the full comparison tables, stretches columns across the
available width and groups bulk edits below them. It keeps all rows and columns
visible for scanning, but the seven-column corridor table may need horizontal
scrolling at smaller widths or larger text scales.

| Existing content | Placement in A | Placement in B |
| --- | --- | --- |
| Corridor filter by node, people use or profile; map-based asset selection; multi-row selection summary | Above the route list | Above the corridor table |
| From, To, Traffic, Corridor width, Effective width, People use, People profiles | Compact route summary plus complete selected-route detail | Seven-column table |
| Traffic direction (Leave unchanged, two-way, one-way); nominal clear width with three decimal places and metre suffix; people classification | Stacked edit panel | Grouped edit drawer |
| Assigned people-profile summary, Choose and Clear profiles actions | Stacked edit panel | Edit drawer with separate actions |
| Apply to selected corridors; two-way lane/payload guidance; effective-width explanation | Inspector and persistent intro | Below-table edit drawer and persistent intro |
| Door filter by node name or floor; map-based node selection; multi-row selection summary | Above the node list | Above the door table |
| Corridor node, Floor, Door opening, Clear opening width | Compact node summary plus complete selected-node detail | Four-column table |
| Door classification (Leave unchanged, door, not a door); clear opening width with three decimal places and metre suffix; Apply to selected nodes | Stacked edit panel | Grouped edit drawer |
| Restrictive-opening guidance; Save/Cancel | Door inspector and fixed footer | Below-table guidance and fixed footer |

Both choices must preserve existing filtering, selection, validation, tooltips,
default values and the two-step workflow: Apply changes selected rows in the
draft, then Save commits the dialog result. Leave unchanged must remain a
distinct value for every bulk-edit field. The full guidance about effective
width, two-way lane fit and restrictive door openings stays readable. Check
both tabs at 1024 × 768 and 1600 × 900 logical windows and at 100%, 150% and
200% display scaling after implementation.

## 5. People movement profile — Option B selected

The user selected Option B on 4 October 2026. Retain the four tabs, place
identity and timeframe side by side, and place Flow controls beside the live
preview. The production dialog has not been changed yet.

Current captures: [Profile and timeframe](captures/people-movement-profile.png),
[Route or corridor assets](captures/people-movement-route.png),
[Flow profile](captures/people-movement-flow.png), and
[AMR interaction](captures/people-movement-interaction.png). A requested
1024 × 768 logical window grew to 1024 × 816 at the current display scale.
The seven Flow profile labels and fields occupy the full width and several
labels wrap. The preview sits below the controls, while the shorter Route and
AMR interaction tabs leave much of the window unused.

Revision images at 1024 × 768 logical pixels:

| Page | Option A — guided steps | Option B — refined tabs |
| --- | --- | --- |
| Profile and timeframe | [A profile](revisions/people-movement-A-profile-1024.png) | [B profile](revisions/people-movement-B-profile-1024.png) |
| Route or corridor assets | [A route](revisions/people-movement-A-route-1024.png) | [B route](revisions/people-movement-B-route-1024.png) |
| Flow profile | [A flow](revisions/people-movement-A-flow-1024.png) | [B flow](revisions/people-movement-B-flow-1024.png) |
| AMR interaction | [A interaction](revisions/people-movement-A-interaction-1024.png) | [B interaction](revisions/people-movement-B-interaction-1024.png) |

Wide comparisons: [A flow at 1600](revisions/people-movement-A-flow-1600.png)
and [B flow at 1600](revisions/people-movement-B-flow-1600.png). Both are
nonfunctional layout concepts with representative values.

**Option A** uses a persistent four-step list and one scrollable work area.
Profile and timeframe groups are stacked. Flow controls sit above the chart.
It gives labels more width and makes the editing sequence explicit, but users
switch steps to revisit earlier settings.

**Option B** retains the current four tabs. Identity and timeframe sit side by
side; Flow controls and preview sit side by side. Each tab scrolls within the
fixed dialog if space becomes tight. It supports direct comparison with the
preview and uses wide displays well, but each column becomes narrower on a
compact display.

| Current section | Controls, options and explanations to preserve |
| --- | --- |
| Profile identity | Unique profile name and example; Staff, Public or Mixed route users; enabled status; profile-name tooltip |
| Daily timeframe | Custom, Full day, Early, Day, Late, Night, Visiting and Meal-service presets; description; start/end times including overnight use; seven active days and Weekdays/Every day/Clear actions |
| Route or corridor assets | Route between different start/end locations or assign directly to selected corridors; location selectors; corridor summary, Select corridor assets and Clear selection; conditional enabled states and the explanation of each route method |
| Flow profile | Constant, ramp up, ramp down and ramp-up/busy/ramp-down shapes; quiet-period and peak people per interval; movement interval; automatic fit to timeframe; manual ramp-up and ramp-down durations; shape-dependent enabled states and tooltips |
| Preview | Existing graph and complete interval/people/alignment summary, updating with shape and time changes |
| AMR interaction | Average walking speed in m/s; AMR speed percentage while sharing the route; crowding/speed example and tooltips |
| Dialog | Full introduction; Save/Cancel; current validation and result values |

Implementation must keep the current validation: a nonblank profile name,
different start and end locations for routed use, at least one selected
corridor for direct use, at least one active day, and quiet-period people no
higher than peak people. The complete profile-shape and preset behavior,
preview calculation, numeric precision and Save/Cancel result format remain.
Check all four pages at 1024 × 768 and 1600 × 900 logical windows and at 100%,
150% and 200% display scaling after implementation.

## 6. Mass collection / bin rotation — Option A selected

The user selected Option A on 4 October 2026. Use focused Collection, Timing
and triggers, and Handling and notes tabs, with a fixed Save/Cancel footer.
The production dialog has not been changed yet.

Current captures: [starting size](captures/mass-collection-760.png) and
[1024 × 768](captures/mass-collection-1024.png). With representative data, the
760 × 620 requested window grows to 760 × 662 logical pixels. The current flat
form places payload and schedule summaries beside action buttons, stretches
numeric controls across the window, and spreads several rows vertically when
the window grows. The explanatory text and Save/Cancel remain at the bottom.

Revision images:

| View | Option A — focused tabs | Option B — grouped page |
| --- | --- | --- |
| 1024 × 768 | [Collection](revisions/mass-collection-A-collection-1024.png), [Timing and triggers](revisions/mass-collection-A-timing-1024.png), [Handling and notes](revisions/mass-collection-A-handling-1024.png) | [Full page](revisions/mass-collection-B-1024.png) |
| 760 × 620 | [Timing and triggers](revisions/mass-collection-A-timing-760.png) | [Stacked page with local scroll](revisions/mass-collection-B-760.png) |
| 1600 × 900 | [Timing and triggers](revisions/mass-collection-A-timing-1600.png) | [Two-column page](revisions/mass-collection-B-1600.png) |

These are nonfunctional layout concepts with representative data. **Option A**
divides the existing fields into Collection, Timing and triggers, and Handling
and notes tabs. It keeps each section short but requires switching tabs to
review the full event. **Option B** keeps one page: identity and handling on
the left, schedule and triggers on the right when wide, stacked in a scrolling
area when compact. It shows the whole event at once on a wide display but
requires scrolling at 760 × 620. Both keep Save/Cancel fixed at the bottom.

| Current content | A | B |
| --- | --- | --- |
| ID, enabled status, required bin store location | Collection | Collection identity and scope group |
| Payload summary, Select and Clear; empty selection means all payload types | Collection | Collection identity and scope group |
| Seven active-day toggles; scheduled-times summary, Edit times and Clear; no fixed times means capacity triggers only | Timing and triggers | Schedule group |
| Capacity percentage, full-bin count, and capacity check interval, with their current precision, units and tooltips | Timing and triggers | Capacity triggers group |
| Replace used/full bins with empty equivalents; notes | Handling and notes | Exchange and notes group |
| Full explanation of replacement and inventory-space trigger behavior | Handling and notes | How the collection works group |
| Save/Cancel | Fixed footer with read-only event summary | Fixed footer with read-only event summary |

Implementation must retain the existing nested payload and scheduled-time
pickers, default values, empty-selection meanings, 0%- and zero-count trigger
disablement, required ID/location/day validation, numeric ranges and result
format. Check compact and wide layouts at 100%, 150% and 200% display scaling
after implementation.

## 7. Task category shared-location wizard — Option B selected

The user selected Option B on 4 October 2026. Keep one grouped page with
assignment controls above the six-column department table and the selection
actions in two rows. The production dialog has not been changed yet. The
one-pixel department-row defect described below remains an implementation
requirement for the selected design.

Current captures: [920 × 620](captures/shared-location-920.png) and
[1024 × 768](captures/shared-location-1024.png). The current single-screen
wizard fits those logical sizes, but its selection actions form one crowded
row. More seriously, the six populated department rows render as blank space
in the local capture: the first row measures one logical pixel high. A
read-only runtime probe with uniform row heights disabled measures that row at
18 logical pixels; [probe capture](captures/shared-location-rows-visible-probe.png).
The implementation pass must fix row visibility for this table regardless of
the chosen design and check other affected tree views. The probe did not
change production code.

Revision images:

| View | Option A — two-step wizard | Option B — grouped single page |
| --- | --- | --- |
| 1024 × 768 | [1 · Assignment](revisions/shared-location-A-step1-1024.png), [2 · Departments](revisions/shared-location-A-step2-1024.png) | [Full page](revisions/shared-location-B-1024.png) |
| 920 × 620 | [1 · Assignment](revisions/shared-location-A-step1-920.png), [2 · Departments](revisions/shared-location-A-step2-920.png) | [Scrollable page](revisions/shared-location-B-920.png) |
| 1600 × 900 | [2 · Departments](revisions/shared-location-A-step2-1600.png) | [Full page](revisions/shared-location-B-1600.png) |

These are nonfunctional layout concepts with representative departments.
**Option A** separates target assignment from department selection. The
second step shows the six-column table at full width and repeats the chosen
target and options above it. Next and Back are navigation only; Save still
produces the current result. It gives the table more height but requires a
step change to revise the target.

**Option B** retains one page, grouping the target controls and department
selection, with four bulk-selection actions in a two-row grid. It shows
everything at once on wide displays; the 920 × 620 version scrolls within
the dialog while Save and the assignment count stay fixed.

| Current content | A | B |
| --- | --- | --- |
| Full explanation of shared pickup/drop-off use | Persistent introduction | Persistent introduction |
| Task category; selected shared-location summary, multi-select picker and Clear | Assignment step; read-only recap on Departments | Assignment group |
| Replace existing assignments; Only enabled departments | Assignment step; read-only recap on Departments | Assignment group |
| Select all, none, current floor, and departments already using category | Departments step, two-row actions | Select departments group, two-row actions |
| Six columns: Use, ID, Name, Floor, Enabled, Current category locations | Departments step | Full-width department table |
| Live count of shared locations and selected departments; Save/Cancel | Fixed footer | Fixed footer |

Preserve category-change behavior, preselected departments, the location
picker, individual row checks, the distinction between replacing and retaining
existing assignments, and the current-floor and already-using-category bulk
actions. “Only enabled departments” currently constrains bulk selection; it
does not hide disabled rows. Save must still require a category, at least one
shared location and at least one department, returning the same assignment
mapping. Verify table rows and column visibility at compact and wide sizes and
at 100%, 150% and 200% display scaling after implementation.

## 8. Auto shared bin groups from category locations — Option A selected

The user selected Option A on 4 October 2026. Keep the compact group table
and selected-group detail panel so full IDs, departments, floors and counts
remain available without widening the table. The production dialog has not
been changed yet.

Current captures: [1040 × 680](captures/shared-bin-groups-1040.png) and
[1024 × 768](captures/shared-bin-groups-1024.png). The seven-column preview
with generated IDs measures about 1221 logical pixels wide with this sample,
so its final update and skipped columns require horizontal scrolling. Long
group IDs and department names run together in the same row. Unlike the
shared-location wizard, this preview's populated rows retain normal height
in the local capture.

Revision images:

| View | Option A — summary table and detail panel | Option B — full group cards |
| --- | --- | --- |
| 1024 × 768 | [A](revisions/shared-bin-groups-A-1024.png) | [B](revisions/shared-bin-groups-B-1024.png) |
| 1040 × 680 | [A](revisions/shared-bin-groups-A-1040.png) | [B](revisions/shared-bin-groups-B-1040.png) |
| 1600 × 900 | [A](revisions/shared-bin-groups-A-1600.png) | [B](revisions/shared-bin-groups-B-1600.png) |

These are nonfunctional layout concepts. The sample has **Overwrite existing
shared bin groups** off to show one skipped group; the current dialog defaults
it on.

**Option A** keeps a compact selectable group table and shows the selected
group's full generated IDs, department names, floors and counts beside it.
It supports scanning many groups, while full details require selecting a row.

**Option B** displays each group in a scrollable card with its checkbox,
department names, floors, full group IDs and counts. It makes every field
readable without horizontal scrolling, but long group lists need vertical
scrolling. Both keep the selection summary and Save/Cancel fixed.

| Current content | A | B |
| --- | --- | --- |
| Full explanation: groups are derived from shared category locations; one physical-bin group ID per stream; category locations do not change | Persistent introduction | Persistent introduction |
| Source task category, default Waste | Group source and rules | Group source and rules |
| Waste-stream summary, Select streams and All | Group source and rules | Group source and rules |
| Shared bin group prefix, Only enabled, Only selected, Overwrite existing, minimum departments per group | Group source and rules | Group source and rules |
| Refresh preview, Select all groups, Select none, Select current floor groups | Preview actions | Preview actions |
| Use, Shared location, Shared bin groups, Departments, Floors, Streams updated, Skipped existing | Summary table plus selected-group detail panel | Full group cards |
| Live selected-group/department/update/skipped summary and Save/Cancel | Fixed footer | Fixed footer |

Preserve the current grouping by assigned category location, the selected
waste-stream filter, ID generation from prefix/location/stream, default and
minimum group-size rules, enabled/selected department filters, overwrite and
skip behavior, preview refresh and checked-group preservation. Save must still
require a category, at least one waste stream and at least one selected group,
returning the same result mapping. Verify long names and IDs, many groups,
compact/wide windows, and 100%, 150% and 200% display scaling after
implementation.

## 9. Route Profiles (active V2 editor) — Option A selected

The user selected Option A on 4 October 2026. Keep the profile list visible
and separate Profile access from Allowed edges in the right pane. The
production dialog has not been changed yet.

The main window opens `RouteProfilesEditorV2` in `advanced_dialogs.py`. The
older `RouteProfilesEditor` in `dialogs.py` explicitly identifies itself as a
legacy editor unused by the main window, so it does not need a duplicate
design revision.

Current captures: [1200 × 720](captures/route-profiles-1200.png) and
[1024 × 768](captures/route-profiles-1024.png). The profile list, name,
lift/node summaries, graphical picker, raw JSON edge editor and two save
actions fit at both sizes. The long route-rule explanation spans the top.
Controls are widely separated, and the JSON editor fills most of the page.

Revision images:

| View | Option A — focused detail tabs | Option B — grouped single editor |
| --- | --- | --- |
| 1024 × 768 | [Profile access](revisions/route-profiles-A-access-1024.png), [Allowed edges](revisions/route-profiles-A-edges-1024.png) | [Full editor](revisions/route-profiles-B-1024.png) |
| 1200 × 720 | [Allowed edges](revisions/route-profiles-A-edges-1200.png) | [Full editor](revisions/route-profiles-B-1200.png) |
| 1600 × 900 | [Allowed edges](revisions/route-profiles-A-edges-1600.png) | [Full editor](revisions/route-profiles-B-1600.png) |

These are nonfunctional layout concepts. **Option A** keeps the persistent
profile list but separates Profile access and Allowed edges into tabs. The
JSON editor has the full right pane when selected; lift and node selections
require switching back to the first tab. **Option B** retains all fields in
one grouped right pane, with profile access above the JSON editor. It makes
the selected profile's access and edges visible together, while the editor
has less vertical space. Both keep Apply Changes and Save All in a fixed
footer.

| Current content | A | B |
| --- | --- | --- |
| Full route-rule explanation, including unrestricted empty lists, directional edges, pickup timing and explicit return profiles | Persistent introduction | Persistent introduction |
| Profile list, Add and Delete; default profile cannot be deleted | Persistent left panel | Persistent left panel |
| Profile name; selected allowed lifts and Pick; selected allowed nodes, Pick and Graphical | Profile access tab | Profile access group |
| Editable JSON array pairs for allowed edges; Generate from selected nodes; Clear edges | Allowed edges tab | Directional allowed edges group |
| Apply Changes for the selected profile; Save All for the collection | Fixed footer | Fixed footer |

Preserve floor-grouped lift/node pickers, graphical map selection and dialog
return, profile rename/add/delete behavior, the existing in-memory Apply
Changes step, Save All callback, and JSON validation. Generating edges from
selected nodes must continue to respect corridor direction. Empty allowed
lists remain unrestricted. Check at 1024 × 768, 1200 × 720 and 1600 × 900
logical sizes and at 100%, 150% and 200% display scaling after implementation.

## 10. Configure multiple departments — Option A selected

The user selected Option A on 4 October 2026. Keep department scope and the
location-role choice visible above focused tabs, with each tab scrolling
independently. The mockups were restyled after this choice to match the earlier
dialog revisions' typography, group borders, spacing and blue primary action.
The production dialog has not been changed yet.

This is the active `BulkDepartmentTaskGenerationDialog` in `dialogs.py`, opened
from task generation for one category at a time. It applies one configuration
to selected eligible departments. It is distinct from the single-category form
reviewed in section 1, but shares its generation settings; the revisions use
the same section names to avoid creating a second, inconsistent workflow.

Current captures: [Stores at 1024 × 768](captures/bulk-department-stores-1024.png)
and [Waste at 920 × 720](captures/bulk-department-waste-920.png). A single
scrolling form holds 38 rows. The current Apply/Cancel footer remains visible,
but the viewport can cut labels and rows at its edge, and staff, returns and
timing settings are distant from the fields that enable them. The Waste variant
still shows disabled generation fields and a notice near the bottom of the
form, which may be out of view.

Revision images (nonfunctional layout concepts):

| View | Option A — fixed scope and focused tabs | Option B — one guided scrolling page |
| --- | --- | --- |
| 1024 × 768 | [Basics](revisions/bulk-department-A-basics-1024.png), [Locations](revisions/bulk-department-A-locations-1024.png), [Returns](revisions/bulk-department-A-returns-1024.png), [Schedule](revisions/bulk-department-A-schedule-1024.png) | [Top](revisions/bulk-department-B-top-1024.png), [Middle](revisions/bulk-department-B-middle-1024.png) |
| 1600 × 900 | [Basics](revisions/bulk-department-A-basics-1600.png), [Schedule](revisions/bulk-department-A-schedule-1600.png) | [Top](revisions/bulk-department-B-top-1600.png), [Middle](revisions/bulk-department-B-middle-1600.png) |

**Option A** keeps the selected departments and location-role choice visible
above tabs: Basics, Locations & routing, Returns & stock, Schedule & staff,
and Notes & help. Each tab scrolls on its own, while Apply/Cancel and the
selection count stay visible. The user switches tabs to review distant fields.

**Option B** puts scope and all related settings in numbered sections on one
scrolling page. The Apply/Cancel footer and selected-count summary stay fixed.
The user can read settings in one sequence, but must scroll back to change
scope or compare distant fields.

| Existing content | A | B |
| --- | --- | --- |
| Selected eligible departments, Select departments, category identity, assigned-location eligibility explanation, department location as pickup/source or drop-off | Fixed scope panel | First page section |
| Enabled, generation mode, priority, payload | Basics tab | 1 · Task basics |
| Pickup/source locations, drop-off destinations, route profile | Locations & routing tab | 2 · Locations and route |
| Tracked item exchange, exchange mode, return task, return payload, return delay, shared-zone release spacing, reusable return pool, pool multiplier, pool hard cap | Returns & stock tab | 3 · Returns and stock |
| Days active, fortnightly recurrence, scheduled times, frequency per day, volume per event, threshold volume, base daily volume, timeframe start/end, payload multiple | Schedule & staff tab, timing group | 4 · Schedule and staff, timing group |
| Staff handling, collection response delay, handling time, handoff timing, initial staff count, staff resource name, out-of-hours fallback, fallback resource name, staff movement, shift pattern, working hours by day | Schedule & staff tab, staff group | 4 · Schedule and staff, staff group |
| Notes; Waste stream-specific generation explanation | Notes & help tab, with the Waste limitation also visible at the top of the dialog when category is Waste | 5 · Notes and guidance, with the Waste limitation also visible at the top of the dialog when category is Waste |
| Apply and Cancel | Fixed footer | Fixed footer |

The images show a representative Stores state. The schedule mockup shows only
hybrid-applicable timing fields; scheduled times and timeframe controls belong
in that group when their modes apply. Exchange mode, staff fallback, reusable
pool details and other conditional controls likewise follow the current
enabling/visibility rules. For Waste, the stream-specific generation settings
remain owned by Departments → Manage waste streams; this dialog retains only
its existing routing, destination, priority and return behavior. Preserve the
current selection filtering, role-dependent endpoints, validations, tooltips,
staff/week-hours pickers, schedule picker, per-department result mapping and
Apply/Cancel semantics. Check compact and wide windows at 100%, 150% and 200%
display scaling after implementation.

## 11. Manual Task — Option A selected

The user selected Option A on 4 October 2026. Use the grouped vertical form
with Task and journey, Release and priority, and Staged container recovery;
keep Save/Cancel visible. The production dialog has not been changed yet.

`TaskFormDialog` in `advanced_dialogs.py` is the active editor for one manual
transport task, including staged-container recovery. The current populated
capture at [560 logical pixels wide](captures/task-form-560.png) shows that a
requested 560 × 360 opening expands to 560 × 581 to fit the form. At
[700 × 600](captures/task-form-700.png), all eleven rows fit, but journey,
timing and recovery settings are one undifferentiated sequence. The detailed
recovery conditions are only in a checkbox tooltip.

Revision images (nonfunctional layout concepts, using the established review
style):

| View | Option A — grouped vertical form | Option B — responsive split form |
| --- | --- | --- |
| 700 × 600 | [A](revisions/task-form-A-700.png) | [B](revisions/task-form-B-700.png) |
| 1024 × 768 | [A](revisions/task-form-A-1024.png) | [B](revisions/task-form-B-1024.png) |
| 1600 × 900 | [A](revisions/task-form-A-1600.png) | [B](revisions/task-form-B-1600.png) |

**Option A** groups the existing controls into Task and journey, Release and
priority, and Staged container recovery in one vertical scrolling page. It
preserves a consistent reading order across screen sizes.

**Option B** places Task and journey beside Release and priority plus Staged
container recovery on wider windows. At compact widths the groups stack in
the same order as Option A. It uses wide screens more fully, while the journey
column is narrower and labels may need wrapping.

| Current controls and guidance | A | B |
| --- | --- | --- |
| Task ID, read-only pickup and drop-off with graph-location pickers, payload, route profile | Task and journey | Left pane when wide, first group when compact |
| Release date and time, target allowance in seconds, priority, comma-separated labels | Release and priority | Right pane when wide, second group when compact |
| Physical container ID, staged-recovery checkbox and its exact-evidence, staged-state and validation guidance | Staged container recovery | Right pane when wide, third group when compact |
| Save and Cancel | Fixed footer | Fixed footer |

The mockups use simple input stand-ins for the date and integer values; the
actual date/time and bounded numeric widgets must remain. Keep the existing
single-location picker behavior, required ID/pickup/drop-off/payload checks,
optional container ID for ordinary tasks, required exact container ID for
recovery, and rejection of recovery with a further return or staff handoff.
Preserve the seeded fields that this editor does not expose, result keys,
manual-task flags and Save/Cancel semantics. Check 700 × 600, 1024 × 768 and
1600 × 900 logical windows at 100%, 150% and 200% display scaling.

## 12. One-to-many Tasks — Option B selected

The user selected Option B on 4 October 2026. Keep the selected-destination
list beside shared task fields on wide screens and stack it above them on
compact screens. The production dialog has not been changed yet.

`BulkOneToManyTaskDialog` in `advanced_dialogs.py` is a separate creator for
one manual task per selected destination. Its current [620 × 500
capture](captures/one-to-many-620.png) expands to 620 × 514 to fit nine form
rows. In the [1024 × 768 capture](captures/one-to-many-1024.png), its
introductory panel expands to almost half the window and pushes the form down.
The currently selected dropoffs are shown in one wrapped summary line.

Revision images (nonfunctional concepts in the established visual style):

| View | Option A — grouped single form | Option B — destination panel |
| --- | --- | --- |
| 620 × 500 | [A](revisions/one-to-many-A-620.png) | [B](revisions/one-to-many-B-620.png) |
| 1024 × 768 | [A](revisions/one-to-many-A-1024.png) | [B](revisions/one-to-many-B-1024.png) |
| 1600 × 900 | [A](revisions/one-to-many-A-1600.png) | [B](revisions/one-to-many-B-1600.png) |

**Option A** groups Base task ID, Pickup, selected Dropoffs, Payload and Route
profile under Journey and destinations, with release, target, priority and
labels under Shared timing and labels. It is compact and follows the chosen
Manual Task form's vertical pattern. Many destination names wrap into a
summary and remain available through Select.

**Option B** keeps a full selected-destination list beside shared task fields
on wide windows. At compact widths the list stacks above the fields, making
the destination set easy to inspect while requiring more scrolling to reach
timing controls. The list is a read-only summary; Select opens the existing
multi-location picker.

| Current control or guidance | A | B |
| --- | --- | --- |
| Explanation that each selected destination creates a task sharing pickup, payload, release time and route profile | Short persistent introduction | Short persistent introduction |
| Base task ID, Pickup, Dropoffs and Select, Payload, Route profile | Journey and destinations | Destination list plus Shared task details |
| Release date/time, target allowance, priority, comma-separated labels | Shared timing and labels | Shared timing and labels |
| Create and Cancel | Fixed footer | Fixed footer |

The mockups' date and integer inputs are visual stand-ins. Keep the actual
date/time widget, bounded numeric widgets and input values. Preserve sorted
dropoff selection, the ≤4-name versus count-only summary behavior where
appropriate, floor-grouped picker, required base ID/pickup/payload/at-least-
one-dropoff validation, the rule that pickup cannot be a dropoff, returned
result keys and manual single-payload flags. Verify compact/wide windows and
100%, 150% and 200% display scaling after implementation.

## 13. Select target days — Option B selected

The user selected Option B on 4 October 2026. Use the full-width calendar,
highlight every selected date, and show the selected-date summary below it.
The production dialog has not been changed yet.

`MultiDaySelectDialog` in `advanced_dialogs.py` supplies multiple target dates.
Current captures: [620 × 500](captures/target-days-620.png), [820 ×
560](captures/target-days-820.png), and [1024 ×
768](captures/target-days-1024.png). The footer lists five selected ISO dates,
but the calendar itself only highlights its single current date. The custom
previous/Today/next row duplicates the calendar widget's own month navigation
bar. At compact widths the toolbar is crowded.

Revision images (nonfunctional concepts in the established style):

| View | Option A — calendar plus selected-date panel | Option B — full-width calendar |
| --- | --- | --- |
| 620 × 500 | [A](revisions/target-days-A-620.png) | [B](revisions/target-days-B-620.png) |
| 820 × 560 | [A](revisions/target-days-A-820.png) | [B](revisions/target-days-B-820.png) |
| 1024 × 768 | [A](revisions/target-days-A-1024.png) | [B](revisions/target-days-B-1024.png) |
| 1600 × 900 | [A](revisions/target-days-A-1600.png) | [B](revisions/target-days-B-1600.png) |

Both options highlight every selected date on the calendar and retain one
month-navigation toolbar with Previous, Today, Next, Clear all and Select
displayed month. At compact widths the selection actions move to a second
toolbar row. The selection count and Apply/Cancel remain fixed.

**Option A** shows a readable list of selected dates beside the calendar.
That list can scroll when many dates are selected, and it remains visible
while browsing months. It reduces calendar cell width, especially at compact
sizes.

**Option B** uses the full available width for the calendar, with a wrapped
selected-date summary below it. It gives the date grid larger cells; long
selection summaries can take vertical space or switch to the existing count
only representation.

Preserve single-date toggle, Shift-click continuous ranges, multi-month
selection persistence, month/year rollover, Today, displayed-month selection,
Clear all, sorted ISO-date result, the current ≤6-date versus count-only
summary threshold, and Apply/Cancel semantics. Selection highlighting must
reflect the stored date set, not just the calendar's current date. Verify
620 × 500, 820 × 560 and 1024 × 768 logical windows and 100%, 150% and 200%
display scaling after implementation.

## 14. Edit Multiple Tasks — Option A selected

The user selected Option A on 4 October 2026. Use grouped update rows with
each checkbox as its field label, and keep Apply/Cancel visible. The
production dialog has not been changed yet.

`EditMultipleTasksDialog` in `advanced_dialogs.py` applies selected changes to
two or more tasks. Current captures: [560 requested × 260, expanded to
347](captures/edit-multiple-tasks-560.png) and [760 ×
520](captures/edit-multiple-tasks-760.png). The current form repeats each
field name beside an “Update…” checkbox and a value widget. At 560 pixels
the rows compete for width; at 760 pixels the introductory panel takes much
more space than its one-line explanation requires.

Revision images (nonfunctional concepts in the established style):

| View | Option A — grouped update rows | Option B — responsive field cards |
| --- | --- | --- |
| 560 × 400 | [A](revisions/edit-multiple-tasks-A-560.png) | [B](revisions/edit-multiple-tasks-B-560.png) |
| 760 × 520 | [A](revisions/edit-multiple-tasks-A-760.png) | [B](revisions/edit-multiple-tasks-B-760.png) |
| 1024 × 768 | [A](revisions/edit-multiple-tasks-A-1024.png) | [B](revisions/edit-multiple-tasks-B-1024.png) |

**Option A** uses each checkbox as the field label and aligns its value beside
it. Timing and priority and Labels and route are separate groups. This is
compact and follows the chosen Manual Task form's grouped reading order.

**Option B** places each checkbox above its value in a field card, two cards
across on wide screens and one per row on compact screens. It gives each
label and control more room, but uses more vertical space.

Both options keep the existing release date/time, target allowance, priority,
comma-separated labels and route profile fields. Checking a field enables
its value; unchecked values remain unchanged. The mockups show two selected
fields to make that state visible; the live dialog currently opens with all
fields unchecked. Preserve the actual date/time and bounded numeric widgets,
seeded values from the first selected task, route profile choices, labels
parsing, rejection when no field is checked, result mapping containing only
checked fields, and Apply/Cancel semantics. Verify compact/wide windows and
100%, 150% and 200% display scaling after implementation.

## 15. Shared multi-select picker — Option A selected

The user selected Option A on 4 October 2026. Keep one grouped checklist,
wrap global selection actions at compact widths, and fix filtered-list
rebuilding so stale rows never overlap. The production picker has not been
changed yet.

`MultiSelectPicker` in `advanced_dialogs.py` is reused by task, route,
department and corridor workflows, so it needs one shared design revision.
Current captures: [520 × 620](captures/multi-select-520.png), [820 ×
720](captures/multi-select-820.png), and [filtered](captures/multi-select-filtered.png).
With the 12 sample locations grouped by floor, the initial 420 × 500 request
expands to 420 × 622. The filtered capture shows a real defect: after typing
“ward,” stale rows overlap the two matches while the summary says four
selected and two visible.

Revision images (nonfunctional concepts in the established style):

| View | Option A — focused grouped checklist | Option B — available and selected panes |
| --- | --- | --- |
| 520 × 620, all | [A](revisions/multi-select-A-all-520.png) | [B](revisions/multi-select-B-all-520.png) |
| 520 × 620, filtered | [A](revisions/multi-select-A-filtered-520.png) | [B](revisions/multi-select-B-filtered-520.png) |
| 820 × 720, all | [A](revisions/multi-select-A-all-820.png) | [B](revisions/multi-select-B-all-820.png) |
| 820 × 720, filtered | [A](revisions/multi-select-A-filtered-820.png) | [B](revisions/multi-select-B-filtered-820.png) |

**Option A** keeps one scrollable grouped checklist. Search and global actions
stay at the top, and the selected count and Apply/Cancel stay visible. At
compact widths the global All/None and visible-selection controls wrap into
two rows. To review hidden selections, the user clears the filter.

**Option B** keeps the same grouped checklist and actions, with a persistent
read-only selected-items pane beside it on wide screens and below it on compact
screens. Hidden selections remain visible while filtering, but the available
checklist is narrower and the compact version uses more vertical space.

Preserve case-insensitive substring search; grouping and sorting; global
All/None across every option; Select visible/Clear visible on current matches;
per-group All/None on that group's visible items; hidden selections across
filter changes; the total and visible selected counts; and the original-option
order of the returned selection. The filtered list must rebuild without stale
widgets or overlap. Check long labels, empty results, many groups, compact and
wide windows, and 100%, 150% and 200% display scaling after implementation.

## 16. Tasks by AMR jump — Option A selected

The user selected Option A on 4 October 2026. Keep the six-column sortable
tree, allow horizontal access to long values, and show full selected-row
details below. The production dialog has not been changed yet.

`TaskJumpDialog` in `amr_sim_visualiser_pyside6.py` opens from the simulation
visualiser. Current expanded captures: [700 × 520](captures/task-jump-700.png),
[980 × 620](captures/task-jump-980.png), and [1400 ×
800](captures/task-jump-1400.png). The single tree has Task ID/Segment,
Payload, Origin, Destination, Duration and Datetime columns. At 700 pixels,
long origins and destinations are elided while the stretch columns provide no
horizontal-scroll reach to their complete values in this capture. The only
jump affordance is double-clicking a task or segment row.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full sortable tree and selected-row detail | Option B — task navigator and detail pane |
| --- | --- | --- |
| 700 × 520 | [A](revisions/task-jump-A-700.png) | [B](revisions/task-jump-B-700.png) |
| 980 × 620 | [A](revisions/task-jump-A-980.png) | [B](revisions/task-jump-B-980.png) |
| 1400 × 800 | [A](revisions/task-jump-A-1400.png) | [B](revisions/task-jump-B-1400.png) |

**Option A** keeps the six-column AMR/task/segment tree. Columns can scroll
horizontally at compact widths, while a selected-row detail area shows the
complete payload, origin, destination, duration and datetime. The tree takes
less vertical room than the current dialog.

**Option B** places a narrow AMR/task/segment navigator beside a full detail
area. It makes long fields readable without horizontal scrolling, but task
attributes are no longer scannable across multiple rows. Explicit Sort by
and Order controls preserve the current six-column and original-order sort
choices.

Preserve AMR grouping, nested task/segment rows, the six data fields, the
three-state sort cycle or its equivalent, numeric duration and datetime
ordering, original insertion-order restoration, and double-click navigation
to the selected task or segment's exact start time and AMR ID. AMR headings
must remain non-jumpable. Selection details must reflect segments as well as
tasks. Verify long names, many AMRs/tasks/segments, compact and wide windows,
and 100%, 150% and 200% display scaling after implementation.

## 17. Tasks by location / department — Option B selected

The user selected Option B on 4 October 2026. Use a compact grouped task
table with complete selected-task details beside it, retaining the existing
filters and jump behavior. The production dialog has not been changed yet.

`TasksByLocationDepartmentDialog` in `amr_sim_visualiser_pyside6.py` is a
separate simulation task browser. Current captures: [Department grouping at
1024 × 768](captures/tasks-by-location-department-1024.png), [at 1420 ×
720](captures/tasks-by-location-department-1420.png), and [Location grouping at
1024 × 768](captures/tasks-by-location-location-1024.png). The tree holds 11
columns. At 1024 pixels it needs about 612 logical pixels of horizontal
scrolling; at the 1420 default it still needs about 216. Location grouping
lists a task under both its start and finish locations when they differ,
while the summary correctly counts unique full tasks.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full table with selected-task detail | Option B — compact table and side detail |
| --- | --- | --- |
| 1024 × 768 | [A](revisions/tasks-by-location-A-1024.png) | [B](revisions/tasks-by-location-B-1024.png) |
| 1420 × 720 | [A](revisions/tasks-by-location-A-1420.png) | [B](revisions/tasks-by-location-B-1420.png) |
| 1600 × 900 | [A](revisions/tasks-by-location-A-1600.png) | [B](revisions/tasks-by-location-B-1600.png) |

**Option A** retains all 11 columns in the grouped tree with horizontal
scrolling and adds a full selected-task detail area below it. Users can scan
the same columns as today, while long values and the `details` text are
readable without hovering. The selected-task area reduces tree height.

**Option B** shows Task, Payload, Start time and Status in the grouped tree,
with all other task fields and the full `details` text beside it. This keeps
task IDs and the primary scan fields readable without horizontal scrolling,
but comparing other fields across several tasks requires selecting each row.

Preserve Group by Department/Location, case-insensitive filtering by task,
payload, department, staff, people count, status, source, displayed times and
finish location; sorted
groups and start-time ordering within groups; the unique-task summary even
when location grouping repeats a task; all 11 data fields and start-location
context; row detail tooltips; and double-click navigation returning the exact
start time, task ID and selected finish or start location. Group headings
remain non-jumpable. Keep Close visible and verify long names, many rows,
1024/1420/1600 logical widths and 100%, 150% and 200% display scaling.

The current Filter placeholder also promises start-location matching, but
`_row_text()` omits `start_location`. Resolve that mismatch during the UI
revision so the displayed search guidance matches the actual results.

## 18. Location inventory spaces (read-only) — Option B selected

The user selected Option B on 4 October 2026. Use responsive full-detail
cards for each inventory space, retaining every read-only value and Close.
The production dialog has not been changed yet.

`LocationInventorySpacesDialog` in `amr_sim_visualiser_pyside6.py` is the
read-only inventory-space viewer for one location. It is distinct from the
inventory-space configuration editors in `dialogs.py`. Current captures:
[800 × 500](captures/inventory-spaces-800.png), [1080 ×
460](captures/inventory-spaces-1080.png), and [1440 ×
720](captures/inventory-spaces-1440.png). The table has ten columns; Task,
Reserved by and Points require horizontal scrolling at compact sizes, and
Points is still mostly beyond view at the default 1080-pixel width.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full table and selected-space detail | Option B — responsive full-detail cards |
| --- | --- | --- |
| 800 × 500 | [A](revisions/inventory-spaces-A-800.png) | [B](revisions/inventory-spaces-B-800.png) |
| 1080 × 460 | [A](revisions/inventory-spaces-A-1080.png) | [B](revisions/inventory-spaces-B-1080.png) |
| 1440 × 720 | [A](revisions/inventory-spaces-A-1440.png) | [B](revisions/inventory-spaces-B-1440.png) |

**Option A** retains the ten-column table and its horizontal scrolling, with
a compact selected-space detail grid below. It supports row comparison and
keeps full values accessible without scrolling sideways for the selected row.

**Option B** presents each space in a card with dimensions, flexibility,
occupancy, payload, task, reservation and points. Cards flow one across at
800 pixels, two across at 1080, and three across at 1440. All values for a
space are visible together, while many spaces require vertical scrolling.

Preserve the location name and count, space name, separate length/width/height
values in metres, flexible and occupied states, payload, task, reserved-by
task and points. Missing values still display as `-`. This remains read-only
with Close visible. Verify long names, no spaces, many spaces, compact/wide
windows, and 100%, 150% and 200% display scaling after implementation.

## 19. Maximum payload-space utilisation — Option B selected

The user selected Option B on 4 October 2026. Use responsive full-detail
cards for each payload space while retaining the peak summary and complete
calculation explanation. The production dialog has not been changed yet.

`PayloadSpaceMaximumUtilisationDialog` in `amr_sim_visualiser_pyside6.py`
shows peak location occupancy and a read-only per-space history. Current
captures: [900 × 560](captures/payload-utilisation-900.png), [1120 ×
500](captures/payload-utilisation-1120.png), and [1440 ×
720](captures/payload-utilisation-1440.png). At 900 logical pixels the last
columns require horizontal scrolling. The existing summary and explanation
span several lines before the table.

Revision images (nonfunctional concepts in the established style):

| View | Option A — comparison table and selected detail | Option B — responsive full-detail cards |
| --- | --- | --- |
| 900 × 560 | [A](revisions/payload-utilisation-A-900.png) | [B](revisions/payload-utilisation-B-900.png) |
| 1120 × 500 | [A](revisions/payload-utilisation-A-1120.png) | [B](revisions/payload-utilisation-B-1120.png) |
| 1440 × 720 | [A](revisions/payload-utilisation-A-1440.png) | [B](revisions/payload-utilisation-B-1440.png) |

**Option A** keeps all eight columns in a table for comparing spaces and
adds a selected-space detail grid for reading values without horizontal
scrolling. The table uses horizontal scrolling at compact widths and vertical
scrolling when many rows are present.

**Option B** presents all eight values in a card for each space. Cards flow
one across at 900 pixels, two across at 1120, and three across at 1440.
It removes horizontal scrolling, while comparing many spaces may require
vertical scrolling.

Both retain the location, maximum occupied/configured count, maximum
utilisation percentage, peak time, simulation horizon, overflow at peak,
complete reconstruction explanation and assignment note. Per-space fields
remain payload-space name, ever occupied, payload entries, occupied duration,
time utilisation percentage, first occupied, last released and occupied at
peak. Missing values show `-`. Keep the view read-only with Close visible.
Verify long names, no spaces, many spaces, compact/wide windows, and 100%,
150% and 200% display scaling after implementation.

## 20. AMR Payload Monitor — Option A selected

The user selected Option A on 4 October 2026. Keep the full comparison
table with a selected-AMR detail area. The production dialog has not been
changed yet.

`AmrPayloadMonitorDialog` in `amr_sim_visualiser_pyside6.py` is a live,
read-only monitor at the current simulation time. Current captures:
[900 × 540](captures/amr-payload-monitor-900.png), [1320 ×
520](captures/amr-payload-monitor-1320.png), and [1600 ×
720](captures/amr-payload-monitor-1600.png). The present 11-column table
requires horizontal scrolling at 900 and its default 1320 logical pixels;
long payload and location values are clipped within cells.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full comparison table and selected detail | Option B — responsive full-detail AMR cards |
| --- | --- | --- |
| 900 × 540 | [A](revisions/amr-payload-monitor-A-900.png) | [B](revisions/amr-payload-monitor-B-900.png) |
| 1320 × 520 | [A](revisions/amr-payload-monitor-A-1320.png) | [B](revisions/amr-payload-monitor-B-1320.png) |
| 1600 × 720 | [A](revisions/amr-payload-monitor-A-1600.png) | [B](revisions/amr-payload-monitor-B-1600.png) |

**Option A** retains all 11 columns for comparing AMRs and adds complete
selected-AMR details below the table. The table still scrolls horizontally
at compact widths, but a selected row's long values remain readable below.

**Option B** puts all 11 values for each AMR in a card. Cards flow one across
at 900 pixels, two across at 1320, and three across at 1600. There is no
horizontal scrolling, though many AMRs require vertical scrolling and
comparison across cards is slower.

Preserve live time, AMR count and payloads-onboard total. Per-AMR fields are
ID, payloads onboard, payload count, slots, task IDs, status, segment type,
from and to locations, floor, and updated time. Missing values display `-`;
zero counts remain zero. The monitor stays nonmodal, read-only, updates as
playback changes, preserves the selected AMR on refresh when possible, and
has Close. Retain a useful empty/no-simulation state. Verify long lists and
values, compact/wide windows, and 100%, 150% and 200% display scaling after
implementation.

## 21. Lift Monitor — Option B selected

The user selected Option B on 4 October 2026. Use a scrollable lift list
with a larger shaft and full details for the selected lift. The production
dialog has not been changed yet.

`LiftMonitorDialog` in `amr_sim_visualiser_pyside6.py` is the separate live
lift window. Current captures with four lifts: [700 ×
520](captures/lift-monitor-700.png), [980 ×
520](captures/lift-monitor-980.png), and [1400 ×
700](captures/lift-monitor-1400.png). Its dark shaft panels are useful, but
every lift is placed in one horizontal row, with no reflow or local scroll.
The current window has no in-dialog Close control.

Revision images (nonfunctional concepts in the established style):

| View | Option A — responsive lift panels | Option B — lift list and selected detail |
| --- | --- | --- |
| 700 × 520 | [A](revisions/lift-monitor-A-700.png) | [B](revisions/lift-monitor-B-700.png) |
| 980 × 520 | [A](revisions/lift-monitor-A-980.png) | [B](revisions/lift-monitor-B-980.png) |
| 1400 × 700 | [A](revisions/lift-monitor-A-1400.png) | [B](revisions/lift-monitor-B-1400.png) |

**Option A** keeps all shaft diagrams visible in a responsive grid, with
served floors, exact position, occupant and waiting queue beside each one.
The grid is two across at 700 and 980 pixels, and four across at 1400;
additional lifts use vertical scrolling.

**Option B** keeps a compact, scrollable lift list on the left and a larger
shaft diagram and complete waiting queue for the selected lift on the right.
It makes one lift easier to inspect at narrow widths, but switching between
lifts is necessary to see all shafts.

Preserve lift ID, served floors, fractional current floor, occupant and
waiting AMR IDs, including `-` when empty. Keep live updates during playback,
existing throttling so the main map stays responsive, nonmodal window
behavior, and the no-lifts message when no lifts are configured. A visible
Close action is included in both revisions. Verify one lift, many lifts,
long IDs and queues, compact/wide windows, and 100%, 150% and 200% display
scaling after implementation.

## 22. Failed Tasks — Option B selected

The user selected Option B on 4 October 2026. Use a compact failed-task
list with a complete selected-task detail area and equivalent sorting.
The production dialog has not been changed yet.

`FailedTasksDialog` in `amr_sim_visualiser_pyside6.py` is the failed-task
browser for a loaded simulation. Current captures: [1000 ×
600](captures/failed-tasks-1000.png) and [1600 ×
720](captures/failed-tasks-1600.png). Its nine-column table needs horizontal
scrolling at both widths; the Failure reason text is truncated even at the
default 1600-pixel width.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full table and selected detail | Option B — task list and full detail |
| --- | --- | --- |
| 1000 × 600 | [A](revisions/failed-tasks-A-1000.png) | [B](revisions/failed-tasks-B-1000.png) |
| 1400 × 700 | [A](revisions/failed-tasks-A-1400.png) | [B](revisions/failed-tasks-B-1400.png) |
| 1600 × 720 | [A](revisions/failed-tasks-A-1600.png) | [B](revisions/failed-tasks-B-1600.png) |

**Option A** retains the sortable nine-column table and adds complete
selected-task details below, including the full failure reason. It supports
scanning across tasks, but the table still scrolls horizontally.

**Option B** gives each failed task a compact entry with task ID, failure
time and destination. Selecting one shows all nine fields and the complete
reason in a scrollable detail area. A Sort by control and direction control
retain sorting on every field; comparing other fields across failures
requires selection.

Preserve the failed-task count; case-insensitive filtering across all nine
fields; sorting by each field in both directions; failed-at time, task ID,
payload, final destination, AMR drop-off zone, pickup, department, AMR and
failure reason. Missing values display `-`. Keep View at destination enabled
only for a selection, double-click navigation, and Close. Navigation must
still seek to the exact failure time, focus the best available destination,
and open that location's inventory payloads when found. Verify long failure
reasons, no matches, many failures, compact/wide windows, and 100%, 150%
and 200% display scaling after implementation.

## 23. Location inventory payloads (read-only) — Option B selected

The user selected Option B on 4 October 2026. Use a space list with a
complete selected-space detail area, including the current tooltip content.
The production dialog has not been changed yet.

The active `LocationInventoryPayloadDialog` is the later definition in
`amr_sim_visualiser_pyside6.py` (near line 2883); the earlier same-named
definition is shadowed and must not be revised separately. The active
`show_location_inventory_payloads` method is also the later definition.
Current captures: [900 × 520](captures/inventory-payloads-900.png), [1420 ×
520](captures/inventory-payloads-1420.png), and [1600 ×
800](captures/inventory-payloads-1600.png). At 900 logical pixels the final
columns need horizontal scrolling. At the default 1420 width they fit,
but long source values truncate. Extensive payload information exists only
in row tooltips.

Revision images (nonfunctional concepts in the established style):

| View | Option A — full table and selected detail | Option B — space list and full detail |
| --- | --- | --- |
| 900 × 520 | [A](revisions/inventory-payloads-A-900.png) | [B](revisions/inventory-payloads-B-900.png) |
| 1420 × 520 | [A](revisions/inventory-payloads-A-1420.png) | [B](revisions/inventory-payloads-B-1420.png) |
| 1600 × 800 | [A](revisions/inventory-payloads-A-1600.png) | [B](revisions/inventory-payloads-B-1600.png) |

**Option A** retains the nine-column comparison table and adds a compact
selected-space detail panel, including the complete current tooltip text
in a locally scrollable read-only area. The table still needs horizontal
scrolling at compact widths.

**Option B** lists inventory spaces with their status and current payload.
The selected space's nine fields and complete tooltip details appear beside
the list in one vertically scrollable detail area. It avoids horizontal
scrolling, but comparing multiple spaces requires selection.

Preserve location name, current playback time, row count, inventory space,
current payload, waste stream, container group, task, AMR, status, updated
time and source. Preserve every existing tooltip line, including payload
dimensions, weight, waste volume and percentage, threshold, fill rate,
instance ID, and repeated context when present. Missing values display `-`.
This remains a read-only snapshot at the selected playback time with Close;
retain empty-space and capacity-overflow rows and the existing no-data
behavior. Verify long values, many spaces, compact/wide windows, and 100%,
150% and 200% display scaling after implementation.

## 24. DXF loading progress — Option A selected

The user selected Option A on 4 October 2026. Keep the compact grouped
progress presentation and accurate processed-count wording. The production
dialog has not been changed yet.

`DXFLoadingDialog` in `visualiser/app.py` is the application-modal progress
window shown while a batch of mapped DXF files loads. Current intermediate
captures: [420 pixels wide](captures/dxf-loading-420.png) and [720 pixels
wide](captures/dxf-loading-720.png), both at 2 of 4 processed with one
failure. The dialog receives only the progress count, total, status message
and failure count. The current `loaded` label counts completed files,
including failures; the revisions call this count `processed` for clarity.

Revision images (nonfunctional concepts in the established style):

| Width | Option A — compact progress | Option B — batch overview |
| --- | --- | --- |
| 420 | [A](revisions/dxf-loading-A-420.png) | [B](revisions/dxf-loading-B-420.png) |
| 720 | [A](revisions/dxf-loading-A-720.png) | [B](revisions/dxf-loading-B-720.png) |

**Option A** keeps one compact progress group with the live message, bar,
processed fraction and failure count. It occupies less screen space.

**Option B** gives processed, remaining and failed counts separate labelled
areas under the same progress bar. At compact width the figures reflow into
two rows; at wider width they sit in one row.

Preserve the exact progress range/value, current status message, processed
and failed counts, application modality, and automatic close when every
file has been processed. Do not imply that a failure can be cancelled from
this dialog or add per-file detail not passed by the loading workflow.
Keep the window readable at 100%, 150% and 200% display scaling.
