# PyInstaller spec for the standalone voicebench executable.
# Build from the repository root with: pyinstaller packaging/voicebench.spec
# The executable carries the core dependencies (numpy, PyYAML, websockets) and the
# bundled example scenarios. The livekit and pipecat SDKs are not included.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# The livekit and pipecat adapter modules load, then report the missing extra when you use them.
hiddenimports = collect_submodules("voicebench") + collect_submodules("websockets")

a = Analysis(
    ["../src/voicebench/__main__.py"],
    pathex=["../src"],
    datas=collect_data_files("voicebench", includes=["examples/*.yaml", "py.typed"]),
    hiddenimports=hiddenimports,
    excludes=["livekit", "pipecat", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="voicebench",
    console=True,
    strip=False,
    upx=False,
)
