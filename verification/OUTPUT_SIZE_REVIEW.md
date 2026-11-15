# Simulation and stress output size

New normal and stress runs share the version-3 event store. Each event retains
its identifiers, original values and types, field presence, full-precision time,
sequence and playback flag. Sparse JSON is compressed in batches of at most
1,000 events or approximately 1 MiB of uncompressed data; an individually larger
event occupies its own block. Event identifiers, exact times and filter columns
remain indexed in SQLite. Only one decoded block is cached, independent of total
run size. Block and event-index writes share a savepoint, including retry after
an insertion failure. Speculative events remain staged until their reservation
transaction commits. Event-type filters, streaming exports, rollback and recovery
of a committed prefix remain available. Defaults are shared per schema and event type;
additional repeated location, journey and source identifiers are interned.
Reporting-state chunks use level-6 lossless compression.

Investigation and project Playback read the canonical store without creating
`simulation_steps.csv` or `visualiser_steps.csv`. Their row adapter preserves the
existing exported CSV strings and columns. Investigation retains its 250,000-event
limit; its 300 MiB file limit applies to CSV inputs. The event-count check rejects
larger SQLite logs before loading them into the viewer.

PDF, lift and department report readers now stream the exact legacy CSV bytes
through the existing pandas parser without writing an expanded event file.
Column order, quoting, Unicode, numeric inference and missing-value handling
remain the same. The stream closes the database when finished or abandoned.
This removes both the retained full CSV copy and its temporary disk footprint
during report generation. Explicit exports and the `verified_inputs` compatibility
API still produce the original CSV format, which can exceed 2 GB.

Historical CSV and formats 1 and 2 of SQLite evidence remain readable. Storage versions and
event counts are checked against the hash-bound evidence. Existing outputs are
not modified or deleted automatically.

## Recorded LTN measurement

`benchmark_output_size.py` re-encoded all 238,466 events from the existing
`ltn_results/run_20261012_202248_2f6_trf6/simulation_steps.csv.sqlite` into a separate
benchmark copy. It also recompressed the saved report-state chunks. The source
was opened read-only. Hashes of every decoded event, sequence, full-precision time
and playback flag matched exactly.

| Measurement | Bytes | MiB |
| --- | ---: | ---: |
| Original store (format 1) | 406,777,856 | 387.93 |
| First optimisation: per-event compression (format 2) | 154,337,280 | 147.19 |
| Current bounded batch compression (format 3) | 55,083,008 | 52.53 |

The current store is 64.31% smaller than the first optimisation and 86.46%
smaller than the original. Its full CSV representation is 327,809,260 bytes
(312.62 MiB). Both stores produced the same CSV byte count and SHA-256 while
streaming, with no CSV file written. Reports now avoid retaining that extra copy.

Re-encoding and both event hash passes took 26.224 seconds locally; comparison
of both full CSV streams took another 17.991 seconds. These are storage benchmarks,
not simulation execution-time comparisons. The first optimisation's results are
in `output-size-ltn-benchmark.json`; current results, event hash and full CSV hash
are in `output-size-v3-benchmark.json`. The disposable benchmark database is removed
after verification to avoid retaining another large output.

`analyse_output_storage.py` compared compression choices on 20,006 events sampled
across the run. Higher per-row compression saved little; layout dictionaries
helped, but bounded blocks saved substantially more. Level-3 block compression
was chosen for its size/time tradeoff. Raw probe timings are in
`output-size-compression-probe.txt`.

## Regression coverage

Checks cover exact legacy CSV exports, report reconstruction, normal/stress
execution, partial evidence and playback, committed-prefix recovery, compressed
Unicode values and types, precise timestamps, event/playback filters, staged
rollback, old uncompressed stores, cancellation, and direct-reader equivalence
without file creation. The first optimisation passed 154 tests, recorded in
`output-size-focused-tests.txt`. The original 238,466-event LTN run also passed
the existing-run verification boundary as a complete format-1 store.

The format-3 follow-up adds coverage for byte/count block boundaries, gapped
event sequences, cached-value mutation, failed-flush retry, large speculative
stages, legacy format-2 BLOBs, streamed CSV byte equivalence, chunked pandas dtype
equivalence, complete report tables, real lift movement/energy evidence,
department review equivalence, and actual PDF generation without an event CSV.

- Storage/report suite: 75 passed (`output-size-v3-report-tests.txt`).
- Reader/partial-run suite: 78 passed (`output-size-v3-reader-tests.txt`).
- Stress execution, baseline reuse and study-file suite: 62 passed
  (`output-size-v3-stress-tests.txt`).

## Reduced stress data and study history — 13 October 2026

Stress Setup now offers Full data (the existing default) and Reduced data.
Reduced trials use format 4 and reference a full format-1/2/3 normal-operation
baseline by path and SHA-256. Baseline event occurrences are matched within each
event type, so inserted scenario-only events do not shift all subsequent matches.
Changed fields use typed, data-only patches; new or substantially changed events
use the ordinary sparse representation when smaller. SQL retains event sequence,
precise time, type and playback selection. Report state and completed-task chunks
also use baseline patches where smaller than independent compressed records.
Readers reconstruct the same full evidence; this does not enable reduced logging.

