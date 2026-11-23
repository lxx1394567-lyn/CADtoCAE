# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/batch_runner_gui.py'],
    pathex=['src'],
    binaries=[('D:/Software/anaconda3/Library/bin/tcl86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/tk86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/ffi.dll', '.')],
    datas=[('src/cadtocae/batch_runner/cae_worker.py', 'cadtocae/batch_runner'), ('src/cadtocae/batch_runner/delivery_worker.py', 'cadtocae/batch_runner')],
    hiddenimports=[],
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
    name='CADtoCAE_BatchRunner',
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
    name='CADtoCAE_BatchRunner',
)
