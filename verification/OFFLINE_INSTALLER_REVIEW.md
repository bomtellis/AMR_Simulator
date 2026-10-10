# Offline Windows installer review — 4 October 2026

The development installer is built by `installer/build.ps1` from the current
project virtual environment, `docs/quick-start` and a supplied portable
`ltn.amrproj`. `installer/AMRSimulator.spec` makes a GUI executable and a console
worker from one PyInstaller analysis. `installer/AMRSimulator.iss` installs to
the current user's LocalAppData with `PrivilegesRequired=lowest`, without a
network dependency or an administrator prompt. It includes the two exercise
inputs, PDF/DOCX/Markdown guide and images. The build requires PyInstaller and
Inno Setup on the build machine; the installed application does not.

The first frozen GUI build failed while importing PySide6.QtCore. PyInstaller
had copied an incompatible `icuuc.dll` from the build host's tooling path; its
ICU exports did not match what Qt6Core imports. The build now excludes that
copy, allowing Qt to use Windows' ICU DLL as the working source environment
does. The frozen launcher dispatches `multiprocessing` child processes before
parsing app options, so the LTN DXF process pool can start. The installed
package also includes the exact application `.py` source
snapshot used by the existing run/report software fingerprints. GUI Simulate
and Report launch the bundled console worker, preserving process isolation and
visible output without relying on a separately installed Python interpreter.

Fresh-install evidence in `installer/build` (ignored build output):

- The installer created both executables, both example inputs and the guide in
  a previously absent workspace test directory. Setup exit code was zero.
- The installed GUI executable's package smoke check exited zero under the
  network-restricted sandbox. It imported the Qt workbench and two-exercise
  help, saved the small project, ran its worker, and exported a PDF report.
- The recorded result is one completed task, zero failed and zero pending.
  The frozen software fingerprint is
  `2708e1c55e09428de07358772bad76320feed705d7e129d771e4c6120b7c2ed0`.
- A normal installed GUI launch with the bundled small map remained running
  without the QtCore exception. The console twin exposed only Qt's offscreen
  font/plugin notices during that launch check.
- A fresh install of the corrected package ran the LTN check from both the GUI
  executable and console twin. Both exited zero. The GUI check opened all six
  DXF floors and the six-step walkthrough, found the seven documented drop-off
  warnings, ran the supplied archive from 05:00 to 11:00, reconciled 206
  completed / 0 failed / 0 pending tasks across 9,839 events, and exported a
  PDF. The stricter check waits for every drawing floor; the preceding frozen
  build failed this path because its child process parsed
  `--multiprocessing-fork` as an app argument. The corrected package also
  passed the small-map installed GUI check.
- The current rebuilt installer also includes inline JSON import validation
  and version 1 archive migration. A fresh installed GUI check opened the
  bundled version 1 LTN project and saved its bounded copy as version 2;
  the small-map and LTN checks both exited zero. The editable source archive
  stayed at version 1. See `JSON_IMPORT_REVIEW.md` and
  `ARCHIVE_MIGRATION_REVIEW.md` for focused editor and migration evidence.
- The latest fresh install includes selected-evidence export, visible
  investigation input limits and the refreshed guide. Its installed GUI
  small-map and LTN checks both exited zero. The LTN check loaded all six DXF
  floors, reconciled 206 completed / 0 failed / 0 pending tasks across 9,839
  events and exported a PDF.
- The newest fresh install also includes the task timeline choice for related
  payload, journey and lift identities. Its installed LTN check followed all
  three identities for task `GEN_CATERING_D1_00004`, and the installed guide PDF
  exactly matches the regenerated source PDF by SHA-256. Small-map and LTN
  installed checks again exited zero.
- The final nested-edit checkpoint rebuild includes the department dialog's
  provisional-save instructions; the installed `visualiser/dialogs.py` matches
  the tested source byte for byte. A new fresh installation passed the small-map
  and LTN GUI checks, including all six DXF floors, 206 completed / 0 failed /
  0 pending tasks across 9,839 events, related-record investigation and PDF
  reporting. The combined department Save/Undo/Redo/project-reopen path passed
  its focused source test.
- The current lifecycle rebuild includes Project history guidance for failed
  saves and recovery. The installed panel source matches the tested source by
  SHA-256. A fresh install again passed both GUI smoke checks, including all
  six LTN floors, 206 completed / 0 failed / 0 pending tasks across 9,839
  events and a PDF report. The save/close/reopen/restore/failed-save/recovery
  workflow passed the focused application test.
- The current run-workflow rebuild includes Simulate guidance for relinking a
  moved folder, read-only playback and frozen-input report export. Its installed
  panel source matches the tested source. A fresh install passed both GUI smoke
  checks, loading all six LTN floors and completing 206 / 0 / 0 tasks across
  9,839 events with a PDF report. The combined move/relink/reopen/playback/report
  workflow passed in the source application without changing the project archive
  or frozen run inputs.
- The installer at `installer/build/setup/AMR-Simulator-Setup-dev.exe` is
  98,193,097 bytes with SHA-256
  `d2932917a0f126bcec9a9e79e69f7b9868f8a16eb276ed6c9600dd40ddacbdf9`.

This verifies the current development package on one Windows host. The LTN
example is a supplied build input rather than a tracked repository binary;
future builds must provide it explicitly. Physical screen review of LTN drawing
interaction, external PDF opening, remote CI execution, signing and the later
user testing/release acceptance remain open.
