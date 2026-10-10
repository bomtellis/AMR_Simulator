# Lift reservation order — review checkpoint

Two conflicts were reproduced against `b8c88fd`. The failure record is in
`baseline/lift-reservation-order-before.txt`.

- **D049:** gap insertion checked that a lift could return to a later pickup
  floor but never reserved or recorded that additional empty movement. Existing
  routes could therefore depend on a car arriving from the wrong floor. Its
  energy, operating time and wear were also absent.
- **D050:** inserting a journey before an existing booking used health already
  reduced by that future booking. The existing booking retained its original
  speed. A failure triggered by the insertion could start repair after the later
  booking rather than after the journey that reached the threshold.

## Scheduling rule and tradeoff

Committed robot routes retain their recorded timings and movement details.
When lift wear or the deterministic failure threshold is enabled, new journeys
are booked after the existing schedule and any repair. This makes the health
and operating-time projection follow the booked chronological order.

When both wear and failures are disabled, a gap can still be used if the new
recorded journey returns the car to the next booking's original starting floor.
That is the starting floor of its empty reposition, if present, rather than
necessarily its passenger pickup floor. No unrecorded reset is added.

This is commitment-order scheduling, not arrival-priority dispatch or an optimal
lift timetable. A robot arriving earlier may wait behind a journey already booked
for a later time. Some earlier gaps remain unused. Using them while wear or
failure thresholds are enabled would require replanning and revalidating every
affected committed route, resource reservation and event record; that is not
implemented. The existing settings apply this rule without a new configuration
option. Project Checks displays an informational **Lift scheduling** finding.

## Review the saved project

Open `scenarios/lift-reservation-order.json`, inspect Project Checks, and simulate
the ten-minute reference. Expect **2 completed tasks, 0 failed, 0 pending**.

The slow robot alone can carry the 10 kg Box. It receives FIRST at time zero,
booking lift service before the light task SECOND is released at 60 seconds.
The fast robot carries SECOND through separate approach and exit corridors so
the reference isolates lift contention. All connector edges have explicit 1 m
lengths. Neither task uses returns or charging.

| Quantity | Independent expectation |
| --- | --- |
| FIRST pickup | 0–2 s |
| Slow approach at 0.01 m/s | 2–102 s |
| First lift service, floor 0 to 1 | 102–107 s: 2 s boarding + 1 s vertical + 2 s alighting |
| FIRST completion | 107 + 100 s exit + 2 s dropoff = **209 s** |
| Health after first booked journey | **90%**; speed multiplier = 1 − 0.5 × 0.1 = **0.95** |
| Fast arrival at lift | 60 + 0.5 s empty approach + 2 s pickup + 0.5 s loaded approach = **63 s** |
| Second lift service | **107–113.105263… s**, including 1/0.95 s empty reposition, 2 s boarding, 1/0.95 s loaded travel and 2 s alighting |
| SECOND completion | 113.105263… + 0.5 s exit + 2 s dropoff = **115.605263… s** |
| Final lift health | **80%**, two journeys and no configured threshold failures |

FIRST finishes later than SECOND because its exit travel is much slower. Lift
order and task-completion order are different quantities.

## Acceptance coverage

Thirteen references in `tests/test_lift_reservation_order.py` cover floor
continuity, safe closed gaps, exact-fit gaps, preservation of an existing empty
reposition, chronological wear, deterministic failure accumulation, zero-duration
repair, individual and shared deliveries, charging travel, failed-commit rollback,
the visible scope finding, and the saved project before/after editor normalisation.
Saved-run checks reconcile task outcomes and each robot's recorded battery balance.

A separate two-second failure reference books service at 100–105 s and 105–110 s.
Each has one vertical operating second. The second reaches the threshold, repair
occupies 110–120 s, and a third service begins at 120 s. Boarding and alighting
do not count toward the operating-time threshold.

## Measured verification results

The full suite passes **629/629 tests**, with **zero broken evidence links**.
The saved reference passes through project checks, a frozen `.amrproj` run and
results investigation with two completions and no failed or pending work.

The six-hour LTN release window changes from **203 to 204 completed tasks**, with
zero failed or pending tasks in either run. The same **152 demand and payload-return
task IDs** complete: 124 generated deliveries, 27 generated payload returns and
one department-waste task. Empty robot returns to charging locations change from
51 to 52 because the altered timings change subsequent robot availability and
idle-return decisions. Generated idle-return IDs include a running counter and
therefore also change when their order changes. The simulator drains committed
work after the release window; these totals are not a six-hour completion cutoff.

An independent scan of recorded lift endpoints, sorted by movement start time,
finds **9 floor discontinuities before the fix and 0 afterwards**. It checks each
movement's origin against the preceding destination, starting from the frozen
configuration's initial floor. Empty-reposition endpoints come from the lift
nodes in the segment details, rather than the waiting robot's location. There
are **0 overlapping lift movements** in either run (2 ms tolerance for rounded
CSV timestamps). The logs contain 371 distinct lift movements before and 368
after; changed allocation can reduce movement count despite one extra robot
return. All **22 robot battery balances** reconcile in both runs.

The checked-in comparison is `baseline/lift-reservation-order-ltn.json`, including
the original event IDs for all nine discontinuities. The generated full evidence
is in `latest/index.html`, `latest/ltn-lift-reservation-order/summary.json` and
`latest/lift-reservation-order-reference/summary.json`.

Observed LTN runtime is **14.297 seconds** on this machine. This is a single
measurement, not a performance improvement claim or an acceptance threshold.
The new detailed outcome fingerprint is
`9140519eb512a425fb5956e26456743bd71bb15594f75ebd430bd3b82095119a`.
Both source configuration files were unchanged by the runs. Automated regression
warning acknowledgement does not constitute human review.

## Remaining limits

Wear and failure counters still represent committed work, not elapsed-time sensor
state. Repairs do not restore health. Failure thresholds are deterministic, not
random MTBF draws. Phase-entry speed sampling does not integrate speed changes or
outages during a movement. Multiple-lift dispatch, interrupted journeys, cancelled
future bookings, and complete lift metric-to-event reconciliation need further
verification. The [full roadmap](ROADMAP.md) remains open.
