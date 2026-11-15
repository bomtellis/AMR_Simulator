# Waypoint route search optimisation — 9 November 2026

The mandatory floor 2 stop and destination-side lift policy are unchanged. Identical corridor queries are reused within one read-only route search; irrelevant lift projections and impossible destination-before-waypoint branches are skipped. A conservative lower bound discards alternatives only after a real valid winner exists. The original queue ordering and equal-time tie handling are retained.

The local corridor cache includes the exact origin, endpoint and unrounded time. AMR, load, orientation, permissions and reservation snapshot are fixed for its lifetime, and it is discarded before booking. Optimistic graph distances are keyed by graph identity, normal/transfer speed, lift service/timing configuration, exact endpoint and waypoint. Bounds ignore restrictions and waiting, so cannot make an invalid route valid. Scenario and geometric routes retain the original evaluation path; bounds are also disabled for parallel routing.

## Current LTN building settings

- Mandatory rule: origin floor 0, destinations 1–5, via floor 2. A 0→1 journey still stops and exits at floor 2 before continuing to floor 1. This rule does not make floor 2 mandatory for unrelated origins.
- Destination-side selection on floor 2 still chooses the suitable lift with the shortest permitted destination-floor corridor route. Busy selected lifts remain eligible; equal distances use earliest completion then lift ID.
- Conditional connection floor remains 2. Reuse of the arrival lift is still allowed.
- Lift transfers remain in the existing fixed timing mode. No saved configuration was changed.

## Measured results

Same saved LTN configuration, full precision comparisons, with only per-run UUIDs normalised:

| Measurement | Original | Optimised |
|---|---:|---:|
| First 277,330 simulation seconds (3.21 days) | 1,200.485 s | 68.488 s |
| Busy period, simulation 09:00–09:02 | 41.128 s | 1.088 s |
| Completed tasks at common stop | 2,041 | 2,041 |
| Recorded events at common stop | 96,515 | 96,515 |
| Failed tasks at common stop | 0 | 0 |

All decoded events, completed task records, AMR state including energy, lift state, lift/edge/node/location reservations, inventory and pending tasks match exactly at the common stop. This is approximately 17.5× faster over the compared run and 37.8× over the busy sample. Timings are observations on this machine, not guarantees; other validation processes ran concurrently.

The final optimised source completed the whole seven-day workload in 193.019 s (plus 1.579 s initialisation), with 4,944 completed tasks, zero failures and 231,099 recorded events. A second optimised week had identical event and component hashes. The original comparison was deliberately bounded to 20 minutes; full-week equivalence against the original is not claimed.

## Regression evidence

The main affected regression suite passed all 284 tests. Further integration checks passed 86 of 87 tests. The failure in `test_selecting_a_charge_request_does_not_spend_or_reserve` also reproduces on the original source: it expects no events but an existing task-deferral timeout remains. It was not changed as part of route optimisation.

All five new differential tests pass: 480 varied original-versus-optimised route queries (including reservation commits and lift wear), eight scenario comparisons, nearest/equal-distance/busy-lift checks, lift-filter evaluation checks and four complete small simulations with fixed/speed-based timing and same/connecting lift journeys. Comparisons cover records, reservations, assets, energy and inventory without rounding away differences.

The saved original implementations and machine-readable `evidence.json` are under `verification/waypoint-search-20261109/`. Large event traces and benchmark snapshots are retained in the Codex workspace under `waypoint-optimisation-work/`, separate from user project runs. Application installation creates checksum-verified rollback copies there. Restart the application to load the changed source.
