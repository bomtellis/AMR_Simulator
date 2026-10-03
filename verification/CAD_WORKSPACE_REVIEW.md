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

This is working interaction infrastructure, not the final A2 appearance. The map
still uses its existing dark palette and legend; dense LTN labels need better
display controls. Selectable snap types, orthogonal/polar constraints, full
location/door footprint drawing, arcs/fillets and multi-object transforms remain.
Layers, run-time editing locks, complete keyboard and custom-rendering
accessibility, numerical engineering input authoring and advanced dialog rework
also remain. Confirm additional material workflows with the user as required by
the roadmap. Nothing in this checkpoint completes traffic or manoeuvre validation.
