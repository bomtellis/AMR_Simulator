# Checkpoint 2M — accumulated demand across polling boundaries

Later correction: [Hybrid demand](HYBRID_DEMAND_REVIEW.md) prevents discrete
events from also filling the hybrid threshold pool. Threshold and scheduled-
threshold event-based filling is retained. The original checkpoint below is
historical evidence with its stated scope.

Review date: 3 October 2026. Baseline: `827cf9b`.

Dynamic volume/event generation now integrates eligible elapsed time before
deciding whether a task can release at the current poll. A poll at department
closing or on an inactive category date retains demand accrued during the earlier
eligible interval. Previously it advanced the contributor timer and discarded
that demand. Long intervals also used only the current category date, potentially
counting closed weekdays or skipped fortnight blocks.

Eligible time is now the intersection of category weekday/fortnight eligibility
and department opening periods throughout the interval. Volume and event fractions
remain stored when the current poll is closed. A later eligible poll can release
pending work even if no additional demand accrued since the last poll. Repeating
the same poll does not duplicate work.

## Independent calculations

Rates retain their existing units: per **24 eligible elapsed hours**, not
automatically per department working day. For example, a rate of 24 m³/day adds
1 m³ during one eligible hour. Eight eligible hours would add 8 m³, not 24 m³.

| Reference | Independent expected result |
| --- | --- |
| Department 09:00–10:00, poll at 10:00, rate 24 m³/day | 1 m³ retained, no closed-time release; next-day 09:00 poll releases one 1 m³ collection |
| Same hour, sporadic frequency 36/day | 1.5 events retained; next opening releases one and retains fraction 0.5 |
| Two eligible hours, 24 fill events/day, 0.3 m³/event, threshold 0.5 m³ | 0.6 m³ accrued = one 0.5 m³ collection + 0.1 m³ residual |
| Seven-day poll interval, Monday-only category, rate 1 m³/day | 1 m³ accrued, not 7 m³ |
| Fourteen-day interval with alternating active/skipped weeks, rate 1 m³/day | 7 m³ accrued, not 14 m³ |
| Ten minutes at rate/frequency 144 per day, final poll before the usual 15-minute interval | One threshold/sporadic task releases at t=600 and completes in the full reference simulation |

Partitioning a polling interval can change when tasks release, but the reference
collected-plus-residual total remains the same. This is not a claim that congested
simulation results or resource waits are independent of polling frequency.

Decimal arithmetic also needed correction: 0.6 m³ divided into 0.2 m³ collections
previously produced two records and left a numerically under-threshold remainder.
Threshold equality now permits relative floating-point error of 1e-12, with zero
absolute tolerance; the remainder is clamped at zero after subtraction. Integer
event extraction permits absolute roundoff of 1e-10 event, so ten 0.1 increments
produce one event. A genuinely underfilled reference (0.2 minus 1e-8 m³) remains
uncollected. These are numerical tolerances, not physical fill margins.

## Mode behavior and input checks

Continuous mode retains accumulated volume but does not itself dispatch
volume-triggered collection tasks. Threshold and hybrid provide that trigger;
tracked-item exchange has its separate consumption path. Demand Preview now
states this distinction instead of only saying that the total is unknown. The
continuous reference verifies stored volume and zero invented collections.

Shared raw input validation now checks `base_daily_volume_m3`,
`frequency_per_day`, `volume_per_event_m3` and `threshold_volume_m3`. Supplied
values must be finite and non-negative; numeric strings remain accepted while
booleans, null, negatives and non-finite values are rejected before import/runtime
normalisation. Zero is permitted and disables the relevant rate or threshold
trigger. Eight option contracts cover category and group-payload paths.

## Acceptance and review

Twelve tests in `tests/test_accumulation_calendars.py` cover the calculations,
closed-time backlog, category weekdays and fortnight blocks, polling partitions,
decimal boundaries, malformed rates and final-partial-poll simulation dispatch.
The initial calendar/conservation reproductions failed before the correction;
local output is retained as `latest/accumulation-before.txt`.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_accumulation_calendars -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/accumulation-ltn
```

The full verification pack passed **1,015 tests in 127.786 seconds**, with **zero
broken evidence links** and unchanged source hashes during execution. Local
outputs are `latest/accumulation-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining the baseline outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/accumulation-ltn/`. This demonstrates bounded regression
repeatability, not complete LTN acceptance. Unrelated local `ltn.json` edits
were preserved.

For manual review, use a project copy with the one-hour department and threshold
reference above. Compare an active-period run with one ending exactly at closure,
then extend to the next opening. Retained accumulation must not be mistaken for
completed transport or physical stock; releases still require an eligible poll.

## Limits and next action

This slice verifies dynamic single-pair volume/event rules. Shared waste pools,
multiple-pair collection semantics, legacy waste generation, tracked-item
consumption/reset behavior and full hybrid-mode interactions remain open. The
general configuration inventory and engineering release gate remain incomplete.
Historical simulation results are preserved for comparison with frozen inputs.

Next: audit shared waste accumulation and collection thresholds, including
department overrides, conservation and the remaining legacy generator path.
Keep the major UI rework and tutorial after the core engineering gates.
