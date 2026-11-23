"""Stable generated files with content-addressed history and a runtime/generator lock."""
import os,json,hashlib,ctypes
from pathlib import Path

def lock_path(folder,project):return Path(folder)/'Step07_Logs'/(project+'.running.lock')
def check_windows_available(path):
    if os.name!='nt' or not path.exists():return
    api=ctypes.WinDLL('kernel32',use_last_error=True);api.CreateFileW.restype=ctypes.c_void_p
    api.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
    h=api.CreateFileW(str(path),0x80000000|0x40000000,0,None,3,0,None)
    if h==ctypes.c_void_p(-1).value:raise ValueError('FILE_BUSY_OR_NOT_WRITABLE: '+str(path))
    api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle(h)

def write_generated(files,folder,project,overwrite):
    folder=Path(folder);lock=lock_path(folder,project);lock.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ValueError('PROJECT_RUNNING_OR_STALE_LOCK: '+str(lock)+'; stop active script or inspect stale lock before updating')
    os.write(fd,json.dumps(dict(pid=os.getpid(),operation='GENERATE')).encode());os.close(fd)
    try:
        changes={};original={}
        for path,text in files.items():
            data=text.encode('utf-8');old=path.read_bytes() if path.exists() else None
            if old==data:continue
            if old is not None and not overwrite:raise ValueError('SCRIPT_OVERWRITE_CONFIRMATION_REQUIRED: '+str(path))
            check_windows_available(path);changes[path]=data;original[path]=old
        archive=folder/'Step07_Archive';backups=[]
        for path,old in original.items():
            if old is None:continue
            archive.mkdir(exist_ok=True);backup=archive/(path.name+'.'+hashlib.sha256(old).hexdigest()[:16]+'.bak')
            if backup.exists() and backup.read_bytes()!=old:raise ValueError('ARCHIVE_CONTENT_CONFLICT')
            if not backup.exists():backup.write_bytes(old)
            backups.append(str(backup))
        updated=[]
        try:
            for path,data in changes.items():
                temp=path.with_name(path.name+'.step07-writing')
                with temp.open('xb') as f:f.write(data)
                os.replace(temp,path);updated.append(path)
        except Exception:
            for path in reversed(updated):
                if original[path] is not None:path.write_bytes(original[path])
                else:path.unlink()
            raise
        return dict(status='UPDATED' if changes else 'ALREADY_IDENTICAL',updated=[str(p) for p in changes],backups=backups)
    finally:lock.unlink()
