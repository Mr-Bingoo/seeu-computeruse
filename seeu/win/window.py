# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 找窗口、窗口信息、截窗口。

App 的写法(跟 Mac 版对齐):
  "Notepad" / "notepad.exe"        按程序名(不分大小写,.exe 可写可不写)
  "Notepad「long.txt」"            程序名 + 窗口标题里有这几个字(App 开着好几个窗口时用)
  "long.txt - Notepad"             程序名对不上就按标题片段找
  "#66624"                         直接给窗口号
同一个程序好几个窗口:取叠放次序最上面那个(= 最近用过的),跟 Mac 版取前面那个窗口一致。
"""
import ctypes
import ctypes.wintypes as wt
import re
import struct
import zlib

from seeu.win import api

u, k, g = api.user32, api.kernel32, api.gdi32


def text(h):
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, buf, 512)
    return buf.value


def cls(h):
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, buf, 256)
    return buf.value


def rect(h):
    r = wt.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def client_origin(h):
    p = wt.POINT(0, 0)
    u.ClientToScreen(h, ctypes.byref(p))
    return p.x, p.y


def pid_tid(h):
    pid = wt.DWORD()
    tid = u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value, tid


def exe(pid):
    h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value.rsplit("\\", 1)[-1]
        return "?"
    finally:
        k.CloseHandle(h)


def info(h):
    pid, _ = pid_tid(h)
    x, y, w, hh = rect(h)
    return {"hwnd": int(h), "title": text(h), "class": cls(h), "exe": exe(pid), "pid": pid, "rect": [x, y, w, hh],
            "minimized": bool(u.IsIconic(h)), "elevated": elevated(pid), "other_desktop": other_desktop(h)}


OTHER_DESKTOP = ("窗口在另一个虚拟桌面上:后台点不动时不借鼠标、不借前台"
                 "(一拉前台系统就会把你切到那个桌面);这一步请你切过去,或把窗口挪到现在的桌面")


def other_desktop(h):
    """这个窗口在不在「别的虚拟桌面」上(11-14 虚拟机实测):系统把别的桌面的窗口藏起来(DWM 隐身标记 = 2,shell 藏的)。
    这种窗口:后台截图、打字照常;控件清单只读得到窗口边框那几项;一拉前台(借鼠标 / 借前台按下)系统就把用户切到那个桌面。
    最小化的不算(那是另一回事)。查不到当「不是」。"""
    try:
        if u.IsIconic(h):
            return False
        v = wt.DWORD()
        if ctypes.WinDLL("dwmapi").DwmGetWindowAttribute(wt.HWND(int(h)), 14, ctypes.byref(v), ctypes.sizeof(v)) != 0:
            return False
        return bool(v.value & 2)      # 是组合标记(1 = 程序自己藏、2 = 系统藏、4 = 跟着上级藏),按位看
    except Exception:   # noqa: BLE001
        return False



_dwm = []


def _dwmapi():
    if not _dwm:
        _dwm.append(ctypes.WinDLL("dwmapi"))
    return _dwm[0]


SEEU_OVERLAYS = ("SeeUFloat", "SeeUToast", "SeeUCursor")


def _clear_layer(h):
    """分层窗口里哪些不算实心盖住(11-15 复查):整体透明度 < 200 的半透明遮罩;SeeU 自己的浮标 / 提示条;
    逐像素透明、又是「不抢焦点的工具浮层」的(录屏框、桌面挂件这类)。
    🔴 逐像素透明的普通窗口照算盖住:微信、QQ、钉钉用它画阴影圆角,窗口本身是实心的(快速复查)。"""
    try:
        ex = u.GetWindowLongW(h, -20)
        if not (ex & 0x80000):                                 # WS_EX_LAYERED
            return False
        if cls(h) in SEEU_OVERLAYS:
            return True
        a, fl = ctypes.c_ubyte(255), wt.DWORD(0)
        if not u.GetLayeredWindowAttributes(h, None, ctypes.byref(a), ctypes.byref(fl)):
            # 逐像素透明(UpdateLayeredWindow):只放过工具浮层(WS_EX_TOOLWINDOW + WS_EX_NOACTIVATE)
            return bool(ex & 0x80) and bool(ex & 0x08000000)
        if fl.value & 2:                                       # LWA_ALPHA
            return a.value < 200
        return False
    except Exception:   # noqa: BLE001
        return False


def _cloaked(h):
    try:
        v = wt.DWORD()
        if _dwmapi().DwmGetWindowAttribute(wt.HWND(int(h)), 14, ctypes.byref(v), ctypes.sizeof(v)) != 0:
            return False
        return v.value != 0
    except Exception:   # noqa: BLE001
        return False


def visible_part(h, n=24):
    """窗口有多少露在屏幕上(0~1,11-15):在窗口里取 n×n 个点,看有几个点没被它上面的窗口盖住、也没跑出屏幕。
    上面的窗口只算看得见、没最小化、没隐身(别的虚拟桌面的窗口是隐身的)、不是「点得穿」的(SeeU 的光标、提示条这类)。"""
    x, y, w, hh = rect(h)
    if w <= 0 or hh <= 0 or u.IsIconic(h):
        return 0.0
    vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
    vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    gw = u.GetWindow
    above, cur, n_up = [], gw(h, 3), 0       # GW_HWNDPREV:叠放次序里往上走
    while cur and n_up < 500:               # 加上限(11-15 复查)
        n_up += 1
        if u.IsWindowVisible(cur) and not u.IsIconic(cur) and not _cloaked(cur) \
                and not (u.GetWindowLongW(cur, -20) & 0x20) and not _clear_layer(cur):      # WS_EX_TRANSPARENT、全透明
            ax, ay, aw, ah = rect(cur)
            if aw > 0 and ah > 0:
                above.append((ax, ay, ax + aw, ay + ah))
        cur = gw(cur, 3)
    seen = 0
    for i in range(n):
        px = x + (i + 0.5) * w / n
        for j in range(n):
            py = y + (j + 0.5) * hh / n
            if not (vx <= px < vx + vw and vy <= py < vy + vh):
                continue
            if not any(a[0] <= px < a[2] and a[1] <= py < a[3] for a in above):
                seen += 1
    return seen / float(n * n)


STALE_CLASSES = ("Chrome_WidgetWin_",)      # Chrome、Edge、Electron 程序(VS Code、Cursor、Trae、WorkBuddy、豆包…)


def stale_shot(h):
    """后台截到的会不会是旧画面(11-15 Win10 实测):Chrome / Electron 窗口整个被盖住(或全在屏幕外)时不重画,
    PrintWindow 拿到的是最后一次画的那一帧 —— 照它按位置点会点错(Win10 上照旧图点 WorkBuddy,点中了别的卡片)。"""
    try:
        return cls(h).startswith(STALE_CLASSES) and visible_part(h) == 0.0
    except Exception:   # noqa: BLE001
        return False

_adv = None


def _token_elevated(hproc):
    global _adv
    if _adv is None:
        _adv = ctypes.WinDLL("advapi32", use_last_error=True)
        _adv.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
        _adv.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    tok = wt.HANDLE()
    if not _adv.OpenProcessToken(hproc, 0x0008, ctypes.byref(tok)):     # TOKEN_QUERY
        return None
    try:
        val, n = wt.DWORD(), wt.DWORD()
        if _adv.GetTokenInformation(tok, 20, ctypes.byref(val), 4, ctypes.byref(n)):   # TokenElevation
            return bool(val.value)
        return None
    finally:
        k.CloseHandle(tok)


def elevated(pid):
    """这个进程是不是以管理员身份运行。读不到(系统进程)返回 None。"""
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        return _token_elevated(h)
    finally:
        k.CloseHandle(h)


def self_elevated():
    k.GetCurrentProcess.restype = wt.HANDLE
    return bool(_token_elevated(k.GetCurrentProcess()))


def list_windows():
    """看得见的顶层窗口,按叠放次序(最上面的在前)。"""
    out = []

    @api.WNDENUMPROC
    def cb(h, _):
        if u.IsWindowVisible(h):
            t = text(h)
            _, _, w, hh = rect(h)
            if t and w > 50 and hh > 30:
                out.append(info(h))
        return True
    u.EnumWindows(cb, 0)
    return out


def _exe_key(name):
    n = name.strip().lower()
    return n[:-4] if n.endswith(".exe") else n


_SPLIT = re.compile(r"^(.*?)「(.*)」$")


def split_target(app):
    """"Notepad「标题」" → ("Notepad", "标题");没写标题 → (app, None)。"""
    m = _SPLIT.match(str(app).strip())
    return (m.group(1).strip(), m.group(2)) if m else (str(app).strip(), None)


def find(app):
    """App 写法 → 窗口信息 dict;找不到抛 RuntimeError。"""
    a = str(app).strip()
    if a.startswith("#") and a[1:].isdigit():
        h = int(a[1:])
        if not u.IsWindow(h):
            raise RuntimeError(f"没有窗口号 {h} 这个窗口了")
        return info(h)
    name, title = split_target(a)
    wins = list_windows()
    key = _exe_key(name)
    hits = [w for w in wins if _exe_key(w["exe"]) == key]
    if title is not None:
        hits = [w for w in hits if title.lower() in w["title"].lower()]
    if not hits and title is None:
        hits = [w for w in wins if name.lower() in w["title"].lower()]
    if not hits:                      # 11-15(照 Mac 版 ax.canon_name):AI 写中文名「记事本」,英文 Windows 上叫 Notepad(反过来也认)
        try:
            from seeu.win import openapp
            alt = openapp.canon(name)
        except Exception:   # noqa: BLE001
            alt = None
        if alt:
            k2, al = _exe_key(alt.replace(" ", "")), alt.lower()
            # 11-15 复查:原来按标题子串,「设置」→ Settings 会对上「settings.json - Visual Studio Code」
            hits = [w for w in wins if _exe_key(w["exe"]) == k2 or w["title"].strip().lower() == al
                    or w["title"].strip().lower().endswith(" - " + al)]
            if title is not None:
                hits = [w for w in hits if title.lower() in w["title"].lower()]
    if not hits:
        raise RuntimeError(f"没有窗口:{app}(程序没开,或名字不对;python -m seeu windows 看看有哪些)")
    return hits[0]


def children(h):
    out = []

    @api.WNDENUMPROC
    def cb(c, _):
        out.append({"hwnd": int(c), "class": cls(c), "visible": bool(u.IsWindowVisible(c))})
        return True
    u.EnumChildWindows(h, cb, 0)
    return out


def child_at(top, sx, sy):
    """屏幕点 (sx, sy) 下最深的子窗口 → (子窗口, 子窗口客户区坐标 x, y)。"""
    ox, oy = client_origin(top)
    cur, x, y = int(top), sx - ox, sy - oy
    while True:
        c = u.RealChildWindowFromPoint(cur, wt.POINT(x, y))
        if not c or int(c) == cur:
            return cur, x, y
        cx, cy = client_origin(c)
        px, py = client_origin(cur)
        x, y = x + px - cx, y + py - cy
        cur = int(c)


def focus_of(top):
    """目标窗口所在线程的焦点控件(窗口在后台也查得到);查不到给窗口本身。"""
    _, tid = pid_tid(top)
    gti = api.GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(api.GUITHREADINFO)
    if u.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
        return int(gti.hwndFocus)
    return int(top)


def top_of(h):
    r = api.user32.GetAncestor(h, api.GA_ROOT)
    return int(r or h)


def foreground():
    return int(u.GetForegroundWindow() or 0)


def cursor():
    """真鼠标位置(物理像素;用 GetPhysicalCursorPos,11-11 踩过 GetCursorPos 单位会变)。"""
    p = wt.POINT()
    u.GetPhysicalCursorPos(ctypes.byref(p))
    return p.x, p.y


# ─────────────────────────────── 截窗口 ───────────────────────────────

def capture(h):
    """PrintWindow 后台截窗口 → (w, h, BGRA 字节)。被挡着也截得到(11-10 真机);最小化的截不到 → 抛 RuntimeError。"""
    if u.IsIconic(h):
        raise RuntimeError("窗口最小化了,截不到画面")
    _, _, w, hh = rect(h)
    if w <= 0 or hh <= 0:
        raise RuntimeError("窗口没有大小,截不到画面")
    hdc = u.GetDC(None)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, hh)
    old = g.SelectObject(mem, bmp)
    try:
        if not u.PrintWindow(h, mem, api.PW_RENDERFULLCONTENT):
            u.PrintWindow(h, mem, 0)
        bi = api.BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(api.BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount, bi.biCompression = w, -hh, 1, 32, 0
        buf = ctypes.create_string_buffer(w * hh * 4)
        g.GetDIBits(mem, bmp, 0, hh, buf, ctypes.byref(bi), 0)
        return w, hh, buf.raw
    finally:
        g.SelectObject(mem, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, hdc)


def shrink(w, h, bgra, max_side=1280):
    """长边缩到 max_side 以内(隔点取样,纯标准库,切片在 C 里做,2500×1900 约几十毫秒)。返回 (w2, h2, BGRA)。
    给 AI 的截图用(省 token);缩放系数是整数,实际尺寸以返回值为准。"""
    f = max(1, -(-max(w, h) // max_side))       # 向上取整
    if f == 1:
        return w, h, bgra
    w2, h2 = w // f, h // f
    row, out = w * 4, bytearray(w2 * h2 * 4)
    for y in range(h2):
        line = bgra[y * f * row:y * f * row + row]
        dst = y * w2 * 4
        for c in range(4):
            out[dst + c:dst + w2 * 4:4] = line[c::4 * f][:w2]
    return w2, h2, bytes(out)


def png_bytes(w, h, bgra):
    """BGRA → PNG(纯标准库)。"""
    raw = bytearray()
    row = w * 4
    for y in range(h):
        raw.append(0)
        line = bgra[y * row:(y + 1) * row]
        rgb = bytearray(w * 3)
        rgb[0::3] = line[2::4]
        rgb[1::3] = line[1::4]
        rgb[2::3] = line[0::4]
        raw += rgb

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def diff_percent(a, b, box=None, w=0, step=3, thresh=16):
    """两张同尺寸 BGRA 画面百分之几的像素不一样(抽样)。box=(x0,y0,x1,y1) 只比这块(要给 w)。尺寸不同返回 100。"""
    if len(a) != len(b) or not a:
        return 100.0
    total = changed = 0
    if box and w:
        x0, y0, x1, y1 = box
        rows = range(max(0, y0), y1, step)
        idx = (((y * w) + x) * 4 for y in rows for x in range(max(0, x0), min(w, x1), step))
    else:
        idx = (p * 4 for p in range(0, len(a) // 4, step))
    for i in idx:
        if i + 2 >= len(a):
            continue
        total += 1
        if abs(a[i] - b[i]) > thresh or abs(a[i + 1] - b[i + 1]) > thresh or abs(a[i + 2] - b[i + 2]) > thresh:
            changed += 1
    return round(changed * 100.0 / max(total, 1), 3)
