# Multi-stop charging — review checkpoint

**D040:** the multi-stop planner rejected a batch needing recharge, even when the
robot was already at an operational charger and a full battery could complete
the shared journey. The scheduler fell back to individual tasks.
`baseline/batch-charging-before.txt` records the reproducing failure at `49db46b`.

The batch planner now discards its insufficient-energy attempt, charges at an
operational charger and rebuilds routing and reservations at the later departure.
If a charging detour is needed, the scheduler checks reachable chargers and the
entire onward batch. A charge request retains pending tasks and reserves no
delivery resources. The serial scheduler rechecks charger availability.
Failed route attempts restore reservations, payload claims and battery counters.

Feasible deliveries retain precedence over charging detours. Among detours, a
feasible charged batch retains the existing multi-stop route-shape preference;
within that class the earliest estimated finish wins with deterministic ties.
This is a dispatch policy, not proof of fleet-wide optimality. If the shared tour
cannot fit a usable full battery, individual deliveries remain candidates.

## Review the references

1. Open [batch-charging.json](scenarios/batch-charging.json). It has two Box tasks
   from A to B and one two-slot robot at charger A with 20% initial charge.
2. Simulate. Expect **two completed tasks**, no failed or pending work, and **one
   shared AMR journey**. Both pickups occur at 242 seconds; dropoffs complete at
   249 and 251 seconds. The batch finishes at **251 seconds**.
3. In Results Investigation inspect the shared journey, charge credit and model
   battery balance. Expect **Matched**, one credit of **0.0024 kWh**, and traction
   of **0.0014266666666666668 kWh** counted once.
4. Open [batch-charge-dispatch.json](scenarios/batch-charge-dispatch.json). FIRST
   moves from charger C to A. T1 and T2 release together at 10 seconds and need
   charging. Their shared charge request sends the robot back to C; both remain
   pending until it returns for pickup. Expect **three completed tasks**, no
   failed or pending work, and a final finish at **165.8 seconds**.
5. Generate the AMR utilisation report section. Applied battery credit and the
   scheduled recharge agree for these completed references; they remain distinct
   concepts in cancelled or partial runs. Shared task energy is unallocated.

## Independent calculations

Loaded power for two 10 kg payloads on a 100 kg capacity robot is
960 × (1 + 0.35 × 20/100) = **1027.2 W**. Empty movement uses **720 W**.
The 10 m loaded route at 2 m/s consumes 1027.2 × 5 / 3,600,000 =
**0.0014266666666666668 kWh**.

| Quantity | Charge at A | Charging detour to C |
| --- | --- | --- |
| Initial battery | 0.003 × 20% = 0.0006 kWh | 0.002 × 40% = 0.0008 kWh |
| Before batch charge | No travel | FIRST: 0.000138 kWh; 1 m empty return: 0.0001 kWh |
| Charge credited | 0.003 - 0.0006 = 0.0024 kWh | 0.002 - 0.000562 = 0.001438 kWh |
| Charge duration at 0.036 kW | 240 seconds | 143.8 seconds |
| Total traction including other travel | 0.0014266666666666668 kWh | 0.000138 + 0.0001 + 0.0001 + 0.0014266666666666668 = 0.0017646666666666667 kWh |
| Final battery | 0.0015733333333333333 kWh | 0.0004733333333333333 kWh |
| Batch finish | 240 + 2 shared pickup + 5 travel + 4 dropoffs = 251 seconds | Charger arrival 10.5 + 143.8 charge + 0.5 approach + 2 pickup + 5 travel + 4 dropoffs = 165.8 seconds |

Fifteen acceptance tests cover both references before and after editor
normalisation, independent energy/timing, charge evidence and report agreement,
resource rollback, recomputed corridor/lift reservations, route-profile
restrictions, sufficient charge, reserve boundaries, full-battery infeasibility,
unreachable chargers, pure estimates, single-delivery precedence and serial
availability rechecks.

Three pre-existing rollback cases assumed depletion at charger A must reject a
batch. They now put the charger elsewhere, retaining their rejection, inventory,
lift-wear and prior-reservation assertions. New cases independently verify that
charging at A succeeds and that late failures after charging still roll back.

The full verification pack passes **579/579 tests**, with zero broken evidence
links. Both saved references complete with zero failed or pending tasks and
matching battery balances; see `latest/batch-charging-reference/summary.json`
and `latest/batch-charge-dispatch-reference/summary.json`.

The six-hour LTN regression completes **203 tasks**, zero failed and zero pending,
in **16.052 seconds**. This is an observed runtime, not a controlled performance
threshold. All **22 robot balances match**; see `latest/batch-charging-balances.json`.
The detailed outcome hash remains
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`,
unchanged from the preceding checkpoint. Frozen inputs and task outcomes
reconcile; see `latest/ltn-batch-charging/summary.json`.

## Limits and next work

Charging and traction retain the documented model-accounting timing; this does
not introduce continuous battery physics or charging losses. Batches are greedy
pickup-first tours and may be rebuilt after a charging detour as work changes.
This does not promise to lock a batch or optimise a whole fleet. Charger queues,
operational failure/recovery interactions and the wider generation-mode matrix
need further independent cases. The [full roadmap](ROADMAP.md) remains open.
