# Lift floor definitions — slice 2Z

Baseline: `f6fa947`. Lift import, Project Checks, save and simulation now share
structural validation. This prevents contradictory floor definitions from creating
different graphs in the editor and simulator.

## Contract and changed behaviour

- Lift IDs are unique, nonblank strings without surrounding whitespace. Generated
  stop names cannot collide with location or corridor-node names.
- Served floors are a nonempty list of unique JSON integers. Negative labels are
  valid; booleans, strings and fractional or floating-point labels are rejected.
- The initial car floor must be served. Its default remains 0; a project serving
  only floors 1 and 2 must explicitly choose a valid starting floor.
- Floor positions match served floors exactly. Every key is a canonical string
  integer, such as `"0"` or `"-2"`, with complete finite x/y coordinates. Numeric
  coordinate strings remain accepted; booleans and nonfinite values are rejected.
- Missing required fields may remain in an incomplete editor draft, but run checks
  and simulation reject it. Explicit malformed data is not silently repaired.

Previously, extra floor positions appeared in editor/preflight graphs while
simulation built stops only for served floors. Other malformed inputs could be
accepted, truncated or fail later during graph construction. Extra and missing
positions now produce a field-specific error. Correct the floor list or position
map explicitly; importing does not discard positions or invent connections.

Lift saves validate the candidate against other graph identities before replacing
the stored record. The dialog checks rename collisions before emitting its result,
so callbacks cannot delete the old lift before discovering this invalid edit.
Findings about graph identity become stale when corridor or location data changes.
Valid rename/floor-removal reference migration remains separate open work.

## Acceptance evidence

Twelve tests in `tests/test_lift_structure.py` cover malformed floor lists, default
and explicit start floors, aliases, missing/extra positions, incomplete/nonfinite
coordinates, duplicate IDs, graph-name collisions, incomplete drafts, negative
floors, atomic save rejection, dialog collision rejection and finding dependencies.
The initial references reproduced failures against the baseline implementation;
the log is retained in `latest/lift-structure-before.txt`.

The negative-floor reference serves -2 and -1 and starts the empty car at -1.
At one floor/second, the original 10-second delivery gains exactly one second of
empty reposition: **11 seconds**. Both raw input and editor-imported data produce
the same four graph points and one completed task. The existing saved 23-second
lift scenario and previous capacity, speed and reliability references remain in
the full suite.

The option inventory now uses `lifts[].floor_locations.*.x` and `.y` for arbitrary
floor labels. Eight structural contracts carry explicit partial dispositions.
Consolidating floor-labelled paths reduces the inventory count without implying
that separate features were implemented or that the full lift model is verified.

The focused lift/evidence run passed **35 tests**. The full suite passed
**1,176 / 1,176 tests in 132.233 seconds**, with zero broken evidence links and
unchanged source hashes. The complete pack took 134.443 seconds. Logs are in
`latest/lift-structure-focused.txt`, `latest/lift-structure-pack-build.txt` and
`latest/evidence.json`.

All 28 currently inventoried lift paths now have explicit dispositions and passing
linked evidence. They retain their partial/unsupported status and limitations.
The total observed backlog is 382 paths; its reduction includes floor-map
canonicalisation and is not a feature-completion percentage.

Both 60-minute LTN demand-window runs completed four tasks, with none failed or
pending, preserving outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Source and project checksums remained unchanged. Results are in
`latest/lift-structure-ltn/`; this bounded regression is not full LTN acceptance.

## User verification

1. Import `scenarios/lift-contract.json` and confirm it still passes input checks
   and completes its single task in 23 seconds.
2. In a copy, add a position for floor 2 without adding it to served floors. Confirm
   import/checks reject the mismatch instead of presenting an extra usable stop.
3. Set the starting floor to 2 while only 0 and 1 are served. Confirm the specific
   error; changing it back restores the valid definition.
4. Try renaming a lift to another existing lift's name. Confirm the dialog reports
   the collision and both original lifts remain present.

## Limits and next work

Per-floor entrance coordinates may differ; these checks do not prove a physically
aligned shaft, cabin doorway clearance or swept geometry. Input-file contracts
cover JSON values, not arbitrary non-JSON Python objects. Full valid rename and
floor-removal reference migration, all editor precision round trips and interacting
lifts remain open. Reviewed partial dispositions are not feature-completion claims.

Next audit robot configuration and physical payload compatibility, using the
existing resource, energy and route references. Keep the remaining workspace,
geometry, approved CAD UI, tutorial and release gates in their agreed order.
Local `ltn.json` changes remain outside this checkpoint.
