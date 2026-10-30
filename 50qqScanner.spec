# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

xtquant_datas, xtquant_binaries, xtquant_hiddenimports = collect_all("xtquant")

a = Analysis(
    ['option_arbitrage_scanner.py'],
    pathex=[],
    binaries=xtquant_binaries,
    datas=[('contracts_config.json', '.')] + xtquant_datas,
    hiddenimports=xtquant_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt uses Windows' ICU DLL; unrelated copies on the build PATH may be incompatible.
a.binaries = [item for item in a.binaries if item[0].lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='50qqScanner',
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
    contents_directory='_internal',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='50qqScanner',
)
