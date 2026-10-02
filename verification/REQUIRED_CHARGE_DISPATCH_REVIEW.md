# Required charging away from a charger — review checkpoint

**D036:** an idle robot above its reserve threshold could leave work pending
indefinitely when its battery was insufficient for a delivery. The scheduler now
recognises an explicit route-energy charging request, checks reachable compatible
chargers and full-battery onward routes, then schedules charging separately.

An already feasible delivery is selected before a charging detour. A robot must
be idle, the task released, and robot locks and exchange holds respected. Each
configured charger is considered, including alternatives to an unusable nearest
charger. The serial scheduler rechecks availability and commits the selected
destination. It does not remove the task or claim its payload/destination during
charging. After charging, ordinary assignment evaluates the pending work again.

If energy insufficiency is discovered only while committing a delivery, its
reservations are rolled back before charging is considered. If no charger can be
reached with the current battery and support the onward task, a pending reason is
recorded; read-only attempts do not emit repeated charging failures. A reachable
intermediate charger can make a long approach feasible even when the uninterrupted
approach plus delivery exceeds full-battery range.

**D037:** availability inspection also cleared stale charger-bay markers. It is
now read-only. Serial reservation or arrival performs cleanup; real occupants and
reservations still prevent claiming their bays. This matters when alternative
charger plans are examined or estimates run concurrently.

Reproduction evidence: `baseline/required-charge-dispatch-before.txt` against
`a1e8e3d`, and `baseline/charger-estimate-mutation-before.txt` before its correction.
The latter was found while adding charger-bay interaction cases to this checkpoint.

## Review the saved project

1. Open [required-charge-dispatch.json](scenarios/required-charge-dispatch.json).
   This uses a deliberately tiny battery to make the engineering calculation easy.
2. Verify C is the charger; C–A is 1 m, A–B is 10 m, speed is 2 m/s, motor power
   960 W, and Box weighs 10 kg against a 100 kg capacity.
3. Battery capacity is 0.002 kWh, initially 40%, charging power 0.036 kW and reserve
   1%. Opportunity charging and automatic idle return are disabled.
4. Run checks and simulate. FIRST moves C→A immediately. LONG is released at
   10 seconds and moves A→B after required charging.
5. Inspect the `route_charge_required` event for LONG: its details link the
   0.00138 kWh required traction, 0.000662 kWh available battery and chosen charger C.

| Quantity | Independent expectation |
| --- | --- |
| FIRST duration | 2 + 1/2 + 2 = **4.5 seconds** |
| FIRST traction | 960 × 1.035 × 0.5 / 3,600,000 = **0.000138 kWh** |
| Battery after FIRST | 0.0008 − 0.000138 = **0.000662 kWh**, above the 0.00002 kWh reserve |
| Trip back to charger | 0.5 seconds; 720 × 0.5 / 3,600,000 = **0.0001 kWh** |
| Recharge | (0.002 − 0.000562) / 0.036 × 3600 = **143.8 seconds** |
| Charging interval | **10.5 to 154.3 seconds** |
| LONG pickup | 154.3 + 0.5 empty travel + 2 loading = **156.8 seconds** |
| LONG arrival | 156.8 + 5 loaded travel + 2 unload = **163.8 seconds** |
| Final battery | (0.002 − 0.0001 − 0.00138) / 0.002 × 100 = **26%** |
| Battery balance | Initial 0.0008 + charged 0.001438 − consumed 0.001718 = **0.00052 kWh** |

Thirteen tests cover this calculation and raw/editor-normalised input, event
evidence, pure estimates, infeasible charging, occupied/stale bays, feasible-work
preference, busy/future/locked work, charger alternatives, intermediate charging,
and a local-movement shortfall found during route commitment.

The full pack passes **540/540 tests**, with zero broken evidence links. The saved
reference completes **2 tasks, zero failed and zero pending**; frozen inputs and
outcome-event reconciliation pass. See
`latest/required-charge-dispatch-reference/summary.json`.

Six-hour LTN completes **203 tasks, zero failed and zero pending** in 15.740
seconds. Its detailed result hash is unchanged:
`d14b1f761b262af7d875bb003e63a6bc776b52c2819ed80751b1ea7413b34cd4`.
See `latest/ltn-required-charge-dispatch/summary.json`.

## Remaining scope

Charger and onward feasibility remain estimates; traffic, local bay movement and
other work can change before commitment. Each committed route is checked again.
Charging makes the robot available for ordinary assignment; it does not promise
exclusive assignment to the task that triggered charging. Direct batch charging,
optimal fleet-wide charging, charging losses and complete report energy allocation
remain open. A currently unavailable charger is a pending constraint, not a proof
that all future charging is impossible.

The [full roadmap](ROADMAP.md) remains open. Automated warning acknowledgement
does not constitute human acceptance of this checkpoint.
