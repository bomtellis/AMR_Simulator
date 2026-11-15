# AMR Simulator duplication audit

The baseline was a SHA-256 snapshot of the active application checkout,
including local source changes. The initial graph covered 197 source files
before application edits. It excluded feature working copies, archived source
snapshots, run output, and virtual environments. The rebuilt graph covers the
same 197 source files and links both JavaScript workbook writers.

## Changes and evidence

| Area | Canonical implementation | Before → after |
| --- | --- | --- |
| Schedule clock parsing | `amr_sim_time_utils.parse_hhmm_to_minutes`, shared by simulation, scenario routing, task generation, and the visualiser | Four parser implementations → one |
| Heading wrap and interpolation | `amr_trajectories.normalise_angle_deg` and `angle_lerp_deg` | Four helper methods → two functions |
| Event identity and provenance | `simulator.Simulation._append_verbose_row` | Two enrichment implementations → one. The compact logger still passes an `EventValues` vector |
| Requested verbose CSV | `Simulation.write_verbose_csv` sends file-backed compact output through `amr_event_store.export_rows`. The in-memory path uses the existing CSV writer | Two serializations → one for each compact backing mode. The CSV contents and sidecar checksum matched |
| Playback and report verification | `amr_run_review.verified_events` returns the verified file and checksum | Playback plus Review had 8 → 6 Python byte-read opens on the event store. PDF generation had 6 → 5. Both still validate the run again after reading its evidence |

The 13 paired workloads covered workbench open/check/save, Simple and Detailed
simulation, scenario and stress workers, lift and human contingency studies,
Review and Playback, PDF, CSV, XLSX, historical SQLite, partial runs, and
cancelled exports. The Simple fixture produced 151 unique events, 12 completed
tasks, and 23 lift movements. The Detailed fixture produced 19 unique events
and one completed task. Decoded events matched in order, including sequence
IDs after normalization of each generated run ID. Playback states, Review
results, eight CSV outputs, three Excel chart parts, and workbook cell data
matched. All three PDF pages matched after removing only the generated-at text.

The existing 1,200-delivery benchmark completed every task before and after
with identical task-record fingerprints and 1,766,957 bytes of saved evidence.
The workflow profiles were single samples, and child-process CPU, Qt
background-thread internals, and physical disk writes were outside the Python
instrumentation. The counts describe observed application operations.

## Remaining candidates

- Compact SQLite, its evidence sidecar, and on-demand CSV serve canonical
  playback, verification, and interchange respectively. Compact report-state
  metadata also supports regeneration of historical exports. Changing these
  contracts would require reader compatibility and a format migration.
- Review still validates standalone and historical logs through its own
  sidecar and legacy fallback path. Sharing that validation with managed-run
  verification would require proving equivalent handling of incomplete and
  unverified evidence.
- The two workbook writers have similar column-letter and literal-cell
  helpers. A shared JavaScript module would require checking packaging and
  report source fingerprints. Their normalizations and workbook data pipelines
  remain independent.
- Explicit export calls can regenerate requested files, including destinations
  that have been removed. Run manifests are written at lifecycle transitions so
  cancellation and recovery can see the latest state.
