# -*- mode: python ; coding: utf-8 -*-
"""One shared application archive with GUI and console worker entry points."""
from pathlib import Path
import os
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

project_root = Path(SPECPATH).resolve().parent
build_version = os.environ.get('AMR_BUILD_VERSION', '0.1.0-dev')
version_numbers = tuple(int(n) for n in build_version.split('-')[0].split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_numbers, prodvers=version_numbers,
                     mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0,
                     date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', 'AMR Simulator'),
        StringStruct('FileVersion', build_version),
        StringStruct('ProductName', 'AMR Simulator'),
        StringStruct('ProductVersion', build_version),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)

a = Analysis(
    [str(project_root / 'amr_app.py')],
    pathex=[str(project_root), str(project_root / 'visualiser'), str(project_root / 'report')],
    binaries=[],
    datas=[],
    hiddenimports=['app', 'amr_report_main', 'amr_report_pdf_report'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

gui = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='AMRSimulator',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
    version=version_info,
)
worker = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='AMRSimulatorWorker',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=True,
    version=version_info,
)
coll = COLLECT(
    gui, worker, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[], name='AMRSimulator',
)
