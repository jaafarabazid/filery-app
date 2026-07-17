# PyInstaller spec - builds a native app for whichever OS it runs on.
# PyInstaller cannot cross-compile: run this on macOS to get the .app, and on
# Windows to get the .exe. The CI workflow does both.
#
#   pyinstaller packaging/pdf-web-optimizer.spec --noconfirm

import os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

HERE = os.path.dirname(os.path.abspath(SPEC))
ICON = os.path.join(HERE, "icon.icns" if sys.platform == "darwin" else "icon.ico")
if not os.path.exists(ICON):
    ICON = None  # run `python packaging/make_icon.py` to generate it

block_cipher = None

# Qt modules we never touch. Dropping them roughly halves the bundle.
EXCLUDE = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtPdf",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "tkinter", "matplotlib", "scipy", "pandas", "skimage", "pytest",
    "IPython", "notebook", "setuptools",
]

a = Analysis(
    ["launcher.py"],          # never point this at app.py: see launcher.py
    pathex=["../src"],
    binaries=collect_dynamic_libs("pikepdf"),
    datas=[],
    hiddenimports=["filery", "filery.app", "filery.cli",
                   "filery.optimizers", "filery.optimizers.pdf"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDE,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Filery",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX corrupts Qt/MuPDF dylibs
    console=False,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Filery",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Filery.app",
        icon=ICON,
        bundle_identifier="io.mantek.filery",
        info_plist={
            "CFBundleShortVersionString": "0.9.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # let users drag a PDF onto the dock icon
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "PDF document",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["com.adobe.pdf"],
                "LSHandlerRank": "Alternate",
            }],
        },
    )
