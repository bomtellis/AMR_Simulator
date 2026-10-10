# Checkpoint 2H — working hours for generated legacy staff tasks

Review date: 3 October 2026. Baseline: `011e04b`.

Generated tasks now carry their effective global shift definition independently
of whether the staff choice is explicit or omitted. Previously `_base_task`
attached working times only when `requires_staff` was true. The simulator later
recognised omitted Stores choices through its compatibility fallback, but missing
time metadata made those jobs appear to have all-day staff availability.

The generator still preserves the distinction between omission and false. Merely
carrying shift metadata does not allocate staff: explicit false remains unstaffed,
as does omission for an ordinary non-Stores delivery. A physical department zone
handoff still forces staff. Legacy direct/static tasks with no generated shift
metadata retain their existing all-day compatibility behaviour.

## Independent acceptance and changed results

Eight tests in `tests/test_generated_staff_hours.py` cover raw/editor parity,
effective starts, ends and weekdays, group pattern selection, custom weekly hours,
staff choice preservation, zone enforcement and full simulation return records.
The mismatched omission cases were reproduced before the fix.

The reference outbound journey releases at 60 s and arrives at 69 s, from
2 s pickup + 10 m / 2 m/s + 2 s drop-off. With default 09:00–17:00 weekday staff
hours and three minutes of handling:

| Staff choice | Handling | Return starts |
| --- | --- | --- |
| Omitted on generated Stores rule | 09:00–09:03 | 09:03:00 |
| Explicit true | 09:00–09:03 | 09:03:00 |
| Explicit false | No staff booking | 69 + 60 = 129 s, or 00:02:09 |

The former omission result was 00:04:09 because the job incorrectly started staff
handling immediately after arrival. Both raw and editor-normalised input now
produce the corrected return and a 180-second staff handling record.

Additional references establish:

- Tuesday-only global hours starting at 10:00 defer a Monday request to Tuesday
  10:00, or 122400 s from the Monday midnight origin.
- A 30-second service requested at t=50 cannot fit a Monday 00:00–00:01 period;
  it waits until the next Monday at t=604800.
- A group rotating pattern carries its 07:00–19:00 definition, while explicit
  custom Monday 11:00–15:00 hours take precedence for the actual booking.
- Explicit false and non-Stores omission produce no staff pool, even though the
  generated task carries the hours needed if its effective requirement changes.

The existing saved [return/import scenario](scenarios/generation-return-import.json)
is tested unchanged through both input paths. Its omitted staff choice and zero
explicit handling duration use the one-minute return delay as the legacy handling
duration. Its corrected return starts at **09:01:00**, then finishes at **09:01:09**
on the inherited Clean route. The earlier 00:02:09 result in checkpoint 2C is
historical. The independent route/delay-only test now explicitly disables staff
to keep measuring arrival-relative delay and route duration separately.

Three global pattern fields now have traced contracts: `start_time`, `end_time`
and `days_active`. Shift-pattern contracts and feature dispositions have been
updated without promoting broader staffing or generation behaviour to complete.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_generated_staff_hours -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/generated-staff-hours-ltn
```

The full pack passed **960 tests in 126.969 seconds**, with **zero broken evidence
links** and unchanged source hashes during testing. Both bounded LTN runs
completed four tasks with zero failed or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Local outputs are `latest/generated-staff-hours-pack-build.txt` and
`latest/generated-staff-hours-ltn/`. The source `ltn.json` and its unrelated
working changes were preserved. This is bounded regression evidence, not full
LTN acceptance.

## Boundaries and next work

Follow-up: [Checkpoint 2I](STAFF_CALENDAR_REVIEW.md) aligns the global switches
and effective legacy staff choice used for timeframe release spreading. The
remaining broader calendar and validation limitations below stay explicit.

Existing projects relying on the accidental all-day treatment can now wait for
staff hours and return later. Keep frozen historical runs for comparison. This
correction does not rewrite saved input, materialise an omitted staff flag, move
fixed scheduled task releases or change the purpose of the initial staff count.

Generation release-spreading still checks explicit `requires_staff`, and the
global `enabled` switch currently participates in generation-window logic rather
than the runtime working-period calculation. Their intended user-facing behaviour
must be reconciled before claiming a unified staff calendar contract. Custom
work/rest cycles, mixed schedules, broad input validation and complete utilisation
also remain open. Next checkpoint: audit the global staff switches and timeframe
release rules, documenting or correcting inconsistencies with focused references.
Then continue the remaining general feature audit and original roadmap.
