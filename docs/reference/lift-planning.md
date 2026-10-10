---
title: Lift planning studies
parent: Technical reference
nav_order: 3
---
# Lift planning studies

Use **Configuration → Plan lift locations** to compare geometrically screened
lift-site proposals against a saved baseline. The study retains its own sidecar
and frozen run evidence. Work from a saved copy of the project.

## Interpret the drawings first

1. In **Interpretation**, choose **Infer drawings**.
2. Review every floor and assign DXF layer **Planning role** values. Establish a
   closed building boundary, circulation, wall openings, retained facilities and
   prohibited areas. Missing circulation or an open/ambiguous boundary needs repair;
   the drawing's bounding box is not a building boundary.
3. Confirm metres versus millimetres and use **Align floor…** for offsets/rotation.
   Use **Exclude area…** for prohibited locations.
4. Tick **I reviewed units, boundaries, circulation, exclusions and floor alignment.**
   only after verifying the overlays.

Interpretation, registration and confirmation belong to the current drawing and
input revision. Later changes make a study stale; recheck before evaluation.

![Lift-planning drawing interpretation and floor review](../building-tutorial/images/interpretation.png)

## Generate and evaluate proposals

In **Proposals**, set **Shaft length**, **Shaft width**, **Landing depth** and
**Clearance**, all in metres. Initial teaching values are 2 m, 2 m, 1 m and
0.1 m respectively; use actual engineering requirements for an operational study.
Choose which existing lifts may move, then **Generate five layout proposals**.
Review floor overlays and any rejection explanation.

Choose **Evaluate scenarios**. Progress identifies the current layout/scenario;
use **Stop evaluation** to retain finished evidence and stop further work.
Reevaluation resumes verified finished runs and retries incomplete work.

Inspect **Scenarios** by department floor and flow. Use **Investigate run**,
**Playback run** and **Report run** for the selected saved evidence. **Locate
moved run…** accepts matching registered evidence; it does not substitute a new
run with different inputs.

![Lift-layout proposals and comparison controls](../building-tutorial/images/proposals.png)

## Save the alternative and its evidence

Use **Evidence → Export comparison CSV… / Export comparison PDF…** to retain
service, distance and waiting evidence. Review service guards and explanation,
not only the recommended row or distance reduction.

**Create design variant…** saves a separate project by default. **Apply selected
layout** is an explicit undoable change to the editable project and makes its
checks stale. Historical runs remain bound to their original inputs.

## Limits

Proposals keep lift count, equipment and flow permissions fixed. Relocating a
lift cannot add capacity or restore a route prohibited by the selected policy.
Washing applies to robots. Floor/flow service must remain acceptable; a shorter
horizontal route alone does not establish a better design.

Geometric screening is not a structural feasibility assessment. Review shafts,
landings, fire strategy, clinical constraints and real lift engineering outside
the simulator. The [building tutorial](../building-tutorial/Building-Flow-Tutorial.md)
provides a teaching exercise, not an operational design approval.
