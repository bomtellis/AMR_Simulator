# Deterministic sporadic demand preview — slice 2U

Baseline: `ad8311d`. The sporadic generator uses a deterministic frequency
accumulator, not random sampling. Demand Preview previously omitted these records
and reported the mode as entirely unknown. It now shows planned sporadic releases
and both components of `scheduled_sporadic`, with accrued, emitted and retained
event accounting in the rule details.

The generator also deducted a whole event before checking whether it could
represent any work. With no valid distinct route pair, that event disappeared.
It now deducts an event only when task records exist. Fractions and blocked whole
events remain available to a subsequent eligible generation poll. The reproducing
failures are recorded in `latest/sporadic-preview-before.txt`.

## Contract and independent references

Rates mean occurrences per **24 eligible elapsed hours**, not per department
working day. One occurrence creates a record for each resolved route pair; rotation
of department locations retains existing behaviour. These event and task counts
are deliberately shown separately. Emission follows the configured polling interval,
with a minimum of 60 seconds and an inclusive final partial poll. Clock-scheduled
records retain their exact calendar times. Preview follows both in chronological
order, without assigning robots or handling returns.

| Reference | Expected result |
| --- | --- |
| 36/day, two active hours, hourly polls | Three events: one at 3,600 s and two at 7,200 s; no retained fraction |
| Same rate, one active hour | One event emitted, 0.5 retained |
| Add schedules at 00:30 and 01:15 | Five records at 1,800, 3,600, 4,500, 7,200 and 7,200 s |
| Department 09:00–10:00; hourly polls from 08:00 to next-day 09:00 | 1.5 events accrue; one releases at next opening and 0.5 remains |
| 144/day over ten minutes; normal poll interval 900 s | One record at the final partial poll, 600 s |
| 1,440/day, configured interval 1 s, ten-minute horizon | Ten records at 60-second intervals |
| Three occurrences, two category route pairs | Six task records; three emitted occurrences |
| Zero frequency with no scheduled component | Explicit no-work rule with total zero |

Thirteen references in `tests/test_sporadic_preview.py` cover these calculations,
saved-scenario parity with a real simulation, input immutability, extreme-rate
guarding, raw/editor parity, retained no-route events, numerical tolerance and
runtime-dependent boundaries. A provenance reference now verifies that a zero
sporadic rate has a known zero total while retaining its origin history.

The independent expected-count calculation uses Decimal rate arithmetic for one
distinct route pair with unrestricted department hours and category dates. Other
cases show no independently computed total; the hand-calculated calendar references
still apply. Event extraction uses the existing absolute roundoff tolerance of
1e-10 event. Generator accounting is labelled separately from independent evidence.

## User verification

Import `scenarios/sporadic-preview.json`, open **Demand preview**, and build the
preview. Inspect the five tasks and hourly timetable. In **Rules**, select Stores
for department D: three sporadic events should be accrued/emitted and zero retained,
with an independent expected count of five including the two schedules.

Run the saved reference with full logging. Its runtime staggering is explicitly
zero, so the five generated event times match the preview exactly. In another copy,
end at 01:00 and remove the scheduled times: one record and a retained fraction of
0.5 should be visible. Generated records are not proof of completed transport.

The full verification pack passed **1,117 / 1,117 tests in 129.512 seconds**,
with **zero broken evidence links** and unchanged source hashes during execution.
The focused preview, provenance, calendar and stock suites passed 81 tests.
Evidence is in `latest/sporadic-preview-focused.txt`,
`latest/sporadic-preview-pack-build.txt` and `latest/evidence.json`.

Both bounded 60-minute LTN demand-window runs completed four tasks with no failed
or pending tasks and unchanged outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/sporadic-preview-ltn/`. This is bounded regression evidence, not full
LTN acceptance. Unrelated working changes to `ltn.json` remain outside the commit.

## Boundaries and next work

Preview times precede configured runtime release staggering and resource waits.
Returns and additional tracked-stock replenishment keep overall demand unknown.
Hybrid/threshold demand remains runtime-dependent; the interaction between hybrid
fill-volume and immediate-event components still needs its own audit. A retained
event does not promise a post-horizon retry or a feasible physical route.

The preview retains its 31-day and 20,000-record limits, adds a 100,000 sporadic
poll-evaluation limit across rules, and rejects extreme projected counts before
generating them. It never silently truncates the planned table.

Continue hybrid mode and inventory interaction verification, then the remaining
core workspace/geometry work, approved CAD UI workflows and tutorial gates.
