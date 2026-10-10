# Exact scheduled dispatch — review checkpoint

Clock schedules and timeframe slots now release at their calculated calendar
times. They no longer wait for the next accumulation update. Resource contention,
configured release staggering, staff handoffs and return-dependent spacing still
apply; an exact release is not a guarantee of immediate assignment.

## Independent calculations

Open `scenarios/generation-final-interval.json`, save a disposable project and run
it. The one task is scheduled for 00:01. With the robot initially available at A,
it must start at **00:01:00** and finish at **00:01:09**:
2 seconds loading + 10 metres / 2 metres per second + 2 seconds unloading.
Demand preview must show one planned release at 60 seconds. Compare actual
assignment and completion in Results investigation, rather than relying solely
on the scheduled release field.

Before D014, the same ten-minute project started this task at 00:10 and finished
at 00:10:09. Before D013 it generated no work at all.

Twenty-two tests in `tests/test_scheduled_dispatch.py` also check:

- A 60-second scheduled release remains at 60 with update intervals of 60, 90.5,
  900 and 3,600 seconds. Normal consumption polls remain at 0, 900 and the final
  1,000-second horizon in a separate mixed-event reference.
- A 23:59 service in a 23:58-start run releases after 60 seconds, including daily
  recurrence. If its department opens next day at 09:01, it releases at 32,580
  seconds instead of disappearing at midnight.
- Monday-only fortnightly work releases on days 0 and 14, not day 7.
- A three-minute staff window with three evenly allocated payloads releases at
  60, 120 and 180 seconds. Seven slots over one minute retain fractional seconds.
- Two half-capacity scheduled fills at 60 and 120 seconds trigger one original-bin
  collection at 120, then its return. Planning the calendar does not precreate
  tasks, fill bins, consume schedule entries or allocate task identities.
- Inclusive horizons, global disable, duplicate schedule times, grouped services,
  overnight timeframes and a department opening beyond the timeframe deadline.
- Preview agreement for deferred schedules and exclusion of effective releases
  before the run starts.

`baseline/scheduled-dispatch-before-fix.txt` and
`baseline/timeframe-dispatch-before-fix.txt` preserve the failing reproductions.

## Intentional changes to prior results

Effective releases before the simulation starts are now excluded for both
department and category-only schedules. The old department clamp replayed these
at zero. A nominal earlier time may still be included if department opening hours
defer its effective release into the run. The existing preview test and independent
count calculation have been updated to this explicit contract.

Schedules deferred across days retain their original occurrence identity, so
separate daily services remain separate. Weekday and fortnight gates retain the
existing evaluation at the effective release time. No separate backlog-merging
policy is introduced.

In the six-hour LTN comparison, `GEN_STORES_D18_00002` starts at **06:50 instead of
07:00**, and `GEN_STORES_D18_00003` at **07:40 instead of 07:45**. Earlier service
changes subsequent return timing, resource contention and some generated return
identifiers. Matching completed-task counts therefore does not mean old and new
results are numerically identical. Old result files remain unchanged.

## Scope and remaining work

Scheduled, scheduled-threshold and scheduled-sporadic clock entries, plus
timeframe slots, use exact events. Continuous consumption, sporadic accumulation,
tracked-item balances and legacy department waste retain their polling cadence;
their full boundary/interaction matrix remains incomplete. Scheduled threshold
fills use current state at the fill event, not a precomputed collection count.

Clock strings retain the existing minute-resolution parser; an HH:MM:SS input is
normalised to HH:MM. Fractional timeframe slots use calculated time rather than
being rounded to a minute. Calendar planning is bounded by the run horizon;
large-horizon memory and performance acceptance limits remain to be established.
These references do not close the full generation or engineering verification gate.

## Recorded verification

- **360/360 tests pass**, with zero broken feature-to-test evidence links.
- Saved-project reference: one task; recorded assignment at **60 seconds** and
  completion at **69 seconds**. Summary and events reconcile. Evidence:
  `latest/exact-schedule-reference/summary.json` and its frozen run folder.
- Six-hour LTN: **203 completed, 0 failed, 0 pending**, with matching summary and
  outcome events. Evidence: `latest/ltn-exact-schedules/summary.json` and
  `comparison.json` for the before/after event comparison.
- Two further six-hour runs reproduce the same detailed outcomes exactly:
  `21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
  Evidence: `latest/ltn-exact-schedule-repeatability/smoke.json`. Initialisation
  took approximately 1.0–1.2 seconds and complete runs 12.4–14.4 seconds locally;
  these observations are not performance acceptance thresholds.
- Source and input preservation checks pass. The reference runner's automatic
  warning acknowledgement does not imply human review or engineering acceptance.
