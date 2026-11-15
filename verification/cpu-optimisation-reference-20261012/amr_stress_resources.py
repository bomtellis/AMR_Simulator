"""RAM admission control and Windows process groups, without extra dependencies."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

GIB = 1024 ** 3


def watch_parent(parent_pid):
    """Exit a background worker even if its owner disappears before containment."""
    import time
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, parent_pid)
        if not handle:
            os._exit(3)
        try:
            while kernel.WaitForSingleObject(handle, 500) == 258:
                pass
        finally:
            kernel.CloseHandle(handle)
    else:
        while os.getppid() == parent_pid:
            time.sleep(.5)
    os._exit(3)


def process_alive(pid):
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


def wait_for_process_exit(pid, timeout=10):
    import time
    if os.name != 'nt':
        deadline = time.monotonic() + timeout
        while process_alive(pid):
            if time.monotonic() >= deadline:
                raise TimeoutError('Background worker did not exit')
            time.sleep(.05)
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if not process_alive(pid):
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
            raise TimeoutError('Background worker did not exit')
    finally:
        kernel.CloseHandle(handle)


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in ('total', 'available', 'total_page', 'available_page',
                                              'total_virtual', 'available_virtual', 'extended')]


class ProcessMemory(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('peak_rss', 'rss', 'peak_paged', 'paged', 'peak_nonpaged',
                                          'nonpaged', 'commit', 'peak_commit', 'private')]


def memory_status():
    if os.name == 'nt':
        value = MemoryStatus()
        value.length = ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            raise OSError('Cannot read available system RAM; stress workers were not started.')
        return {'total': value.total, 'available': value.available}
    fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {key: int(fields[field].split()[0]) * 1024 for key, field in
            [('total', 'MemTotal'), ('available', 'MemAvailable')]}


def process_memory(pid):
    if os.name != 'nt':
        fields = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        rss = int(fields['VmRSS'].split()[0]) * 1024
        return dict(rss=rss, private=rss, peak=max(rss, int(fields.get('VmHWM', '0').split()[0]) * 1024))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            raise ProcessLookupError(f'Worker {pid} has exited.')
        value = ProcessMemory()
        value.size = ctypes.sizeof(value)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.size):
            raise ctypes.WinError(ctypes.get_last_error())
        return dict(rss=value.rss, private=value.private, peak=max(value.peak_rss, value.peak_commit))
    finally:
        kernel.CloseHandle(handle)


def admission(settings, system, estimate, own, active_memory=0, active_count=0):
    """Respect user cap, physical headroom, and measured per-trial peak plus 50%."""
    reserve = min(system['total'] * .5, max(settings['reserve_ram_gib'] * GIB, system['total'] * .2))
    limit = min(settings['ram_limit_gib'] * GIB, system['total'] * .5)
    cost = max(256 * 1024 ** 2, estimate * 1.5)
    count = min(settings['workers'], max(1, (os.cpu_count() or 1) - 2))
    budget_slots = max(0, int((limit - own - active_memory) // cost))
    free_slots = max(0, int((system['available'] - reserve) // cost))
    return dict(limit=int(limit), reserve=int(reserve), cost=int(cost),
                slots=max(0, min(count - active_count, budget_slots, free_slots)))


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_ulonglong * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class ProcessGroup:
    """Closing the owner's handle kills every assigned worker, even on a crash.

    Windows also enforces an aggregate committed-memory ceiling. Workers wait
    on a gate until assignment succeeds, so execution never starts unprotected.
    """
    def __init__(self, limit_bytes):
        self.handle = None
        if os.name != 'nt':
            return
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        value = ExtendedLimits()
        value.basic.flags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        value.job_memory = int(limit_bytes)
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(value), ctypes.sizeof(value)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        if self.handle is None:
            return
        handle = self.kernel.OpenProcess(0x101, False, pid)  # TERMINATE | SET_QUOTA
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(handle)

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
