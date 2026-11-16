param(
    [Parameter(Mandatory = $true)][string]$Compiler,
    [string]$Python = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$clang = (Resolve-Path -LiteralPath $Compiler).Path
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$pythonInfo = & $pythonPath -B -c 'import json, platform, sys, sysconfig; print(json.dumps(dict(root=sys.base_prefix, suffix=sysconfig.get_config_var("EXT_SUFFIX"), lib=sysconfig.get_config_var("LDLIBRARY"), machine=platform.machine())))'
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the selected Python interpreter.' }
$info = $pythonInfo | ConvertFrom-Json
if ($info.machine -ne 'AMD64' -or $info.suffix -notlike '*-win_amd64.pyd') {
    throw 'This build script needs Windows x64 CPython.'
}

$build = Join-Path $root 'build/corridor-native'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$env:ZIG_LOCAL_CACHE_DIR = Join-Path $build 'zig-local'
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $build 'zig-global'
$name = "_amr_corridor_native$($info.suffix)"
$binary = Join-Path $build $name
$flags = @('cc', '-shared', '-O3', '-ffp-contract=off', '-fno-fast-math',
    '-fno-exceptions', '-fno-rtti', '-Wall', '-I', (Join-Path $info.root 'include'),
    (Join-Path $root 'native/corridor_module.cpp'), (Join-Path $info.root "libs/$([IO.Path]::ChangeExtension($info.lib, '.lib'))"),
    '-o', $binary)
& $clang @flags
if ($LASTEXITCODE -ne 0) { throw 'The corridor extension failed to build.' }

& $pythonPath -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import _amr_corridor_native; assert callable(_amr_corridor_native.evaluate)' $build
if ($LASTEXITCODE -ne 0) { throw 'The built corridor extension failed to load.' }
$destination = Join-Path $root $name
Copy-Item -LiteralPath $binary -Destination $destination -Force
Get-FileHash -Algorithm SHA256 -LiteralPath $destination
