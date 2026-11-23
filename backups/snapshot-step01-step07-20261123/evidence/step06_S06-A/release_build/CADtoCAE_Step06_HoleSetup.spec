# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/config', 'config'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/spdc_hoop_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hole_profiles.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hole_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hoop_hole_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/beam_brace_tie_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/analysis_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hole_transforms.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hole_derived_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/analysis_geometry.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/purlin_bolt_preset_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_b1_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_groups_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/support_beam_connector_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_integration_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/hoop_brace_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/dp_hoop_brace_runtime.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_geometry.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_b1_plan.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/connector_groups.py', 'cadtocae'), ('F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src/cadtocae/support_beam_connector.py', 'cadtocae')]
binaries = [('D:/Software/anaconda3/Library/bin/tcl86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/tk86t.dll', '.'), ('D:/Software/anaconda3/Library/bin/ffi.dll', '.')]
hiddenimports = []
tmp_ret = collect_all('openpyxl')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['../../scripts/step06_hole_setup_gui.py'],
    pathex=['F:/Codex/Wind Resistance of PV Support Structures/CADtoCAE-feature-step06-development/src'],
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
