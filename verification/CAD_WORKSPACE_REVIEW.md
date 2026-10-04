# Production CAD workspace and interaction checkpoint

The latest user request makes UI features and interactions the current priority.
This checkpoint implements the confirmed graph-focused workbench conventions in
the production PySide6 application. The full UI roadmap and core engineering gates
remain open. The full tutorial and illustrated guide follow the delivered UI.

## Try the implemented workflow

1. Open a reference project or LTN in the normal editor. The compact toolbar and
   project tree leave most of the window for the graph. Properties and the full
   tool tabs start collapsed. **More tools** restores the existing advanced tools.
2. Choose **Corridor**. Click successive endpoints, or enter `X,Y` in metres.
   Once a start exists, enter `@10,0` for a ten-metre eastward segment or `@10<90`
   for ten metres north. Angles use degrees, zero east and ninety north.
3. Inspect the endpoint preview and length/angle feedback before pressing Enter.
   Typed input bypasses grid and three-decimal rounding. Existing point and edge
   snaps still apply and are explicitly shown; edge snaps split the old corridor
   with its attributes and applicable references preserved. Invalid input remains
   in the field with an inline explanation and makes no project edit.
4. Press blank Enter or Escape to finish. Escape clears the uncommitted draft;
   placed steps remain separately undoable. Changing stage disables the drawing
   input so a hidden command cannot edit the layout from Configuration or Check.
5. Choose **Select**. Drag empty space left-to-right to enclose objects completely,
   or right-to-left to select objects touched. Solid/dashed rectangles also name
   the rule. Shift or Ctrl toggles selection. Escape during a selection drag
   restores the preceding selection. Labels and underlays are not graph objects.
6. Click **Properties** to edit the highlighted object. Selection itself never
   expands this panel. Apply an edit, undo and redo it, then save/reopen the
   `.amrproj`. **Focus canvas** temporarily hides supporting panels and restores
   their previous state. Hidden property drafts remain pending and recoverable.

Floor and Snap controls share the existing state. Snap also remains accessible
through toolbar overflow and More tools. These view controls do not create project
revisions or stale previously current checks. Panel state is retained in this
window; persistence across restarts is outside this checkpoint.

## Evidence

Full isolated checkpoint on 4 October 2026, after the rectangle and object-snap
increments: **1,927/1,927 tests passed** across 167 modules, zero broken evidence
links, and source unchanged throughout execution (380.095 seconds). The pack is
`verification/latest/cad-snaps-verified/index.html`, with machine-readable evidence
and the tested source archive beside it. Tested HEAD was `aa0a82a`; the snapshot
also includes the preserved local simulator/LTN changes and local LTN regression
tests, so this is not a clean-checkout claim. The inventory still identifies 267
options needing semantic review. Full-suite success does not close that audit,
human acceptance, the operating-workload benchmark or remaining roadmap features.

The next confirmed workflow gap is simulation-time editing: `ProjectRunsPanel`
blocks starting a second run and document switching, but layout/configuration
mutators do not yet share a running-project lock. The agreed requirement is to
lock project editing while simulation runs, while retaining investigation and
view navigation. This remains open after this regression checkpoint.

Verification on 3 October 2026: **1,805/1,805 tests passed**, including 38 new
CAD/workflow cases; zero broken evidence links. The pack confirmed its source
remained unchanged during execution (167.25 seconds including pack generation).
The shortened LTN regression ran twice: four completed tasks, zero failures and
zero pending, with identical outcomes to the preceding checkpoint. Its final
simulation time was 7,928.480894 seconds; assigned work may drain beyond the
one-hour demand horizon. This is regression evidence, not independent numerical
validation of the full LTN project.

Acceptance modules: `test_cad_workspace`, `test_cad_selection`,
`test_cad_drawing_input` and `test_cad_workflow_acceptance`.
They exercise real Qt mouse/key events, geometry at different zooms, large text
and small windows, pending drafts, mode/stage changes, per-operation undo and
portable save/reopen. Independent expectations include two ten-metre segments
and a moved endpoint producing a segment of length `sqrt(104)` metres.

