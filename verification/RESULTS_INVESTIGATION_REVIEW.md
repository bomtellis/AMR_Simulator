# Results investigation checkpoint — 2 October 2026

4 October related-record update: selecting a task now offers a timeline choice
for every payload, native journey and lift identity recorded on that task's
events. Each choice shows all matching records across the saved run, including
records shared with other tasks. Returning to the task restores its own timeline.
Selected-evidence export identifies the chosen record and writes exactly that
run-wide timeline. Legacy events without a native journey ID do not gain an
invented identity. The focused investigation and quick-start tests pass (39
tests); the installed LTN log contains 9,839 events and all 206 tasks have
recorded related identities. A fresh installed LTN smoke followed all three
identity types for task `GEN_CATERING_D1_00004` and passed the run/report check.

4 October selected-evidence update: Results investigation now offers
**Export selected evidence** for the chosen task, metric or lift. It writes the
entire selected timeline across all 500-event pages, with event identities,
source rows, the run/log binding, coverage and the selected record. The
existing **Export investigation** action still writes the complete analysis.
The panel states its 250,000-event / 300 MiB input limits before a file is
opened and explains that larger files are rejected without truncation. A real
saved LTN run exported all 80 events for a selected task with exact ID coverage
and the source checksum. The focused investigation, lift, stock and partial-run
group passes 69 tests, including a 1,201-event, three-page selected export.
Parsing and analysis remain in memory within the stated limits.

4 October update: new simulation runs emit `task_pending_at_stop` records for
live tasks remaining in the pending queue. Select **pending at stop** in the
outcome filter, select a task, and read its snapshot in the details area. The
snapshot includes run status, remaining scheduled-event count, and the last
recorded candidate reason, or explicitly states that no reason was recorded.
The last candidate reason is not a diagnosis of every candidate robot. These
tasks are not failed or completed, and no completion duration is fabricated.

Full bound logs reconcile pending IDs against their saved summary alongside
completed and failed IDs. Cancellation and geometric stops retain partial
coverage. Logs without an explicit snapshot continue to show **outcome not
recorded**; missing evidence is never automatically interpreted as pending.
An earlier pending snapshot can be followed by a confirmed completion if a run
continues; a pending snapshot after a confirmed outcome is flagged as a conflict.
Repeated exports retain stable IDs without adding duplicate stop records.

Validation: 129 focused tests pass, including seven new evidence/UI cases and
existing partial-run, project, deferral, battery and payload-accounting checks.
Previously saved scale-run CSVs are not rewritten to add this new evidence.

Separate scheduled/sporadic task volumes now have linked outcome metrics. See
[Direct-event volume outcomes](DIRECT_EVENT_VOLUME_REVIEW.md) for definitions,
scope, failure-phase evidence and independent reference calculations.

Version 2 accumulated-waste evidence now covers legacy collection outcomes as
well as dynamic pools. See [Legacy waste outcomes](LEGACY_WASTE_BALANCE_REVIEW.md)
for scope, compatibility and failure/retry reference calculations.

Later stock metrics and receipt reconciliation are documented in
[Tracked-stock results evidence](TRACKED_STOCK_EVIDENCE_REVIEW.md). Open a new
fully logged run to inspect remaining stock, unmet consumption and delivery
evidence per item; older runs without receipts retain unknown stock reconciliation.

Update: D008 below was subsequently resolved by the payload service checkpoint.
See `PAYLOAD_SERVICE_REVIEW.md` for the new evidence; the old log is retained as
the historical defect reproduction and is not repaired retrospectively.

Open **Home → Results investigation** in the editor, or select a saved launcher
run and choose **Investigate Results**. Open its full `simulation_steps.csv` or
the run folder. Reading happens in the background. The workspace does not use
the editor's current project to reconstruct a historical run.

## User review

1. Open `verification/latest/ltn-investigation`. The six-hour LTN demand window
   contains 203 observed tasks and 203 recorded completions, with no failures.
   The simulator drains assigned work after the demand window as before.
2. Select a task. Review release, assignment and completion times, then select
   its event rows for recorded waits, failure explanations and route details.
   An absent release or assignment is shown as **Not recorded**, not zero delay.
3. Open **Metrics**. Selecting a metric shows its definition and contributing
   event rows. Multi-stop assignments share a journey; carried task counts do
   not multiply lift segment counts.
