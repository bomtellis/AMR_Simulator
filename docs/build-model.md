---
title: Build a model
nav_order: 4
has_children: true
permalink: /build-model/
---
# Build a model

## Create and preserve the project

Choose **File → New project** (`Ctrl+N`). Set the number of floors and the shared
level height in metres, then optionally assign a DXF or PDF to each floor. Floors
start at 0; floors remain available in Layout even without drawings.

Use **File → Save project as** (`Ctrl+Shift+S`) to save a portable `.amrproj`.
Fresh projects use this format by default; an opened JSON retains JSON saves until
you convert it. The portable archive stores configuration, deduplicated drawings
and saved revisions. **Simulation logs and reports remain external**.

Keep your project and its results folder when moving or sharing a study. Use
**Project revisions** to compare or restore saved configurations; restoring
preserves current edits in history. Use **Undo/Redo** for completed edits, and
save after reviewing them. Draft dialogs have their own Save/Cancel behaviour.
Automatic recovery copies help recover interrupted editing, but are not a backup
of your complete study and external runs.

## Import and check floor drawings

In Layout select the floor, or right-click its tree entry and use **Add DXF**.
PDF underlays use their page, scale and alignment settings. Fit the view and
measure a known distance before drawing routes. Model coordinates and lengths
are in **metres**. A building drawing in millimetres needs correct scaling.

Use **View → DXF layers** to control the drawing background. Use **View → Model
layers** for model assignment, visibility, locks and drawing style. Visibility
and layer names do not grant route permission.

To change vertical distances later, choose **Configuration → Building settings**,
edit **Level height**, then Save. This applies to all adjacent levels and
preserves effective lift speed in metres per second while recalculating floors
per second. Save the project and rerun checks.

## Draw the travel network

1. Place meaningful locations and corridor nodes at endpoints, junctions and turns.
2. Choose **Corridor** to connect routes while creating nodes, or **Edge** to
   connect two existing graph points. Connect every pickup, dropoff, start,
   charging, wash and lift access point needed by the study.
3. Use **More tools → Edit → Drawing behaviour** for **Bidirectional edges** and
   **Chain edge creation**. Direction is part of the route model.
4. Select **End**, **Mid**, **Perp**, **Cross** or **Near** in the Object snap
   controls. Grid snap is separate. Finish or cancel the current drawing command
   before switching tasks; the first exercise uses blank Enter to finish a corridor.
5. Inspect Properties for widths, doors and other constraints. Review graph
   connectivity rather than relying on lines that merely look joined.

Left-to-right selection windows enclose objects; right-to-left windows select
touched objects. Shift or Ctrl modifies a selection. Selection alone does not
open Properties. Undo/Redo applies to each completed drawing edit.

In Simple mode, drawings provide the background and the graph defines travel.
Detailed geometry requires additional explicit physical inputs; importing CAD
alone does not establish collision-safe movement.

## Add departments and routes

The Layout **Department** tool places or edits a department marker. Its menu
opens **Manage departments…**; the full editor is also under
**Configuration → Departments**. Assign each workflow's pickup and delivery
locations on the correct floor and save both the department dialog and list.

Use **Configuration → Route profiles** to define allowed nodes, directed edges
and lifts for clean, dirty or other flows. Validate outbound, return and empty
robot travel separately; displaying two differently coloured flows is not proof
of operational separation.

Read [routes and constraints](user-guide/04-routes-and-constraints.md) and
[department settings](user-guide/05-adding-departments.md), then use
[Project checks](check-simulate.md) to find disconnected or invalid inputs.

## Learn with a complete example

The [building flow tutorial](building-tutorial/Building-Flow-Tutorial.md) guides
you through a three-floor, 40 × 20 m per-floor example, including robots, payloads,
charging, washing, demand, lift access and a comparison study.

Download its [floor 0](building-tutorial/floor-0.dxf),
[floor 1](building-tutorial/floor-1.dxf) and
[floor 2](building-tutorial/floor-2.dxf) drawings. Import these separately;
the [side-by-side drawing](building-tutorial/building-three-floors.dxf) is for
presentation, not per-floor import. Generate portable starter/checkpoint archives
using the instructions on the tutorial page rather than copying machine-specific
paths from a reference JSON.
