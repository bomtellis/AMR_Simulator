# AMR Simulator 0.1.1

Windows x64 update for the Building flow tutorial.

## Tutorial fixes

- Completion is checked again when a corridor is finished with Escape,
  without requiring another model edit or a manual check.
- Location-name correction markers show the required name separately from
  the existing incorrect name. Floor-2 service locations show **Clean-F2**
  and **Dirty-F2**.
- Name repairs direct users to **Select → double-click location → Name → Save**.
  Names remain read-only in the layout Properties panel.

Part 3 actions 18 and 19 are covered by regression checks using the door
Properties controls, location placement and editing, automatic completion,
undo and redo. The installed application also checks these floor-2 gates.

## Downloads

- **AMR-Simulator-0.1.1-Windows-x64-Setup.exe**: install for the current user,
  then open AMR Simulator from the Start menu. Python is bundled.
- **AMR-Simulator-0.1.1-Windows-x64-Portable.zip**: extract the entire archive
  into a writable folder and open `AMRSimulator/AMRSimulator.exe`.
- **AMR-Simulator-0.1.1-Source.zip**: matching source and build instructions.
- **SHA256SUMS.txt** and **release-manifest.json**: checksums and verification evidence.

Open **Help → Building flow tutorial** for the current 12-part course.
Practice projects, drawings and guides are bundled. Save working projects and
simulation results outside the application folder. Existing project and tutorial
progress files can be reused; the current action is checked again when resumed.

## Verification and limits

Verification uses a fresh installation on the Windows build host, including
the repaired tutorial gates, the small-map save/run/playback/report workflow,
all 12 building-course chapter checks and the 48-run lift comparison suite.
The ordinary building reference run completes 36 tasks with zero failed or
pending work.

The package is unsigned. Windows may display an unknown-publisher warning.
Reference checks on one host do not establish validation of every model or
operational design. The optional supplied LTN example is not included.

Licence: AGPL-3.0; see the bundled `LICENSE` and matching source archive.