4. Select **Payload tracking conflicts**. LTN records two exits for one clinical
   waste container before its next entry. Inspect both contributing rows; this is
   an unresolved tracking inconsistency, not automatically a lost payload. The log supports 189
   paired transfers, but this is not a complete payload-conservation claim.
   **Payload exits without a later entry** is a separate check and is zero here.
   The affected tasks are `GEN_WASTE_D12_00122` and
   `RETURN-GEN_WASTE_D12_00122-67`, at 18,165.873 s and 18,384.547 s.
   D008 remains an open evidence/instance-tracking investigation; no automatic
   repair or claim of payload loss is made at this checkpoint.
5. Open **Run evidence**. Confirm completed/failed task sets match the final
   summary. Open an older log without its sidecar and confirm it is identified
   as legacy/partial evidence. An empty legacy log must not claim zero activity.
6. Check readability, task filtering and keyboard selection on your display.
   Export saves the investigation with its contributing records and input snapshot.

## New run evidence

Each logged event receives a run-specific stable identifier. Each committed AMR
assignment receives a journey identifier shared by a multi-stop batch. Full and
playback exports retain those identifiers. Generated task records carry their
originating rule paths; static task origins refer to the frozen input task list.

`simulation_steps.csv.run.json` binds the exported file checksum to the frozen
configuration, source-file fingerprints and recorded final completed/failed task
sets. Playback exports get their own sidecar, explicitly marked as filtered.
Keep each sidecar with its CSV when moving a run folder. This is recoverable
engineering evidence, not a tamper-proof audit system.

Legacy logs receive reproducible identifiers derived from unchanged file bytes
and row position. Missing provenance is not invented. A legacy launcher input
copy is used only if its file checksum matches the manifest, and it remains
explicitly unbound to the old log. The original `config_source` path is never
used to substitute current inputs.

The reader rejects conflicting duplicate event IDs, a file changing during read,
and rows belonging to a different run. Identical duplicate IDs are counted once
and flagged. Changed CSV/config checksums discard the bound context and final
summary rather than silently trusting them.

## Metric definitions and limits

- **Tasks observed:** distinct task identifiers in event records.
- **Completed / failed tasks:** distinct tasks with the respective terminal event.
  Conflicting outcomes are flagged and excluded from both totals.
- **Tasks without a recorded outcome:** observed or explicitly configured requests
  without terminal evidence; they are not automatically classified as pending.
- **Payload transfers:** paired exit and later entry for one physical instance at
  different locations. Initial population is not a transfer.
- **Assigned AMR journeys:** distinct assigned route plans, not completed journeys.
- **Planned lift movements:** transfer and reposition segment records, once per
  segment, regardless of the number of tasks being carried.

Route segments can be logged at assignment, ahead of execution. A segment marked
`completed` in older output is not used as proof of task completion. Wait intervals
can overlap and are not summed into an additive causal breakdown. Missing reasons,
timestamps, profiles or physical IDs remain explicit gaps.

This checkpoint reconciles completed/failed task sets against the recorded run
summary. It does not independently certify every existing PDF/CSV report metric,
reconstruct completed vehicle journeys, or prove full payload conservation.
Legacy multi-stop journeys are reconstructed only where batch evidence exists.
Logs above 300 MiB or 250,000 events are rejected explicitly. Timeline tables now
display 500 events per page, with previous/next controls and direct page selection.
All contributing records remain available in chronological order and in both
full and selected-timeline exports;
paging does not truncate evidence or alter metrics. File parsing and analysis still
retain the accepted log in memory; larger-than-limit loading remains outstanding.
Direct event-schema migration is additive;
existing report/visualiser columns remain available.

## Verification evidence

On 4 October 2026, 62 focused investigation, lift, tracked-stock and partial-run
tests passed after timeline pagination. A 1,201-event UI reference verifies page
boundaries, source-row identity, the final partial page, retained evidence and
clearing stale detail after filtering or load failure. This establishes bounded
table creation, not a measured 300 MiB load-time or memory guarantee. The full
verification pack was not rerun for this UI checkpoint.

The full test report is `latest/index.html`. New tests cover independently known
timeline arithmetic, the nine-second reference delivery, width failures, native
and legacy identities, shared movements, summary reconciliation, modified evidence,
missing events, UI links and summary-only/filtered exports.

The six-hour LTN verbose run preserved its input and retained outcome hash
`593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5` from earlier
checkpoints. Its 9,061 event rows support 203 assigned journeys and 371 planned
lift movements, in addition to the task and partial payload counts above.
The local workspace was rendered and inspected with LTN evidence.

Reproduce the integration check:

```powershell
.venv/Scripts/python.exe -m verification.investigation --config ltn.json --minutes 360 --output verification/latest/ltn-investigation
```

Pause here for user review before beginning the unified-project editing stage.
The remaining independent feature audit and the limitations above remain open.
