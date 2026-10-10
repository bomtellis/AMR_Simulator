# Windows development installer

From the repository root, install `requirements.txt` and PyInstaller into
`.venv`, then run:

```powershell
& installer\build.ps1 -LtnProject ltn.amrproj -Iscc 'C:\path\to\ISCC.exe'
```

The LTN project is a supplied portable build input. The build script requires
it; it does not package `ltn.json` with machine-specific drawing paths.
The output is `installer/build/setup/AMR-Simulator-Setup-dev.exe`. Build files
stay under the ignored `installer/build` directory.

The installer defaults to a current-user LocalAppData directory and needs no
administrator rights or network connection. It carries the practice map, LTN
project, and the PDF, DOCX and Markdown quick-start guide. The GUI launches
the bundled console worker for simulations and report export. The build removes
an incompatible ICU DLL that PyInstaller can collect from this host's tooling
path; Qt then uses Windows' system ICU as it does in the working source
environment. Older version 1 `.amrproj` files open without being rewritten;
Save upgrades them to version 2. To verify an
installed copy without opening the GUI, run:

```powershell
& 'C:\path\to\AMRSimulator.exe' --package-smoke 'C:\writable\smoke-output'
```

`smoke.json` records a saved small-map run, reopened project, actual Review and
Playback, compact Simple settings and PDF report. Read-only review verifies that
saved inputs and event CSV have not changed. This command excludes LTN workloads;
`error.txt` contains a traceback on failure. This is a development package,
not a signed or release-accepted build.

The 9 October Simple delivery and checksums are described in
[the delivery review](../verification/SIMPLE_DELIVERY_REVIEW.md).

For the supplied LTN archive, run the more complete installed check with a
writable output directory:

```powershell
& 'C:\path\to\AMRSimulator.exe' --package-smoke-ltn 'C:\writable\ltn-output'
```

It opens all LTN DXF floors and the walkthrough, checks bay-entry findings,
runs the 05:00–11:00 exercise, reconciles recorded outcomes, and exports a PDF.
`ltn-smoke.json` records the result; `ltn-progress.txt` and `ltn-error.txt`
locate a failure. The check uses a temporary drawing cache under its output
directory so it can run in a restricted filesystem sandbox.
