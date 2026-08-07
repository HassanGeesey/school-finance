# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the School Finance desktop app (ticket 13).

Build with::

    python -m PyInstaller packaging/SchoolFinance.spec --noconfirm --clean

Output: ``dist/SchoolFinance.exe`` — a single, hidden (no console) executable.
The app's templates and static assets (app.css, Inter fonts, icons, HTMX,
Chart.js) are bundled so the school runs fully offline.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
APP_DIR = os.path.join(ROOT, "app")

a = Analysis(
    [os.path.join(APP_DIR, "desktop", "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(APP_DIR, "templates"), "app/templates"),
        (os.path.join(APP_DIR, "static"), "app/static"),
        (os.path.join(SPECPATH, "icon.png"), "."),
    ],
    hiddenimports=[
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "python_multipart",
    ],
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
    a.zipfiles,
    a.datas,
    [],
    name="SchoolFinance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, "icon.ico"),
)
