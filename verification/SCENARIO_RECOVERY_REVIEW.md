# Scheduled outages and recovery — review checkpoint

`baseline/scenario-recovery-before.txt` records four failing references against
`75f7a8c`. They identified these defects:

- **D044:** a temporary robot outage had no scheduled recovery wake-up; without
  another event, valid work could remain pending after the outage ended. Scenario
  start/end boundaries now invalidate route estimates and retry pending work.
- **D045:** structural route feasibility used current lift availability, turning
  a temporary lift outage into a terminal task failure. Terminal checks now use
  allowed lift connections, dimensions, corridor widths and health constraints;
  the assignment planner still applies operational availability.
- **D046:** multi-stop assignment omitted the robot availability gate used for
  individual work. Multi-stop and separate charging admission now respect it.
- **D047:** an overnight window tested the current weekday instead of the day
  the interval began. Monday 23:00–01:00 now includes Tuesday 00:00. Exact end
  timestamps are excluded, with fractional seconds retained in the comparison.

## Review the saved projects

1. Open [robot-outage-recovery.json](scenarios/robot-outage-recovery.json).
   R is unavailable from 00:00 to 00:01. Run checks and simulate.
2. Expect **one completed task**, no failed or pending work, assignment at
   **60 seconds** and completion at **69 seconds**. The independent duration is
   60 seconds waiting + 2 seconds pickup + 10 m / 2 m/s + 2 seconds dropoff.
3. Open [lift-outage-recovery.json](scenarios/lift-outage-recovery.json).
   L1 is unavailable for the same minute. Expect **one completed task**, no failed
   or pending work, assignment at **60 seconds** and completion at **70 seconds**.
   After recovery: 2 seconds pickup + two 1 m corridors / 2 m/s + 4 seconds
   lift boarding + 1 second vertical travel + 2 seconds dropoff = **10 seconds**.
4. In Results Investigation inspect task waits, assignment and outcome records.
   The full log also records `scenario_boundary` checks at 0 and 60 seconds.
   Both projects enable enhanced scenario logging so frozen-input and outcome
   reconciliation are available.

Thirteen references cover these projects before/after editor normalisation,
multi-stop admission, charging admission, fractional boundary instants,
overlapping/adjacent outages, overnight weekdays, all-day intervals, disabled
and unmatched scenarios, recovery beyond the run horizon, original deferral
deadlines and permanent route restrictions during an outage.

The full verification pack passes **605/605 tests**, with **zero broken evidence
links**. Both saved references complete their one task with no failed or pending
work, and their frozen inputs and task outcomes reconcile. See
`latest/robot-outage-reference/summary.json` and `latest/lift-outage-reference/summary.json`.

The six-hour LTN run completes **203 tasks**, zero failed and zero pending, in
**16.211 seconds** (an observation, not a controlled performance threshold).
Its detailed outcome hash remains unchanged:
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`.
See `latest/ltn-scenario-recovery/summary.json`.

## Calendar and scheduling contract

Windows are half-open: start inclusive, end exclusive. Selected weekdays belong
to the start day. Equal start/end clock values retain the existing all-day
meaning, now explicitly midnight to midnight on each selected day. Overlapping
active events retain the most restrictive availability and speed factors.
Boundaries are scheduled only within the configured demand horizon; recovery
after that horizon does not invent additional operational time. A task can remain
pending, or expire under its original configured deferral deadline.

This fixes admission and recovery. It does not cancel, interrupt or reroute work
already committed when an outage begins. Corridor/lift timing still uses existing
segment-entry approximations; complete interaction tests for mid-segment outages,
chained corridor closures, lift repair/wear and speed-only scenarios remain open.
Partial availability retains its existing speed-factor approximation; it is not
a stochastic uptime model. Timezone/DST policies and complete malformed-scenario
validation also remain open. This is general engineering verification, and the
[full roadmap](ROADMAP.md) remains unfinished.
