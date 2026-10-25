from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


backend_dir = Path(SPECPATH)
hidden_imports = (
    collect_submodules("app")
    + collect_submodules("langchain_google_genai")
    + collect_submodules("langchain_openai")
    + collect_submodules("langgraph")
)
datas = collect_data_files("langgraph")

a = Analysis(
    [str(backend_dir / "run_backend.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
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
    name="pomopet-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
