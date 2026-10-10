# Location outline verification — slice 2AG

## Behaviour and fixes

Location outlines now share coordinate resolution and plan measurement between
the editor, reports and playback visibility. A complete local `dx`/`dy` pair
wins over a legacy absolute `x`/`y` pair at each point. Mixed representations
are supported. Import retains the supplied representation; explicit outline edits
store local offsets, retain point metadata and no longer round to millimetres.

The reference triangle at location `(100, 200)` has vertices `(100, 200)`,
`(104, 200)`, `(100, 203)`: its envelope is 4 m by 3 m and its area is
`4 × 3 / 2 = 6 m²`. Reports previously treated absolute vertices as zero local
offsets. Playback also added the location origin to absolute vertices a second
time, causing incorrect visibility selection. Both consumers now agree with the
editor. A translated shoelace calculation also fixes catastrophic cancellation:
the same 6 m² triangle at origin `(1e12, -1e12)` previously measured 67,108,864 m²
in the editor. These changes affect drawings and reported plan measurements,
not transport timing.

Shared input validation rejects malformed point containers, incomplete coordinate
pairs, effective boolean/nonfinite coordinates and overflowing conversions or
polygon metrics before editor import, simulation or Project Checks. Failed edits
leave the previous outline intact. Empty/missing outlines remain valid. Short
outlines are retained as legacy drawing data and have zero plan measurements.
An effective local pair takes precedence; unused absolute aliases are not interpreted.

## Model scope

Project Checks displays `LOCATION_OUTLINE_SCOPE` for nonempty outlines. They guide
drawing, storage arrangement and reported plan measurements. They are **not
simulation walls** and do not enforce room containment or swept-footprint clearance.
Storage arrangement uses an axis-aligned envelope and can extend outside a concave
outline. This checkpoint does not validate simple polygons, self-intersections,
repeated/collinear vertices, physical room area or access/turning clearance.

Local vertices follow a moved location; legacy absolute vertices remain fixed
until explicitly edited into local form. Floating-point representation and display
rounding remain. General inventory-space report reconciliation is a separate open
contract; this change corrects location outline measurements only.

## Verification evidence

Twelve new tests cover independent triangle measurements, large-origin arithmetic,
submillimetre JSON persistence, compressed project preservation, metadata, raw/editor
validation, atomic failed edits, precedence, location moves, drawing cancellation,
one-step undo/redo, standalone reporting and playback visibility. The transport
reference remains 9 seconds with missing, one-point and tiny triangular outlines:
2 seconds load + 10 metres / 2 metres per second + 2 seconds unload.

The initial eight reproductions failed before fixes; retained log:
`latest/location-outlines-before.txt`. The focused suite passed **87 tests**;
`latest/location-outlines-focused.txt`. The first full pack passed 1,271 of 1,272
tests and found missing default/editor metadata in four new contract entries.
That documentation was corrected; all nine evidence-schema tests then passed.
The first-run log is retained as `latest/location-outlines-first-pack-tests.txt`.
The final full suite passed **1,272 / 1,272 tests in 136.544 seconds**, with
**zero broken evidence links**. See `latest/location-outlines-pack-build.txt`,
`latest/tests.txt` and `latest/evidence.json`.

Both 60-minute LTN demand-window runs completed four tasks, with zero failed or
pending. Initialisation took 1.330 and 1.421 seconds; total time 1.671 and 1.763
seconds. Both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Source/input hashes remained unchanged. See `latest/location-outlines-ltn/smoke.json`.
This bounded smoke check is not full LTN acceptance or an agreed performance gate.

## User verification

1. In a project copy, draw/edit a location boundary. Save, reopen and confirm its
   geometry. Undo and redo a completed boundary edit; cancel a second edit and
   confirm the first boundary remains.
2. Use the 4 m by 3 m reference triangle above. Confirm the location dialog and
   generated report show 6 m². Import legacy absolute points at a nonzero location
   origin and confirm playback selects the correct visible region.
3. Open Project Checks and confirm the outline scope finding explains that the
   boundary does not constrain simulation movement.
4. Try an incomplete point or nonfinite coordinate in a disposable JSON copy;
   confirm it cannot be imported/run as valid geometry.

## Next work

Continue remaining input contracts and department/workspace gaps, including
storage/report reconciliation where raw and normalized representations differ.
Keep verified physical geometry, the approved graph-focused CAD UI, tutorial and
release gates in their planned sequence. The unrelated `ltn.json` edit is excluded
from this checkpoint.
