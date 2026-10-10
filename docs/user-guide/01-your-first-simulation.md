---
title: First-run checklist
nav_order: 1
parent: First simulation
---
# Your first simulation

Use the [illustrated quick-start guide](../quick-start/AMR-Simulator-Quick-Start.md)
for the full exercise. These are the current workbench steps.

## Before you start

[Install and open](../install.md) the application. Use the tracked
[small-map JSON](../quick-start/small-map.json); this input needs no external
hospital drawings. It has locations A, B and C, robot types R1/R2 and task T1.
C is intentionally disconnected.

## Complete the workflow

1. Choose **File → Open project / JSON** and open the small map.
2. In **Layout**, choose **Corridor**, click B then C with endpoint snapping,
   and press blank Enter to finish. Expect A–B and B–C connections.
3. Choose **File → Save project as**, and save `small-map.amrproj` in your study folder.
4. Choose **Check → Run checks**. After B–C is connected this fixture should
   have no errors or warnings; informational scope notes remain.
5. Choose **Simulate → Save, check and simulate**, review checks, and start.
6. Select the completed run and choose **Investigate selected run**. Expect
   T1 completed, zero failed and zero pending for the reference input.
7. Choose **Playback selected run** and follow the recorded path.
8. Choose **Report selected run**, select sections and **Generate report**.
   Use **Open generated PDF**; retain the supporting CSVs in the run folder.

Reopen the project to confirm the saved connection and robot types. Later
editing does not change the frozen run. A successful process is not proof every
request in a larger scenario was served: inspect recorded task outcomes.

## Optional LTN exercise

The full quick-start guide also describes a 05:00–11:00 LTN exercise on
1 January 2026. It requires the separately supplied portable LTN archive and its
drawings, normally distributed in a development package. The source checkout's
LTN JSON can contain external paths and is not a self-contained replacement.
Complete the small map or building tutorial while that package is unavailable.
