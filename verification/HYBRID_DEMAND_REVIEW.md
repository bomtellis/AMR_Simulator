# Hybrid demand conservation — slice 2V

Baseline: `c7ed9ac`. A one-hour hybrid rule with 0.4 m³ of continuous demand and
one discrete 0.4 m³ event generated three 0.4 m³ task records. The discrete event
was dispatched directly and also added to the threshold pool. The resulting
1.2 m³ of represented work exceeded the intended 0.8 m³ of combined demand.
The original failures are in `latest/hybrid-generation-before.txt`.

## Changed-result contract

Hybrid now has two independent components:

- `base_daily_volume_m3` fills the continuous pool. Each complete threshold
  creates one threshold collection, retaining any remainder.
- `frequency_per_day` accrues deterministic events. Each whole event creates
  direct sporadic task records with `volume_per_event_m3`; it does not also fill
  the threshold pool.

Both rates retain their per-24-eligible-hour units. The existing valid-route-pair
multiplicity still applies to direct events. Department closure delays release
but does not discard either accumulated component.

Threshold and scheduled-threshold modes still use frequency events as bin fill.
In scheduled-threshold waste, clock-scheduled fills and frequency fills remain
separate configured contributions. The fix does not remove either of these inputs.

Existing hybrid configurations with positive frequency and event volume can
generate fewer threshold collections after this correction. Compare historical
runs using their saved inputs and software identity. If two deliberately distinct
services are required, define separate rules rather than depending on duplicated
volume within one event.

## Editing and explanations

Mode help is shared between Demand Preview and the category, bulk-department,
individual waste-stream and bulk waste-stream editors. Hybrid preview still has
unknown runtime demand, but its explanation describes the two components.
Category and bulk-department editors now show frequency and event-volume inputs
in threshold modes; previously the active runtime inputs were hidden there.
Plain scheduled waste disables frequency, which does not affect that mode, while
keeping event volume editable. Changing modes retains the stored values.

## Independent references and review

Twelve tests in `tests/test_hybrid_generation.py` cover raw/editor parity,
zero-base and zero-frequency cases, fractional retained volume, department closing,
threshold and scheduled-threshold compatibility, a full simulation, preview
explanation and all four editor paths.

For a one-hour reference, `base_daily_volume_m3 = 9.6` contributes 0.4 m³,
`frequency_per_day = 24` contributes one 0.4 m³ event and the threshold is 0.4 m³.
Expected: one threshold task plus one direct task, totalling 0.8 m³. With base rate
zero, only the direct event remains. With base rate 4.8, the direct event remains
0.4 m³ and the continuous pool retains 0.2 m³ without another collection.

Import `scenarios/hybrid-demand.json` and run with full logging. This ordinary
transport reference completes two tasks without failures. Inspect the generated
task reasons: one sporadic and one threshold. Open Demand Preview to review the
mode explanation, then open the generation editor and switch between threshold,
hybrid and scheduled modes to inspect the active controls and mode help.

The full verification pack passed **1,129 / 1,129 tests in 131.444 seconds**,
with **zero broken evidence links** and unchanged source hashes during execution.
The focused hybrid/sporadic/calendar/waste/editor suites passed 53 tests.
Evidence is in `latest/hybrid-generation-focused.txt`,
`latest/hybrid-generation-pack-build.txt` and `latest/evidence.json`.

Both bounded 60-minute LTN demand-window runs completed four tasks with no failed
or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/hybrid-generation-ltn/`. This is bounded regression evidence, not full
LTN acceptance. Unrelated local `ltn.json` edits are outside this checkpoint.

## Remaining boundaries

The accumulated-waste evidence covers hybrid's continuous threshold pool. Direct
sporadic and ordinary scheduled task volumes still need their separate outcome
accounting; they must not be added to that pool or described as confirmed disposal.
The ordinary transport reference does not prove physical waste-bin availability,
washing, returned-container timing or mixed-service inventory capacity.

Continue direct-event outcome accounting and inventory interactions, then the
remaining workspace, geometry, approved CAD UI and tutorial stages.
