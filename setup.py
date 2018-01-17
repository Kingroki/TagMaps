import sys
from cx_Freeze import setup, Executable

#Derive Package Paths Dynamically
import os.path
PYTHON_INSTALL_DIR = os.path.dirname(os.path.dirname(os.__file__))
os.environ['TCL_LIBRARY'] = os.path.join(PYTHON_INSTALL_DIR, 'tcl', 'tcl8.6')
os.environ['TK_LIBRARY'] = os.path.join(PYTHON_INSTALL_DIR, 'tcl', 'tk8.6')

# Dependencies are automatically detected, but it might need fine tuning.
#build_exe_options = {"packages": ["os"], "excludes": []}
includes_mod = ['numpy.core._methods', 
                'numpy.lib.format',
                'matplotlib.backends.backend_tkagg',
                'seaborn',
                'seaborn.cm',
                'scipy.sparse.csgraph',
                'scipy.sparse.csgraph._validation',
                ]#,'scipy.spatial.ckdtree'

include_folders_files = ["C:/Python36/DLLs/tcl86t.dll", 
                         "C:/Python36/DLLs/tk86t.dll",
                        '01_Input/',
                         '00_Config/',
                        ("D:/03_EvaVGI/05_Code/Py/standalone_tag_cluster_hdbscan/matplotlibrc","matplotlibrc")
                        ]
packages_mod = ["tkinter", "tkinter.filedialog"]
excludes_mod = ["scipy.spatial.cKDTree"]



# GUI applications require a different base on Windows (the default is for a
# console application).
base = None
#base = "Console"
#if sys.platform == "win32":
#    base = "Win32GUI"

executables = [
    Executable('generateTagClusters.py', base=base)
]

setup(  name = "generateTagClusters",
        version = "0.9.1",
        description = "Tag Clustering for Tag Maps",
        options = {'build_exe': {'includes': includes_mod, 'include_files': include_folders_files,'packages':packages_mod,'excludes':excludes_mod}},
        executables = executables)