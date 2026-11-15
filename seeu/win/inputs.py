# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 后台点击、打字、按键、滚动,和「借前台再还」。

全部是往目标窗口发消息(PostMessage),不动真鼠标、不换前台。依据(探路,见 SeeU-相关要点「11-11 C-1.1.5」):
  - 点击:发给那一点下最深的子窗口(Chrome 是 Chrome_RenderWidgetHostHWND)。老程序、Chrome、VS Code 都认;WinUI 3 新界面不认。
  - 打字:WM_CHAR 一个字一个字发,中文直接进。WinUI 窗口(新记事本)焦点读出来是外壳,要发给 RichEditD2DPT。
  - 回车这类键:Post「按下 + 抬起」、扫描码带对,对方自己的消息循环会翻出字符;🔴 别再补 WM_CHAR(会换两行)。
  - 滚动:老程序认 WM_MOUSEWHEEL(发给那一点下的子窗口);Chrome / Electron 不认滚轮消息,认 WM_VSCROLL(一格约 100 像素)。
  - 借前台:UIA 按按钮会把目标拉到前台;SeeU 是后台进程时直接 SetForegroundWindow 还不回去(系统拦),
    先发一个空键(VK 0xE8,不对应任何字)让系统认为我们刚收到输入,再还就成(3/3,占前台 0.12~0.18 秒)。
