# Recovery and unsaved-work checkpoint — 2 October 2026

Project lifecycle update (4 October 2026): the Project history panel now tells
users to keep the editor open if Save fails and explains that Recovery copies
opens an available snapshot as unsaved work to save under a new filename. An
application-level check saves two project revisions, closes and reopens the
window, restores the first revision, captures another edit, forces an atomic
save failure and confirms the last valid archive remains byte-identical. A
second editor opens that recovery snapshot and saves a distinct portable
project without changing the original. Fifty-five focused project/recovery/
workbench tests pass. Recovery still depends on a successful prior capture.

The editor now tracks unsaved configuration changes, offers Save / Discard /
Cancel before opening another file or closing, and captures a separate recovery
copy every 30 seconds while edits are pending. Saved project history is unchanged.

## User review

1. Open a disposable example JSON or `.amrproj`. Change floor height or another
   configuration value. Within two seconds the title and filename show **Unsaved
   changes**. Saving clears that indication; exporting JSON does not save an open
   project's edits or clear its indication.
2. Try opening another file. Choose **Cancel** and confirm your edits remain.
   Try closing and cancel again. Choose **Save** while opening another file and
   confirm the original received the edit. Cancelling the Save filename dialog
   must also cancel the pending open/close.
3. Make a new edit and leave all modal dialogs closed for at least 30 seconds.
   Hover over the filename to see the last recovery time or a failure message.
   Recovery waits until a drag or modal editing operation has finished.
4. Choose **Home → Recover unsaved work** and select the latest copy. Confirm
   its time and source filename. If replacing a workspace with edits, choose
   Cancel first to check it remains intact; repeat and choose Discard to recover.
5. Recovery opens as an unsaved document with drawings initially hidden. Use
   **Load configured drawings** to inspect them, then save under a new filename.
   Confirm the original source is unchanged. A JSON save writes its drawings to
   a durable adjacent folder; a project save embeds them.
6. Open a second editor, edit the same disposable source externally, and try
   saving from the first editor. A detected external change must block overwrite.
   Save as a new project or export a new JSON to preserve your edits.

No forced crash is needed for this manual review. The automated suite starts a
separate process, commits a snapshot, exits abruptly without normal cleanup and
checks that the next process can recover its independent expected value.

## Recovery contract

Recovery lives under Qt's per-user generic data location in
`AMR Simulator/recovery` (normally `%LOCALAPPDATA%` on Windows), separately from
the project. Each editor session owns a separate atomic snapshot; sessions never
overwrite each other's snapshots. Drawings are compressed, content-addressed and
shared across snapshots. Only configured DXF/PDF underlays are collected; external
simulation outputs are excluded.

Snapshots include configuration, source filename/checksum, project revision ID
when available, capture time and drawing warnings. A missing or unreadable drawing
does not lose the rest of the configuration: its original path and a warning are
retained. Available drawings are copied and checked on recovery. Malformed or
checksum-mismatched snapshots remain visible as unreadable and are not loaded.
Recovery never writes back to the source automatically, and changed or missing
source files are reported when the copy opens.

Successful save/open and deliberate Discard on close clear only this session's
snapshot. Cancel and failed save/open preserve pending edits and recovery copies.
Reverting all edits to the saved configuration clears this session's older copy
at the next recovery interval. Older sessions' snapshots remain available even
after recovery; shared drawing assets are retained to avoid deleting data needed
by another session. Automatic retention cleanup and a recovery-management panel
are outstanding, so this folder may grow as new drawing versions are edited.

## Evidence and limitations

`test_recovery.py` covers independent recovered values, abrupt process exit,
original drawing removal, missing-drawing warnings, corrupt data, unsupported
versions, failure to replace snapshots, isolated sessions, Save/Discard/Cancel,
changed source files and durable drawing export after recovery.

Capture and restore remain synchronous. A crash can lose changes made after the
last successful capture; long modal edits and active drags postpone capture.
An unchanged configuration does not trigger another capture, so changes made to
external drawing files alone are not monitored. Recovery is not a backup against
loss of the computer or user profile. Drawing members are limited to 256 MiB,
each snapshot to 512 MiB of unique expanded drawings and 32 MiB of metadata.

[Undo and redo](UNDO_REDO_REVIEW.md) now supplies a shared completed-edit history.
A full individual-command model, project-to-run revision binding,
result relinking and the unified simulation workflow remain outstanding. Existing
simulation verification limitations, including D008, remain open.
