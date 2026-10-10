# Shared-journey energy — review checkpoint

**D038:** each multi-stop task repeated the whole shared journey's energy, and the
transport matrix summed those task records. Two tasks could therefore report twice
the journey energy. Missing lift energy in legacy reports also became zero.
`baseline/shared-energy-before.txt` records the reproduced task-record defect
against commit `52e5980`.

Shared task records now have `energy_kwh: null`, `lift_energy_kwh: null` and
`energy_basis: shared_journey_not_allocated`. Their explicitly named
`journey_energy_kwh` and `journey_lift_energy_kwh` preserve the shared totals.
No arbitrary per-task allocation has been invented. Transport-matrix groups
containing shared journeys leave total task energy blank and name that basis.
Its existing `trips` column counts task transfers, not distinct AMR journeys.

Results Investigation and report analysis now use the same movement-energy
ledger. Each native event ID is counted once, regardless of how many tasks it
names. Conflicting duplicate identities are rejected. Explicit source attribution
separates robot traction from lift electricity. Charging input is excluded, so
adding battery recharge to traction cannot double-count this movement ledger.

An energy total is established only with a complete, checksum-bound full log,
the `segment_energy_sources_v1` capability, and valid attribution on every relevant
movement. Missing, mismatched, negative or non-finite energy leaves that source
unknown. Known zero requires the same evidence. Attributed observations remain
available separately in incomplete logs and are not presented as full-run totals.

## Review the saved project

1. Open [shared-journey-energy.json](scenarios/shared-journey-energy.json).
   T1 and T2 each carry a 10 kg Box from A to B on one two-slot robot.
2. Run checks and simulate. Expect **two completed tasks and one assigned AMR
   journey**, containing one lift transfer. There are no failed or pending tasks.
3. Open Results Investigation. Select **Planned AMR traction (kWh)** and **Planned
   lift supply (kWh)** to inspect their contributing movement event IDs.
4. Generate the **Lift usage** report section. The source table and lift table
   should agree with the following calculation. The reviewed example is
   `latest/shared-energy-reference/energy-review.pdf`.
5. Inspect `transport_matrix.csv`: two task transfers, blank energy, and
   `shared_journey_not_allocated`. This does not mean zero energy.

| Quantity | Independent expectation |
| --- | --- |
| Onboard mass | **20 kg**, two payloads |
| Corridor movement | Two 1 m connectors / 2 m/s = **1 second** |
| Traction power | 960 × (1 + 0.35 × 20/100) = **1027.2 W** |
| AMR traction | 1027.2 / 3,600,000 = **0.000285333333 kWh** |
| Lift supply | (1020 × 9.81 × 3 + 100 × 4) / 3,600,000 = **0.008449611111 kWh** |
| Shared journey total | **0.008734944444 kWh**, counted once |
| Task-specific energy | **Not allocated**, for both tasks |

Twelve references cover the independent balance, raw/editor-normalised projects,
task and transport output, matching investigation/report values, duplicate and
conflicting events, absent/invalid attribution, legacy and incomplete logs,
checksum mismatch, known zero, and visibility of small energy values.

The PDF was rendered and visually inspected. Energy values use six significant
figures so small values remain visible without splitting across table lines;
underlying calculation and investigation evidence retain their precision.

The full pack passes **552/552 tests**, with zero broken evidence links. The saved
reference completes **2 tasks, zero failed and zero pending**, with frozen inputs
and outcome-event reconciliation intact; see `latest/shared-energy-reference/summary.json`.

Two six-hour LTN runs each complete **203 tasks, zero failed and zero pending**.
Completion identities, timestamps, assignments and battery values match the
previous checkpoint; only run-specific identifiers differ in completion events.
The detailed outcome hash changes because shared completion energy is now scoped
explicitly and lift-reposition segments carry explicit zero supply attribution.
Both new runs have hash
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`.
The first took 22.416 seconds alongside the full pack; an isolated repeat took
16.115 seconds. These are observations, not a controlled performance threshold.
See `latest/ltn-shared-energy/summary.json`, `latest/ltn-shared-energy-repeat/summary.json`
and `latest/ltn-shared-energy-comparison.json`.

LTN's complete movement ledger establishes **8.311817324286864 kWh AMR traction**
and **7.688514302600464 kWh lift supply**, with no missing attribution records.

## Remaining scope

These are recorded **route-plan** energy totals, not measured execution or a full
building electricity balance. Planned movements can be logged before execution.
Stationary AMR auxiliaries, charging losses, battery input/output reconciliation,
per-task allocation rules and complete report metric reconciliation remain open.
Historical logs are not rewritten or upgraded merely by opening them. For legacy
logs the report shows **Not established**, even if older numeric energy fields exist.
The [full roadmap](ROADMAP.md) remains open; automated results do not constitute
human acceptance of this checkpoint.
