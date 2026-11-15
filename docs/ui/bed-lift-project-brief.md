# Bed-lift controls: implementation brief

- Application: existing Windows AMR Simulator, Python 3.13 / PySide6.
- Audience/tasks: hospital logistics design; identify bed lifts, assign daily
  AMR access, tune FM queue tolerance and inspect fallback usage.
- Scope: extend existing native lift/building dialogs and lift results. Preserve
  the current shell, theme, drawing commands and asynchronous analysis lifecycle.
  Individual bed demand and clinical dispatch are outside this feature.
- Authoritative state: project configuration and simulation model. Existing
  editor transaction boundaries own save/cancel and undo/redo. Display the wait
  limit in minutes; store seconds. Window editing uses labelled HH:MM cells,
  Add/Remove actions and an explicit all-day checkbox.
- Compatibility: missing mode remains FM; empty bed windows prohibit AMR use.
  No changes to existing CSV columns; extra evidence lives in segment details.
  Both canvas and lift-list editing preserve the new fields and transfer mode.
- Layout: retain existing scrollable dialogs, fixed Save/Cancel controls and
  platform theme. Bed access controls enable only for bed mode. Results use the
  existing scrollable table; unknown FM comparisons display Unavailable.
- Accessibility: native combo, checkbox, spin box and editable table controls,
  descriptive accessible names, keyboard selection and focus, no colour-only
  state. Validate errors before applying changes.
- Verification: focused transaction/keyboard tests and rendered native screens
  at 100% and 150% scale. Evidence is retained under outputs/bed-lift-fallback
  in the implementation workspace. Screen-reader and mixed-monitor hardware
  testing are not claimed.
- Deployment: verified staging copy, baseline hash checks, rollback manifest;
  no project reclassification and no writes to synced reference files.
