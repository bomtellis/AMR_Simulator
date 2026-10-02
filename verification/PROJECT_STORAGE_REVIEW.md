# Portable project storage checkpoint — 2 October 2026

This is the first part of the unified project release. It adds portable storage
and saved revision restore to the existing editor. The simulator and launcher
continue to accept JSON; use **Export JSON** to provide their input.

## User review

1. Open a disposable JSON example with **Home → Open project / JSON**. Choose
   **Save project as** and save an `.amrproj` file. Required drawings must exist;
   repair missing paths before saving. Opening without drawings skips rendering,
   but still preserves and packages their bytes on project save.
2. Move this project to another folder. Open it without its original drawings
   and check the floor underlays and alignment. LTN floors 3 and 4 currently use
   the same DXF, whose bytes are stored once.
3. Change a setting and choose **Save**. Open **Project revisions**, select an
   earlier revision and **Compare with current edits**. Configuration differences
   include the embedded drawing identifiers.
4. Make another edit without saving, then choose **Preserve edits and restore
   selected revision**. Check the earlier values are restored and the previously
   unsaved edit appears in its own saved revision. Restore that to recover it.
5. Choose **Export JSON**. A JSON file and adjacent drawings folder are produced.
   Open the JSON in the existing launcher. Export leaves the open project and its
   history unchanged. Exported paths are absolute for existing tool compatibility;
   export again after moving the project to another computer.
6. Check readability and keyboard operation on your display. The revision panel
   stays open while editing; press Compare again to refresh its difference view.

## Storage contract

Version 1 is a compressed ZIP containing a manifest, canonical configuration
snapshots and SHA-256-addressed drawing bytes. Only `floor_dxf_files` and
`floor_pdf_underlays` collect external files. Results folders, CSV logs and report
files are never collected. Snapshots retain all other configuration data.
Opening a project materializes drawings in a temporary cache for the renderer;
persistent snapshots use portable internal references.

Unchanged saves do not add revisions. Restore appends history and preserves
current edits first. Saves flush a temporary file on the destination volume, then
replace the destination. Failed write/replace preserves the old file and session
history. JSON saves also use atomic replacement. Checks before replacement detect
external changes to an already-open project; this is not a multi-user locking
protocol or a tamper-proof audit.

The reader verifies configuration/drawing hashes and revision links, rejects
duplicate or unexpected archive entries and never extracts arbitrary paths.
Limits: 256 MiB per member, 512 MiB expanded data, 512 MiB archive size and 10,000
entries. Unknown format versions are refused without changing the file. JSON
import explicitly enters schema version 1; there is no older project schema yet.

## Evidence and remaining work

`test_project_storage.py` covers portability, deduplication, revision restore
including unsaved edits and historical drawings, independent expected values,
failed saves, external modifications, malformed archives, editor integration
and export. The unchanged original JSON is also checked.

Run the real-project measurement with:

```powershell
.venv/Scripts/python.exe -m verification.project_storage --config ltn.json --output verification/latest/ltn-storage
```

This saves a review copy without changing LTN. `storage.json` records size,
deduplication and one local save/open timing sample. Open timing excludes drawing
rendering. Large saves/opening run synchronously in the editor; responsive progress
and cancellation remain to be added.

The local LTN sample stored 227,733,904 bytes of unique drawings plus configuration
in a 15,140,327-byte archive. Six drawing references shared five stored drawings.
Save took 1.877 s and open 0.316 s; the configuration roundtrip matched and source
bytes were unchanged. These are single-machine measurements, not performance guarantees.

Recovery and unsaved-change prompts are now covered by the next
[recovery checkpoint](RECOVERY_REVIEW.md). Global undo/redo,
history pruning, project-to-run revision bindings, relinking results and a single
simulation/review workflow remain outstanding. Revisions recover saved work;
they do not recover edits lost before a save. All retained revisions contribute
to archive size. Previous project caches remain until editor shutdown so
background drawing readers can finish safely.

Earlier verification limitations, including LTN payload-tracking defect D008,
remain open. This checkpoint does not complete the simulator acceptance gate
or verify geometric traffic.
