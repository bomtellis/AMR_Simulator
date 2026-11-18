# Run organisation

The Simulate panel shows saved and memory runs together in a table with Name, Date and time, Storage, Status and Note columns. The default order is newest first. The Date order control also offers oldest first. Dates use recorded creation times and display in the computer's local time zone. Older missing links can recover their date from the original run identifier; unknown dates stay at the bottom.

Select a row and choose **Edit name and note...**, or double-click it. Save applies the changes; Cancel leaves them unchanged. Notes support multiple lines. Full notes appear in the selected-run details and the Note column tooltip. Blank names restore the default label. Names are limited to 200 characters and notes to 10,000 characters.

Names and notes for saved runs are stored with their stable run references in the AMR project. They survive reopen and explicit relinking, including when a run folder is temporarily unavailable. Editing a discovered run also links it to the project. These metadata saves preserve unsaved model changes and do not create a configuration revision or change recorded run files.

Memory runs retain their names and notes for the lifetime of the run. **Save run** carries them into the saved project. Discarding an unsaved memory run discards its annotations with its results.

## Implementation and compatibility brief

This is a scoped update to the existing PySide6 Simulate panel. A native table replaces the dense one-line list; native palette styling and the existing simulation, playback, investigation, route-analysis, report and relink handlers remain authoritative. The table keeps the existing selection adapter used by tutorials and workflow tests. Selection is restored by the run object or folder identity when dates are reordered or rows refreshed.

Optional `user_name`, `note` and `created_at` fields extend external-results references. Existing project archives without these fields still open. Stable IDs, configuration revisions, event stores, simulation calculations, run directories and report verification rules retain their existing roles. No startup migration or automatic rewrite of prior run folders is performed.

## Verification and limits

Automated coverage checks mixed saved/memory chronological order, stable actions after reordering, annotation save/cancel, multiline notes, persistence, missing and discovered links, relinking, memory-to-disk publication, failed metadata writes and preservation of unsaved model edits. Existing memory-run, persistent-link, project-run and workspace suites also passed.

Native offscreen previews were inspected at 1200 and 900 logical pixels with Segoe UI, including selected rows and the edit dialog. Labels, dates, storage and status remain visible; long names and notes can be read through tooltips and the selected-run details. Logs are bounded and the run table receives available height. Full screen-reader, high-contrast, mixed-display and translation certification is outside this change.

The guarded installer records checksums and backs up each replaced source file. Rollback restores those files; no user run folders are renamed or removed.