Actual application captures (regenerate locally alongside the evidence pack):

- [LTN drawing workspace](latest/cad-workspace-ltn.png)
- [Typed drawing preview](latest/cad-workspace-drawing.png)
- [Explicit contextual properties](latest/cad-workspace-properties.png)
- [Latest verification pack](latest/index.html)

## Remaining UI work

### Intersection snapping, 4 October 2026

**More tools → Edit → Drawing behaviour → Intersections (connect junction)**
explicitly joins corridors at a nearby intersection. The preview says **Connect
intersection**; clicking or submitting the typed point splits all corridors through
that point and creates one shared identity, or reuses the unique existing point.
Existing doors retain their width restriction. T-junctions and multi-way crossings
are supported. The operation is one undoable edit and preserves directed corridor
attributes, distance overrides and applicable profile/resource references through
the existing subdivision transaction. Standalone node and door placement use the
same target. Merely drawing across a corridor still does not insert a junction.

The existing 0.45 m attraction tolerance and direction constraints apply. Distant
segments are removed before intersection pairs are tested; duplicate directed edge
records share one physical segment. Ambiguous or near-coincident point identities
are rejected without mutation. Parallel segments alone have no unique intersection.

118 focused CAD tests pass. References cover independent crossing coordinates and
distance partitions, profile preservation, three-way crossings, existing doors,
T-junctions, repeated placement, invalid identities, floors, tolerance, constraints,
anchor connection, production door placement and undo. A 10,000-distant-corridor
case verifies only the two local segments enter pair search; this is algorithmic
evidence, not an LTN runtime benchmark. Automatic insertion at crossings along a
new route and human workflow acceptance remain open.

### Selectable object snaps, 4 October 2026

Under **More tools → Edit → Drawing behaviour**, the object target selector offers
the existing nearest point/edge behaviour, endpoints/graph points, or corridor
midpoints. It applies to corridor drawing, standalone nodes and doors. Switching
the selector refreshes typed previews without changing project data. Object snap
off disables attraction and the selector; exact overlaps still reuse points or
split edges to preserve topology. The existing 0.45 m attraction tolerance applies.
Midpoint feedback explicitly identifies the split, and direction constraints still
take precedence. These are session editing preferences.

98 focused tests passed, covering independent diagonal midpoint geometry, endpoint
attraction, tolerance/floor boundaries, exact overlap, constrained direction,
preview/commit parity, door and node placement, and atomic undo. Perpendicular and
intersection snap choices remain open; explicit crossing-junction creation remains
available separately. Human workflow approval and the full release gate remain open.

Perpendicular snapping is now available as **Perpendicular from route end**.
It projects the current route endpoint onto a finite corridor within the existing
cursor attraction tolerance; it never extends a corridor beyond its endpoints.
At a projected endpoint it reuses that point, otherwise placement splits the
corridor with the existing transaction. Without a route start there is no
perpendicular attraction, and feedback explains the missing anchor. This also
means standalone nodes and doors have no perpendicular anchor. Exact overlaps
still preserve topology. Orthogonal/polar constraints take precedence; typed
coordinates retain their documented constraint override.

101 focused CAD tests pass, including independent diagonal projections, endpoint
reuse, out-of-range/zero-length projections, finite anchors, compatible/conflicting
direction constraints, typed preview parity and undo. Intersection snapping and
automatic crossing insertion remain open. The full verification pack has not been
rerun for this increment.

### Rectangular location boundaries, 4 October 2026

Right-click a location in Select mode and choose **Draw rectangular boundary**.
Click the first corner and then the opposite corner. A dashed outline displays
width and height in metres before placement; the existing boundary remains saved
until the second valid corner applies the replacement. Grid spacing controls the
corners. The alternative **Draw rectangular location boundary** placement mode
first asks the user to select the location. Existing polygon tools remain available.