"""
import ctypes
import time

from seeu.win import api, window as W

u = api.user32

VK = {"return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B, "backspace": 0x08, "delete": 0x2E,
      "forwarddelete": 0x2E, "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "apps": 0x5D}
VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
MOD_VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12}
# 「是能打字的地方」的子窗口类名:焦点读不出来(WinUI 外壳、后台 Chrome)时按这个找
EDIT_CLASSES = ("RichEditD2DPT", "Chrome_RenderWidgetHostHWND", "Edit", "RICHEDIT50W", "RichEdit20W", "Scintilla")
CHROMIUM_CLASSES = ("Chrome_RenderWidgetHostHWND",)
EMPTY_VK = 0xE8   # 系统没分配的虚拟键,只拿来「让系统认为刚收到输入」


def _lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def click(top, sx, sy, right=False, double=False):
    """后台点屏幕点 (sx, sy)。返回 (收到消息的子窗口, 类名)。"""
    t, x, y = W.child_at(top, sx, sy)
    down, up, mk = (api.WM_RBUTTONDOWN, api.WM_RBUTTONUP, api.MK_RBUTTON) if right else \
        (api.WM_LBUTTONDOWN, api.WM_LBUTTONUP, api.MK_LBUTTON)
    lp = _lp(x, y)
    u.PostMessageW(t, api.WM_MOUSEMOVE, 0, lp)
    u.PostMessageW(t, down, mk, lp)
    u.PostMessageW(t, up, 0, lp)
    if double:
        time.sleep(0.05)
        u.PostMessageW(t, api.WM_LBUTTONDBLCLK, mk, lp)
        u.PostMessageW(t, up, 0, lp)
    return t, W.cls(t)


LONG_MAX_MS = 10000      # 长按上限(跟 Mac 版一样)


def long_press(top, sx, sy, ms=1000):
    """后台长按屏幕点:按下 → 停 ms 毫秒 → 松开(11-12)。返回 (收到消息的子窗口, 类名)。"""
    ms = max(50, min(int(ms), LONG_MAX_MS))
    t, x, y = W.child_at(top, round(sx), round(sy))
    lp = _lp(x, y)
    u.PostMessageW(t, api.WM_MOUSEMOVE, 0, lp)
    u.PostMessageW(t, api.WM_LBUTTONDOWN, api.MK_LBUTTON, lp)
    time.sleep(ms / 1000)
    u.PostMessageW(t, api.WM_LBUTTONUP, 0, lp)
    return t, W.cls(t)


def drag(top, pts, hold_ms=0, step_ms=15):
    """后台拖动(11-12):起点按下 → (停 hold_ms)→ 沿 pts 每段插几个点发「按着键移动」→ 终点松开。
    消息都发给起点处的那个子窗口,坐标按它算(拖出它的范围就是负数 / 超出,系统照样这么发)。
    只对认窗口消息的程序有效;自己读真鼠标位置的(很多画布、游戏)不认,交给真鼠标那一档。"""
    pts = [(round(px), round(py)) for px, py in pts]
    t, x0, y0 = W.child_at(top, pts[0][0], pts[0][1])
    ox, oy = pts[0][0] - x0, pts[0][1] - y0          # 屏幕点 → 这个子窗口里的坐标
    rel = [(round(px - ox), round(py - oy)) for px, py in pts]
    u.PostMessageW(t, api.WM_MOUSEMOVE, 0, _lp(*rel[0]))
    u.PostMessageW(t, api.WM_LBUTTONDOWN, api.MK_LBUTTON, _lp(*rel[0]))
    time.sleep(max(0, hold_ms) / 1000 + 0.05)
    for (ax, ay), (bx, by) in zip(rel, rel[1:]):
        n = max(2, int(max(abs(bx - ax), abs(by - ay)) / 20))
        for i in range(1, n + 1):
            u.PostMessageW(t, api.WM_MOUSEMOVE, api.MK_LBUTTON, _lp(round(ax + (bx - ax) * i / n), round(ay + (by - ay) * i / n)))
            time.sleep(step_ms / 1000)
    time.sleep(0.05)
    u.PostMessageW(t, api.WM_LBUTTONUP, 0, _lp(*rel[-1]))
    return t, W.cls(t)


def type_target(top):
    """往哪个子窗口发字:线程焦点是个真子窗口就用它;读出来是外壳本身(WinUI、后台 Chrome)就找能打字的子窗口。"""
    f = W.focus_of(top)
    # 🔴 焦点是按「线程」记的:Chrome 好几个窗口共用一个界面线程,读出来的可能是别的窗口里的控件(11-11 真机:字打进了另一个 Chrome 窗口)
    if f != int(top) and W.cls(f) != W.cls(top) and W.top_of(f) == int(top):
        return f
    kids = [c for c in W.children(top) if c["visible"]]
    for want in EDIT_CLASSES:
        for c in kids:
            if c["class"] == want:
                return c["hwnd"]
    return int(top)


WM_ACTIVATE, WM_ACTIVATEAPP, WM_NCACTIVATE = 0x0006, 0x001C, 0x0086
CHROMIUM_TOPS = ("Chrome_WidgetWin_1",)


class fake_active:
    """Chrome / Electron(VS Code)只在「自认为被激活」时才处理后台发来的按键和字符(11-11 重启后真机:回车、打字时灵时不灵,
    之前靠的是被点过、切过之后残留的激活状态)。动手前给目标窗口补发「你被激活了」(不真的切前台),做完补发「你失去激活了」还原。
    真机:前台是别的程序时 Chrome / VS Code 回车、打字都稳,前台一直没动;做完不还原,下一次不补发就又不认 → 还原有效。
    🔴 只补发「拿到焦点」(WM_SETFOCUS)不够。只对 Chromium 系窗口做,别的程序不需要、也别乱发。"""
    def __init__(self, top):
        self.top = int(top)
        self.on = W.cls(self.top) in CHROMIUM_TOPS

    def __enter__(self):
        if self.on:
            u.PostMessageW(self.top, WM_NCACTIVATE, 1, 0)
            u.PostMessageW(self.top, WM_ACTIVATEAPP, 1, 0)
            u.PostMessageW(self.top, WM_ACTIVATE, 1, 0)     # WA_ACTIVE
            time.sleep(0.15)
        return self

    def __exit__(self, *a):
        if self.on:
            time.sleep(0.05)
            u.PostMessageW(self.top, WM_ACTIVATE, 0, 0)
            u.PostMessageW(self.top, WM_ACTIVATEAPP, 0, 0)
            u.PostMessageW(self.top, WM_NCACTIVATE, 0, 0)
        return False


def type_text(top, text, target=None, gap=0.01):
    """WM_CHAR 逐字发。emoji 这类要两个 UTF-16 单元的,两半各发一次。换行按回车键发(见 key)。返回目标子窗口。"""
    t = target or type_target(top)
    with fake_active(top):
        for ch in text:
            if ch == "\n":
                _key(top, "return", (), t)
                continue
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                u.PostMessageW(t, api.WM_CHAR, int.from_bytes(b[i:i + 2], "little"), 1)
            time.sleep(gap)
    return t


def _vk_of(name):
    n = str(name).strip().lower()
    if n in VK:
        return VK[n]
    if len(n) == 1:
        r = u.VkKeyScanW(n)
        if r != -1:
            return r & 0xFF
    raise ValueError(f"不认识的键:{name}")


def key(top, name, mods=(), target=None):
    """后台按一个键(可带 ctrl / shift / alt),见 _key。Chromium 系窗口前后补发激活消息(见 fake_active)。"""
    t = target or type_target(top)
    with fake_active(top):
        return _key(top, name, mods, t)


def _key(top, name, mods=(), target=None):
    """后台按一个键(可带 ctrl / shift / alt)。修饰键也按「按下…抬起」发给同一个子窗口。
    ⚠️ 带修饰键的组合:有的程序读的是系统键盘状态(发消息改不了),可能不认 —— 调用方要核实。"""
    t = target or type_target(top)
    vk = _vk_of(name)
    mvk = [MOD_VK[m] for m in mods]
    alt = "alt" in mods
    down = api.WM_SYSKEYDOWN if alt else api.WM_KEYDOWN
    upm = api.WM_SYSKEYUP if alt else api.WM_KEYUP

    def lp(v, up):
        sc = u.MapVirtualKeyW(v, 0)
        x = 1 | (sc << 16) | ((1 << 29) if alt else 0)
        return x | (1 << 30) | (1 << 31) if up else x
    def send(post):
        for m in mvk:
            post(t, down, m, lp(m, False))
        post(t, down, vk, lp(vk, False))
        post(t, upm, vk, lp(vk, True))
        for m in reversed(mvk):
            post(t, upm, m, lp(m, True))
    if mvk:
        # 带修饰键:Post 完把「按着」的状态多留 0.5 秒,等对方处理完再改回去(11-11 真机:留 0.15 秒时 Chrome 时好时坏,
        # Ctrl+A 变成打出 a)。🔴 同步发(SendMessage)试过,Chrome 完全不认修饰键,别再试。
        _with_mods(t, mvk, lambda: send(u.PostMessageW), hold=0.5)
    else:
        send(u.PostMessageW)
    return t



_WARMED = set()


class wt_MSG(ctypes.Structure):
    import ctypes.wintypes as _w
    _fields_ = [("hwnd", _w.HWND), ("message", _w.UINT), ("wParam", _w.WPARAM), ("lParam", _w.LPARAM),
                ("time", _w.DWORD), ("pt", _w.POINT), ("lPrivate", _w.DWORD)]


def _with_mods(t, mvk, fn, hold=0.15):
    """程序判断 Ctrl / Shift / Alt 按没按,看的是它线程的键盘状态,光发消息改不了(11-11 真机:Ctrl+A 变成打出 a)。
    挂到目标线程上(共用键盘状态),临时把修饰键设成「按着」,发完等它处理掉再改回去、解挂。不碰用户正在用的前台线程。"""
    import ctypes
    _, tt = W.pid_tid(W.top_of(t))
    me = api.kernel32.GetCurrentThreadId()
    # 🔴 线程要先有自己的消息队列才挂得上别的线程(11-11 真机:每个进程第一次 Ctrl+A 都失败,后面的都成 —— 第一次挂失败了没查)。
    # PeekMessage 一下就会建队列。
    msg = wt_MSG()
    u.PeekMessageW(ctypes.byref(msg), None, 0x0400, 0x0400, 0)     # WM_USER,PM_NOREMOVE
    if (me, tt) not in _WARMED:
        # 🔴 每个进程第一次挂到某个线程上,键盘状态设了也不生效(11-11 真机:新进程第一次 Ctrl+A 在 Chrome、VS Code 里都打出了 a,
        # 之后的都对);先空挂一次再松开就好了(对照 2/2)。原因没查清,照做就行。
        if u.AttachThreadInput(me, tt, True):
            time.sleep(0.05)
            u.AttachThreadInput(me, tt, False)
            time.sleep(0.05)
        _WARMED.add((me, tt))
    attached = bool(u.AttachThreadInput(me, tt, True))
    if not attached:
        raise RuntimeError("挂不上目标程序的线程,带 Ctrl / Shift / Alt 的组合键发不了(目标可能是管理员窗口)")
    old = (ctypes.c_ubyte * 256)()
    u.GetKeyboardState(old)
    st = (ctypes.c_ubyte * 256)()
    ctypes.memmove(st, old, 256)
    for m in mvk:
        st[m] |= 0x80
        if m == 0x11:
            st[0xA2] |= 0x80      # 左 Ctrl
        elif m == 0x10:
            st[0xA0] |= 0x80      # 左 Shift
        elif m == 0x12:
            st[0xA4] |= 0x80      # 左 Alt
    try:
        u.SetKeyboardState(st)
        fn()
        time.sleep(hold)          # 等对方把消息处理掉(处理时读的是这时的状态)
    finally:
        u.SetKeyboardState(old)
        u.AttachThreadInput(me, tt, False)


def scroll(top, sx, sy, dy=0, dx=0):
    """后台在屏幕点 (sx, sy) 滚动。dy 负 = 往下翻(跟 Mac 版一样);单位约等于像素。返回用的办法。"""
    t, _, _ = W.child_at(top, sx, sy)
    c = W.cls(t)
    if c in CHROMIUM_CLASSES:
        # Chrome / Electron:滚轮消息不认,滚动条消息认,一格约 100 像素(11-11 真机)
        for amount, msg in ((dy, api.WM_VSCROLL), (dx, api.WM_HSCROLL)):
            n = max(1, round(abs(amount) / 100)) if amount else 0
            code = api.SB_LINEDOWN if amount < 0 else api.SB_LINEUP
            for _ in range(min(n, 50)):
                u.PostMessageW(t, msg, code, 0)
        return "滚动条消息"
    lp = _lp(sx, sy)   # 滚轮消息的坐标是屏幕坐标
    for amount, msg in ((dy, api.WM_MOUSEWHEEL), (dx, api.WM_MOUSEHWHEEL)):
        if not amount:
            continue
        notches = max(1, round(abs(amount) / 100))
        delta = 120 if amount > 0 else -120
        if msg == api.WM_MOUSEHWHEEL:
            delta = -delta          # 横向:正数 = 往右;dx 负 = 往左翻页 → 内容往右
        for _ in range(min(notches, 50)):
            u.PostMessageW(t, msg, (delta & 0xFFFF) << 16, lp)
    return "滚轮消息"


def borrow_front(target_top, act, timeout=5.0):
    """做一件会把 target_top 拉到前台的事(act),一被拉上去就把前台还给原来的窗口。
    返回 dict(stolen=被拉上去没有, back=还回去没有, held_ms=占了多久, how=用的办法)。等待有硬上限。"""
    if W.other_desktop(target_top):     # 11-14:按下会把窗口拉到前台 = 把用户切到那个虚拟桌面
        raise RuntimeError(W.OTHER_DESKTOP)
    fg0 = W.foreground()
    result = dict(stolen=False, back=True, held_ms=0, how="")
    import threading
    err = []

    def run():
        try:
            act()
        except Exception as e:      # noqa: BLE001
            err.append(e)
    th = threading.Thread(target=run, daemon=True)
    t0 = time.time()
    th.start()
    while time.time() - t0 < timeout:
        fg = W.foreground()
        if fg and fg != fg0 and fg0 and W.pid_tid(fg)[0] == W.pid_tid(target_top)[0]:
            s = time.time()
            result["stolen"] = True
            ok = give_back(fg0)
            result.update(back=ok[0], how=ok[1], held_ms=round((time.time() - s) * 1000))
            # 有的程序按完之后自己又把窗口拉上来一次(新建标签页之类),盯 0.8 秒,再被抢就再还(最多 3 次)
            t1, again = time.time(), 0
            while time.time() - t1 < 0.8 and again < 3:
                f2 = W.foreground()
                if f2 != fg0 and f2 and W.pid_tid(f2)[0] == W.pid_tid(target_top)[0]:
                    again += 1
                    ok = give_back(fg0)
                    result.update(back=ok[0], again=again)
                time.sleep(0.01)
            break
        if not th.is_alive() and time.time() - t0 > 1.0:
            break
        time.sleep(0.005)
    th.join(timeout=max(0.0, timeout - (time.time() - t0)))
    if err:
        raise err[0]
    return result


def give_back(fg0):
    """把前台还给 fg0。先直接还;不行就发空键再还(见文件开头)。返回 (还成没, 办法)。"""
    u.SetForegroundWindow(fg0)
    time.sleep(0.03)
    if W.foreground() == fg0:
        return True, "直接还"
    u.keybd_event(EMPTY_VK, 0, 0, 0)
    u.keybd_event(EMPTY_VK, 0, 2, 0)
    u.SetForegroundWindow(fg0)
    time.sleep(0.03)
    return W.foreground() == fg0, "空键再还"


def idle_seconds():
    """用户(或任何输入)最近一次动鼠标键盘到现在几秒。"""
    import ctypes
    li = api.LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(api.LASTINPUTINFO)
    if not u.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return max(0.0, (api.kernel32.GetTickCount() - li.dwTime) / 1000.0)