References are relative where possible. Opening reduced evidence requires the
original baseline checksum; missing/modified baselines and reference chains are
rejected. The source baseline stays read-only. A matching existing compact normal
run can be reused; otherwise the study runs a full baseline once. Existing studies
without a data-mode setting retain full-data behavior. The storage choice is frozen
with the study settings. Previous output files are not automatically converted.

`benchmark_reduced_data.py` encoded the existing LTN combination trial
`stress-b85fca194165/runs/run_20261013_054452_7i3pdi3s` against its normal baseline
`run_20261013_054327_qc5m951r`. Both originals were opened read-only.

| Trial database | Bytes | MiB |
| --- | ---: | ---: |
| Full compact format 3 | 55,480,320 | 52.91 |
| Reduced format 4 | 37,785,600 | 36.04 |

This is a **31.89%** additional reduction for this trial, excluding the shared
baseline retained once per study. Of 240,601 events, 142,690 used baseline patches.
Compressed report payloads fell from 7,992,860 to 3,428,602 bytes. All decoded
events, precise times and playback flags matched; the 332,389,630-byte CSV stream
also matched byte for byte. Report payloads reconstructed exactly. Encoding plus
event verification took 178.882 seconds; CSV verification took another 40.056
seconds while other tests were running. This is not a simulation runtime benchmark;
reduced mode trades additional comparison/read work for disk savings, which vary
with the disruption. The disposable benchmark database was removed afterwards.
Machine-readable evidence is in `reduced-stress-ltn-benchmark.json`.

The Previous studies view discovers adjacent study files and backups and remembers
external study paths in a project-local history index. It shows status, saved trial
count, storage mode, date and location; missing indexed files remain visible. No
recursive scan of run outputs is needed. The real LTN project displayed six existing
studies/backups. Rendered setup and history screens were inspected in
`reduced-stress-setup.png` and `reduced-stress-history.png`.

Validation: **206 tests passed** across four final suites:

- 95 storage/report/stress regression tests (`reduced-stress-regression-tests.txt`).
- 25 stress UI tests (`reduced-stress-ui-tests.txt`). This diagnostic run also logged
  one transient Windows sharing error in an existing cancellation test's polling
  callback; its cancellation/resume assertions and the suite completed successfully.
- 24 dialog workflow tests (`reduced-stress-workflow-tests.txt`).
- 62 reduced-data, integrity, baseline-reuse, history, partial-run, playback and
  investigation tests (`reduced-stress-final-tests.txt`).

New tests cover inserted events, sequence gaps, nested speculative rollback,
typed nested data, exact filters/timestamps, report-state patches, relocation,
missing/tampered baselines, forbidden dependency chains, real disruption exports
and service metrics, persistent worker/resume behavior, normal-run reuse, legacy
study settings, saved-file discovery, and mode/history UI actions.

## Selected stress tests in PDF reports — 13 October 2026

The project report panel now includes a stress-trial checkbox selector spanning
multiple saved studies. The stress Results tab also opens this report workflow.
Users may select individual trials or whole studies and see affected assets,
outcomes and added delay before confirming. The optional Stress-test comparison
section includes each study's baseline, selected outcomes and disruption windows.
Normal reports retain their previous default sections. The comparison can also
be inserted into an existing PDF through the existing supplement workflow.

`amr_stress_report.py` verifies frozen study identity, selected trial inputs,
baseline compatibility and metrics recomputed from canonical events. It accepts
historical recorded software without allowing changed settings or results, and
rechecks source hashes after PDF generation. Reduced stores are read directly;
no full event CSV is materialized. The report manifest records selection and
source checksums; a compact JSON comparison snapshot accompanies the PDF.

Validation covered **100 distinct tests**: 50 in `stress-report-regression-tests.txt`
and 61 in `stress-report-ui-final-tests.txt`, with 11 shared tests. Tests include
multiple-study selection, duplicate merging, explicit exclusions, frozen-input
differences, historical reused baselines, missing reduced-data baselines,
tampered/replaced/running studies, changes during generation, actual background
report generation and request cleanup, PDF outlines, and existing-PDF insertion.
Existing report layout, storage, stress selection and resume checks passed.

An example under `output/pdf/stress-test-selection-example/report.pdf` uses two
selected trials from `Lift stress.stress.json` (one passing and one failing) and
one from `ltn.stress.json`. The four-page PDF is 10,724 bytes. All pages were
rendered with bundled Poppler and visually inspected; tables, headings, source
references, page numbering and linked contents were legible without clipping.
Every outline destination was checked against its actual page heading. The
selector was also rendered and inspected (`stress-report-selection.png`).
Original simulation/stress evidence and existing PDFs were retained unchanged.
