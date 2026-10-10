# Explicit trajectories and drawable workbench — first geometry checkpoint

Run `.\.venv\Scripts\python.exe -m visualiser.geometry_workbench` from the repository.
This is an executable geometry/CAD workflow prototype for review. It does not
replace the main editor or enable a new simulation mode. The graph dominates;
properties and the reference tutorial are hidden until opened. This demonstrates
interactions for the pending workflow approval without claiming the complete A2
application shell has been delivered.

## Implemented

- Analytic straight and circular-arc motions, minimum radius retained exactly,
  tangent headings, explicit stationary pivots with configured angular speed.
- Infeasible requested turns fail explicitly. A permitted pivot is recorded as a
  pivot with rotation time and zero translational distance; it is not disguised
  as a curved route. No automatic obstacle avoidance or straight-path fallback.
- Centred loaded rectangular footprints with optional clearance. Straight sweeps
  use exact convex hulls; curved/pivot sweeps use conservative recursive bounds
  on continuous corner motion. Sampled clear poses alone cannot establish safety.
- Separate collision, unresolved clearance, search-budget and invalid-input
  outcomes. Requested-route infeasibility does not prove all alternative routes
  infeasible. Numerical contact tolerance is 1e-10 m; coordinates/footprints are
  bounded to ±1e9 m. Default clearance resolution is 0.001 m, 50000 check budget.
- Route and rectangular-obstacle drawing, typed coordinates, 0.25 m snapping,
  Shift orthogonal placement, Enter finish, Escape draft cancellation, wheel zoom,
  pan, fit, and one undo/redo command per completed edit. Parameter changes undo.
- Atomic separate study JSON saves, recomputed evidence on reopen, retention of
  infeasible studies, failed import without replacing the current study.
- A runnable reference tutorial and an illustrated two-page prototype chapter,
  with editable builder and screenshots of the actual Qt workbench under
  `docs/geometry-workbench/`. PDF output: `output/pdf/geometry-workbench-guide.pdf`.

## Independent references

The default route is (0,0) → (6,0) → (6,6), radius 2 m. Two 4 m straights and a
quarter-circle give 8 + π = 11.141592653589793 m, and the same seconds at 1 m/s.
The 1.10 m opening admits a 0.90 m load with 0.05 m clearance each side; 1.01 m
load width fails. A shorter (0,0) → (1,0) → (1,1) request cannot fit radius 2 m.
With pivots explicitly allowed, travel is 2 m and a 90° pivot takes 2 s at 45°/s:
4 s total at 1 m/s. A 3–4–5 straight takes 2.5 s at 2 m/s.

Tests also cover clockwise mirroring, adjacent fillet overlap, U-turn permission,
thin walls between endpoints, rotating corners, just-fit/just-fail passage,
unresolved conservative bounds, search limits, serialized exact geometry and
actual Qt editing/save/cancel/undo workflows.

The final full verification pack passed **1,397/1,397 tests in 146.275 seconds**,
with no broken evidence links and source unchanged during testing. Geometry has
13 analytic/clearance and eight Qt workflow tests; the combined focused set with
run controls passed 31 tests. Both pages of the generated PDF were rendered and
visually inspected. Screenshots come from the running Qt widgets.

The repeated one-hour LTN smoke check retained four completed tasks, zero failed
and zero pending, with unchanged input/source and identical outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Initialisation took 1.393317/1.456897 s; total time 1.755119/1.818467 s. Assigned
work drains beyond the demand horizon. This confirms legacy regression behaviour,
not full LTN validation or geometric traffic integration.

## What remains

This geometry engine is not yet connected to simulator route timing, reservation
transactions, energy or saved playback. The production simulator retains legacy
behaviour. Endpoint headings follow path tangents; robot/load footprints share a
centre and do not model offset loads or articulated vehicles. Display footprints
are illustrations of the same motion model; certification uses conservative
continuous bounds, not only displayed samples. Drawings are not collision walls.

Next: integrate the explicit model with simulator and recorded trajectories in an
opt-in versioned mode; then directional lanes, narrow passages and junction
conflicts, reversing and multi-point planning. Add project/editor controls after
workflow review. The approved A2 visual direction remains; complete application
workflows, accessibility, the full tutorial/LTN example and final guide remain
open. This prototype chapter is not the completed application user guide.
