# Charging travel, capacity and energy — review checkpoint

Charging travel now reserves corridor and node capacity, including both horizontal
legs of a lift journey. It consumes the robot's empty-travel motor energy and
calculates recharge duration from the battery energy remaining on arrival.
Lift energy is recorded separately as infrastructure consumption.

A charger may be reached using energy below the normal battery reserve threshold,
but a trip requiring more than the available battery is rejected. Charger selection
considers energy reachability: a reachable charger with a longer wait can be chosen
over an earlier but energy-infeasible destination. Rejection restores touched state.

## Project for review

Open [charging-travel.json](scenarios/charging-travel.json), save a disposable
project and simulate. One robot starts at A with 50% of a 10 kWh battery. It delivers
a 10 kg box to B over a 10 m corridor, then returns to A for opportunity charging.
The charger provides 2 kW; the robot travels at 2 m/s with 960 W rated motor power.

Inspect playback and the charge interval against these independent calculations:

| Stage | Expected result |
| --- | --- |
| Delivery | Pickup 2 + travel 10/2 + dropoff 2 = **9 seconds**. |
| Delivery energy | Existing loaded-power model: 960 × (1 + 0.35 × 10/100) = 993.6 W; 993.6 × 5 / 3600000 = **0.00138 kWh**. |
| Opportunity charging starts travelling | Checks every 60 seconds; the 60-second idle requirement is first met at **120 seconds**. |
| Return travel | 10/2 = **5 seconds**; arrival at **125 seconds**. Empty power is 0.75 × 960 = 720 W; energy is **0.001 kWh**. |
| Recharge | Missing energy = 5 + 0.00138 + 0.001 = **5.00238 kWh**; /2 × 3600 = **9004.284 seconds**. |
| Finish | **9129.284 seconds**, with 100% battery, one completed delivery and no failures. |

The saved-project evidence is in `latest/charging-travel-reference/`. Its frozen
inputs and task summary/events reconcile. Both raw and editor-normalised versions
are tested. This small case intentionally omits local charger-bay manoeuvres.

## Defects and reference scope

- **D022:** charging trips did not reserve horizontal corridors. Two robots could
  use a single-capacity 10 m corridor simultaneously. With zero spacing and node
  clearance in the reference, they now finish at **5 and 10 seconds**.
- **D023:** charging travel used no battery energy, gave insufficient-battery
  robots a route, and understated recharge time. Motor energy is now consumed
  once; energy annotations reconcile with travel segments. Lift supply energy
  is recorded once on the transfer segment, including reposition/standby overhead.
- **D024:** the legacy recharge helper emitted unhandled events and never filled
  the battery. It now delegates to the working charge-cycle scheduler.

Twelve tests cover capacity, energy, log totals, finite battery boundaries, waiting,
alternative chargers, cross-floor travel, rollback after energy consumption,
legacy scheduling and the review project. A cross-floor reference verifies
0.5 + 1 + 0.5 = **2 seconds**, **0.0002 kWh** of motor energy and
1000 × 9.81 × 3 / 3600000 = **0.008175 kWh** of lift energy under its explicitly
unit-efficient, zero-counterweight, zero-standby model. Lift energy does not reduce
the AMR battery on these charging trips.

Before-fix results are retained in `baseline/charge-travel-before-fix.txt`.
The full local verification pack passes **419/419 tests**, with zero broken
feature-to-test links; see `latest/index.html` and `latest/evidence.json`.
The six-hour LTN run remains **203 completed, zero failed and zero pending**, with
unchanged detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
Input preservation and task reconciliation pass; runtime was about 14 seconds.
See `latest/ltn-charge-travel/summary.json`. This bounded result does not imply
that charging-heavy projects retain their former results.

## Remaining limits

Empty traction power remains the existing 75% approximation, not a measured motor
curve. Explicit waiting and lift travel consume no AMR traction energy; stationary
auxiliary loads and charger efficiency are not modelled here. Charger-bay local
manoeuvres, physical lane trajectories and arrival-time occupancy semantics need
further work. Selection still uses existing graph/lift searches, not an exhaustive
search over all energy-feasible paths.

Delivery routes retain legacy lift-energy/battery attribution and require a
separate reconciliation audit. Charging failures still use legacy failure records;
complete separation of operational failures from delivery outcomes, charging
journey identities and all report-energy totals remain open. The transaction
protects route planning, not later exceptions while publishing assignment events.

The subsequent [exchange checkpoint](EXCHANGE_CLAIMS_REVIEW.md) verifies exclusive
empty-bin claims. The full [roadmap](ROADMAP.md) remains open.
The earlier unexplained preview-process interruption is still recorded in
`baseline/multi-stop-verification-observation.txt`. Automated warning
acknowledgement does not record human review.
