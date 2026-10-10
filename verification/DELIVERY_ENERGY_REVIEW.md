# Delivery energy — review checkpoint

**D033:** delivery plans counted corridor queues and lift travel as robot driving,
deducted lift electricity from the AMR battery, and kept the full batch weight
after a dropoff. Cross-floor trips could overdraw the battery. Lift annotations
also used the task payload during empty approaches and omitted boarding standby.
The failures reproduced against `fbea718` are retained in
`baseline/delivery-energy-before.txt`.

Traction is now calculated on each corridor or local manoeuvre using the payloads
actually onboard. Empty driving uses 75% of rated motor power; loaded driving uses
`rated power × (1 + 0.35 × min(1, onboard kg / primary capacity kg))`.
Explicit stationary waits, loading, washing and riding a lift consume no traction
under this retained approximate model. They still consume simulation time.

Lift supply is recorded once on each lift-transfer segment, including repositioning,
doors and the existing standby formula with boarding. Its `energy_source` is
`lift_supply`; traction segments use `amr_battery` in their event details.
The legacy plan `energy_kwh` remains the sum of traction and lift supply.
`amr_energy_kwh` and `corridor_energy_kwh` contain traction, including local manoeuvres.
Battery state and robot cumulative energy use traction only. Exact route commitment
must preserve the reserve; rejection rolls back energy and resource claims.

## Independent calculation and review

1. Open [delivery-energy.json](scenarios/delivery-energy.json) in the editor.
2. Check the Box is 10 kg, robot motor is 960 W, battery 10 kWh at 50%, and speed
   is 2 m/s. There are two 1 m corridor connectors and a one-floor lift journey.
3. The lift car is 1000 kg, height 3 m, efficiency 1, counterweight and regeneration
   zero. Doors take zero seconds; boarding takes 2 seconds at each end; standby is 100 W.
4. Run checks and simulate. Expect one completed task, no failures, at 00:00:10.
5. Inspect movement events using the calculations below. Raw and editor-normalised
   versions are both exercised by the automated reference.

| Quantity | Independent expectation |
| --- | --- |
| Elapsed time | Pickup 2 + corridor 0.5 + lift travel 1 + boarding 4 + corridor 0.5 + unload 2 = **10 seconds** |
| Robot traction | `960 × 1.035 × 1 / 3,600,000` = **0.000276 kWh** |
| Lift supply | `(1010 × 9.81 × 3 + 100 × 4) / 3,600,000` = **0.008367861111 kWh** |
| Journey energy | **0.008643861111 kWh** |
| Battery afterwards | `50 − 100 × 0.000276 / 10` = **49.99724%**; rounded task summaries show 50.00% |
| Queue variant | An 18-second wait before 5 seconds of loaded driving still uses **0.00138 kWh** traction |
| Two-drop batch | 5 seconds carrying 20 kg, then 5 carrying 10 kg: `960 × (1.07 × 5 + 1.035 × 5) / 3,600,000` = **0.002806666667 kWh** |

Twelve reference tests also cover empty approaches, lift repositioning, boarding,
shared batch event totals, local departure movement, estimate purity, projected
charge state, exact battery rejection and rollback after a late failure.

The full pack passes **518/518 tests**, with zero broken evidence links. The saved
reference completes one task with no failure or pending work, retains its input
snapshot, and reconciles outcomes against events; see
`latest/delivery-energy-reference/summary.json`.

Six-hour LTN completes **203 tasks, zero failed and zero pending**, in 15.707 seconds.
Its detailed outcome hash is now
`d14b1f761b262af7d875bb003e63a6bc776b52c2819ed80751b1ea7413b34cd4`;
see `latest/ltn-delivery-energy/summary.json`. Comparison with the preceding
staged-recovery checkpoint confirms identical completion identities and robot
assignments. Battery fields differ on 201 completion events. Twelve completion
times differ: four become about 72–86 seconds earlier and eight shift by at most
2 milliseconds. Recharge event counts remain 38; reduced motor consumption shortens
charging (the first AMR-C-1 charge changes from 214.043 to 109.112 seconds).
The detailed hash must therefore change; it includes energy and segment records.
`latest/ltn-energy-comparison.json` records changed completion fields.

## Boundaries of this checkpoint

This is a check of the implemented engineering approximation, not a measured
vehicle energy model. Stationary robot auxiliaries, robot own mass in lift energy,
charging losses and a complete building-electricity balance are not modelled here.
Fast assignment estimates and preliminary charging decisions still omit some
traffic and local-bay effects. A route rejected by the final energy check does not
yet trigger charging replanned from its full trajectory.

Batch task completion records repeat the shared journey energy. Sum movement
events once per journey; do not sum those task records to infer total consumption.
Full report reconciliation and old-log missing-evidence presentation remain open.
Historical logs cannot be corrected merely by opening them with this version.
The full [roadmap](ROADMAP.md) remains open. Automated checks do not constitute
human acceptance of this checkpoint.
