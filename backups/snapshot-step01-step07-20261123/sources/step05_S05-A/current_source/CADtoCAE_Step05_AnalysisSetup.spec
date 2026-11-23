# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('config', 'config'), ('src/cadtocae/*runtime.py', 'cadtocae'), ('src/cadtocae/column_axis.py', 'cadtocae')]
binaries = [('D:/Software/anaconda3/Library/bin/tcl86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/tk86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/ffi.dll', '.')]
hiddenimports = []
tmp_ret = collect_all('openpyxl')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['scripts/step05_analysis_script_gui.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CADtoCAE_Step05_AnalysisSetup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CADtoCAE_Step05_AnalysisSetup',
)
