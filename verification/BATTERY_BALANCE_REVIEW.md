# Battery input and model balance — review checkpoint

**D039:** an in-place pre-task recharge filled the battery but its exported charge
segment recorded zero input. `baseline/battery-charge-input-before.txt` reproduces
this against simulator commit `9436cdf`: expected **0.0009 kWh**, observed **0**.
The segment now records the planned input. New applied-charge events and final
robot summaries separately reconcile energy actually credited by the model.

This verifies model bookkeeping. Delivery traction is deducted at route commitment;
in-place charging is credited during that commitment. Separate charge cycles credit
at completion. Planned charging is never substituted for an applied credit.
Charging efficiency is implicitly 100%; this is not measured electricity demand
or a continuous physical battery trajectory. Lift electricity remains separate.

## Review the saved reference

1. Open [required-charge-dispatch.json](scenarios/required-charge-dispatch.json).
   Run checks and simulate its two deliveries with one robot.
2. Open Results Investigation. Expect **two completed tasks**, zero failed and
   zero pending. Select **Applied battery charging (kWh)** to inspect its credit
   event, and **Model battery balance: R-1** to inspect all balance records.
3. Expect **Matched** and the following independently calculated values.
4. Generate the **AMR utilisation** report section. Check the scheduled recharge
   summary and the separate recorded model battery balance table.

| Quantity | Independent expectation (kWh) |
| --- | --- |
| Initial battery | 0.002 × 40% = **0.0008** |
| First loaded delivery | 960 × 1.035 × (1/2) / 3,600,000 = **0.000138** |
| Empty travel to charger | 960 × 0.75 × (1/2) / 3,600,000 = **0.0001** |
| Battery at charger | 0.0008 - 0.000138 - 0.0001 = **0.000562** |
| Applied charge | 0.002 - 0.000562 = **0.001438** |
| Empty approach after charging | **0.0001** |
| Second loaded delivery | 960 × 1.035 × (10/2) / 3,600,000 = **0.00138** |
| Total traction | **0.001718** |
| Final battery | 0.0008 + 0.001438 - 0.001718 = **0.00052** |

At 0.036 kW, the recharge lasts **143.8 seconds**. Separate tests cover the in-place
charge defect: initial 0.0001 + applied 0.0009 - traction 0.000276 = final 0.000724 kWh.

Full balance requires a checksum-bound finished full log, explicit energy and
battery capabilities, one final summary per expected robot and valid attributed
records. Credits and movement totals must also agree with final model counters.
Absolute balance tolerance is 1e-9 kWh; counter comparisons additionally allow
1e-9 relative tolerance. A mismatch is shown explicitly. Missing capability,
missing robot summaries and cancelled runs remain **Not established**. Valid
partial observations remain inspectable without claiming a complete balance.
Repeated native event IDs count once; conflicting duplicates are rejected.

Twelve acceptance tests cover both charging mechanisms, raw/editor-normalised
reference inputs, report/investigation agreement, known zero, cancelled charging,
rejected route rollback, missing credits, incomplete coverage, altered final state,
duplicate/conflicting events and repeat exports.

The full pack passes **564/564 tests**, with **zero broken evidence links**. The
saved reference completes **2 tasks**, with zero failed or pending, and establishes
the exact balance above. Its two-page report was rendered and visually inspected;
the reviewed example is `latest/battery-balance-reference/battery-review.pdf`.
Small energy values retain six significant figures in both report tables.

The six-hour LTN regression completes **203 tasks**, with zero failed or pending,
in **16.081 seconds** (an observation, not a performance threshold). All **22 robot
balances match**; total applied charging is **3.931007709822394 kWh**. The largest
absolute residual is approximately 7.11e-15 kWh, below the stated tolerance.
Its detailed outcome hash is unchanged from the preceding checkpoint:
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`.
Frozen inputs and task outcomes reconcile. See `latest/ltn-battery-balance/summary.json`
and `latest/battery-balance-comparison.json` for the recorded evidence.

## Remaining scope

Direct batch charging, charger contention and operational-failure boundaries need
further independent cases. Stationary auxiliary consumption, charging losses and
continuous battery state are not added by this checkpoint. Full report metric
reconciliation and the [remaining roadmap](ROADMAP.md) stay open. Automated
results do not constitute human acceptance.
