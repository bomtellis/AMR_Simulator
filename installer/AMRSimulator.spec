# -*- mode: python ; coding: utf-8 -*-
"""One shared application archive with GUI and console worker entry points."""
from pathlib import Path
import os
import sysconfig
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

project_root = Path(SPECPATH).resolve().parent
native_corridor = project_root / ('_amr_corridor_native' + sysconfig.get_config_var('EXT_SUFFIX'))
report_assets = [
    'amr_lift_movement_workbook.mjs',
    'amr_lift_trip_workbook.mjs',
    'report/amr_department_workbook.mjs',
    'report/assets/department_review_template.xlsx',
]
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
    binaries=[(str(native_corridor), '.')] if native_corridor.is_file() else [],
    datas=[(str(project_root / name), str(Path(name).parent)) for name in report_assets],
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
    strip=False, upx=True, upx_exclude=[native_corridor.name], name='AMRSimulator',
)
