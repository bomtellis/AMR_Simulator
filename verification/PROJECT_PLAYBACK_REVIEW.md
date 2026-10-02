# Project playback — review checkpoint

Completed project runs can now play inside **Review → Playback**. The map,
timeline, task navigation and lift/payload monitors reuse the existing visualiser.
The standalone visualiser remains available with its original file-loading path.

## Try this checkpoint

1. Open a saved `.amrproj`, choose **Simulate**, and select a completed run.
2. Choose **Playback selected run**. The heading identifies the saved revision
   and number of timestamped events. Loading and input checks run in a background
   worker. Incomplete, modified or reduced evidence is rejected.
3. Use **First Move**, **Play**, the time slider or a click on the timeline.
   **Jump to Task** and **Failed Tasks** retain the existing navigation.
   The timeline's **Fit** option fits the simulation window; zoom in to inspect
   short activities. Scroll vertically to see additional robots.
4. Change floors, use **Fit View**, or scroll the control column to follow a robot
   and change playback speed. Controls and timeline remain usable at 1280 × 800.
5. Use **Lift Monitor** or **AMR Payload Monitor**. Leaving Playback pauses the
   run and closes its auxiliary dialogs. Returning does not restart playback.
6. Choose **Investigate this run** to inspect supporting records, or **Next** to
   report on the played run. A different selection in Simulate does not silently
   substitute another run for the report.
7. Make an unsaved layout/configuration change and return to Playback. The run
   still uses its original geometry and inputs. Opening another project clears
   playback. A late worker completion cannot restore the previous project's run.

![Reference playback with the shared project navigator](images/project-playback-reference.png)

![LTN playback with the embedded timeline](images/project-playback-ltn.png)

## Independent checks and evidence

`tests/test_project_playback.py` adds 18 acceptance cases. On the reference path,
the robot loads for 2 seconds, then travels from (0, 0) to (3, 4) at 2 m/s. At
3 seconds it is at **(1.2, 1.6)**; at 4 seconds it is at **(2.4, 3.2)**. Seeking
backwards returns to the same position and retains the native event identity.
The complete task still takes **9 seconds**.

Tests also cover read-only parsing, equivalence with standalone parsing, frozen
configuration isolation, modified evidence, changes during loading, asynchronous
completion, obsolete selections, project/revision identity, desktop layout,
pause/close behaviour, undo availability, and the playback-to-report transition.

The saved six-hour LTN run was also loaded: **9,612 events**, including the local
lift monitor. Loading took approximately **0.4 seconds** in this environment;
initial widget/data setup took approximately **0.1 seconds**. These are observations,
not performance acceptance thresholds. The run's existing 204 completed, zero
failed and zero pending outcomes are unchanged by playback. Timing and source
run details are in `latest/playback-ui-review.json`.

## Boundaries still open

- The integrated path requires a completed project run and full matching event
  evidence. Older or incomplete logs remain accessible through Results
  investigation and the standalone tools; they are not promoted to verified runs.
- Positions interpolate the recorded segment endpoints. Planned segment records
  do not prove actual execution, swept clearance, turn feasibility or lane rules.
  Clean/dirty/shared access continues to be defined by route profiles.
- The map shows model geometry without drawing underlays. Embedded rendering uses
  Qt's raster viewport; the standalone visualiser retains its OpenGL option.
- Configured containers and optional waste-fill estimates are derived displays.
  Waste-fill estimation is off by default and explicitly labelled. Use Results
  investigation for evidence coverage and reconciled physical counts.
- Loading retains an in-memory event index. Obsolete loads finish safely in the
  background and their results are ignored; interruptible loading, paging and a
  representative large-log performance gate remain open. The initial scene and
  timeline are built on the UI thread.
- Contextual properties, fuller object navigation, all accessibility controls,
  verified geometric traffic and the remaining roadmap gates are still open.

Run the acceptance suite with:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_project_playback -v
.venv/Scripts/python.exe -m verification.run --output verification/latest
```
