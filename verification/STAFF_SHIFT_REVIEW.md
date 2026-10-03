# Checkpoint 2G — travel and service across staff team boundaries

Review date: 3 October 2026. Baseline: `abd3d1d`.

This fixes the roster-selection defect reproduced in the staff report review.
The allocator now constrains the complete travel-and-handling reservation to one
four-day team block. If a free person cannot reach and finish within that block,
it replans with the incoming roster, using that team's own availability and last
location. It retains the original requested time for delay evidence. Existing
reservations, active batches and location history are not changed by rejected
candidate windows.

## Independent expectations

The reference has locations A and B 10 m apart, walking speed 1.2 m/s, and team
blocks of 345600 seconds anchored to the simulation start. The planner tests use
explicit direct-task working times or their legacy all-day default to isolate
the team boundary from daily hours.

| Reference | Expected booking |
| --- | --- |
| Team A finishes at B five seconds before its block ends; request A one second before the boundary | Incoming B starts at the boundary, finishes one second later; original request shows a one-second wait |
| The same case under each of the three movement policies | Same team and timing; outgoing roster stays at B and available at boundary minus 5 s |
| Team B has a known last location B from an earlier block | Its walk begins at the new block, arriving after 10 / 1.2 = 8.333 s; no outgoing-team location is borrowed |
| Incoming B already has a conflicting future reservation | Add B person 2 at the boundary; preserve A and the existing B booking |
| Two-second overnight service requested one second before the block ends | Start with B at the boundary rather than straddling teams |
| One-second service finishing exactly at the boundary | Permit A to finish at the boundary |
| Simulation starts at midday | Use four days from that origin, not calendar midnight |
| Another outgoing person is already at the destination and can finish in time | Use that person before deferring to B |
| Both teams have walking distances that cannot fit any work period | Stop the bounded search and expose the existing schedule-fallback flag |

The first six boundary tests were run before the fix: five failed, including all
three movement-policy subcases; the exact-finish case already passed. Nine tests
now cover the correction, bounded fallback, generated shift-pattern propagation
and group override parity in raw/editor-normalised inputs. Actual staff handling
logs are checked for team/person identity. Only committed bookings appear in the
assignment list.

Two shift-pattern option contracts now trace the category and group settings.
Explicitly staff-enabled generated tasks default to 09:00–17:00 weekday hours
for `none`, or 07:00–19:00 for `four_on_four_off_12h`. A group `none` replaces
the category's rotating pattern. The sizing model still uses two teams at the
peak on-shift count and adds staff when the chosen team is fully busy.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_staff_shift_boundaries -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/staff-shift-ltn
```

The full evidence pack passed **952 tests in 127.041 seconds**, with **zero broken
evidence links** and unchanged source hashes during testing. Both bounded LTN runs
completed four tasks with zero failed or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Local logs are in `latest/staff-shift-pack-build.txt` and `latest/staff-shift-ltn/`.
This bounded regression is not full LTN acceptance. The source `ltn.json` and its
unrelated local changes were preserved.

## Changed results and limits

A newly used incoming team has no initial location, retaining the existing
zero-travel assumption for its first booking. It can therefore begin earlier
than the incorrectly retained outgoing person's old travel plan. Returning
teams retain their location and must walk within their own block. These changes
can affect return timing and staffing counts in boundary cases; historical logs
are unchanged.

Roster search is bounded to 35 days of advancement. Impossible schedules retain
the existing `working_hours_fallback` behaviour, now visible in handling logs and
reports. Such a booking is not verified against working hours or team boundaries.
This checkpoint does not establish fixed-capacity queueing, optimal staffing,
cross-floor physical staff/lift capacity or complete utilisation.

Custom `work_days` and `rest_days` values are retained by input normalisation but
do not alter the allocator's fixed four-day cycle. Heterogeneous patterns within
one category and wider validation remain open; these are not arbitrary roster
patterns despite the stored fields.

## Next reproduced issue

Follow-up: [Checkpoint 2H](GENERATED_STAFF_HOURS_REVIEW.md) corrects the missing
generated shift metadata described below and verifies the changed return timing.

Generated legacy Stores tasks with `requires_staff` omitted correctly receive
staff under the compatibility fallback, but do not receive generated shift-time
metadata. In the return reference, requesting 60 s of staff work at t=60 gives:

- Omitted requirement: `requires_staff=None`, blank shift start, handling at 60 s.
- Explicit true: shift start `09:00`, handling at 32400 s.

Both require staff, yet only the explicit choice observes the configured global
hours. Next: reconcile effective legacy staff requirements before attaching shift
metadata, preserve explicit false and forced zone handoffs, and verify changed
return timing. Continue the general feature audit afterward; geometry, approved
UI rework and tutorial remain in their agreed order.
