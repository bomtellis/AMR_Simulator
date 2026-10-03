# Lift timing, envelope and input contracts — slice 2Y

Baseline: `1a5341b`. This checkpoint records 19 partial scalar contracts and the
unsupported legacy size-unit capacity field, with independent timing, envelope,
reservation and editor references. Existing reliability and energy references
remain linked; their limited model scope is retained.

## Corrections and changed results

Simulation has used `speed_floors_per_sec` as its authoritative base speed. The
editor previously preferred separately stored `speed_m_per_sec`, which could be
stale. For 0.5 floors/s, 3 m floors and stale metadata of 99 m/s, both old lift
display methods showed 99; the effective speed was 1.5 m/s. They now show 1.5.
The prior methods were executed from the baseline Git revision; the reproduction
is retained locally in `latest/lift-contract-baseline.json`.

Import preserves the configured floors/s value. A runnable lift must specify it;
an incomplete editor draft can still omit it. Project Checks warns when stored
m/s differs from the effective speed. Acknowledging this warning permits an
exploratory run, and a floor-height edit makes that acknowledgement stale.
Existing simulation speed and timing do not silently migrate to the metadata.

Saving a lift previously rounded the converted floors/s value to three decimals:
1 m/s over 3 m floors became 0.333 floors/s and took 3.003003 seconds per floor.
Conversion now retains precision, producing 3 seconds. The m/s editor still uses
three decimal places, so arbitrary JSON precision does not universally round-trip.

Omitted boarding and cabin-size values in the dialog and store save API now agree
with runtime defaults: 5 seconds and 2.8 × 1.8 × 2.1 m. Previously the dialog/save
defaults were 6 seconds and 1 × 1 × 2 m, so opening and saving an older sparse lift
could change its behaviour. Existing explicit values remain authoritative; newly
created lifts also use the harmonised defaults.

Malformed scalar values are now rejected before simulation and editor import.
Checks cover finite values, booleans, positive speed and dimensions, nonnegative
times/powers/masses, efficiency fractions and the existing supported health
ranges. Numeric strings remain accepted. Zero handling time, zero repair duration,
zero wear and disabled failures remain valid. Health-speed multiplier is explicitly
0.05–1, matching the runtime range rather than silently clamping lower values.
An invalid save is checked before replacing the stored lift.

## Independent references

For a car initially one floor above pickup, 0.5 floors/s, 3 s door allowance and
4 s boarding allowance, a service arriving at time 10 has:

| Phase | Expected elapsed time |
| --- | ---: |
| Reposition to pickup | 10–12 |
| Door and boarding | 12–19 |
| Loaded vertical travel | 19–21 |
| Door and alighting | 21–28 |

The saved `scenarios/lift-contract.json` adds 2 s pickup handling, a 0.5 s approach,
the same 18 s lift service, a 0.5 s departure and 2 s drop-off handling: **23 s**.
Its exclusive reservation is **2.5–20.5 s**. Raw and editor-imported projects match.

Cabin boundaries include exact fit, a 0.0001 m shortfall in each dimension, payload
rotation and an oversized robot. Two independent robots retain exclusive lift
reservations and finish at 10 and 16 s in the separate concurrency reference,
whether legacy size-unit capacity is 0, 1 or 100. Project Checks explicitly shows
that this unused field cannot increase physical capacity or permit co-occupancy.

Fourteen new tests also cover runtime defaults, valid boundary inputs, structured
findings, stale warnings, actual dialog defaults and atomic rejection of bad saves.
The focused lift/evidence suites passed **47 tests**. The full suite passed
**1,164 / 1,164 tests in 132.188 seconds**, with **zero broken evidence links**
and unchanged source hashes. The complete pack took 134.364 seconds; results are
in `latest/lift-contract-pack-build.txt` and `latest/evidence.json`. The observed
inventory retains 405 paths awaiting individual review; this is not a missing
feature count.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending. They retained the preceding outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Source and input checksums stayed unchanged. Outputs are in
`latest/lift-contract-ltn/`. This bounded regression is not full LTN acceptance.

## User verification

1. Import `scenarios/lift-contract.json`, run Project Checks, then simulate with
   full logging. Confirm one completed task, no failures and the 23 s completion.
2. Inspect the lift movement records: one empty reposition and one loaded transfer.
3. In a copy, set m/s metadata to 99 while retaining 0.5 floors/s. Confirm the
   mismatch warning and effective 1.5 m/s display. Save the lift to synchronise.
4. Try a nonpositive cabin dimension or negative door time through JSON import;
   confirm a field-specific error before simulation.

## Limits and next work

Cabin fit is the maximum of robot and oriented payload dimensions. It does not
sum stacked heights, model a doorway or prove swept clearance. There is no rated
cabin mass input or independent multi-robot sharing of a car. The energy model
remains an approximation; reliability uses deterministic operating-time thresholds,
not sampled stochastic failures. Mid-phase changes are not integrated.

These contracts do not close lift floor IDs, served-floor membership, start-floor
and coordinate validation, all editor range/precision round trips or multiple-lift
interactions. Audit those structural references next, then move to the outstanding
robot, location and department fields. Keep later geometry, approved CAD UI,
tutorial and release gates in the planned order. Unrelated local `ltn.json` edits
remain outside this commit.
