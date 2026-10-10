# Windows installer and tagged releases

The installed application includes Python, Qt, simulation/report workers,
the current 12-part Building flow tutorial, generated practice projects,
drawings, Markdown/PDF guides and the project licence. Installation works
offline and defaults to the current user's LocalAppData folder without an
administrator prompt. A portable ZIP can be supplied alongside the installer.

Setup checks the current user's AMR Simulator uninstall registration and removes
the previous package before installing this one, including a rebuilt package
with the same version. Close AMR Simulator and its workers first. Setup stops
if removal fails or Windows needs a restart. The registered uninstaller removes
its installed files; saved projects, results and untracked files are retained.
Portable copies are not registered and must be replaced manually.

## Build on Windows x64

Use Python 3.13 in `.venv`, install the pinned application/build dependencies,
and install Inno Setup (this host uses 7.1.0). From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r installer\requirements-build.txt
& .\installer\build.ps1 -Version 0.1.1 -Iscc 'C:\path\to\ISCC.exe'
```

On this host the compiler is already at `tmp\inno-tool\ISCC.exe`, the script's
default. Versioned outputs stay in the ignored `installer/build/releases/0.1.1`
folder, preserving previous development deliveries. Both frozen executables
and the installer carry version 0.1.1. The build cleans PyInstaller analysis,
keeps exact application source files for run/report fingerprints, and removes
the incompatible ICU DLL that can be collected from this host's tooling PATH.

The public build uses tracked practice inputs and regenerates the tutorial
projects and guides. It requires no separately supplied LTN project or generated
PDF/DOCX from an earlier checkout. To include an authorised portable LTN example,
explicitly add `-LtnProject 'C:\path\to\ltn.amrproj'`. The in-app walkthrough
still lists that optional exercise when its input is not bundled; use the small
map or Building flow tutorial instead.

Omit `-Version` for the backwards-compatible development output
`installer/build/setup/AMR-Simulator-Setup-dev.exe` (version 0.1.0-dev).

## Verify a fresh installation

Verify an upgrade from the previous release and a same-version replacement.
This test installs the previous package into `upgrade-previous`, upgrades into
an absent `installed` folder, reinstalls there, and checks that untracked
project files inside and outside the installation folders retain their bytes.
It refuses to run when a normal installation outside the build area is
registered. Use a separate Windows account in that case.

```powershell
$releaseRoot = Join-Path (Get-Location) 'installer\build\releases\0.1.1'
$installedApp = Join-Path $releaseRoot 'installed'
& .\installer\verify_upgrade.ps1 -Version 0.1.1 -PreviousVersion 0.1.0
$worker = Join-Path $installedApp 'AMRSimulatorWorker.exe'
$releaseTemp = Join-Path $releaseRoot 'temp'
New-Item -ItemType Directory -Path $releaseTemp -Force | Out-Null
$env:TEMP = $releaseTemp
$env:TMP = $releaseTemp
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest tests.test_quick_start.QuickStartTests.test_small_map_has_two_types_and_completed_connected_reference tests.test_building_tutorial tests.test_workbench_lifecycle tests.test_tutorial_status tests.test_tutorial_circulation tests.test_tutorial_placement tests.test_tutorial_bubble *> (Join-Path $releaseRoot 'source-checks.log')
if ($LASTEXITCODE -ne 0) { throw 'Source checks failed' }
& $worker --package-smoke (Join-Path $releaseRoot 'smoke-small')
if ($LASTEXITCODE -ne 0) { throw 'Small-map verification failed' }
& $worker --package-smoke-building (Join-Path $releaseRoot 'smoke-building')
if ($LASTEXITCODE -ne 0) { throw 'Building-course verification failed' }
.\.venv\Scripts\python.exe installer\package_release.py --version 0.1.1
```

Each check writes `smoke.json`, screenshots and reports; `error.txt` locates a
failure. Packaging requires passing fresh-installed checks and matching software
fingerprints and upgrade/reinstall evidence for the exact Setup executable.
Review the generated guides visually and try a normal GUI launch.
Checks cover one Windows host and reference projects, not complete validation.
The package is unsigned; Windows may display an unknown-publisher warning.

## Publish manually as 0.1.1

No GitHub Actions workflow or publishing command is added. Build/package
commands work locally and never upload anything.

1. Review and commit the packaging changes and restored small-map practice
   input on `main`. The tag must identify the same application source used
   in the build. If application code changes, rebuild and reverify first.
2. Push that commit yourself to the intended repository. The build manifest
   records the base commit and pending changes; the supplied Source ZIP
   contains the actual build source even before those changes are committed.
3. In GitHub open **Releases → Draft a new release**.
4. Choose **0.1.1**, create the tag on your pushed release commit (or select
   an existing matching tag), and set the title to **AMR Simulator 0.1.1**.
5. Paste `installer/RELEASE-0.1.1.md` into the release description. Attach the
   installer, portable ZIP, Source ZIP, manifest and checksum file from
   `installer/build/releases/0.1.1/assets`.
6. Review and publish the release. Use the pre-release checkbox if distributing
   it for testing.

Release assets are uploaded separately; do not commit the installer or build
folders into the source repository. Official guidance:
[Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

After publication, fill in `docs/_data/downloads.yml` with:

```yaml
windows_url: "https://github.com/bomtellis/AMR_Simulator/releases/download/0.1.1/AMR-Simulator-0.1.1-Windows-x64-Setup.exe"
windows_version: "0.1.1"
windows_details: "Windows x64 installer. Includes Python and the guided tutorial."
```

The website download is configured for that exact repository, tag and filename.
It becomes available once you upload and publish the matching release asset.
