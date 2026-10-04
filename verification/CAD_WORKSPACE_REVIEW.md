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
snap choices and automatic crossing junctions remain
open; this checkpoint does not claim those capabilities.

This is working interaction infrastructure, not the final A2 appearance. The map
still uses its existing dark palette and legend; dense LTN labels need better
display controls. Selectable snap types, full
location/door footprint drawing, arcs/fillets and multi-object transforms remain.
Layers, run-time editing locks, complete keyboard and custom-rendering
accessibility, numerical engineering input authoring and advanced dialog rework
also remain. Confirm additional material workflows with the user as required by
the roadmap. Nothing in this checkpoint completes traffic or manoeuvre validation.
