# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('config', 'config'), ('src/cadtocae/hole_runtime.py', 'cadtocae'), ('src/cadtocae/hoop_hole_runtime.py', 'cadtocae'), ('src/cadtocae/beam_brace_tie_runtime.py', 'cadtocae'), ('src/cadtocae/analysis_runtime.py', 'cadtocae'), ('src/cadtocae/hole_transforms.py', 'cadtocae'), ('src/cadtocae/hole_derived_runtime.py', 'cadtocae'), ('src/cadtocae/analysis_geometry.py', 'cadtocae')]
binaries = [('D:/Software/anaconda3/Library/bin/tcl86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/tk86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/ffi.dll', '.')]
hiddenimports = []
tmp_ret = collect_all('openpyxl')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['scripts/step06_hole_setup_gui.py'],
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
    name='CADtoCAE_Step06_HoleSetup',
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
    name='CADtoCAE_Step06_HoleSetup',
)
