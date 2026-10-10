param(
    [ValidatePattern('^\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$')]
    [string]$Version = '0.1.0-dev',
    [string]$LtnProject = '',
    [string]$Iscc = 'tmp\inno-tool\ISCC.exe'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$ltn = if ($LtnProject) { if ([IO.Path]::IsPathRooted($LtnProject)) { $LtnProject } else { Join-Path $root $LtnProject } }
$compiler = if ([IO.Path]::IsPathRooted($Iscc)) { $Iscc } else { Join-Path $root $Iscc }
$outputRoot = if ($Version -eq '0.1.0-dev') { Join-Path $PSScriptRoot 'build' } else { Join-Path $PSScriptRoot "build\releases\$Version" }
$distRoot = Join-Path $outputRoot 'dist'
$dist = Join-Path $distRoot 'AMRSimulator'
if (-not [IO.Path]::GetFullPath($dist).StartsWith([IO.Path]::GetFullPath($outputRoot) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must stay under installer\build.'
}
foreach ($path in @($python, $compiler, (Join-Path $root 'docs\quick-start\small-map.json'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required build input missing: $path" }
}
if ($ltn -and -not (Test-Path -LiteralPath $ltn -PathType Leaf)) { throw "Optional LTN project missing: $ltn" }
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

Push-Location $root
$previousVersion = $env:AMR_BUILD_VERSION
try {
    $env:AMR_BUILD_VERSION = $Version
    $buildLog = Join-Path $outputRoot 'pyinstaller.log'
    & $python -m PyInstaller --clean --noconfirm `
        --distpath $distRoot --workpath (Join-Path $outputRoot 'work') `
        'installer\AMRSimulator.spec' *> $buildLog
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $buildLog -Tail 35 }
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    if (-not (Test-Path -LiteralPath (Join-Path $dist 'AMRSimulator.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $dist 'AMRSimulatorWorker.exe') -PathType Leaf)) {
        throw 'Frozen application is missing.'
    }

    # Run/report fingerprints hash application source files. Keep the exact
    # build inputs beside the frozen modules; do not include tests or guides.
    $internal = Join-Path $dist '_internal'
    # This build host exposes an ICU 78 DLL through its tooling PATH. PyInstaller
    # may collect it although PySide6's Qt6Core resolves Windows' system ICU.
    # The collected DLL lacks the unsuffixed exports QtCore requires.
    foreach ($name in @('icuuc.dll', 'icudt78.dll', 'icuuc.dll.disabled')) {
        $conflict = Join-Path $internal $name
        if (Test-Path -LiteralPath $conflict -PathType Leaf) {
            Remove-Item -LiteralPath $conflict
        }
    }
    Get-ChildItem -LiteralPath $root -Filter '*.py' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $internal $_.Name) -Force
    }
    foreach ($folder in @('visualiser', 'report')) {
        Get-ChildItem -LiteralPath (Join-Path $root $folder) -Filter '*.py' -File -Recurse | ForEach-Object {
            $relative = [IO.Path]::GetRelativePath($root, $_.FullName)
            $destination = Join-Path $internal $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        }
    }

    $assetArgs = @('installer\prepare_assets.py', '--output', $dist, '--version', $Version)
    if ($ltn) { $assetArgs += @('--ltn-project', $ltn) }
    & $python @assetArgs
    if ($LASTEXITCODE -ne 0) { throw 'Practice projects and help generation failed.' }

    $compileLog = Join-Path $outputRoot 'inno-compile.log'
    $setupRoot = Join-Path $outputRoot 'setup'
    $setupName = if ($Version -eq '0.1.0-dev') { 'AMR-Simulator-Setup-dev' } else { "AMR-Simulator-$Version-Windows-x64-Setup" }
    & $compiler "/DAppVersion=$Version" "/DSourceDir=$dist" "/O$setupRoot" "/F$setupName" (Join-Path $PSScriptRoot 'AMRSimulator.iss') *> $compileLog
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $compileLog -Tail 30
        throw 'Inno Setup compile failed.'
    }
    Write-Output (Join-Path $setupRoot "$setupName.exe")
}
finally {
    $env:AMR_BUILD_VERSION = $previousVersion
    Pop-Location
}
