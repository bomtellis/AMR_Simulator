# Storage report reconciliation — slice 2AH

## Corrected behaviour

Location reports now count configured **payload bays** separately from AMR parking
and charging bays. They use the same AMR markers and legacy alias precedence as
the simulator. An explicit blank modern slot `amr_type` overrides legacy `amr`.
The catalog retains separate total-bay and AMR-bay counts. Inventory plan area
sums payload-bay outlines only; dimension-only bays do not acquire invented drawn
area. Overlapping outlines are still summed, not unioned.

Report bay dimensions now follow runtime modern/legacy aliases, zero inference,
payload height inference and fallback names. Payload report dimensions use the
same `size_units` defaults as the simulator. Fixed bays include known parent
payload restrictions; explicit `flexible` overrides `flexible_payloads`, including
false. Reports no longer overstate storage just because a robot bay is present or
a legacy dimension was not recognised.

The audit also exposed an input interpretation defect shared by runtime and editor:
mixed absolute/local bay points were measured in different coordinate systems.
All configuration-aware consumers now resolve points relative to the parent
location before measuring the envelope. Runtime, editor import and setters,
Project Checks, initial fleet allocation and report inference use that resolution.
Overflow during conversion is a blocking input error. Existing all-local projects
retain their dimensions. Results can change for mixed-coordinate projects because
their former inferred envelopes were wrong.

## Independent references

- A bay at location `(6, 8)` with points local `(0, 0)`, absolute `(10, 8)` and
  local `(0, 3)` has envelope **4 × 3 m**, triangle area **6 m²**. The previous
  inference incorrectly produced **10 × 8 m**. A 5 × 4 m robot cannot fit this bay.
- One payload bay and one AMR bay provide **one** configured payload space. Two
  simultaneous payloads have at least **one** space shortfall. All-AMR layouts
  provide zero configured payload bays.
- Modern length `"0"` with legacy length 99 and a 4 m outline resolves to **4 m**,
  while explicit legacy width 3 and height 2 remain **3 m** and **2 m**.
- A payload defined only with `size_units = 1.5` has **1.5 × 1.5 × 1.5 m**
  dimensions and can infer a 1.5 m bay height.
- A 1 × 0.7 × 1 m payload fits a 0.7 × 1 × 1 m bay after plan rotation. The
  existing `1e-6 m` payload tolerance permits a `0.0000005 m` excess but not
  `0.000002 m`; height is checked without sideways rotation.
- A small and large payload fit a small and large bay simultaneously even when
  the large bay is listed first. Distinct matching uses the existing independently
  verified iterative matching helper; greedy order cannot consume the only viable
  large bay unnecessarily.

## Evidence and limits

The initial eight tests reproduced six failures; see `latest/storage-report-before.txt`.
Twelve new tests now pass in a **95-test focused suite**, with all **nine contract
evidence checks** passing. Logs: `latest/storage-report-focused.txt` and
`latest/storage-report-evidence-check.txt`. The full pack passed **1,284 / 1,284
tests in 135.907 seconds**, with **zero broken evidence links** and unchanged
source hashes during testing. See `latest/storage-report-pack-build.txt`,
`latest/tests.txt` and `latest/evidence.json`.

The two 60-minute LTN demand-window runs each completed four tasks with zero
failed/pending, initialising in 1.367 and 1.438 seconds and finishing in 1.713 and
1.783 seconds. Both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/storage-report-ltn/smoke.json`. This is bounded regression evidence,
not full LTN acceptance or a performance threshold.

Capacity comparisons describe nominal configured bays. They do not reconstruct
live reservations, actual bay assignments, blocking occupancy markers, access,
queues, manoeuvres or swept geometry. The report now labels missing geometry as
**count only**, both in detail data and summary. A count-only shortfall is a lower
bound; zero does not prove dimensional fit. The summary metric is now “Configured
payload spaces across zones”, since fixed bays count too. Consumers depending on
the former “Configured flexible spaces across zones” label need to adopt the new
label.

Reports still need complete event-coverage reconciliation, including distinction
between missing evidence and zero activity, initial stock coverage, and legacy
logs. This checkpoint does not establish those broader requirements. Outlines are
algebraic plan measurements, not validated physical polygons. Modern frozen runs
have preflight-validated configurations; this work is not a complete schema
migration for malformed historical report inputs.

## User verification

1. In a copy of a project, give a drop-off location one payload bay and one robot
   bay. Generate a report and confirm configured payload storage is one space.
2. Import a bay with legacy dimensions and a zero modern dimension that invokes
   outline inference. Compare its dimensions in editor, simulation and report.
3. Try the mixed-coordinate triangle above at `(6, 8)`. Confirm its 4 × 3 m
   envelope and that it cannot hold the 5 × 4 m robot.
4. Review the capacity basis and interpretation rows. Count-only estimates must
   remain visibly different from compatible-dimension estimates.

## Next work

Continue department input contracts and then remaining workspace gates. Retain
the open full-report event-coverage/stock reconciliation requirement. Verified
physical geometry, approved graph-focused CAD UI, tutorial and final release work
remain in their planned order. The unrelated `ltn.json` edit is not included here.
