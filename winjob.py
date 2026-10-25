import _winapi
from contextlib import contextmanager
import ctypes as c
import msvcrt
import os
import subprocess

kernel = c.WinDLL("kernel32", use_last_error=True)
kernel.CreateJobObjectW.argtypes = [c.c_void_p, c.c_wchar_p]
kernel.CreateJobObjectW.restype = c.c_void_p
kernel.AssignProcessToJobObject.argtypes = [c.c_void_p, c.c_void_p]
kernel.SetInformationJobObject.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_uint32]
kernel.QueryInformationJobObject.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_uint32, c.c_void_p]
kernel.TerminateJobObject.argtypes = [c.c_void_p, c.c_uint32]
kernel.ResumeThread.argtypes = [c.c_void_p]
kernel.ResumeThread.restype = c.c_uint32
kernel.SetThreadExecutionState.argtypes = [c.c_uint32]
kernel.SetThreadExecutionState.restype = c.c_uint32


class Accounting(c.Structure):
    _fields_ = [(name, c.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        (name, c.c_uint32) for name in ("faults", "processes", "active", "terminated")]


class BasicLimits(c.Structure):
    _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", c.c_uint32),
                ("minimum_ws", c.c_size_t), ("maximum_ws", c.c_size_t), ("active", c.c_uint32),
                ("affinity", c.c_size_t), ("priority", c.c_uint32), ("scheduling", c.c_uint32)]


class ExtendedLimits(c.Structure):
    _fields_ = [("basic", BasicLimits), ("io", c.c_uint64 * 6), ("memory", c.c_size_t * 4)]


def checked(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


def accounting(job):
    info = Accounting()
    checked(kernel.QueryInformationJobObject(job, 1, c.byref(info), c.sizeof(info), None))
    return info


def cpu(job):
    info = accounting(job)
    return (info.user + info.kernel) / 10000000.0


def terminate(job):
    checked(kernel.TerminateJobObject(job, 1))


@contextmanager
def awake():
    previous = checked(kernel.SetThreadExecutionState(0x80000001))
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(previous)


@contextmanager
def start(args, cwd, env, out, err):
    job = checked(kernel.CreateJobObjectW(None, None))
    process = thread = None
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000
        checked(kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
        with open(os.devnull, "rb") as input_file:
            handles = [msvcrt.get_osfhandle(file.fileno()) for file in (input_file, out, err)]
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            for handle in handles: os.set_handle_inheritable(handle, True)
            try:
                # Suspender antes de asignar el job incluye también los hijos de los lanzadores.
                process, thread, _, _ = _winapi.CreateProcess(None, subprocess.list2cmdline(args), None, None, True,
                    0x4 | 0x400 | subprocess.CREATE_NO_WINDOW, env, str(cwd), startup)
            finally:
                for handle in handles: os.set_handle_inheritable(handle, False)
        checked(kernel.AssignProcessToJobObject(job, process))
        if kernel.ResumeThread(thread) == 0xFFFFFFFF:
            raise c.WinError(c.get_last_error())
        _winapi.CloseHandle(thread); thread = None
        yield job, process
    finally:
        kernel.TerminateJobObject(job, 1)
        if process is not None:
            if _winapi.GetExitCodeProcess(process) == 259: _winapi.TerminateProcess(process, 1)
            _winapi.WaitForSingleObject(process, 5000)
            _winapi.CloseHandle(process)
        if thread is not None: _winapi.CloseHandle(thread)
        _winapi.CloseHandle(job)


def exit_code(process):
    return _winapi.GetExitCodeProcess(process)
