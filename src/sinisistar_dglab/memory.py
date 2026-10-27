"""Windows read-only process primitives adapted from Ricca (GPL-3.0-only)."""
import ctypes,os,struct
from ctypes import wintypes
TH32CS_SNAPPROCESS=2
TH32CS_SNAPMODULE=8
TH32CS_SNAPMODULE32=16
PROCESS_QUERY_INFORMATION=0x400
PROCESS_QUERY_LIMITED_INFORMATION=0x1000
PROCESS_VM_READ=0x10
INVALID_HANDLE_VALUE=ctypes.c_void_p(-1).value
MAX_PATH=260
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * MAX_PATH),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32FirstW.restype = wintypes.BOOL
kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class ProbeError(RuntimeError):
    pass


def _win_error(action: str) -> ProbeError:
    error = ctypes.get_last_error()
    return ProbeError(f"{action} failed (Windows error {error}: {ctypes.FormatError(error).strip()})")


def _snapshot(flags: int, process_id: int = 0) -> int:
    handle = kernel32.CreateToolhelp32Snapshot(flags, process_id)
    if handle == INVALID_HANDLE_VALUE:
        raise _win_error("CreateToolhelp32Snapshot")
    return handle


def _process_image_path(process_id: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return ""
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(capacity)):
            return ""
        return os.path.normcase(os.path.abspath(buffer.value))
    finally:
        kernel32.CloseHandle(handle)


def find_process_id(name: str, expected_path: str = "") -> int:
    expected = os.path.normcase(os.path.abspath(expected_path)) if expected_path else ""
    snapshot = _snapshot(TH32CS_SNAPPROCESS)
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == name.casefold():
                process_id = int(entry.th32ProcessID)
                if not expected or _process_image_path(process_id) == expected:
                    return process_id
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    if expected:
        raise ProbeError(f"Selected game executable is not running: {expected_path}")
    raise ProbeError(f"{name} is not running")


def find_module_base(process_id: int, name: str) -> int:
    snapshot = _snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, process_id)
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szModule.casefold() == name.casefold():
                return int(entry.modBaseAddr)
            ok = kernel32.Module32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    raise ProbeError(f"{name} is not loaded in process {process_id}")


class ProcessReader:
    def __init__(self, process_id: int):
        self.process_id = process_id
        self.handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, process_id
        )
        if not self.handle:
            raise _win_error(f"OpenProcess({process_id})")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "ProcessReader":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        ):
            raise _win_error(f"ReadProcessMemory(0x{address:X})")
        if bytes_read.value != size:
            raise ProbeError(
                f"Short memory read at 0x{address:X}: expected {size}, got {bytes_read.value}"
            )
        return buffer.raw

    def pointer(self, address: int, label: str) -> int:
        value = self.pointer_value(address)
        if value == 0:
            raise ProbeError(
                f"{label} is null; load a save and enter an active gameplay stage"
            )
        return value

    def pointer_value(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def uint32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def int32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def uint8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def float32(self, address: int) -> float:
        return struct.unpack("<f", self.read(address, 4))[0]

    def boolean(self, address: int) -> bool:
        return bool(self.uint8(address))

    def managed_string(self, pointer_address: int, max_chars: int = 4096) -> str:
        """Read a nullable IL2CPP System.String pointer."""
        string_object = self.pointer_value(pointer_address)
        if not string_object:
            return ""
        length = self.int32(string_object + 0x10)
        if length < 0 or length > max_chars:
            raise ProbeError(
                f"Invalid managed string length {length} at 0x{string_object:X}"
            )
        if length == 0:
            return ""
        return self.read(string_object + 0x14, length * 2).decode(
            "utf-16-le", errors="replace"
        )

