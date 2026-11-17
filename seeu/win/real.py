# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 最后一档退路:借用户的真鼠标 / 真键盘(跟 Mac 版「借用鼠标」一个档次,归同一个设置管)。

后台(发消息)和借前台按下(UIA)都不行时才走这里:
  1. 让路:用户最近 1 秒内动过鼠标键盘就先等,最多等 6 秒;一直在用就不借,报「用户正在用电脑」(user_busy)。
  2. 把目标窗口拉到前台(空键 + SetForegroundWindow,见 inputs.give_back),核对那一点最上面的确实是目标窗口(没被挡、不是别的程序)。
  3. 真鼠标点 / 真键盘打(SendInput),整个过程约 0.2 秒。
  4. 还原:鼠标放回原处、前台还给原来的程序。
最小化的窗口不拉出来(会改窗口状态),直接报做不了。
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

from seeu.win import api, inputs, safety, window as W

u = api.user32
IDLE_NEED = 1.0       # 用户停手多久才借
WAIT_MAX = 6.0        # 最多等用户停手这么久


class UserBusy(RuntimeError):
    """用户正在用电脑,SeeU 不借。"""


class SeeUBusy(UserBusy):
    """别的 SeeU 任务正在借鼠标键盘,排队等到上限还没轮到(11-17 C-2.6 多任务调度)。不是被拦:稍后重试。"""


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


u.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
u.SendInput.restype = wt.UINT
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.WindowFromPoint.argtypes = [wt.POINT]
u.WindowFromPoint.restype = wt.HWND
u.BringWindowToTop.argtypes = [wt.HWND]

LEFTDOWN, LEFTUP, RIGHTDOWN, RIGHTUP = 0x0002, 0x0004, 0x0008, 0x0010
KEYUP, UNICODE = 0x0002, 0x0004


def _send(*items):
    arr = (INPUT * len(items))(*items)
    n = u.SendInput(len(items), arr, ctypes.sizeof(INPUT))
    if n != len(items):
        raise RuntimeError("系统没收下这次输入(可能被别的程序拦了,或目标是管理员窗口)")


def _mouse(flags):
    i = INPUT(type=0)
    i.u.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return i


MOVE, ABSOLUTE, VIRTUALDESK = 0x0001, 0x8000, 0x4000


def _move_abs(sx, sy):
    """真的鼠标移动到屏幕点(SendInput 绝对坐标)。"""
    vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)          # 虚拟桌面左上角
    vw, vh = max(1, u.GetSystemMetrics(78) - 1), max(1, u.GetSystemMetrics(79) - 1)
    i = INPUT(type=0)
    i.u.mi = MOUSEINPUT(round((sx - vx) * 65535 / vw), round((sy - vy) * 65535 / vh), 0, MOVE | ABSOLUTE | VIRTUALDESK, 0, 0)
    return i


def _key(vk=0, scan=0, flags=0):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def wait_idle():
    """等用户停手(最多 WAIT_MAX 秒)。一直在用抛 UserBusy。"""
    t0 = time.time()
    while time.time() - t0 < WAIT_MAX:
        if inputs.idle_seconds() >= IDLE_NEED:
            return
        time.sleep(0.1)
    raise UserBusy("用户正在用电脑,SeeU 先不借鼠标键盘(等用户停手再试)")


def _bring(top):
    if u.IsIconic(top):
        raise RuntimeError("窗口最小化了,SeeU 不把它拉出来(请先把窗口打开)")
    if W.other_desktop(top):        # 11-14:拉别的虚拟桌面上的窗口,系统会把用户切过去
        raise RuntimeError(W.OTHER_DESKTOP)
    if W.foreground() == top:
        return
    u.keybd_event(inputs.EMPTY_VK, 0, 0, 0)
    u.keybd_event(inputs.EMPTY_VK, 0, 2, 0)
    u.SetForegroundWindow(top)
    u.BringWindowToTop(top)
    t0 = time.time()
    while time.time() - t0 < 1.0:
        if W.foreground() == top:
            return
        time.sleep(0.02)
    raise RuntimeError("没能把目标窗口拉到前台")


