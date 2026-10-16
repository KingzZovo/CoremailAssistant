# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for CoremailAssistant.
Optimized for minimum binary footprint, excluding unused Qt modules and scientific libraries.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None

# 仅收集 jieba 必要的字典数据文件
jieba_datas = collect_data_files('jieba')

# 仅收集 scikit-learn 元数据
sklearn_metadata = copy_metadata('scikit-learn')

datas = [
    ('config.py', '.'),
    ('README.md', '.'),
    ('.env.example', '.'),
] + jieba_datas + sklearn_metadata

# 严苛剪枝：显式剔除所有本助手完全未使用的庞大子模块，缩减 200MB+ 冗余体积
excluded_modules = [
    # 剔除未使用的 PySide6 庞大子组件
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQml',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DExtras',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner',
    'PySide6.QtTest',
    'PySide6.QtSpatialAudio',
    'PySide6.QtBluetooth',
    'PySide6.QtPositioning',
    'PySide6.QtLocation',
    'PySide6.QtSensors',
    'PySide6.QtNfc',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtVirtualKeyboard',
    'PySide6.QtSql',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    # 剔除未使用的 scipy 庞大科学计算子库（本项目仅用到 sparse 与 sgd）
    'scipy.spatial',
    'scipy.stats',
    'scipy.optimize',
    'scipy.integrate',
    'scipy.interpolate',
    'scipy.signal',
    'scipy.ndimage',
    'scipy.io',
    'scipy.cluster',
    # 剔除未使用的 sklearn 子模块
    'sklearn.datasets',
    'sklearn.tree',
    'sklearn.ensemble',
    'sklearn.neural_network',
    'sklearn.manifold',
    'sklearn.decomposition',
    'sklearn.neighbors',
    # 剔除无关第三方工具
    'matplotlib',
    'tkinter',
    'IPython',
    'notebook',
    'pytest',
    'sphinx',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'unittest',
        'unittest.mock',
        'pydoc',
        'doctest',
        'sklearn',
        'sklearn.base',
        'sklearn.feature_extraction.text',
        'sklearn.linear_model',
        'sklearn.linear_model._stochastic_gradient',
        'sklearn.utils._typedefs',
        'sklearn.neighbors._typedefs',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'requests',
        'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CoremailAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CoremailAssistant',
)
