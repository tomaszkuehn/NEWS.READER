# -*- mode: python ; coding: utf-8 -*-
# Budowanie: venv-win7\Scripts\pyinstaller --clean --noconfirm newsreader-win7.spec
# Wymagania: Python 3.8 (Windows 7+) + deps z requirements-win7.txt.

a = Analysis(
    ['tray.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.')],
    hiddenimports=['cryptography.hazmat.primitives.asymmetric.padding',
                   'cryptography.hazmat.primitives.hashes',
                   'cryptography.hazmat.primitives.serialization'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NewsReader-win7',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
    version='version_info.txt',
)