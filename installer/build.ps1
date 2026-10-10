param(
    [string]$LtnProject = 'ltn.amrproj',
    [string]$Iscc = 'tmp\inno-tool\ISCC.exe'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$ltn = if ([IO.Path]::IsPathRooted($LtnProject)) { $LtnProject } else { Join-Path $root $LtnProject }
$compiler = if ([IO.Path]::IsPathRooted($Iscc)) { $Iscc } else { Join-Path $root $Iscc }
$dist = Join-Path $PSScriptRoot 'build\dist\AMRSimulator'
$outputRoot = Join-Path $PSScriptRoot 'build'
if (-not [IO.Path]::GetFullPath($dist).StartsWith([IO.Path]::GetFullPath($outputRoot) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must stay under installer\build.'
}
foreach ($path in @($python, $ltn, $compiler)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required build input missing: $path" }
}

Push-Location $root
try {
    & $python -m PyInstaller --clean --noconfirm `
        --distpath 'installer\build\dist' --workpath 'installer\build\work' `
        'installer\AMRSimulator.spec'
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

    $guide = Join-Path $dist 'docs\quick-start'
    New-Item -ItemType Directory -Path $guide -Force | Out-Null
    foreach ($name in @('AMR-Simulator-Quick-Start.md', 'AMR-Simulator-Quick-Start.docx',
                        'AMR-Simulator-Quick-Start.pdf', 'small-map.json')) {
        Copy-Item -LiteralPath (Join-Path $root "docs\quick-start\$name") -Destination $guide -Force
    }
    Copy-Item -LiteralPath (Join-Path $root 'docs\quick-start\images') -Destination $guide -Recurse -Force
    $buildingGuide = Join-Path $dist 'docs\building-tutorial'
    New-Item -ItemType Directory -Path $buildingGuide -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $root 'docs\building-tutorial') -File | Where-Object {
        $_.Extension -in @('.dxf', '.amrproj', '.md', '.pdf') -or $_.Name -eq 'coverage.json'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $buildingGuide -Force }
    Copy-Item -LiteralPath (Join-Path $root 'docs\building-tutorial\images') -Destination $buildingGuide -Recurse -Force
    $examples = Join-Path $dist 'examples'
    New-Item -ItemType Directory -Path $examples -Force | Out-Null
    Copy-Item -LiteralPath $ltn -Destination (Join-Path $examples 'ltn.amrproj') -Force

    $compileLog = Join-Path $outputRoot 'inno-compile.log'
    & $compiler (Join-Path $PSScriptRoot 'AMRSimulator.iss') *> $compileLog
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $compileLog -Tail 30
        throw 'Inno Setup compile failed.'
    }
    Write-Output (Join-Path $PSScriptRoot 'build\setup\AMR-Simulator-Setup-dev.exe')
}
finally {
    Pop-Location
}
