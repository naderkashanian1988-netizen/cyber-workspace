# CYBER WORKSPACE — PyInstaller spec (Windows, onedir) — v1.0.0-rc.1
#
# Build (from the repository root, any CWD works — paths come from SPECPATH):
#   pyinstaller Build/Configuration/cyber_workspace.spec --distpath dist --workpath build --noconfirm --clean
# Produces: dist/CyberWorkspace/CyberWorkspace.exe (+ _internal/).
# See Documentation/BUILD.md for the full pipeline.

import os

spec_dir = SPECPATH                                  # Build/Configuration/
repo_root = os.path.dirname(os.path.dirname(spec_dir))
win_root = os.path.join(repo_root, "Source", "Windows")
icon_dir = os.path.join(win_root, "assets", "icon")

block_cipher = None

a = Analysis(
    [os.path.join(win_root, "run_app.py")],
    pathex=[win_root],
    binaries=[],
    datas=[
        (os.path.join(win_root, "db", "schema.sql"), "db"),
        (os.path.join(icon_dir, "app_icon_256.png"), "assets/icon"),
    ],
    hiddenimports=[
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "cyber_workspace.adapters.browser",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="CyberWorkspace",
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(icon_dir, "cyber_workspace.ico"),
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False,
    name="CyberWorkspace",
)