def _check_point(top, sx, sy):
    h = u.WindowFromPoint(wt.POINT(int(sx), int(sy)))
    root = W.top_of(int(h)) if h else 0
    if root and root != int(top) and W.cls(root) == "SeeUFloat":    # 11-13:挡在上面的是 SeeU 自己的浮标 → 让它先收起来再看
        from seeu.win import floatwin
        floatwin.send("hide")
        time.sleep(0.25)
        h = u.WindowFromPoint(wt.POINT(int(sx), int(sy)))
        root = W.top_of(int(h)) if h else 0
    if root and root != int(top) and W.cls(root) == "SeeUToast":    # 11-14 复查:挡在上面的是 SeeU 自己的提示条 → 收掉再看
        from seeu.win import cursor
        cursor.send("untoast")
        time.sleep(0.25)
        h = u.WindowFromPoint(wt.POINT(int(sx), int(sy)))
        root = W.top_of(int(h)) if h else 0
    if root != int(top):
        who = W.info(root) if root else {}
        why = safety.why_not(who) if who else None
        raise RuntimeError("那个位置最上面不是目标窗口" + (f"(是「{who.get('title', '')[:20]}」)" if who else "")
                           + (f";而且{why}" if why else "") + ",SeeU 不点")


def _tell_float(top, kind):
    """告诉浮标「正在借用户的鼠标 / 键盘」(变橙、提示别动、这几秒不接鼠标)。浮标只是显示,出错不能耽误干活。"""
    try:
        import os
        from seeu.win import floatwin
        floatwin.borrow(os.path.splitext(W.info(int(top)).get("exe") or "")[0], kind)
    except Exception:   # noqa: BLE001
        pass


import contextlib


@contextlib.contextmanager
def slot():
    """借前台 / 借真鼠标那几百毫秒:SeeU 任务之间一次一个(sched.real_slot,最多等 15 秒,排不上抛 SeeUBusy)。
    调度模块出问题就不排(跟原来一样)。"""
    try:
        from seeu import sched
        cm = sched.real_slot()
        cm.__enter__()
    except Exception as ex:   # noqa: BLE001
        if type(ex).__name__ == "Busy":
            raise SeeUBusy(str(ex))
        yield
        return
    try:
        yield
    finally:
        cm.__exit__(None, None, None)


def borrow(top, act, kind="mouse"):
    """让路 → 拉前台 → act() → 还原前台和鼠标。返回 dict(held_ms, back)。kind = 借的是鼠标还是键盘(浮标上的提示用)。"""
    if W.other_desktop(top):        # 先查再让路、再亮浮标:不借就别打扰
        raise RuntimeError(W.OTHER_DESKTOP)
    # 11-17 C-2.6:几个 SeeU 任务同时要借真鼠标 → 排队,一次一个(同 Mac 的 sched.real_wait,最多等 15 秒)
    try:
        from seeu import sched
        slot = sched.real_slot()
    except Exception:   # noqa: BLE001 —— 调度模块出问题不挡借鼠标(跟原来一样)
        slot = None
    if slot is None:
        return _borrow(top, act, kind)
    try:
        waited = slot.__enter__()
    except sched.Busy as ex:
        raise SeeUBusy(str(ex))
    except Exception:   # noqa: BLE001
        return _borrow(top, act, kind)
    try:
        r = _borrow(top, act, kind)
        if waited and waited >= 0.5:
            r["waited"] = waited
        return r
    finally:
        slot.__exit__(None, None, None)


REBASE = threading.local()      # 11-18 C-2.8:act._verify 放进来的「重拍动作前」函数


