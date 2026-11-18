# Demand day schedule and FM arrangements

Open **Task generation → Day schedule**. The same graphical editor is available in
**FM logistics planning → Day schedule**.

## Editing demand

Select **Demand** to edit the original demand schedules. Each category has separate
lanes for its configured groups and independent department rules. Shared groups
appear once. Disabled schedules are hidden until **Show disabled** is selected.

- Drag a timeframe bar to move the whole window; drag either end to resize it.
- Drag a scheduled-time marker to move its release. Markers have no duration.
- Gestures move in five-minute steps. The selected schedule's **Start / release**
  and **End** fields accept exact HH:MM values; **Set times** applies them.
- Select any visible schedule using the selection list for keyboard editing.
  Left/right arrows on the timeline move its selected item by five minutes.
- **Escape** cancels a drag before it changes the draft.
- **Ctrl-click** toggles additional bars or markers; **Shift-click** selects a
  chronological range within/across schedules. **Ctrl+A** selects every editable
  item in the current view. Selected bars have a stronger outline and a selection
  count. Drag any selected bar, or use left/right arrows, to move the selection
  together while preserving spacing and window lengths.
- A multi-selection always moves as a whole; resize a single bar to change its
  length. Invalid moves are rejected together, including collisions with an
  unselected clock release or an FM cohort leaving its dispatch window.
- Configured-group and independent department notes appear directly beneath their
  names. Category-wide notes appear under the category header. Notes wrap fully and
  increase that row's height. Overlapping continuation lanes show the notes once.
- **Service day** filters the recurring schedule. Edits affect every active day;
  they do not create weekday exceptions. Fortnightly recurrence is shown in the
  selected schedule details. Linked pieces at midnight represent one window.
- Use **Zoom** or **Fit day** to adjust the view. Overlapping releases occupy
  separate lanes so each remains selectable.
- **Open settings…** opens the existing group/department editor. Waste-stream
  timing stays in the existing Departments editor; changes opened through the
  demand dialog remain in its draft until the outer dialog is saved. Department
  identities must be renamed through the main Departments workflow.

Saving the demand dialog applies one undoable edit; save the project to retain it
on disk. Cancel discards its changes.

## Daily stacked demand preview

Choose **Day schedule → Demand preview…** to open a separate, resizable window.
The preview shows a stacked bar chart of planned trips across the day. Each colour
represents a category; the legend includes that category's daily total. The complete
chart remains fixed at the top while the category counts and notes scroll below it.
The editable day schedule's time ruler also stays fixed when its rows scroll.

- Choose an actual **Preview date** within the simulation period. Recurrence and
  department opening hours use the existing demand generator and the original run
  start, including fortnightly schedules and overnight work.
- **Hourly** bars are the default. Select **30 minutes** or **15 minutes** for more
  detail. Hover a bar for its interval total and category breakdown.
- Edits to schedule bars refresh the open preview automatically. **Adjust category
  in schedule** selects and reveals the corresponding editable schedule or FM window.
- Add **Category notes** in Parameters → Notes & help, or use **Save notes** beside
  the selected category in Day schedule. These notes belong to the whole category;
  existing department/group notes remain separate and are also included in the preview.
- **Save PDF…** writes a landscape document with the stacked chart, matching legend,
  counts and all configuration notes. Long category tables continue onto numbered pages.
- **Save PNG…** writes a high-resolution image of the full chart and every category,
  including notes outside the visible area. Exports follow the selected time interval.

Each planned transport request counts as one trip. Load units are shown separately.
Returns, accumulation and inventory-triggered work can add trips; these categories
are marked as having additional/variable demand rather than being assigned invented
fixed totals. This preview does not claim the actual number of batched AMR journeys.
Inputs that change during calculation cannot replace a newer preview or be exported
as if they were current. Closing the preview does not save or alter the project.

## Suggesting an arrangement

1. Choose **Suggest arrangement**. The existing FM planner generates cohorts and
   windows for all eligible categories and compares sequences across shared lifts.
   It uses the project configuration together with this dialog's current demand
   and department drafts.
2. Review the totals and select an arrangement. Ranking minimises unresolved work,
   late work, peak lift occupancy, then lift waiting. If none improves the original
   timing, **Current Task Generation timings** remains selected.
3. In **FM plan** mode, original demand appears as outlines. Filled bars are FM
   dispatch windows and markers are cohort releases. Moving a window retains its
   offsets; resizing must keep every release inside the window.
