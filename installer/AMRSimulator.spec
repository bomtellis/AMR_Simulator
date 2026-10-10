# -*- mode: python ; coding: utf-8 -*-
"""One shared application archive with GUI and console worker entry points."""
from pathlib import Path

project_root = Path(SPECPATH).resolve().parent

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
)
worker = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='AMRSimulatorWorker',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=True,
)
coll = COLLECT(
    gui, worker, a.binaries, a.datas,
    strip=False, upx=True, upx_exclude=[], name='AMRSimulator',
)