def rebase():
    """排完队、等完用户停手,真动手前调:让 act._verify 重拍「动作前」(那张原来是排队前拍的)。出错不管。"""
    f = getattr(REBASE, "f", None)
    if f:
        try:
            f()
        except Exception:   # noqa: BLE001
            pass


def _borrow(top, act, kind):
    wait_idle()
    rebase()
    _tell_float(top, kind)
    fg0, c0 = W.foreground(), W.cursor()
    t0 = time.time()
    try:
        _bring(top)
        # 之前后台动作补发的「失去激活」可能比真切前台的消息还晚处理,把 Chromium 窗口又弄成「未激活」(11-11 真机:真键盘打字落空)
        # → 真到前台后再补一次「激活」
        if W.cls(top) in inputs.CHROMIUM_TOPS:
            u.PostMessageW(top, inputs.WM_NCACTIVATE, 1, 0)
            u.PostMessageW(top, inputs.WM_ACTIVATE, 1, 0)
            time.sleep(0.15)
        act()
        time.sleep(0.05)
    finally:
        u.SetCursorPos(*c0)
        back = True
        if fg0 and fg0 != top:
            back = inputs.give_back(fg0)[0]
    return dict(held_ms=round((time.time() - t0) * 1000), back=back)


def click(top, sx, sy, right=False):
    def act():
        _check_point(top, sx, sy)
        u.SetCursorPos(int(sx), int(sy))
        time.sleep(0.03)
        _check_point(top, sx, sy)            # 移过去之后再查一次(悬停弹出的提示框之类)
        d, up = (RIGHTDOWN, RIGHTUP) if right else (LEFTDOWN, LEFTUP)
        _send(_mouse(d), _mouse(up))
    return borrow(top, act)


def type_text(top, text):
    """真键盘打字(Unicode 输入,跟输入法无关)。换行按回车。"""
    def act():
        items = []
        for ch in text:
            if ch == "\n":
                items += [_key(0x0D), _key(0x0D, flags=KEYUP)]
                continue
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                unit = int.from_bytes(b[i:i + 2], "little")
                items += [_key(0, unit, UNICODE), _key(0, unit, UNICODE | KEYUP)]
        for i in range(0, len(items), 40):
            _send(*items[i:i + 40])
            time.sleep(0.01)
    return borrow(top, act, "keyboard")


def long_press(top, sx, sy, ms=1000):
    """真鼠标长按(11-12)。"""
    ms = max(50, min(int(ms), inputs.LONG_MAX_MS))

    def act():
        _check_point(top, sx, sy)
        u.SetCursorPos(int(sx), int(sy))
        time.sleep(0.03)
        _check_point(top, sx, sy)
        _send(_mouse(LEFTDOWN))
        try:
            time.sleep(ms / 1000)
        finally:
            _send(_mouse(LEFTUP))
    return borrow(top, act)


def drag(top, pts, hold_ms=0):
    """真鼠标拖动(11-12):起点、终点都要在目标窗口上(最上面就是它)才拖。"""
    def act():
        _check_point(top, *pts[0])
        _check_point(top, *pts[-1])
        u.SetCursorPos(int(pts[0][0]), int(pts[0][1]))
        time.sleep(0.03)
        _check_point(top, *pts[0])
        _send(_mouse(LEFTDOWN))
        try:
            time.sleep(max(0, hold_ms) / 1000 + 0.05)
            # 11-12 画图实测:中间点用 SetCursorPos 挪,画图(WinUI 指针输入)不当成「按着移动」,L 形拖成了起点到终点的斜线
            # → 中间点改用 SendInput 发真的鼠标移动(绝对坐标,按整个虚拟桌面换算到 0~65535)
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                n = max(2, int(max(abs(bx - ax), abs(by - ay)) / 20))
                for i in range(1, n + 1):
                    _send(_move_abs(ax + (bx - ax) * i / n, ay + (by - ay) * i / n))
                    time.sleep(0.012)
            time.sleep(0.05)
        finally:
            _send(_mouse(LEFTUP))
    return borrow(top, act)