4. After manual adjustments, choose **Compare arrangements** again. Calculated
   results become stale when their inputs change. **Discard FM draft** returns to
   the accepted plan without changing native demand.
5. **Use arrangement** validates actual demand and operating calendars. In the
   demand dialog it accepts the plan into the draft; save the dialog and project.
   In the FM planning screen it applies through the existing project command;
   save the project to retain it.

Plans use the existing `task_generation.fm_logistics` format and do not rewrite
native demand times, quantities, frequency, group membership, or routing settings.
**Disable FM plan** restores native release behaviour. If native timing changes
invalidate a plan's slot references, regenerate or disable the plan before saving.
Missing department assignments must be resolved in the FM planner's existing
Planning settings review.

Runtime-dependent demand is identified rather than assigned invented windows.
The existing forecast estimates lift use and arrivals. Full fleet/staff queues
remain outcomes of normal simulation, not guarantees of an optimisation result.

## Engineering and verification record — 17 November 2026

Application: the existing Windows PySide6 AMR Simulator. This is a bounded panel
addition using its palette and native controls, following the Engineering Studio
central-workspace direction. Existing forms, domain generators, FM algorithms,
project format, export formats, and controller/undo boundaries remain authoritative.
No dependency or schema migration is required.

The dialog adds optional full-project and draft-department callbacks, preserving
existing constructor callers. Draft adapters live in `amr_demand_schedule` and the
shared Qt panel in `visualiser.day_schedule`. Worker inputs are deep-copied and
results are checked against project, demand, department and plan snapshots.

Baseline: 30 existing generation-settings, configured-group and FM tests passed
before changes. Final regression run: **193 tests passed** across 17 relevant test
modules, including 24 new schedule tests and the latest return-priority checks. Evidence is recorded in the staged
`verification/day-schedule/regressions.json`.

| Acceptance check | Result and evidence |
| --- | --- |
| Move, resize, snap, exact edits, cancellation | Pass: adapter tests plus real Qt mouse/keyboard gestures |
| Group identity, compatibility endpoints and independent schedules | Pass: group edits and generation regression tests |
| Save/reopen and project Undo/Redo | Pass: integrated application tests for demand and FM edits |
| FM shared calculations and no automatic application | Pass: comparison equality, all-category suggestions and draft-only tests |
| Stale jobs, invalid windows and missing assignments | Pass: snapshot rejection, validation and assignment tests |
| Normal and enlarged layout | Pass: Qt-rendered LTN demand and FM fixture at 100%, and 150% with 12-point text |
| Keyboard alternative to custom canvas | Pass: native selection list, exact-time fields and arrow/Escape interaction |
| Screen-reader certification / mixed-monitor transition | Not performed; native alternative controls are present |
| Full optimiser or simulator changes | Not applicable; existing forecast and runtime contracts are reused |

The rendering harness registers a Windows system font because the offscreen Qt
plugin has no system font database, and uses explicit desktop dimensions. Screenshots
are generated from actual widgets, not mockups. Packaging into a new standalone
executable is not part of this source update. Restart the source application after
installation. The installation manifest records exact original and updated hashes,
and the backup directory contains the three replaced application files.

### Stacked preview verification — 17 November 2026

The follow-up adds the pop-out chart, whole-category notes, fixed chart/ruler and
complete PNG/PDF exports without changing generation or FM scheduling algorithms.
The daily counts reconcile with the existing generator; interval aggregation preserves
every category total. Tests cover midnight boundaries, fortnightly recurrence, FM
release shifts, live edits, notes persistence without group detachment, stale results,
complete exports and multi-page PDFs.

The final combined run passed **210 tests**, including 17 new preview tests. Qt-rendered
screenshots and PNG exports were inspected at normal scale and at 150% with enlarged
text. Landscape PDFs, including a long-notes pagination fixture, were rendered using
Poppler and visually reviewed. Evidence lives in `verification/day-trip-preview` in
the staged workspace. Source hashes are checked before installation, and originals
are backed up separately from the first timeline update.

### Group notes and multi-selection verification

The row layout now uses measured note heights for painting, hit testing and
selection navigation. Batch moves update an isolated draft once, including adjacent
scheduled times that would collide if moved individually. FM windows carry their
cohorts once even if both the window and cohort marker are selected. Ctrl/Shift
selection, keyboard moves, actual mouse dragging, Escape, midnight wrap, invalid
batch rejection and unchanged group membership/notes are covered by 10 additional
tests. The combined regression run passed **220 tests**. A rendered Qt preview of
wrapped group notes and multiple selected releases was visually checked.
