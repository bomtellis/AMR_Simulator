# AMR Simulator 0.1.0

Windows x64 desktop feasibility and planning tool for autonomous mobile robot
logistics within buildings.

## Downloads and getting started

- **AMR-Simulator-0.1.0-Windows-x64-Setup.exe**: install for the current user,
  then open AMR Simulator from the Start menu. Administrator rights and a
  separate Python installation are not required.
- **AMR-Simulator-0.1.0-Windows-x64-Portable.zip**: extract the whole archive
  into a writable folder and open `AMRSimulator/AMRSimulator.exe`.
  Keep `_internal` and the other bundled files beside the executable.
- **AMR-Simulator-0.1.0-Source.zip**: matching application source and build recipe.
- **SHA256SUMS.txt** and **release-manifest.json**: file checksums and build/
  verification information.

Start with **Help → Building flow tutorial**. The current 12-part course,
three-floor drawings, starter, chapter checkpoints and completed reference
projects are bundled. Course tools create a working copy in your chosen folder.
Save working projects and simulation results outside the application folder.

The small-map exercise and generated PDF guides are also included. The separate
supplied LTN example is optional and is not included in this public build.

## Capabilities

Model building layouts, robot fleets, payloads, demand, route permissions,
lifts, charging and staff handling. Check inputs, save simulation runs,
investigate completed/failed/pending work, play back results, compare layouts,
and export PDF reports and CSV evidence.

## Verification and limits

Release verification uses a fresh installation on the Windows build host:

- The small-map workflow saves and reopens a project, completes one task with
  zero failed/pending work, opens investigation and playback, and exports a PDF.
- The dedicated building reference completes all 12 tutorial chapters, runs
  the 48-run lift comparison suite and the ordinary course run, and exports
  run/comparison reports. The ordinary reference run completes 36 tasks with
  zero failed/pending work.

The package is unsigned and Windows may display an unknown-publisher warning.
Checks cover reference cases on one Windows host; they do not establish full
model validation, performance on all computers, or acceptance of an operational
design. Review modelling assumptions, project checks and recorded run evidence.

Licence: AGPL-3.0; see the bundled `LICENSE` and matching source archive.