Escape/right-click cancels; mode, floor or workspace changes discard the draft.
Zero-width/height rectangles are rejected, and a location changed during drawing
must be selected again. Completion is one undoable edit and stores the footprint
relative to the location so later movement carries it. Preview updates only the
canvas overlay and does not rebuild drawing underlays.

The inline rectangle bar also accepts `width,height` or `width,height,angle`.
Dimensions are metres; rotation is counterclockwise degrees from east, defaulting
to zero. The preview is centred on the location anchor and exact dimensions bypass
grid snapping. Choose **Apply dimensions** or press Enter to commit; clear the
entry to return to two-corner drawing. Invalid dimensions disable Apply and explain
the problem inline. The bar appears only during this command.

127 focused tests passed across rectangle geometry, drafting, selection, drawing,
properties, workspace and history. References cover opposite corner ordering,
invalid coordinates, nonmutating preview, replacement cancellation, stale input,
grid placement, relative storage and undo/redo. Independent rotated references
check known corner coordinates, centre and area. Clearing numerical input restores
corner placement, and stale input cannot overwrite a changed location. General
multi-object rotation, robot swept-footprint validation and human workflow
acceptance remain open. The full-suite baseline predates this increment.

### Existing-point and T-junction checkpoint, 4 October 2026

**Create junction at crossing** now reuses a unique graph point exactly at the
intersection, including an existing door, location or lift stop. Its name,
attributes and existing references remain intact. T-junctions reuse the branch
endpoint and split only the through corridor. Already connected endpoints produce
no edit. Multiple coincident identities, department markers and merely nearby
points are rejected explicitly rather than merged or moved. Two selected links
on the active floor remain required; automatic crossing insertion is unchanged.

Eighty-eight focused tests passed. New references verify reuse of a 0.7 m door
(0.8 m passage rejected, 0.6 m allowed), untouched branch metadata in a T-junction,
retained one-way restrictions, ambiguous-point rejection, reused selection identity
and atomic undo/redo. Full-suite evidence remains the earlier baseline.

### Explicit crossing junction checkpoint, 4 October 2026

Select two crossing corridors, then use **Create junction at crossing** in the
right-click menu, or **More tools → Edit → Corridor sections → Create crossing
junction**. One new shared node replaces the crossing, splitting both physical
links and their explicit reverse records. Widths, directions, proportional
distance overrides, and profile/resource references use the existing subdivision
rules. Creating the junction connects the graph; profile restrictions still apply
to each branch. The entire operation is one undoable edit.

The original checkpoint supported two interior crossings; the extension above
also handles existing points and T-junctions. Parallel/overlapping links, missing
links and nonfinite geometry remain rejected atomically. Drawings remain underlays, and line crossings
are not automatically connected. Traffic reservation and congestion timing can
change when a physical link gains sections, as with ordinary subdivision.

Eighty-four focused geometry, routing, selection and subdivision tests passed.
References verify the independent crossing at (4, 0), preserved 8+12 m and 9+21 m
distance overrides, one-way routing, separate reverse-edge attributes, clean-profile
exclusion of the dirty branch, rejection and undo/redo. The prior full pack remains
the baseline; it was not rerun for this checkpoint. Automatic multi-crossing
insertion remains open; existing-point joining is covered by the extension above.

### Numerical movement checkpoint, 4 October 2026

**Edit → Move selected by…**, the selection's right-click menu, and **Ctrl+M**
with canvas focus open an inline displacement bar. Enter `dx,dy` in metres or
`@distance<angle` (degrees, east zero, north 90). The preview names affected
active-floor points, includes selected corridor endpoints once each, and shows
the signed translation before Apply. The graph is not changed by editing the
draft. Apply performs one atomic, undoable move preserving topology and relative
geometry; typed distances bypass grid/direction constraints. Escape/Cancel hides
the draft without mutation. Floor, mode or workspace changes hide the bar.
Selection changes refresh its preview; zero/invalid inputs cannot be applied.

