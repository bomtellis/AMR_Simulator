# Storage bay inputs and preservation — slice 2AC

Baseline: `751443e`. This checkpoint closes specific bay input and edit defects;
the complete location/stock and geometry contracts remain under review.

## Corrections and changed results

A misspelled payload template previously disappeared from the simulator's set of
allowed payloads. An empty allowed set meant unrestricted storage, so the typo
could broaden a fixed bay's compatibility. Runtime and Project Checks now reject
unknown template references. AMR restrictions must name a configured type or an
existing instance of that type. References may remain unresolved in an editable
draft, with the exact text preserved, but must be resolved before simulation.

Raw import and simulation reject duplicate resolved bay names within a location,
malformed bay/template lists, incomplete or nonfinite coordinates, negative or
nonfinite dimensions, invalid reference types and non-boolean storage flags.
Numeric dimension strings remain accepted. Unnamed bays resolve to `Space N`;
those resolved names must also be unique. Complete local dx/dy pairs take
precedence over complete absolute x/y pairs. Slot coordinates may be omitted;
outline points must supply coordinates. Empty and two-point legacy outlines are
retained: these checks do not establish a valid physical polygon.

The editor's bay setter previously dropped every bay with fewer than three outline
points, rounded geometry to millimetres, discarded payload occupancy/reservation
markers and replaced some legacy dimensions and flexibility settings. It now
validates before changing the project, retains dimension-only bays and legacy
outlines, preserves metadata, and shares runtime envelope inference without
rounding. Invalid edits leave the project unchanged. Other dialogs' numeric
precision and all editing paths are not yet verified.

Initial `occupied` markers block the relevant bay but do not, by themselves,
create physical payload stock or contribute storage volume. Project Checks now
explains this distinction. Existing stale AMR occupancy cleanup remains supported;
runtime occupancy IDs are not treated as configured AMR-type restrictions.

## Independent references and evidence

The new `test_inventory_input_contracts` cases specify the expected behaviour:

- A fixed bay with template `Typo` fails preflight and raw simulation even when
  another correctly named payload would fit its envelope.
- With quantity one of type `R`, restrictions `R` and `R-1` resolve, while `R-2`
  and a misspelled type do not. Parent and slot restrictions are both checked.
- Names `Bay`/`Bay` and unnamed-first-bay/`Space 1` collide and are rejected.
- Saving a dimension-only bay keeps **1.0004 m** and its blocking/reservation
  markers. A legacy two-point bay retains **1.0004 × 0.7004 × 1.0004 m**,
  its flexibility flag, sub-millimetre slot position and rotation precision.
- An occupied bay provides no free destination but creates **zero physical
  instances**. Changing a referenced catalog makes the finding stale.
- Zero explicit length/width retain runtime's legacy inference from points:
  local points (0,0) and (2,3) produce a **2 × 3 m** envelope.

Initial failures are in `latest/inventory-input-before.txt`. The focused bay,
physical payload, editor, charging, reservation, recovery, checks and local-manoeuvre
suites passed **130 tests**. The full suite passed **1,216 / 1,216 tests in
135.157 seconds**, with **zero broken evidence links** and unchanged source
hashes. Logs are in `latest/inventory-input-focused.txt`,
`latest/inventory-input-pack-build.txt` and structured `latest/evidence.json`.
The observed inventory retains **327 paths awaiting individual review**; this is
not a count of missing features.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending. Source/input checksums were unchanged and both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Results are in `latest/inventory-input-ltn/`. This bounded regression does not
establish full LTN acceptance.

The first full run caught an older local-obstacle fixture using undefined payload
`Other` as a template. That fixture now declares `Other` as a real payload and
retains its original assertions: no completed movement, no stored payload and no
unsafe local manoeuvre. The input validator was not relaxed for the placeholder.
The initial full-run log is retained in `latest/inventory-input-pack-initial.txt`.

## User verification

1. In a project copy, misspell a bay's payload template. Check the project and
   confirm the finding identifies that template and blocks running.
2. Restore the correct name, check again, and confirm the reference error clears.
3. Import a dimension-only bay with `length_m: 1.0004`, then save its inventory
   spaces. Confirm the bay remains and its dimension is unchanged.
4. Inspect an initially occupied bay. Confirm Project Checks explains that the
   marker is not initial physical stock; use stock-generation rules for stock.
5. Try a duplicate bay name or malformed outline. Confirm rejection leaves the
   existing configuration intact.

## Remaining limits and next work

All these storage contracts retain a partial disposition. Fit is still an
axis-aligned envelope with plan rotation, not polygon containment or swept
clearance. The unknown-height sentinel, stacking/packing, contradictory mixed
AMR/payload classifications, legacy slot aliases and the complete location schema
remain open. Runtime's zero-as-inference convention remains; general preflight
still rejects explicit zero modern dimensions, so that policy needs reconciliation.
Initial occupancy is not a stock seeding interface. Long mixed-workflow stock
conservation still requires independent acceptance evidence.

Next audit location dimensions, wash/concurrency inputs and references, complete
the remaining bay classification/zero-policy decisions, then proceed to department
and workspace gaps. Geometry, approved graph-focused CAD UI, tutorial and release
gates retain their planned order. The unrelated `ltn.json` change is excluded.
