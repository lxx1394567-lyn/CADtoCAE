"""Discover loaded Windows Tcl/Tk dependencies in the selected build Python."""
import argparse
import ctypes
import json
from pathlib import Path
import re
import sys
import tkinter
import _tkinter
import _ctypes

import pefile
import PyInstaller


def inspect_runtime():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    binaries = {}
    # Importing tkinter and ctypes above actually loads these DLLs. Query their
    # resolved locations rather than guessing a Conda/Python installation path.
    for extension in (_tkinter.__file__, _ctypes.__file__):
        with pefile.PE(extension) as pe:
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                name = entry.dll.decode('ascii')
                if not re.fullmatch(r'(?:tcl|tk|(?:lib)?ffi)[\w.-]*\.dll', name, re.I):
                    continue
                handle = kernel.GetModuleHandleW(name)
                buffer = ctypes.create_unicode_buffer(32768)
                if not handle or not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
                    raise RuntimeError('Cannot locate loaded dependency: ' + name)
                binaries[name] = str(Path(buffer.value).resolve())
    if not any(name.lower().startswith('tcl') for name in binaries) or not any(
            name.lower().startswith('tk') for name in binaries):
        raise RuntimeError('Could not discover both Tcl and Tk runtime DLLs.')
    tcl = tkinter.Tcl()
    return {'python': sys.executable, 'version': sys.version,
            'pyinstaller': PyInstaller.__version__, 'tk_version': tkinter.TkVersion,
            'tkinter_extension': _tkinter.__file__, 'binaries': list(binaries.values()),
            'tcl_library': tcl.eval('info library')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path)
    args = parser.parse_args()
    runtime = inspect_runtime()
    if args.package:
        internal = args.package / '_internal'
        required = [internal / '_tkinter.pyd', internal / '_tcl_data' / 'init.tcl',
                    internal / '_tk_data' / 'tk.tcl']
        required += [internal / Path(path).name for path in runtime['binaries']]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise RuntimeError('Incomplete Step02 runtime: ' + ', '.join(missing))
        runtime['package_check'] = 'PASS'
    print(json.dumps(runtime))


if __name__ == '__main__':
    main()
