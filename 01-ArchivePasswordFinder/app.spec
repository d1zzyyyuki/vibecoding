# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：精简 Qt 组件，输出单文件 exe。"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('zipcpu.dll', '.')],
    datas=[('assets', 'assets')],
    hiddenimports=['cuda', 'gpu', 'hashcat_gpu', 'capability'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'doctest',
              'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick',
              'PySide6.QtSvg', 'PySide6.QtOpenGL', 'PySide6.QtPdf',
              'PySide6.QtVirtualKeyboard', 'PySide6.QtWebEngineCore'],
    noarchive=False,
    optimize=0,
)

# --- 只保留运行 UI 必需的 Qt 二进制，显著减小体积、加快启动 ---
_PYSIDE_KEEP = {
    'pyside6\\qt6core.dll',
    'pyside6\\qt6gui.dll',
    'pyside6\\qt6widgets.dll',
    'pyside6\\qtcore.pyd',
    'pyside6\\qtgui.pyd',
    'pyside6\\qtwidgets.pyd',
    'pyside6\\pyside6.abi3.dll',
    'pyside6\\plugins\\platforms\\qwindows.dll',
    'pyside6\\plugins\\imageformats\\qico.dll',
    'pyside6\\plugins\\imageformats\\qjpeg.dll',
}


def _keep_qt(name):
    low = name.lower().replace('/', '\\')
    if not low.startswith('pyside6\\'):
        return True
    if low in _PYSIDE_KEEP:
        return True
    if low.startswith('pyside6\\msvcp140') or low.startswith('pyside6\\vcruntime140'):
        return True
    if low.startswith('pyside6\\plugins\\styles\\'):
        return True
    return False


a.binaries = [b for b in a.binaries if _keep_qt(b[0])]
a.datas = [d for d in a.datas if _keep_qt(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ArchivePasswordFinder',
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
    version='version_info.txt',
    icon=['assets/icon.ico'],
)


