# Robot configuration and payload-slot compatibility — slice 2AA

Baseline: `701b414`. Editor import and simulation now share the same slot resolver
and orientation parser, with explicit robot input checks and 29 field dispositions.
These are scoped engineering references, not certification of robot/load geometry.

## Corrections and changed results

For legacy single-slot robots, runtime used `payload_size_capacity` as the fallback
for each omitted deck dimension. The editor instead substituted 1 m. A legacy size
of 2 with a 1.5 × 1.5 × 1.5 m load therefore fit before import but not afterward.
Both paths now preserve the 2 m dimensional fallback. This legacy value is not a
volume or an aggregate multi-slot capacity. Explicit dimensions take precedence;
nonempty explicit slots override all top-level capacity settings.

An explicit empty slot-orientation list previously meant lengthways in runtime but
both orientations after editor import. Empty/unknown permissions now produce a
field-specific error. Omitted permissions still allow both orientations. The
editor's legacy comma-separated string format now resolves consistently in raw
simulation as well: `SIDEWAYS` means sideways, rather than being iterated as
characters and falling back to lengthways. Payload and slot permissions intersect.

Robot inputs now reject malformed dimensions, speeds, capacities, battery settings,
quantity, multi-stop flags and slot definitions before lossy normalisation. Zero
quantity remains a valid deliberately inactive fleet entry. Numeric integer strings
are accepted; fractions and booleans are not counts. Empty slot lists retain the
legacy single-slot definition; missing capacity fields can remain in incomplete
editor drafts but prevent running. Explicit nonpositive capacities are invalid,
even when a different slot definition would override them.

Incomplete slot fields remain absent through save/import rather than becoming
fabricated zeros. A regression test reopens the normalised draft and confirms it
remains editable while simulation still rejects the missing capacities.

The shared checks also reject duplicate robot IDs and duplicate resolved slot
names. Project Checks retains existing numeric finding IDs where applicable,
avoids duplicate findings on the same field and records which check groups ran.

Project Checks exposes that per-type `start_location` is ignored and supplied
manual-compatibility metadata is recomputed. Initial placement follows charging
inventory allocation. Robot `weight_kg` can support report attribution, but robot
own mass remains absent from the current lift-energy equation.

## Independent references

Fifteen new tests in `tests/test_robot_contracts.py` cover:

- Exact mass, length, width and height limits, and failure with a 0.0001 shortfall.
- Legacy dimensional fallback and explicit-slot precedence through raw/editor runs.
- Intersected orientation permissions and a load that fits only after plan rotation.
- Rejection of invalid inputs without modifying the source configuration.
- Quantity 0/2, derived flags, defaults and visible ignored-field limitations.
- A 10 m journey at 2 m/s with two 2 s handling phases: **9 seconds**.
- A 5 kWh battery at 25%: **1.25 kWh** available, **1 kWh** reserve at 20%, and
  **9,000 seconds** ideal charge time for the missing 3.75 kWh at 1.5 kW.

The initial references reproduced baseline failures in
`latest/robot-contract-before.txt`. The broader checks, editing, multi-stop and
charging integration run passed **121 tests** in
`latest/robot-contract-integration.txt`. The full suite passed **1,191 / 1,191
tests in 132.604 seconds**, with **zero broken evidence links** and unchanged
source hashes. The complete pack took 134.812 seconds; see
`latest/robot-contract-pack-build.txt` and `latest/evidence.json`.

All 28 currently inventoried robot fields now have explicit dispositions, with
their partial/unsupported scope retained. The complete observed inventory has
353 paths still awaiting individual review; this is not a missing-feature count.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending and retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Source and input checksums stayed unchanged. Outputs are in
`latest/robot-contract-ltn/`; the bounded regression is not full LTN acceptance.

## User verification

1. Open the existing `scenarios/door-pass.json` reference and confirm its one task
   still completes in 9 seconds.
2. In a copy, set the robot's explicit slot mass limit below the payload mass.
   Confirm Project Checks explains that no active robot slot can carry the payload.
3. Set slot orientations to an empty list or an unknown name. Confirm import or
   run checks reject it instead of choosing a default orientation.
4. Compare a legacy robot using only a size fallback with its editor-imported form;
   inspect that all three resolved dimensions retain that value.

## Limits and next work

Per-slot capacity and orientation checks do not prove combined deck packing,
aggregate structural mass limits or swept clearance. Legacy size fallback remains
a cube-like dimensional approximation. Energy remains an idealised model without
stationary auxiliaries, charging losses or robot own mass in lift energy. Full
fleet optimisation and all editor range/precision round trips remain open.

Next audit physical payload inputs and location compatibility/storage fields,
retaining the established stock and conservation references. Then continue the
department and workspace gaps before geometry, the approved CAD UI, tutorial and
final release gates. Unrelated local `ltn.json` changes remain outside this commit.
