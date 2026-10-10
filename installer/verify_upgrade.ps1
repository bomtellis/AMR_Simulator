param(
    [ValidatePattern('^\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$')]
    [string]$Version = '0.1.1',
    [ValidatePattern('^\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$')]
    [string]$PreviousVersion = '0.1.0'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildRoot = Join-Path $root 'installer\build\releases'
$releaseRoot = Join-Path $buildRoot $Version
$previousSetup = Join-Path $buildRoot "$PreviousVersion\assets\AMR-Simulator-$PreviousVersion-Windows-x64-Setup.exe"
$setup = Join-Path $releaseRoot "setup\AMR-Simulator-$Version-Windows-x64-Setup.exe"
$oldApp = Join-Path $releaseRoot 'upgrade-previous'
$installedApp = Join-Path $releaseRoot 'installed'
foreach ($path in @($previousSetup, $setup)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing installer: $path" }
}
foreach ($path in @($oldApp, $installedApp)) {
    if (Test-Path -LiteralPath $path) { throw "Verification needs an absent target: $path" }
}
# This verification changes registration. Never uninstall a normal installation
# outside the build area while preparing the test fixture.
$key = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F11500E1-1BF4-47AB-83A0-0208A01B6952}_is1'
foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
    $hive = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
    $entry = $hive.OpenSubKey($key)
    try {
        if ($entry) {
            $existing = ([string]$entry.GetValue('UninstallString')).Trim('"')
            if (-not [IO.Path]::GetFullPath($existing).StartsWith($buildRoot+'\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'A normal installation is registered outside the test area. Use an isolated Windows account for upgrade verification.'
            }
        }
    } finally { if ($entry) { $entry.Dispose() }; $hive.Dispose() }
}

function Install-TestPackage([string]$Installer, [string]$Directory, [string]$LogName) {
    $log = Join-Path $releaseRoot $LogName
    $process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', ('/DIR="'+$Directory+'"'), ('/LOG="'+$log+'"')) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Installer failed ($($process.ExitCode)): $log" }
}

Install-TestPackage $previousSetup $oldApp 'upgrade-baseline.log'
$practice = Join-Path $releaseRoot 'dist\AMRSimulator\docs\building-tutorial\starter.amrproj'
$oldProject = Join-Path $oldApp 'user-practice.amrproj'
$outsideProject = Join-Path $releaseRoot 'user-practice-outside.amrproj'
Copy-Item -LiteralPath $practice -Destination $oldProject
Copy-Item -LiteralPath $practice -Destination $outsideProject
$projectHash = (Get-FileHash -LiteralPath $practice -Algorithm SHA256).Hash
Install-TestPackage $setup $installedApp 'upgrade-install.log'
if (Test-Path -LiteralPath (Join-Path $oldApp 'AMRSimulator.exe')) { throw 'The previous executable was not removed' }
if (Test-Path -LiteralPath (Join-Path $oldApp '_internal\amr_tutorial.py')) { throw 'The previous payload was not removed' }
if (Get-ChildItem -LiteralPath $oldApp -File -Recurse | Where-Object { $_.FullName -ne $oldProject }) { throw 'Previous package files remain after removal' }
$insideProject = Join-Path $installedApp 'user-practice.amrproj'
Copy-Item -LiteralPath $practice -Destination $insideProject
Install-TestPackage $setup $installedApp 'reinstall.log'
foreach ($path in @($oldProject, $outsideProject, $insideProject)) {
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $projectHash) { throw "Saved project changed: $path" }
}
$actual = (Get-Item -LiteralPath (Join-Path $installedApp 'AMRSimulator.exe')).VersionInfo.ProductVersion
if ($actual -ne $Version) { throw "Installed version differs: $actual" }
if (-not (Select-String -LiteralPath (Join-Path $releaseRoot 'upgrade-install.log') -SimpleMatch "Removing registered AMR Simulator version $PreviousVersion" -Quiet)) { throw 'Upgrade detection evidence missing' }
if (-not (Select-String -LiteralPath (Join-Path $releaseRoot 'reinstall.log') -SimpleMatch "Removing registered AMR Simulator version $Version" -Quiet)) { throw 'Same-version detection evidence missing' }
$evidence = [ordered]@{ status='passed'; from=$PreviousVersion; to=$Version; same_version_reinstall=$true; saved_projects_preserved=$true; previous_payload_removed=$true; setup_sha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant() }
$evidence | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseRoot 'upgrade-check.json') -Encoding utf8
Write-Output 'Upgrade and same-version replacement passed; saved projects preserved.'
