# Lift wear, repair and service timing — review checkpoint

**D048:** a lift journey delayed by repair used the scenario speed at planning
time instead of its future service time. The reference completed its second task
at **86 seconds** instead of the independently calculated **88 seconds**.
`baseline/lift-repair-before.txt` records the failure at `315739d`.

Slot planning now samples reposition speed at reposition start, loaded speed
after boarding, and any reset movement at its planned start. A candidate with an
unavailable future phase is rejected before non-finite times can enter further
route calculations. Pending work can retry at scheduled recovery boundaries.

## Review the saved reference

1. Open [lift-repair-slowdown.json](scenarios/lift-repair-slowdown.json).
   Two single-task robots carry one Box each from A on floor 0 to B on floor 1.
2. Simulate. Expect **two completed tasks**, no failed or pending work. Their
   completion times are **10 seconds** and **88 seconds**.
3. Inspect the lift segments in Results Investigation. The first service occupies
   **2.5–7.5 seconds**. After a 70-second repair, the second service occupies
   **77.5–85.5 seconds**. It includes a 2-second empty reposition and a 2-second
   loaded movement because the scenario halves lift speed from 60 to 120 seconds.
4. Inspect the final lift state: **two committed journeys**, **two recorded
   failures**, health **100%** (wear is disabled in this reference), and the second
   repair ending at **155.5 seconds**. These are planning/model counters, not
   independent execution sensors.

## Independent calculation

The first pickup takes 2 seconds and its 1 m approach takes 0.5 seconds. Boarding
takes 2 seconds, one floor at 1 floor/s takes 1 second, and alighting takes
2 seconds: lift finish = **2.5 + 2 + 1 + 2 = 7.5 seconds**. A 0.5-second exit
connector and 2-second dropoff give completion at **10 seconds**.

The configured failure threshold is 1/3600 hour = **one vertical operating second**.
The first service reaches it, so the 70-second repair finishes at **77.5 seconds**.
The second robot needs one floor of empty repositioning, then one loaded floor.
At half speed each takes 2 seconds: **77.5 + 2 + 2 boarding + 2 + 2 alighting =
85.5 seconds**. Its exit and dropoff add 2.5 seconds, giving **88 seconds**.
The second service reaches the threshold again; repair ends at **155.5 seconds**.

Eleven references cover this saved project before/after editor normalisation,
phase-specific speed changes, exact repair waits, disabled failure thresholds,
zero-duration repair, pure estimates, rejected-commit rollback, shared-journey
wear, the inclusive minimum-health boundary, post-wear threshold scaling and an
unavailable future lift phase that recovers before assignment.

## Verification results

The full engineering suite passed **616/616 tests**, with **zero broken evidence
links**. The saved reference completed **2 tasks**, with **0 failed** and
**0 pending**. The six-hour LTN regression completed **203 tasks**, with **0 failed**
and **0 pending**, in **17.294 seconds**. Its detailed outcome fingerprint remains
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`, matching the
previous checkpoint. Both runs preserved their inputs and reconciled completion
and failure totals against recorded events. These timings are observations from
this machine, not performance acceptance thresholds.

Generated evidence is in `latest/index.html`,
`latest/lift-repair-reference/summary.json` and
`latest/ltn-lift-repair/summary.json`. Automated warning acknowledgement during
these regression runs does not constitute human review or approval.

## Verified model rules and limits

Wear is applied once per committed lift journey, including a shared payload
journey, and rounded to three decimal places. Repositioning does not add a second
wear count. The failure accumulator includes empty and loaded vertical travel;
boarding, door and waiting time are excluded. The configured mean-time value is
currently used as a deterministic operating-time threshold, scaled by post-wear
health with a 10% lower bound. Zero disables threshold failures. A reached
threshold schedules repair after committed service, then resets the accumulator.
Repair does not restore health, and a zero repair duration still records a failure.

Minimum health is inclusive: exactly at the threshold the lift can operate;
wear below it can make later work terminally infeasible. Speed uses health before
the journey, whereas the failure threshold uses health after wear. These rules
describe the current approximation and are not a calibrated reliability model.

Follow-up D049/D050 in [LIFT_RESERVATION_ORDER_REVIEW.md](LIFT_RESERVATION_ORDER_REVIEW.md)
protects committed floor continuity and orders bookings chronologically when
wear or failure thresholds are enabled. It supersedes the earlier-gap limitation
below for those settings; the remaining reliability-model limits still apply.

Known scheduled speed is sampled at phase entry. Mid-phase speed changes and
outage interruption are not integrated over the trajectory. Repair/wear state is
applied during serial route commitment; inserting journeys into earlier gaps
does not constitute a fully chronological reliability simulation. Independent
coverage for complex reservation gaps, multiple lifts, health restoration policy,
stochastic failures and complete metric-to-event reporting remains open. The
[full roadmap](ROADMAP.md) remains unfinished.
