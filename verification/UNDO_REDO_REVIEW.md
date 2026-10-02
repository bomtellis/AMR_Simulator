# Undo and redo checkpoint — 2 October 2026

The editor now has a shared in-memory configuration history. Use **Edit → Undo /
Redo**, **Ctrl+Z**, **Ctrl+Y**, or **Ctrl+Shift+Z**. Buttons name the next available
operation. Saved project revisions and simulation outputs remain separate.

## User review

1. Open a disposable project and move a corridor node through several positions
   in one drag. Undo once: it should return to its starting coordinates. Redo
   once: it should return to its final coordinates. Selection and panning are
   not project edits and should not consume undo steps.
2. Delete a node with connected edges. Undo must restore the node and its edges
   together. Try adding a node, connecting a corridor, changing door width and
   editing a route profile. Check the configuration as well as the drawing.
3. Change simulation settings, AMRs, payloads or demand rules. Close the settings
   window, then undo and redo the completed changes. A modal management session
   is grouped as one operation; nested callbacks do not create extra steps.
4. In the task editor or planner, save your changes and close its window before
   undoing. Undo is intentionally unavailable while an editor, placement, boundary
   drawing or drag is unfinished. Finish or cancel that operation first.
5. Undo and then make a different edit. The old redo branch must disappear.
   Cancelling a dialog or changing display options should keep redo available
   when it makes no configuration change.
6. Save the project, make an edit and undo back to the saved values. The unsaved
   indication should clear. Undoing an edit that was already saved should show
   unsaved changes, while the file on disk remains unchanged until the next Save.
7. Open Project checks, make and check an edit, then undo it. Findings should
   immediately become stale. Demand preview uses the same configuration-change
   checking. Undo never rewrites saved simulation events or results.
8. Save as `.amrproj`, then undo a preceding configuration edit. Drawing mappings
   should still resolve to the packaged drawings. Opening another document,
   recovery or saved-revision restore starts a new undo history.

## Implementation and evidence

Completed editing operations feed a shared compressed-snapshot history, allowing
existing dialogs and model methods to remain in use. Nested operations are grouped.
Canvas drags commit on release. A two-second idle check catches otherwise untracked
direct configuration changes; immediate Undo also captures a pending change before
stepping back. Such changes use the label **Configuration changes**. This is an
incremental integration, not a wholesale conversion to individual command objects.

Snapshot history is limited to 100 changes and a 32 MiB compressed budget. Older
steps expire first; the current snapshot is always retained even if it alone
exceeds that budget. The button tooltip reports expired steps. New edits discard
the redo branch. No-op operations preserve it. Normal saves retain history;
packaging drawings updates historical runtime paths to their cached equivalents.

The acceptance suite covers independently expected coordinates, node/edge restore,
door and profile edits, settings, nested operations, interrupted edits, no-ops,
branching, limits, keyboard shortcuts, save/dirty-state behaviour, drawing
packaging, project boundaries, stale checks and recovery of the current undone
state. Existing verification tests remain in place.

## Limits and subsequent work

Undo history is session-local and is not stored in `.amrproj` or recovery snapshots.
Use saved revisions across sessions. External changes to drawing-file bytes,
simulation outputs, exported files, selection and viewport state are not undone.
Open modeless task windows group changes until they close; per-row command history
is not yet available. A failed operation that partially changed configuration can
be undone, but automatic transaction rollback is not claimed.

Storage and snapshot compression remain synchronous. Contextual human-readable
property comparisons, a full project tree, the unified simulation workflow,
project-to-run revision binding, result relinking and faster corridor editing
remain outstanding. Existing simulation limitations, including D008, remain open.
