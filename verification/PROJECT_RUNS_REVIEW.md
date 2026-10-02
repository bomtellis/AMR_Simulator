# Project-bound simulation checkpoint — 2 October 2026

The editor now supports **Home → Project runs → Save, check and simulate**.
This joins saved project storage, preflight, execution and Results investigation
within the existing window. It is an incremental workflow; the full project tree,
embedded playback and report workspace are still to come.

## User review

1. Open a disposable project and select **Project runs**. Choose **Results
   location…** if required. The default is a sibling folder named
   `<project-name>_results`; outputs are never added to the `.amrproj` archive.
2. Choose **Save, check and simulate**. This first saves current edits as a project
   revision. Review findings and acknowledge warnings. Errors block the run.
   Cancelling checks removes the private draft run, but keeps the project save.
3. Run the door-pass reference scenario. Expect one completed delivery in nine
   seconds. Select its row and inspect the project/revision identifiers, software
   fingerprint and task totals, then choose **Investigate selected run**.
4. Edit the main project while a run is active. The run must continue using its
   frozen inputs. It remains linked to the earlier revision after another save.
   Opening another project or closing the editor waits until the run is stopped
   or finished; editing and saving the current project remain available.
5. Try **Stop run** on a disposable run. It must be labelled cancelled, never
   complete. Stopping terminates the simulation process and can leave partial
   event records without final evidence; do not interpret those as zero activity.
6. Move a completed run folder, then use **Locate moved run…**. The link is accepted
   only if its project identity, revision and saved configuration match this
   project's history. An unrelated project with identical geometry must not match.
7. Check the frozen `config.json`, `project_configuration.json`, checks,
   `run_manifest.json`, event CSV and its `.run.json` evidence sidecar. Change a
   copy of the inputs or checks and confirm it no longer qualifies for execution.

## Run evidence and storage

Before review, a private external draft materializes the saved revision and its
drawings. Approval records the exact checked inputs and warning acknowledgements.
Before execution the worker verifies configuration hashes, the portable revision
configuration, drawing bytes, acknowledgements and the software fingerprint.
The simulation process uses these frozen inputs, never live editor data.

Each run has a unique preparation identifier in addition to the simulator's event
run ID. New full and playback evidence include project identity, revision identity,
revision configuration hash and preparation identity. Finalization checks that
the completed simulator evidence belongs to those inputs and that preparation.
The original saved project is not consulted to reconstruct results. Older CLI and
launcher runs remain readable, with project revision shown as **Not recorded**.

The worker checks for source-file changes before execution and after simulation.
This is source fingerprinting, not a bundled executable environment or a
tamper-proof audit. Configuration and evidence hashes detect accidental changes;
they are not signatures. A completed run may contain failed tasks: completion
describes the run process, while task outcomes remain separate.

Run folders contain their own drawing copies and all simulation CSV exports,
including full and playback logs. Moving a folder retains its input/evidence
matching; the reader resolves its drawing bytes inside the moved folder. Frozen
JSON still records original runtime paths, so use the project or a fresh export
for legacy playback tools after a move. Completed runs cannot be executed again
in place; prepare a new run to keep earlier results intact.

## Evidence and remaining work

The six-hour LTN run through this workflow completed 203 tasks with no failed or
pending tasks. Completed/failed event sets reconciled, and its detailed outcome
fingerprint matched the earlier reference exactly:
`593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`.
The original LTN file was unchanged. Reproduce this using:

```powershell
.venv/Scripts/python.exe -m verification.project_runs --config ltn.json --minutes 360 --output verification/latest/ltn-project-run-ordered
```

This regression exposed D009: sorted configuration serialization changed category
iteration order and generated task IDs. Project, undo and recovery storage now
preserve that order. Existing schema-1 files remain readable, but files/snapshots
already saved in sorted order cannot recover the original order automatically.
Reimport the original JSON when comparing with a pre-storage baseline. JSON object
ordering is currently behaviourally significant to generation; removing that
dependency would require a separately verified simulator change.

`test_project_runs.py` exercises a real editor-launched child process, independent
nine-second delivery arithmetic, live editor changes, saved revision identity,
cancelled checks, stale review, external input/check/software changes, interrupted
runs, swapped evidence, moved folders and project mismatch. It also checks that
simulation outputs do not enter the compressed project archive.

Location choices and moved-run links currently last for the editor session. Runs
in the default sibling results folder are rediscovered on reopening. Persistent
external-run references inside project metadata, a full project tree, playback
integration and report generation from this workspace remain outstanding. The
existing launcher and CLI remain available, including the launcher's previously
documented machine-specific workspace setting.

Preparing drawings, checks and listing input evidence are synchronous. Large run
collections need paging/background discovery. Relinking verifies input binding;
Results investigation performs event-log integrity checks separately. Missing
or invalid candidate folders are counted and excluded from the run list.

The prior simulation verification limitations, including payload-tracking issue
D008, remain open. This workflow checkpoint does not certify the simulator.
