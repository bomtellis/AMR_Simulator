# JSON import workflow — 4 October 2026

Open a supported `.json` file with **File → Open project / JSON**. The file
remains editable even when field validation finds issues. The main workspace
shows a scrollable **import validation** panel with every issue; it no longer
opens a modal validation warning. Edit the affected inputs and choose
**Recheck**. **Hide** collapses the panel; **File → Validate JSON** rechecks and
restores it if issues remain. Run **Project checks** before simulation. Use
**File → Save project as** to create a portable `.amrproj`, then reopen it to
confirm the corrected fields.

The new workflow test imports a JSON configuration with an invalid task
pickup, shows the issue inline without a modal warning, hides and restores it
through Validate JSON, corrects the task, rechecks, saves an archive, and
reopens the supported 4.25 m floor-height field. The project storage,
workspace, check, lifecycle and CAD group passes 86 tests. At 1100×760 the
inline panel occupies 154 px of height in an offscreen Qt rendering; the
underlying graph remains visible. This is a layout check rather than physical
screen or accessibility approval.

Malformed JSON syntax and unreadable files still report a fatal open error
without replacing the current project. The panel reflects the import or last
recheck; it does not silently revalidate every keystroke. This closes the
inline validation part of checkpoint 4's import workflow, not the wider
project-delivery gate. Previous archive migration is recorded separately in
`ARCHIVE_MIGRATION_REVIEW.md`.
