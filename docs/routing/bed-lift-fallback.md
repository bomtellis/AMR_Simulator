# Bed lifts as a last-resort AMR option

In the lift editor, set **Lift use** to **Bed lift — AMR fallback**, then add
daily AMR access windows or select **Allow AMR fallback all day**. Existing
lifts remain **FM lift — preferred** until explicitly changed. No windows
means the bed lift is unavailable to AMRs.

In **Building settings**, **FM waiting limit before bed-lift fallback** defaults
to five minutes and is editable in minutes. It measures the sum of predicted
time from arrival at each FM lift to entry beginning, including repositioning
and the door allowance before entry. Exactly at the limit, FM remains preferred.

The planner first finds the existing preferred FM-only journey. When its wait
exceeds the limit, or no usable FM route exists, it evaluates alternatives using
FM and bed lifts. Fallback alternatives prioritise completion time over soft
destination walking-distance and preferred-lift choices. Required lift selections,
route-profile permissions, mandatory stops, payload fit, health, outages and
reservations still apply. A fallback must arrive strictly earlier than the FM
plan; ties stay FM. Empty AMR moves use the same policy.

Access windows use the simulation clock and repeat daily. Enter HH:MM times;
24:00 is accepted as an end time. An end earlier than the start crosses midnight.
Overlapping windows are rejected, including overlap with yesterday's overnight
window. Touching windows form a continuous allowance. All day is 00:00–24:00.
The complete booking, from repositioning start through final exit, must fit in
permitted time and finish by the configured simulation horizon. The search can
wait for a subsequent window. It does not move or preempt existing bookings.

These windows represent AMR capacity allowances. Individual bed movements,
clinical priorities and interruptions of committed journeys are not simulated.
The application's existing restriction on lifts with geometric motion remains.

## Stored configuration

Lift fields:

```json
{
  "usage_mode": "bed_fallback",
  "amr_access_windows": [
    {"start": "09:00", "end": "11:00"},
    {"start": "23:00", "end": "01:00"}
  ]
}
```

The building field `bed_lift_fallback_wait_sec` defaults to `300` when absent.
Missing `usage_mode` means `fm`. Settings round-trip through both lift-editing
paths, project save/reopen and undo/redo; copied configuration owns its windows.
Existing projects need no migration or changes to their saved lifts.

## Evidence and results

**Lift & Route Analysis → Lifts** shows fallback counts and, alongside each
recorded transfer, its fallback reason, bed lifts, predicted FM wait and estimated
arrival-time saving. Comparison values are **Unavailable** when no FM route
existed. Savings are planning estimates, not a second simulated baseline run.
The route inspector retains the same details, and the comparison export includes
the counts and recorded segment evidence. Counts represent distinct planned
AMR journeys, so connections do not inflate the journey count.

Project checks report structural reachability separately from daily access;
being reachable does not guarantee a slot at the requested time.

## Implementation and verification

`amr_bed_lifts` owns validation, FM-first comparison and window scheduling.
The shared journey entry point selects between private candidate plans; the
shared booking entry point enforces windows for fixed and graph-based transfers.
Only the chosen plan is materialised and booked. The policy and phase participate
in relevant cache identities. With no bed lifts, the existing planner is used
unchanged.

Focused tests cover threshold boundaries, ties, insufficient capacity, blocked
permissions, empty moves, connections, forced-floor requirements, outages,
connector reservations, window boundaries, overnight/multi-day periods, horizon
limits, competing bookings, estimate/commit parity, actual completed run evidence,
validation and editing transactions. Installation uses checked source hashes,
per-file rollback copies and automatic restoration on failure.
