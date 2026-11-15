# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 系统接口声明(ctypes,只用标准库)。

从探路程序 `参考/Windows探路/probe.py` 挪过来整理的。🔴 64 位 Windows 上句柄、指针都是 8 字节,
不声明类型 ctypes 会按 int 传 → OverflowError(11-10 真机踩过),所以每个用到的函数都写明参数类型。
Mac 上 import 这个文件会失败(没有 windll),替身测试用 SEEU_WIN_FAKE 换掉整个模块。
"""
import ctypes
import ctypes.wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 坐标一律用物理像素(高分屏缩放下不乱)。UIA 也会把线程切成高 DPI 感知(11-11 踩过:前后两次 GetCursorPos 单位不一样),
# 进程一开始就设好,两边一致。
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0200, 0x0201, 0x0202, 0x0203
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MOUSEWHEEL, WM_MOUSEHWHEEL, WM_VSCROLL, WM_HSCROLL = 0x020A, 0x020E, 0x0115, 0x0114
SB_LINEUP, SB_LINEDOWN = 0, 1
WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0102, 0x0104, 0x0105
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
MK_LBUTTON, MK_RBUTTON, MK_SHIFT, MK_CONTROL = 0x0001, 0x0002, 0x0004, 0x0008
PW_RENDERFULLCONTENT = 0x00000002
GWL_STYLE, GWL_EXSTYLE = -16, -20
ES_PASSWORD = 0x0020
GA_ROOT = 2

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _sig(fn, args, res=None):
    fn.argtypes = args
    if res is not None:
        fn.restype = res


_sig(user32.EnumWindows, [WNDENUMPROC, wt.LPARAM], wt.BOOL)
_sig(user32.EnumChildWindows, [wt.HWND, WNDENUMPROC, wt.LPARAM], wt.BOOL)
_sig(user32.GetWindowTextW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.GetClassNameW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.PostMessageW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL)
_sig(user32.SendMessageW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], ctypes.c_ssize_t)
_sig(user32.SendMessageTimeoutW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t)],
     ctypes.c_ssize_t)
_sig(user32.PrintWindow, [wt.HWND, wt.HDC, wt.UINT], wt.BOOL)
_sig(user32.RealChildWindowFromPoint, [wt.HWND, wt.POINT], wt.HWND)
_sig(user32.GetForegroundWindow, [], wt.HWND)
_sig(user32.SetForegroundWindow, [wt.HWND], wt.BOOL)
_sig(user32.GetAncestor, [wt.HWND, wt.UINT], wt.HWND)
_sig(user32.GetParent, [wt.HWND], wt.HWND)
_sig(user32.GetDC, [wt.HWND], wt.HDC)
_sig(user32.ReleaseDC, [wt.HWND, wt.HDC], ctypes.c_int)
_sig(user32.IsWindow, [wt.HWND], wt.BOOL)
_sig(user32.IsWindowVisible, [wt.HWND], wt.BOOL)
_sig(user32.IsIconic, [wt.HWND], wt.BOOL)
_sig(user32.GetWindowRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL)
_sig(user32.GetClientRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL)
_sig(user32.ClientToScreen, [wt.HWND, ctypes.POINTER(wt.POINT)], wt.BOOL)
_sig(user32.GetWindowThreadProcessId, [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD)
_sig(user32.GetGUIThreadInfo, [wt.DWORD, ctypes.c_void_p], wt.BOOL)
_sig(user32.GetPhysicalCursorPos, [ctypes.POINTER(wt.POINT)], wt.BOOL)
_sig(user32.MapVirtualKeyW, [wt.UINT, wt.UINT], wt.UINT)
_sig(user32.VkKeyScanW, [wt.WCHAR], ctypes.c_short)
_sig(user32.keybd_event, [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t], None)
_sig(user32.GetWindowLongW, [wt.HWND, ctypes.c_int], ctypes.c_long)
_sig(user32.GetLastInputInfo, [ctypes.c_void_p], wt.BOOL)
_sig(user32.PeekMessageW, [ctypes.c_void_p, wt.HWND, wt.UINT, wt.UINT, wt.UINT], wt.BOOL)
_sig(user32.AttachThreadInput, [wt.DWORD, wt.DWORD, wt.BOOL], wt.BOOL)
_sig(user32.GetKeyboardState, [ctypes.c_void_p], wt.BOOL)
_sig(user32.SetKeyboardState, [ctypes.c_void_p], wt.BOOL)
_sig(gdi32.CreateCompatibleDC, [wt.HDC], wt.HDC)
_sig(gdi32.CreateCompatibleBitmap, [wt.HDC, ctypes.c_int, ctypes.c_int], wt.HBITMAP)
_sig(gdi32.SelectObject, [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ)
_sig(gdi32.DeleteObject, [wt.HGDIOBJ], wt.BOOL)
_sig(gdi32.DeleteDC, [wt.HDC], wt.BOOL)
_sig(gdi32.BitBlt, [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD], wt.BOOL)
_sig(user32.GetWindow, [wt.HWND, wt.UINT], wt.HWND)
_sig(user32.GetLayeredWindowAttributes, [wt.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], wt.BOOL)
_sig(gdi32.GetDIBits, [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT], ctypes.c_int)
_sig(kernel32.OpenProcess, [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE)
_sig(kernel32.QueryFullProcessImageNameW, [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)], wt.BOOL)
_sig(kernel32.CloseHandle, [wt.HANDLE], wt.BOOL)
_sig(kernel32.GetCurrentThreadId, [], wt.DWORD)
_sig(kernel32.GetTickCount, [], wt.DWORD)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]