Ninety-two focused CAD and workspace tests passed. The broader discovery run
started before this checkpoint did not return a result and was interrupted after
checks found unchanged process CPU time and no completion output. Its retained
output is `latest/cad-broad-regression.txt`; it is not a passing full-suite result.
Full-suite diagnosis and human workflow acceptance remain open. Rotation, copying
and scaling are not implemented by this displacement command.

### Group movement checkpoint, 4 October 2026

Use Select and Shift/window selection to choose objects, then drag a selected
point or corridor line to translate the group. Selected corridor endpoints move
with selected points, once each; unselected connecting corridors stretch between
their retained endpoint identities. Only the active floor moves. Grid snapping
applies to the grab anchor, preserving relative offsets and existing coordinate
precision across the group. Location outlines remain relative to their location.
The selection survives the drag, and release records one undoable edit. Escape,
mode changes and floor changes cancel an in-progress move and restore the original
coordinates without creating a history entry. Movement reuses the existing
coalesced graph refresh, retaining drawing underlays.

Seventy focused selection/drawing/history/workflow tests passed, including new
references for line dragging, mixed point/corridor selection, floor isolation,
room shape and fractional offsets, cancellation, undo and redo. Rotation, scaling,
copying remain separate open transform requirements; typed displacement is now
available through the numerical movement checkpoint above.
No full-suite or human visual acceptance is claimed for this checkpoint.

### Direction constraints checkpoint, 4 October 2026

The corridor coordinate bar now offers **Free direction**, **Orthogonal (90°)**,
and **Polar 45° / 30° / 15°**. The first point is unconstrained; subsequent mouse
placements project onto the nearest permitted direction from the current route
end. Grid rounding applies before direction projection. Object attraction is
accepted only if it preserves that direction; an exact corridor intersection
still splits the corridor using the existing attribute-preserving operation.
Typed coordinates explicitly bypass grid and direction constraints, with that
override stated in feedback. Changing controls invalidates the old preview.
Free direction remains the default, and the selector is confined to the existing
corridor input bar rather than adding another permanent side panel.

Ninety-three focused CAD tests passed. Independent references cover horizontal,
vertical and diagonal projection, off-grid anchors, exact typed coordinates,
nearby object rejection, aligned object reuse, edge splitting, preview/placement
parity and undo/redo. Human workflow acceptance remains open. These controls do
not introduce curved edges, robot turning geometry or multi-object transforms.

### Snapping checkpoint, 4 October 2026

The drawing toolbar now separates **Grid snap** from **Object snap**. Under
**More tools → Edit → Drawing behaviour**, grid spacing is adjustable from
0.001 to 1000 metres (default 1 metre). These are session editing controls, not
simulation inputs. Grid display remains adaptive to zoom and independent of the
placement grid. Corridor, standalone node and door placement share the same
target resolution. Typed coordinates bypass grid rounding while respecting the
object-snap choice; changing that choice refreshes the typed preview. Turning
object snap off disables nearby attraction, but an exact overlap still reuses a
point or splits a corridor to avoid duplicate topology. Defaults retain previous
snapping behaviour. Placement remains undoable and split attributes/references
use the existing atomic subdivision implementation.

Ninety focused CAD tests passed, including independent grid arithmetic, exact
input, invalid spacing, object attraction, undo/redo and existing drawing, door,
workspace and deletion workflows. The full verification pack and human visual
acceptance have not been rerun for this checkpoint. Separate endpoint/midpoint
perpendicular/intersection snap choices and automatic crossing junctions remain
open; this checkpoint does not claim those capabilities.

This is working interaction infrastructure, not the final A2 appearance. The map
still uses its existing dark palette and legend; dense LTN labels need better
display controls. Remaining snap types, full
location/door footprint drawing, arcs/fillets and multi-object transforms remain.
Layers, run-time editing locks, complete keyboard and custom-rendering
accessibility, numerical engineering input authoring and advanced dialog rework
also remain. Confirm additional material workflows with the user as required by
the roadmap. Nothing in this checkpoint completes traffic or manoeuvre validation.
