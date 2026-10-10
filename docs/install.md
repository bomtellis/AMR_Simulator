---
title: Install and open
nav_order: 2
permalink: /install/
---
# Install and open on Windows

## Source installation

You need Windows, **Python 3.13**, and a writable folder. The repository's
engineering checks use Python 3.13. Install Python from
[python.org](https://www.python.org/downloads/windows/), including the Python
launcher. Git is useful for updates, but downloading the repository ZIP also works.

1. Open [the repository](https://github.com/bomtellis/AMR_Simulator).
   Select **main**, then **Code → Download ZIP**, and extract it. Alternatively,
   with Git installed, use the commands below.
2. Open PowerShell in the extracted repository folder. It must contain
   `amr_app.py`, `simulator.py` and `requirements.txt`.
3. Create an isolated environment and install the dependencies:

```powershell
# With Git; skip these two commands if you already extracted the ZIP.
git clone --branch main https://github.com/bomtellis/AMR_Simulator.git
cd AMR_Simulator

py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe amr_app.py
```

The first dependency installation needs an internet connection. These commands
use the environment's Python directly, so PowerShell script activation is not
required. Wait for installation to finish successfully before launching.

## Open a project or the practice input

In the workbench choose **File → Open project / JSON**. For the first exercise,
open `docs/quick-start/small-map.json` inside your repository copy. You can also
open it directly:

```powershell
.\.venv\Scripts\python.exe amr_app.py docs\quick-start\small-map.json
.\.venv\Scripts\python.exe amr_app.py "C:\AMR studies\hospital.amrproj"
```

Launching without a file offers new-project setup. Choose floor count and level
height, then assign drawings if available. **Skip setup** opens an empty project;
it still needs layout, robot and demand configuration before simulation.

If a drawing cannot be rendered, inspect and repair its configuration with:

```powershell
.\.venv\Scripts\python.exe amr_app.py "C:\AMR studies\hospital.json" --without-drawings
```

This skips display loading. Missing drawing files still need repair before a
portable project can package them. Read [projects and layouts](build-model.md).

## Development installer

There is no published installer release at the documentation's reviewed revision.
If your project team provides `AMR-Simulator-Setup-dev.exe`, use that package's
instructions and confirm its revision. It is a development package, not a signed
release-accepted build.

The installer defaults to your LocalAppData folder, requires no administrator
rights, and carries its dependencies for offline operation. Its bundled examples
can include the portable LTN project and generated tutorial archives. Save your
own working copies outside the installed examples folder.

For package builders, install PyInstaller into the source environment, install
Inno Setup separately, and provide a portable LTN project containing its drawings:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
& installer\build.ps1 -LtnProject "C:\AMR package inputs\ltn.amrproj" -Iscc "C:\path\to\ISCC.exe"
```

The build requires that LTN archive; a source-only checkout does not supply it.
Output: `installer/build/setup/AMR-Simulator-Setup-dev.exe`. Follow the
[installer build and smoke-check instructions](https://github.com/bomtellis/AMR_Simulator/blob/main/installer/README.md)
before distributing a package. Installer creation is optional for using the tool.

## Updating and opening older work

With Git, save your projects and runs first, update your clean source checkout
with `git pull --ff-only`, then rerun the dependency installation command.
With a ZIP, extract the newer source into a separate folder. Keep your studies
and their external results folders together and retain the older application
revision when results must be reproducible.

Older supported `.amrproj` archives can be opened; saving may upgrade their
storage format. Save a separate copy before a cross-version comparison. JSON
retains external drawing references until converted to a portable project.

Continue with [your first simulation](quick-start/AMR-Simulator-Quick-Start.md).
