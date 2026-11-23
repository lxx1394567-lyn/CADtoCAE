# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/batch_runner.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src/cadtocae/batch_runner/cae_worker.py', 'cadtocae/batch_runner'), ('src/cadtocae/batch_runner/delivery_worker.py', 'cadtocae/batch_runner'), ('src/cadtocae/batch_runner/step07_verify.py', 'cadtocae/batch_runner'), ('src/cadtocae/batch_runner/step07_adapter.py', 'cadtocae/batch_runner')],
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
    name='CADtoCAE_BatchRunner_CLI_V40',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='CADtoCAE_BatchRunner_CLI_V40',
)
