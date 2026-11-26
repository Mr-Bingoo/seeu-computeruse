# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 代理光标(照 Mac 版 seeu_lib/cursor_overlay.py):纯显示的透明小窗口,画一个箭头跟着 SeeU 的动作走。

跟系统鼠标没关系,用户照常用自己的鼠标。样子和规则照 Mac:
  - 后台模式 = 紫色 + 「SeeU」;让路模式(借用户的鼠标键盘)= 亮橙 + 署名(没写署名用这台电脑的用户名)。
  - 箭头白描边、身后一团会呼吸的光晕、右下角名牌;移动走一条弧线、到点冲过一点再回、按速度倾斜;点击时箭头缩一下 + 一圈波纹。
  - 停下 5 秒后原地呼吸;60 秒没动作淡出;10 分钟没消息进程自己退出。
  - 目标窗口被挡住、或在别的虚拟桌面上,就不画(显示进程每 0.2 秒查一次)。
🔴 窗口永远不抢前台、不接鼠标(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)。
调用方:show(kind, x, y, label, color, owner, key, auto) / wait(key, on) / hide(key) / quit();坐标是屏幕物理像素(跟 SeeU 动作层一致)。
照 Mac:key = 哪个任务,一个任务一只光标(不带 key = 跟老调用共用一只);auto = 名牌按规则(屏幕上只有它一只写「SeeU」,
多只写任务名);wait = 排队中:箭头右上飘 z + 整只变淡到 0.45、不呼吸(待机光点只给「停下等下一步」,两种不叠)。
环境变量 SEEU_NO_CURSOR=1 不画(同 Mac)。显示进程:python -m seeu.win.cursor serve(调用方会自己拉起)。
"""
import json
import math
import os
import socket
import subprocess
import sys
import time

PORT = 47831                 # 同 Mac seeu_lib/cursor_overlay。🔴 别跟浮标(floatwin 47833)同号:原来撞号,两个显示进程只能活一个、消息串台
WIN_W, WIN_H = 150, 90           # 窗口大小(逻辑像素,乘缩放)—— 同 Mac 的点
TIP = (40.0, 40.0)               # 箭头尖端在窗口里的位置
PURPLE = (0.50, 0.47, 0.87)      # 后台模式(#7F77DD)
ORANGE = (1.0, 0.624, 0.039)     # 让路模式(#FF9F0A)
MOVE_S, MOVE_MAX_S = 0.28, 0.65  # 移动时长:按距离算,最短约 0.22、最长 0.65 秒
RING_S = 0.45                    # 点击波纹
FADE_AFTER_S = 60
ARC_K, ARC_MAX = 0.22, 90.0
OVERSHOOT = 1.25
TILT_K, TILT_MAX = 0.04, 0.35
GLOW_R = 30.0
PRESS_S = (0.09, 0.17)
IDLE_AFTER_S, BREATH_AMP, BREATH_S = 5.0, 0.18, 2.8
FOCUS_EVERY, FOCUS_S = 3, 1.0                                      # 每 3 次呼吸,缩回原大小那 1 秒里扫一道反光
SHINE_TAIL, SHINE_TIP, SHINE_W = (12.5, 16.5), (0.8, 0.6), 5.0     # 反光起止点(相对尖端)、光带半宽(同 Mac)
ARROW_C = (7.0, 9.0)
IDLE_EXIT_S = 600
MAX_CURSORS = 8                  # 同 Mac:一个任务一只光标,同时最多几只(再多挤掉最久没动的)
WAIT_ALPHA = 0.45                # 排队中整只光标的透明度(打瞌睡 + 变淡)
WAIT_MAX_S = 40                  # 排队提示最多显示这么久(调度那边排队上限 30 秒),没人来收就自己停
WAIT_FADE_S = 0.25               # 排队变淡 / 轮到变亮的过渡
ZZ_S = 2.7                       # 一个 z 飘完的时长;3 个错开 1/3(同 Mac)
ZZ_FROM, ZZ_TO = (17.0, 3.0), (32.0, -22.0)    # z 飘的起点、终点(z 的中心,相对尖端,y 朝下;同 Mac)
FONT = "Microsoft YaHei UI"       # 名牌里有中文时用
FONT_LATIN = "Segoe UI Semibold"  # 纯英文名牌(SeeU、@用户名)用,跟 Mac 的 10 号半粗最接近
TOAST_W, TOAST_H, TOAST_GAP, TOAST_BTN_W, TOAST_PAD = 340, 66, 10, 58, 10   # 提示条(同 Mac;PAD = 四周给阴影留的边)
OPEN_ZH, OPEN_EN = "打开 ›", "Open ›"


def _en():
    try:
        from seeu.i18n import lang
        return lang() == "en"
    except Exception:   # noqa: BLE001
        return False
# 箭头外形(相对尖端,同 Mac):("M", x, y) 起点,("L", x, y) 直线,("Q", cx, cy, x, y) 二次曲线
ARROW = [("M", 0.5, 1.5), ("L", 4, 17.5), ("Q", 4.6, 19.8, 6.2, 18.2), ("L", 9.2, 13.5), ("L", 14.8, 12.6),
         ("Q", 17, 12.1, 15.3, 10.6), ("L", 2, 0), ("Q", 0, -0.8, 0.5, 1.5)]
_last_xy = {}           # 光标名 → 上次送去的位置(按距离算走多久)


def travel_s(x0, y0, x1, y1, s=1.0):
    """离得越远走越久(同 Mac 公式:0.22 + 距离(点)× 0.0009,最长 0.65 秒)。s = 屏幕缩放(坐标是物理像素)。"""
    d = math.hypot(x1 - x0, y1 - y0) / max(s, 0.5)
    return min(MOVE_MAX_S, 0.22 + d * 0.0009)


# ───────── 调用方用的(任何平台都能导入;不在 Windows 上就什么也不做) ─────────
def send(*parts):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(json.dumps(list(parts), ensure_ascii=False).encode("utf-8"), ("127.0.0.1", PORT))
        s.close()
    except OSError:
        pass


def _running():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


_serve_fail = [0.0]


def ensure_serve(force=False):
    """显示进程没起就拉起(无窗口、跟调用方脱钩)。SEEU_NO_CURSOR=1 时不起(提示条 force=True 照起:那是留痕,不是光标)。"""
    if (os.environ.get("SEEU_NO_CURSOR") and not force) or sys.platform != "win32":
        return False
    if _running():
        _serve_fail[0] = 0.0              # 冷启动慢(杀毒在扫)超过 3 秒被记成起不来,其实后来起来了 → 放下
        return False
    if time.time() < _serve_fail[0]:      # 刚拉过没起来(沙箱 / 安全软件拦)→ 60 秒内不再试,免得每个动作白等 3 秒
        return False
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    env = dict(os.environ)
    lib = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
    args = [pyw if os.path.exists(pyw) else py, "-m", "seeu.win.cursor", "serve"]
    for flags in (0x00000008 | 0x01000000 | 0x00000200, 0x00000008 | 0x00000200):   # 先试脱离作业,被拒(Codex 里)就不带
        try:
            subprocess.Popen(args, env=env, creationflags=flags, close_fds=True)
            break
        except OSError:
            continue
    for _ in range(30):
        if _running():
            return True
        time.sleep(0.1)
    _serve_fail[0] = time.time() + 60
    return False


def show(kind, x, y, label="SeeU", color=PURPLE, owner=0, key=None, auto=False):
    """kind = move | click。返回光标走到位要多久(秒),调用方可以等这么久再动手(让波纹跟动作对上)。
    key = 哪个任务的光标(不传 = 跟老调用共用一只);auto = 名牌按规则(只有它一只时写 SeeU,多只时写 label)。"""
    if os.environ.get("SEEU_NO_CURSOR") or sys.platform != "win32":
        return 0.0
    ensure_serve()
    if time.time() < _serve_fail[0] and not _running():      # 显示进程起不来:没东西可等
        return 0.0
    k = str(key) if key else "_"
    prev = _last_xy.get(k)
    t = travel_s(*prev, x, y) if prev else MOVE_S
    _last_xy[k] = (x, y)
    send(kind, float(x), float(y), label, list(color), int(owner or 0), *([k, "auto" if auto else "fixed"] if key else []))
    return t


def wait(key, on=True):
    """排队中:这个任务的光标打瞌睡(飘 z + 变淡);on=False 收掉。光标还没出来过就什么也不做。"""
    if os.environ.get("SEEU_NO_CURSOR") or sys.platform != "win32" or not key:
        return
    send("wait", str(key), 1 if on else 0)


def toast(title, body="", secs=6.0, link=None, color=None):
    """屏幕右上角提示条(同 Mac cursor_overlay.toast)。link:点右下「打开 ›」时打开它;不给就只能点 × 关。secs 秒后淡出(最多 60)。"""
    if sys.platform != "win32":
        return
    ensure_serve(force=True)
    send("toast", str(title or ""), str(body or ""), float(secs), link or "", list(color) if color else None)


def hide(key=None):
    """藏光标:带 key 只藏那个任务的,不带全藏(老行为)。"""
    if key:
        send("hide", str(key))
    else:
        send("hide")


def quit():   # noqa: A001
    send("quit")


# ───────── 纯计算(离线测试用) ─────────
def ease_back(p, k=OVERSHOOT):
    p -= 1.0
    return 1.0 + (k + 1.0) * p * p * p + k * p * p


def arc_point(frm, to, ctl, p):
    """二次贝塞尔:从 frm 经过控制点 ctl 到 to,p = 0..1(可以略超 1,冲过头)。"""
    q = 1.0 - p
    return (q * q * frm[0] + 2 * q * p * ctl[0] + p * p * to[0], q * q * frm[1] + 2 * q * p * ctl[1] + p * p * to[1])


def arc_ctl(frm, to, s=1.0, side=None):
    """弧线控制点:中点往垂直方向偏 距离 × ARC_K(最多 ARC_MAX 点 × 缩放)。
    side=1 往上拱(屏幕 y 小的一边)、-1 往下;不给就随机一边(照 Mac cursor_overlay:按毫秒单双数挑)。"""
    if side is None:
        side = 1 if (int(time.time() * 1000) % 2) else -1
    mx, my = (frm[0] + to[0]) / 2.0, (frm[1] + to[1]) / 2.0
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    d = math.hypot(dx, dy)
    if d < 1:
        return (mx, my)
    off = min(ARC_MAX * s, d * ARC_K)
    nx, ny = -dy / d, dx / d
    if ny > 0:
        nx, ny = -nx, -ny
    if side < 0:
        nx, ny = -nx, -ny
    return (mx + nx * off, my + ny * off)


def press_scale(t):
    """点击后 t 秒箭头的缩放:0.09 秒缩到 0.82,0.17 秒弹回。"""
    a, b = PRESS_S
    if t < 0 or t > a + b:
        return 1.0
    return 1.0 - 0.18 * (t / a) if t < a else 0.82 + 0.18 * ((t - a) / b)


def breath(t):
    """停下以后的呼吸:0 → BREATH_AMP → 0,周期 BREATH_S。"""
    return BREATH_AMP * 0.5 * (1 - math.cos(2 * math.pi * (t % BREATH_S) / BREATH_S))


def breath_k(t):
    """待机后 t 秒的呼吸量 0..1(同 Mac:0.5 - 0.5 cos)。"""
    return 0.5 - 0.5 * math.cos(2 * math.pi * t / BREATH_S)


def shine(t):
    """待机后 t 秒的反光:返回 (光带位置 0..1 或 None, 光带透明度, 尖端闪光透明度)。周期 = BREATH_S × FOCUS_EVERY(同 Mac 的关键帧)。"""
    total = BREATH_S * FOCUS_EVERY
    u = t % total
    f0 = total - FOCUS_S
    band, op = None, 0.0
    if u >= f0:
        q = (u - f0) / FOCUS_S
        e = q * q * (3 - 2 * q)
        band, op = e, (0.35 + 0.6 * e) if q < 0.999 else 0.0
    if u < 0.45:
        fl = 0.9 * (1 - u / 0.45) if t >= total else 0.0     # 第一轮开头没有上一次的闪光
    elif u > total - 0.15:
        fl = 0.9 * (u - (total - 0.15)) / 0.15
    else:
        fl = 0.0
    return band, op, fl


def text_color(rgb):
    """名牌字色:浅色底用深色字,深色底用白字(同 Mac)。"""
    r, g, b = rgb
    return (0.10, 0.17, 0.27) if 0.299 * r + 0.587 * g + 0.114 * b > 0.62 else (1.0, 1.0, 1.0)


# ───────── 显示进程 ─────────
def serve():
    import ctypes
    from ctypes import wintypes as wt
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:   # noqa: BLE001
        pass
    u = ctypes.WinDLL("user32", use_last_error=True)
    g = ctypes.WinDLL("gdi32")
    k32 = ctypes.WinDLL("kernel32")
    gp = ctypes.WinDLL("gdiplus")
    P, F = ctypes.c_void_p, ctypes.c_float
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE), ("hIcon", P), ("hCursor", P), ("hbrBackground", P),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("a", wt.LONG), ("b", wt.LONG), ("c", wt.DWORD), ("d", wt.DWORD)]

    class BLEND(ctypes.Structure):
        _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]

    class RECTF(ctypes.Structure):
        _fields_ = [("x", F), ("y", F), ("w", F), ("h", F)]

    class GpStartup(ctypes.Structure):
        _fields_ = [("ver", ctypes.c_uint32), ("cb", P), ("a", wt.BOOL), ("b", wt.BOOL)]

    class PTF(ctypes.Structure):
        _fields_ = [("x", F), ("y", F)]

    u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]; u.DefWindowProcW.restype = LRESULT
    u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, P, wt.HINSTANCE, P]
    u.CreateWindowExW.restype = wt.HWND
    u.GetDC.argtypes = [wt.HWND]; u.GetDC.restype = P
    u.ReleaseDC.argtypes = [wt.HWND, P]
    u.UpdateLayeredWindow.argtypes = [wt.HWND, P, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), P, ctypes.POINTER(wt.POINT),
                                      wt.DWORD, ctypes.POINTER(BLEND), wt.DWORD]
    u.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, P]
    u.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.DestroyWindow.argtypes = [wt.HWND]
    u.WindowFromPoint.argtypes = [wt.POINT]; u.WindowFromPoint.restype = wt.HWND
    u.GetAncestor.argtypes = [wt.HWND, wt.UINT]; u.GetAncestor.restype = wt.HWND
    u.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]; u.MonitorFromPoint.restype = P
    u.LoadCursorW.argtypes = [P, P]; u.LoadCursorW.restype = P
    u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]; u.FindWindowW.restype = wt.HWND
    u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    u.IsWindowVisible.argtypes = [wt.HWND]; u.IsWindow.argtypes = [wt.HWND]; u.IsIconic.argtypes = [wt.HWND]
    g.CreateCompatibleDC.argtypes = [P]; g.CreateCompatibleDC.restype = P
    g.CreateDIBSection.argtypes = [P, P, wt.UINT, ctypes.POINTER(P), P, wt.DWORD]; g.CreateDIBSection.restype = P
    g.SelectObject.argtypes = [P, P]; g.SelectObject.restype = P
    g.DeleteObject.argtypes = [P]; g.DeleteDC.argtypes = [P]
    k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]; k32.GetModuleHandleW.restype = wt.HINSTANCE

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", PORT))
        sock.setblocking(False)
    except OSError:
        return                                   # 已经有一份在跑

    tok = ctypes.c_size_t()
    gp.GdiplusStartup(ctypes.byref(tok), ctypes.byref(GpStartup(1, None, False, False)), None)

    st = dict(msg=time.time(), quit=False)          # 全局:最后一次收到消息(空闲退出看它)、要不要退出;提示条也用
    curs = {}                                       # 光标名(任务)→ 这只光标的状态;老调用不带名字 = "_"

    def new_cursor(key, now):
        """一只光标一份状态 + 一个透明窗口(原来全机一份的那些字段,原样搬进来)。"""
        h = u.CreateWindowExW(EX_CUR, "SeeUCursor", "SeeU cursor", 0x80000000, 0, 0, WIN_W, WIN_H, None, None, hinst, None)
        return dict(key=key, hwnd=h, on_screen=False, cur=None, frm=None, to=None, ctl=None, t0=0.0, dur=MOVE_S, ring_t0=None,
                    press_t0=None, tilt=0.0, last=now, shown=False, alpha=0.0, label="SeeU", label_raw="SeeU", auto=False,
                    color=PURPLE, owner=0, vis=True, last_chk=0.0, s=1.0, arrive=now, waiting=False, wait_t=0.0, wait_fade=0.0)

    def get_cur(key, now):
        c = curs.get(key)
        if c is None:
            if len(curs) >= MAX_CURSORS:            # 有上限:挤掉最久没动的那只
                old = min(curs.values(), key=lambda x: x["last"])
                retire(old)
            c = curs[key] = new_cursor(key, now)
        return c

    def retire(c):
        try:
            u.DestroyWindow(c["hwnd"])
        except Exception:   # noqa: BLE001
            pass
        curs.pop(c["key"], None)

    def live(c, now):
        return c["shown"] and c["vis"] and c["cur"] is not None and now - c["last"] < FADE_AFTER_S

    def want_label(c, n):
        return "SeeU" if (c["auto"] and n <= 1) else c["label_raw"]

    def relabel(now):
        n = sum(1 for c in curs.values() if live(c, now))
        for c in curs.values():
            c["label"] = want_label(c, n)

    def scale_at(x, y):
        try:
            mon = u.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))
            return (dx.value or 96) / 96.0
        except Exception:   # noqa: BLE001
            return 1.0

    pt = {}
    pts = {}            # 几只光标在不同缩放的屏幕上 → 每种尺寸留一块画布,别每帧重建

    def canvas(s):
        pw, ph = int(WIN_W * s), int(WIN_H * s)
        if pt.get("pw") == pw and pt.get("ph") == ph:
            return
        if (pw, ph) in pts:
            pt.clear()
            pt.update(pts[(pw, ph)])
            return
        mem = g.CreateCompatibleDC(None)
        bits = P()
        dib = g.CreateDIBSection(mem, ctypes.byref(BIH(ctypes.sizeof(BIH), pw, -ph, 1, 32, 0, 0, 0, 0, 0, 0)), 0, ctypes.byref(bits), None, 0)
        g.SelectObject(mem, dib)
        bmp, gr = P(), P()
        gp.GdipCreateBitmapFromScan0(pw, ph, pw * 4, 0x000E200B, bits, ctypes.byref(bmp))
        gp.GdipGetImageGraphicsContext(bmp, ctypes.byref(gr))
        gp.GdipSetSmoothingMode(gr, 4)
        gp.GdipSetTextRenderingHint(gr, 4)
        gp.GdipSetPixelOffsetMode(gr, 4)
        pt.clear()
        pt.update(pw=pw, ph=ph, mem=mem, dib=dib, bmp=bmp, gr=gr)
        pts[(pw, ph)] = dict(pt)

    def argb(rgb, a=1.0):
        r, g_, b = rgb
        return ctypes.c_uint32((int(max(0, min(1, a)) * 255) << 24) | (int(r * 255) << 16) | (int(g_ * 255) << 8) | int(b * 255))

    fams = {}
    for name in (FONT, FONT_LATIN, "Segoe UI"):
        fm = P()
        if gp.GdipCreateFontFamilyFromName(name, None, ctypes.byref(fm)) == 0 and fm:
            fams[name] = fm
    fonts = {}

    def font(px, text):
        latin = all(ord(c) < 0x2E80 for c in text) and FONT_LATIN in fams
        key = (round(px, 1), latin)
        if key not in fonts:
            f = P()
            gp.GdipCreateFont(fams[FONT_LATIN] if latin else fams.get(FONT), F(px), 0 if latin else 1, 2, ctypes.byref(f))   # 2 = 像素
            fonts[key] = f
        return fonts[key]

    fmt = P()
    gp.GdipStringFormatGetGenericTypographic(ctypes.byref(fmt))

    def measure(text, f):
        box = RECTF()
        gp.GdipMeasureString(pt["gr"], ctypes.c_wchar_p(text), -1, f, ctypes.byref(RECTF(0, 0, 1000, 100)), fmt, ctypes.byref(box), None, None)
        return box.w, box.h

    def arrow_T(ox, oy, sc, rot, s, k=1.0):
        """箭头上的点 → 画布坐标:先绕箭头中心 ARROW_C 缩放 sc(点击按下)、旋转 rot(倾斜),再以尖端为中心放大 k(待机呼吸,同 Mac)。"""
        cx, cy = ARROW_C
        cr, sr = math.cos(rot), math.sin(rot)

        def T(x, y):
            x, y = (x - cx) * sc, (y - cy) * sc
            x, y = x * cr - y * sr, x * sr + y * cr
            return F(ox + (x + cx) * k * s), F(oy + (y + cy) * k * s)
        return T

    def arrow_path(ox, oy, sc, rot, s, k=1.0):
        T = arrow_T(ox, oy, sc, rot, s, k)
        p = P()
        gp.GdipCreatePath(0, ctypes.byref(p))
        cur = None
        for seg in ARROW:
            if seg[0] == "M":
                cur = (seg[1], seg[2])
            elif seg[0] == "L":
                gp.GdipAddPathLine(p, *T(*cur), *T(seg[1], seg[2]))
                cur = (seg[1], seg[2])
            else:                                # 二次曲线 → 三次贝塞尔(两个控制点都放在二次的控制点上,同 Mac 画法)
                _, qx, qy, x, y = seg
                gp.GdipAddPathBezier(p, *T(*cur), *T(qx, qy), *T(qx, qy), *T(x, y))
                cur = (x, y)
        gp.GdipClosePathFigure(p)
        return p

    def draw(st, now):
        s = st["s"]
        canvas(s)
        gr = pt["gr"]
        gp.GdipGraphicsClear(gr, ctypes.c_uint32(0))
        col = st["color"]
        tx, ty = TIP[0] * s, TIP[1] * s
        still = st["to"] is None and abs(st["tilt"]) < 0.002
        bt = now - st["arrive"] - IDLE_AFTER_S                      # 待机多久了(到位后 5 秒开始)
        breathing = still and bt >= 0 and not st["waiting"]        # 排队中(打瞌睡)不呼吸(两种等法分开)
        bk = breath_k(bt) if breathing else 0.0
        # 光晕:一团径向渐变(同心圆一圈圈叠)。平时透明度 0.19~0.41 来回(半个来回 0.45π 秒);待机呼吸时跟着呼吸、略放大
        if breathing:
            ga, gs = 0.19 + 0.22 * bk, 1.0 + 0.1 * bk
        else:
            ga, gs = 0.30 - 0.11 * math.cos(math.pi * now / (0.45 * math.pi)), 1.0
        if st["press_t0"] is not None:
            q = (now - st["press_t0"]) / 0.4
            gs = 1.0 + 0.27 * (q / 0.25 if q < 0.25 else max(0.0, 1 - (q - 0.25) / 0.75)) if 0 <= q <= 1 else 1.0
        gcx, gcy, R = tx + 6 * s, ty + 8 * s, GLOW_R * s * gs
        n = 14
        for i in range(n, 0, -1):
            r = R * i / n
            b = P()
            gp.GdipCreateSolidFill(argb(col, ga * (1 - (i - 1) / n) * 0.22), ctypes.byref(b))
            gp.GdipFillEllipse(gr, b, F(gcx - r), F(gcy - r), F(2 * r), F(2 * r))
            gp.GdipDeleteBrush(b)
        # 点击波纹
        if st["ring_t0"] is not None and now >= st["ring_t0"]:
            p = min(1.0, (now - st["ring_t0"]) / RING_S)
            if p < 1:
                r = (5 + 20 * p) * s
                pen = P()
                gp.GdipCreatePen1(argb(col, 0.8 * (1 - p)), F(2.5 * s), 2, ctypes.byref(pen))
                gp.GdipDrawEllipse(gr, pen, F(tx - r), F(ty - r), F(2 * r), F(2 * r))
                gp.GdipDeletePen(pen)
        # 箭头:主色填充 + 白描边 1.6
        sc = press_scale(now - st["press_t0"]) if st["press_t0"] is not None else 1.0
        k = 1 + BREATH_AMP * bk
        path = arrow_path(tx, ty, sc, st["tilt"], s, k)
        b, pen = P(), P()
        gp.GdipCreateSolidFill(argb(col), ctypes.byref(b))
        gp.GdipFillPath(gr, b, path)
        if breathing:                            # 反光:从尾部扫到尖端,只露出箭头里的那部分;到点尖端闪一下
            band, op, fl = shine(bt)
            T = arrow_T(tx, ty, sc, st["tilt"], s, k)
            if band is not None and op > 0.01:
                ux, uy = SHINE_TIP[0] - SHINE_TAIL[0], SHINE_TIP[1] - SHINE_TAIL[1]
                ul = math.hypot(ux, uy); ux, uy = ux / ul, uy / ul
                cx_, cy_ = SHINE_TAIL[0] + (SHINE_TIP[0] - SHINE_TAIL[0]) * band, SHINE_TAIL[1] + (SHINE_TIP[1] - SHINE_TAIL[1]) * band
                gp.GdipSetClipPath(gr, path, 0)
                for j in range(-8, 9):           # 白色光带:中间亮、两边淡(17 条细线叠出渐变)
                    o = j * SHINE_W / 8.0
                    a_ = op * (1 - abs(j) / 9.0) * 0.32
                    px_, py_ = cx_ + ux * o, cy_ + uy * o
                    lp = P()
                    gp.GdipCreatePen1(argb((1, 1, 1), a_), F(SHINE_W / 8.0 * 1.6 * s * k), 2, ctypes.byref(lp))
                    gp.GdipDrawLine(gr, lp, *T(px_ - uy * 30, py_ + ux * 30), *T(px_ + uy * 30, py_ - ux * 30))
                    gp.GdipDeletePen(lp)
                gp.GdipResetClip(gr)
            if fl > 0.01:
                fx_, fy_ = T(1.4, 1.5)
                for j in range(5, 0, -1):
                    rr_ = 4.5 * s * j / 5.0
                    fb = P()
                    gp.GdipCreateSolidFill(argb((1, 1, 1), fl * 0.3), ctypes.byref(fb))
                    gp.GdipFillEllipse(gr, fb, F(fx_.value - rr_), F(fy_.value - rr_), F(2 * rr_), F(2 * rr_))
                    gp.GdipDeleteBrush(fb)
        gp.GdipCreatePen1(argb((1, 1, 1)), F(1.6 * s), 2, ctypes.byref(pen))
        gp.GdipSetPenLineJoin(pen, 2)
        gp.GdipDrawPath(gr, pen, path)
        gp.GdipDeleteBrush(b); gp.GdipDeletePen(pen); gp.GdipDeletePath(path)
        # 名牌:箭头右下的小胶囊
        f = font(10 * s, st["label"])             # 同 Mac 的 10 号字(上一版放大了 1.18 倍,对比图里比 Mac 大一号)
        tw, th = measure(st["label"], f)
        pw, ph = tw + 12 * s, th + 4 * s
        px, py = tx + 13 * s, ty + 17 * s
        rp = P()
        gp.GdipCreatePath(0, ctypes.byref(rp))
        rr = ph / 2
        gp.GdipAddPathArc(rp, F(px), F(py), F(2 * rr), F(ph), F(90), F(180))
        gp.GdipAddPathArc(rp, F(px + pw - 2 * rr), F(py), F(2 * rr), F(ph), F(270), F(180))
        gp.GdipClosePathFigure(rp)
        b = P()
        gp.GdipCreateSolidFill(argb(col), ctypes.byref(b))
        gp.GdipFillPath(gr, b, rp)
        gp.GdipDeleteBrush(b); gp.GdipDeletePath(rp)
        b = P()
        gp.GdipCreateSolidFill(argb(text_color(col)), ctypes.byref(b))
        gp.GdipDrawString(gr, ctypes.c_wchar_p(st["label"]), -1, f, ctypes.byref(RECTF(F(px + 6 * s), F(py + 2 * s), F(tw + 4), F(th + 4))), fmt, b)
        gp.GdipDeleteBrush(b)
        if st["waiting"]:
            draw_zz(gr, st, now, tx, ty, s)

    def draw_zz(gr, st, now, tx, ty, s):
        """打瞌睡:箭头右上方飘起 3 个 z(任务色、白描边),越飘越大、淡出;3 个错开 1/3(同 Mac 和小样)。"""
        for i in range(3):
            q = ((now - st["wait_t"]) / ZZ_S - i / 3.0) % 1.0
            if now - st["wait_t"] < i * ZZ_S / 3.0:
                continue                                          # 后两个还没轮到出场
            op = q / 0.2 if q < 0.2 else max(0.0, 1 - (q - 0.2) / 0.8)
            e = 1 - (1 - q) ** 2                                  # 越飘越慢(小样 ease-out)
            cx = tx + (ZZ_FROM[0] + (ZZ_TO[0] - ZZ_FROM[0]) * e) * s
            cy = ty + (ZZ_FROM[1] + (ZZ_TO[1] - ZZ_FROM[1]) * e) * s
            sc = round((0.6 + 0.9 * q) * 20) / 20.0               # 按 0.05 一档取字号(字体对象有缓存,别每帧一个新字号)
            zf2 = font(10 * s * sc, "z")
            w_, h_ = measure("z", zf2)
            x0, y0 = cx - w_ / 2, cy - h_ / 2
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-0.7, -0.7), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7)):   # 白描边
                b = P()
                gp.GdipCreateSolidFill(argb((1, 1, 1), 0.9 * op), ctypes.byref(b))
                gp.GdipDrawString(gr, ctypes.c_wchar_p("z"), -1, zf2, ctypes.byref(RECTF(F(x0 + dx * s), F(y0 + dy * s), F(w_ + 4), F(h_ + 4))), fmt, b)
                gp.GdipDeleteBrush(b)
            b = P()
            gp.GdipCreateSolidFill(argb(st["color"], op), ctypes.byref(b))
            gp.GdipDrawString(gr, ctypes.c_wchar_p("z"), -1, zf2, ctypes.byref(RECTF(F(x0), F(y0), F(w_ + 4), F(h_ + 4))), fmt, b)
            gp.GdipDeleteBrush(b)

    def push(st):
        hwnd = st["hwnd"]
        x, y = st["cur"]
        s = st["s"]
        hdc = u.GetDC(None)
        pos = wt.POINT(int(round(x - TIP[0] * s)), int(round(y - TIP[1] * s)))
        u.UpdateLayeredWindow(hwnd, hdc, ctypes.byref(pos), ctypes.byref(wt.SIZE(pt["pw"], pt["ph"])), pt["mem"],
                              ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(BLEND(0, 0, int(255 * st["alpha"]), 1)), 2)
        u.ReleaseDC(None, hdc)

    def visible_at(st, x, y):
        """目标窗口(owner)在这一点上没被挡、在当前虚拟桌面上,才画。没给 owner 就总画。"""
        o = st["owner"]
        if not o:
            return True
        try:
            from seeu.win import window as W
            if not u.IsWindow(o) or u.IsIconic(o) or W.other_desktop(o):
                return False
            h = u.WindowFromPoint(wt.POINT(int(x), int(y)))
            root = u.GetAncestor(h, 2) if h else 0
            if root and (int(root) == int(hwnd_box[0] or 0) or any(int(root) == int(c_["hwnd"] or 0) for c_ in curs.values())):
                return True                      # 点上是 SeeU 自己的光标(别的任务那只也算)= 没被挡
            return bool(root) and int(root) == int(o)
        except Exception:   # noqa: BLE001
            return True

    def handle(m, now):
        kind = m[0]
        if kind == "quit":
            st["quit"] = True
            return
        if kind == "hide":
            st["msg"] = now
            targets = [curs[m[1]]] if len(m) > 1 and m[1] in curs else ([] if len(m) > 1 else list(curs.values()))
            for c in targets:                     # 带光标名只藏那一只;不带全藏(老行为)
                c.update(shown=False, waiting=False, last=now - FADE_AFTER_S - 2)
            return
        if kind == "wait" and len(m) >= 3:        # wait 光标名 1|0 —— 排队中打瞌睡 + 变淡
            st["msg"] = now
            c = curs.get(str(m[1]))
            if c is not None:
                on = bool(m[2])
                if on != c["waiting"]:
                    c["waiting"], c["wait_fade"] = on, now + WAIT_FADE_S + 0.15
                    if on:
                        c["wait_t"] = now
                c["last"] = now
            return
        if kind == "untoast":             # 提示条挡在要点的位置上(real._check_point)→ 立刻收掉
            for t in toasts:
                u.DestroyWindow(t["hwnd"])
            del toasts[:]
            return
        if kind == "toast" and len(m) >= 5:
            toast_new(m[1], m[2], m[3], m[4], m[5] if len(m) > 5 and m[5] else PURPLE, now)
            st["msg"] = now
            return
        if kind not in ("move", "click"):
            return
        x, y, label, color, owner = m[1], m[2], m[3] if len(m) > 3 else "SeeU", m[4] if len(m) > 4 else PURPLE, m[5] if len(m) > 5 else 0
        key = str(m[6]) if len(m) > 6 and m[6] else "_"          # 第 7/8 段:光标名(哪个任务)、名牌规则 auto / fixed
        auto = len(m) > 7 and m[7] == "auto"
        st["msg"] = now
        move_cursor(get_cur(key, now), kind, x, y, label, color, owner, auto, now)

    def move_cursor(st, kind, x, y, label, color, owner, auto, now):
        """一只光标收到 move / click(原来 handle 里那一段;st 是这只光标的状态)。"""
        if st["waiting"]:                     # 动了 = 不在排队了(轮到变亮也走 0.25 秒过渡)
            st["waiting"], st["wait_fade"] = False, now + WAIT_FADE_S + 0.15
        st.update(label_raw=str(label or "SeeU")[:40], auto=auto, color=tuple(color), owner=int(owner or 0), last=now)
        n = sum(1 for c in curs.values() if live(c, now) or c is st)
        st["label"] = want_label(st, n)
        st["s"] = scale_at(x, y)
        if st["cur"] is None or not st["shown"] or st["alpha"] < 0.05:
            st.update(cur=(x, y), frm=None, to=None, arrive=now)        # 从看不见到看见:直接出现在那里
        else:
            st.update(frm=st["cur"], to=(x, y), t0=now, dur=travel_s(*st["cur"], x, y, st["s"]), ctl=arc_ctl(st["cur"], (x, y), st["s"]))
            st["arrive"] = now + st["dur"]
        st["shown"] = True
        st["vis"] = visible_at(st, x, y)
        if kind == "click":
            delay = st["dur"] if st["to"] else 0.0
            st["ring_t0"] = now + delay
            st["press_t0"] = now + delay


    # ───── 提示条(照 Mac cursor_overlay 的 toast):屏幕右上角,深色圆角卡片,左边色条、标题、正文、右上 ×、有链接时右下「打开 ›」。
    # 不进通知中心、不抢前台;最多叠 4 条(新的在上);secs 秒后淡出(最多 60 秒);浮标在那一列时从它下面开始叠。
    toasts = []          # dict(hwnd, until, title, body, link, color, alpha)
    tc = {}              # 提示条共用的一块画布

    def t_canvas(s):
        pw, ph = int((TOAST_W + 2 * TOAST_PAD) * s), int((TOAST_H + 2 * TOAST_PAD) * s)
        if tc.get("pw") == pw and tc.get("ph") == ph:
            return
        if tc.get("gr"):
            gp.GdipDeleteGraphics(tc["gr"]); gp.GdipDisposeImage(tc["bmp"]); g.DeleteDC(tc["mem"]); g.DeleteObject(tc["dib"])
        mem = g.CreateCompatibleDC(None)
        bits = P()
        dib = g.CreateDIBSection(mem, ctypes.byref(BIH(ctypes.sizeof(BIH), pw, -ph, 1, 32, 0, 0, 0, 0, 0, 0)), 0, ctypes.byref(bits), None, 0)
        g.SelectObject(mem, dib)
        bmp, gr = P(), P()
        gp.GdipCreateBitmapFromScan0(pw, ph, pw * 4, 0x000E200B, bits, ctypes.byref(bmp))
        gp.GdipGetImageGraphicsContext(bmp, ctypes.byref(gr))
        gp.GdipSetSmoothingMode(gr, 4); gp.GdipSetTextRenderingHint(gr, 4); gp.GdipSetPixelOffsetMode(gr, 4)
        tc.update(pw=pw, ph=ph, mem=mem, dib=dib, bmp=bmp, gr=gr)

    def rrect(gr, x, y, w, h, r, color, a):
        p = P()
        gp.GdipCreatePath(0, ctypes.byref(p))
        d = 2 * r
        gp.GdipAddPathArc(p, F(x), F(y), F(d), F(d), F(180), F(90))
        gp.GdipAddPathArc(p, F(x + w - d), F(y), F(d), F(d), F(270), F(90))
        gp.GdipAddPathArc(p, F(x + w - d), F(y + h - d), F(d), F(d), F(0), F(90))
        gp.GdipAddPathArc(p, F(x), F(y + h - d), F(d), F(d), F(90), F(90))
        gp.GdipClosePathFigure(p)
        b = P()
        gp.GdipCreateSolidFill(argb(color, a), ctypes.byref(b))
        gp.GdipFillPath(gr, b, p)
        gp.GdipDeleteBrush(b); gp.GdipDeletePath(p)

    def text_at(gr, txt, px, size, bold, color, a, x, y, w, h, s):
        f = P()
        latin = all(ord(c) < 0x2E80 for c in txt) and FONT_LATIN in fams
        gp.GdipCreateFont(fams[FONT_LATIN] if latin and bold else (fams.get("Segoe UI") or fams.get(FONT)) if latin else fams.get(FONT),
                          F(size * s), 1 if (bold and not latin) else 0, 2, ctypes.byref(f))
        b = P()
        gp.GdipCreateSolidFill(argb(color, a), ctypes.byref(b))
        sf = P()
        gp.GdipCloneStringFormat(fmt, ctypes.byref(sf))
        gp.GdipSetStringFormatTrimming(sf, 3)          # 放不下用「…」结尾
        gp.GdipDrawString(gr, ctypes.c_wchar_p(txt), -1, f, ctypes.byref(RECTF(F(x), F(y), F(w), F(h))), sf, b)
        gp.GdipDeleteStringFormat(sf); gp.GdipDeleteBrush(b); gp.GdipDeleteFont(f)

    def t_draw(t, s):
        t_canvas(s)
        gr = tc["gr"]
        gp.GdipGraphicsClear(gr, ctypes.c_uint32(0))
        o = TOAST_PAD * s
        W_, H_ = TOAST_W * s, TOAST_H * s
        for i in range(6, 0, -1):                      # 淡淡的阴影(同 Mac 窗口阴影)
            rrect(gr, o - i * s * 0.6, o - i * s * 0.2 + 2 * s, W_ + i * s * 1.2, H_ + i * s * 1.2, 12 * s + i * s, (0, 0, 0), 0.035)
        rrect(gr, o, o, W_, H_, 12 * s, (0.11, 0.11, 0.13), 0.94)
        r_, g_, b_ = t["color"]
        rrect(gr, o + 10 * s, o + 12 * s, 4 * s, H_ - 24 * s, 2 * s, t["color"], 1.0)
        text_at(gr, t["title"], 0, 13, True, (1, 1, 1), 1.0, o + 24 * s, o + 10 * s, W_ - 64 * s, 20 * s, s)
        cx, cy = o + W_ - 18 * s, o + 18 * s               # 右上 ×
        b = P()
        gp.GdipCreateSolidFill(argb((1, 1, 1), 0.18), ctypes.byref(b))
        gp.GdipFillEllipse(gr, b, F(cx - 10 * s), F(cy - 10 * s), F(20 * s), F(20 * s))
        gp.GdipDeleteBrush(b)
        pen = P()
        gp.GdipCreatePen1(argb((0.85, 0.85, 0.85)), F(1.8 * s), 2, ctypes.byref(pen))
        gp.GdipSetPenStartCap(pen, 2); gp.GdipSetPenEndCap(pen, 2)
        d = 4.5 * s
        gp.GdipDrawLine(gr, pen, F(cx - d), F(cy - d), F(cx + d), F(cy + d))
        gp.GdipDrawLine(gr, pen, F(cx + d), F(cy - d), F(cx - d), F(cy + d))
        gp.GdipDeletePen(pen)
        bw = (W_ - 90 * s) if t["link"] else (W_ - 36 * s)
        text_at(gr, t["body"], 0, 12, False, (0.82, 0.82, 0.82), 1.0, o + 24 * s, o + 31 * s, bw, H_ - 34 * s, s)
        if t["link"]:                                  # 右下「打开 ›」:只有点它才跳(同 Mac:整张可点容易误跳)
            bx, by = o + W_ - TOAST_BTN_W * s - 10 * s, o + H_ - 26 * s
            rrect(gr, bx, by, TOAST_BTN_W * s, 20 * s, 10 * s, t["color"], 0.95)
            lab = OPEN_EN if _en() else OPEN_ZH
            text_at(gr, lab, 0, 11, True, text_color(t["color"]), 1.0, bx + 12 * s, by + 2.5 * s, TOAST_BTN_W * s, 18 * s, s)

    def t_layout():
        """右上角往下叠;浮标(SeeUFloat)在那一列时从它下面开始。坐标是物理像素。"""
        wa = wt.RECT()
        u.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)       # 工作区(去掉任务栏)
        s = scale_at(wa.right - 10, wa.top + 10)
        right, top = wa.right - int(16 * s), wa.top + int(16 * s)
        try:
            fw = u.FindWindowW("SeeUFloat", None)
            if fw and u.IsWindowVisible(fw):
                r = wt.RECT()
                u.GetWindowRect(fw, ctypes.byref(r))
                if r.right > right - TOAST_W * s and r.left < right and r.top < top + 200 * s:
                    top = max(top, r.bottom + int(TOAST_GAP * s))
        except Exception:   # noqa: BLE001
            pass
        for i, t in enumerate(toasts):
            t["pos"] = (int(right - (TOAST_W + TOAST_PAD) * s), int(top - TOAST_PAD * s + i * (TOAST_H + TOAST_GAP) * s))
            t["s"] = s

    @WNDPROC
    def tproc(h, msg, wp, lp):
        if msg == 0x0021:                              # 不激活
            return 3
        if msg == 0x0202:                              # 左键松开:× 关掉;「打开 ›」打开链接;别处不做事
            t = next((t for t in toasts if t["hwnd"] == h), None)
            if t:
                s = t.get("s", 1.0)
                x, y = (lp & 0xFFFF) / s - TOAST_PAD, ((lp >> 16) & 0xFFFF) / s - TOAST_PAD
                if x >= TOAST_W - 32 and y <= 32:
                    t["until"] = 0.0
                elif t["link"] and x >= TOAST_W - TOAST_BTN_W - 14 and y >= TOAST_H - 30:
                    try:
                        os.startfile(t["link"])
                    except Exception:   # noqa: BLE001
                        pass
                    t["until"] = 0.0
            return 0
        return u.DefWindowProcW(h, msg, wp, lp)

    u.RegisterClassW(ctypes.byref(WNDCLASSW(0, tproc, 0, 0, k32.GetModuleHandleW(None), None, u.LoadCursorW(None, ctypes.c_void_p(32649)),
                                            None, None, "SeeUToast")))

    def toast_new(title, body, secs, link, col, now):
        ex_ = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000      # LAYERED | TOPMOST | TOOLWINDOW | NOACTIVATE(不穿透:× 和按钮要能点)
        h = u.CreateWindowExW(ex_, "SeeUToast", "SeeU", 0x80000000, 0, 0, 10, 10, None, None, k32.GetModuleHandleW(None), None)
        toasts.insert(0, dict(hwnd=h, until=now + max(1.0, min(float(secs), 60.0)), title=str(title or "")[:120],
                              body=str(body or "")[:300], link=link or None, color=tuple(col or PURPLE), alpha=0.0, shown=False))
        for old in toasts[4:]:
            u.DestroyWindow(old["hwnd"])
        del toasts[4:]
        t_layout()

    def toast_tick(now):
        if not toasts:
            return
        if now - st.get("t_chk", 0) > 1.0:
            st["t_chk"] = now
            t_layout()
        for t in list(toasts):
            want = 1.0 if now < t["until"] else 0.0
            t["alpha"] = min(want, t["alpha"] + 0.12) if want > t["alpha"] else max(want, t["alpha"] - 0.06)
            if t["alpha"] <= 0.0 and want == 0.0:
                u.DestroyWindow(t["hwnd"])
                toasts.remove(t)
                t_layout()
                continue
            t_draw(t, t["s"])
            hdc = u.GetDC(None)
            u.UpdateLayeredWindow(t["hwnd"], hdc, ctypes.byref(wt.POINT(*t["pos"])), ctypes.byref(wt.SIZE(tc["pw"], tc["ph"])), tc["mem"],
                                  ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(BLEND(0, 0, int(255 * t["alpha"]), 1)), 2)
            u.ReleaseDC(None, hdc)
            if not t["shown"]:
                u.ShowWindow(t["hwnd"], 4)
                t["shown"] = True

    hwnd_box = [0]

    @WNDPROC
    def proc(h, msg, wp, lp):
        if msg == 0x0021:                        # WM_MOUSEACTIVATE → 不激活
            return 3
        if msg == 0x0084:                        # WM_NCHITTEST → 穿透
            return -1
        return u.DefWindowProcW(h, msg, wp, lp)

    hinst = k32.GetModuleHandleW(None)
    wc = WNDCLASSW(0, proc, 0, 0, hinst, None, None, None, None, "SeeUCursor")
    u.RegisterClassW(ctypes.byref(wc))
    EX_CUR = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000   # LAYERED | TRANSPARENT | TOPMOST | TOOLWINDOW | NOACTIVATE
    # 定时器挂在一个永远不显示的宿主窗口上(光标窗口一只一个,会回收)
    hwnd = u.CreateWindowExW(EX_CUR, "SeeUCursor", "SeeU cursor host", 0x80000000, 0, 0, 1, 1, None, None, hinst, None)
    hwnd_box[0] = hwnd
    canvas(1.0)

    def tick():
        now = time.time()
        while True:
            try:
                data, _ = sock.recvfrom(65536)
                handle(json.loads(data.decode("utf-8")), now)
            except BlockingIOError:
                break
            except (OSError, ValueError):
                break
        if st["quit"] or (now - st["msg"] > IDLE_EXIT_S and not toasts):
            for t in toasts:
                u.DestroyWindow(t["hwnd"])
            for c in list(curs.values()):
                retire(c)
            u.DestroyWindow(hwnd)
            u.PostQuitMessage(0)
            return
        toast_tick(now)
        for c in list(curs.values()):
            try:
                step(c, now)
            except Exception:   # noqa: BLE001 —— 一只出错不耽误别的光标
                pass
        relabel(now)

    def step(st, now):
        """一只光标一帧:移动、倾斜、遮挡、透明度、画、回收(原来 tick 里那一段,按光标各算各的)。"""
        if st["cur"] is None:
            if now - st["last"] > FADE_AFTER_S + 5:
                retire(st)
            return
        # 位置:弧线 + 冲过头;倾斜跟着速度走
        if st["to"] is not None:
            p = min(1.0, (now - st["t0"]) / max(0.05, st["dur"]))
            prev = st["cur"]
            st["cur"] = arc_point(st["frm"], st["to"], st["ctl"], min(ease_back(p), 1.15))
            vx = st["cur"][0] - prev[0]
            want = max(-TILT_MAX, min(TILT_MAX, vx * TILT_K / max(st["s"], 0.5))) if p < 1.0 else 0.0
            st["tilt"] += (want - st["tilt"]) * 0.18
            if p >= 1.0:
                st.update(cur=st["to"], to=None)
        else:
            st["tilt"] += (0.0 - st["tilt"]) * 0.18
            if abs(st["tilt"]) < 0.002:
                st["tilt"] = 0.0
        if st["waiting"]:
            if now - st["wait_t"] > WAIT_MAX_S:       # 排队提示有上限:没人来收就自己停(调度那边最多等 30 秒)
                st["waiting"], st["wait_fade"] = False, now + WAIT_FADE_S + 0.15
            else:
                st["last"] = max(st["last"], now - 1)    # 排队中不淡出
        if now - st["last_chk"] > 0.2 and st["owner"] and st["shown"]:     # 两次动作之间被挡住 / 切走桌面也藏(同 Mac 每 0.2 秒查)
            st["last_chk"] = now
            st["vis"] = visible_at(st, *(st["to"] or st["cur"]))
        want = 1.0 if st["shown"] and st["vis"] and now - st["last"] < FADE_AFTER_S else 0.0
        if st["waiting"]:
            want = min(want, WAIT_ALPHA)
        if want > 0 and now < st["wait_fade"]:        # 排队变淡 / 轮到变亮:0.25 秒匀速过渡
            d = (1 / 60.0) / WAIT_FADE_S
            st["alpha"] = min(want, st["alpha"] + d) if want > st["alpha"] else max(want, st["alpha"] - d)
        else:
            st["alpha"] += (want - st["alpha"]) * (0.35 if want > st["alpha"] else 0.12)
        if st["alpha"] < 0.02 and want == 0.0:
            if st["on_screen"]:
                u.ShowWindow(st["hwnd"], 0)
                st["on_screen"] = False
            if now - st["last"] > FADE_AFTER_S + 5 and not st["waiting"]:
                retire(st)                            # 淡出完了、又过了一会:回收这只(别的任务的光标不受影响)
            return
        draw(st, now)
        push(st)
        if not st["on_screen"]:
            u.ShowWindow(st["hwnd"], 4)               # SW_SHOWNOACTIVATE
            st["on_screen"] = True

    TIMERPROC = ctypes.WINFUNCTYPE(None, wt.HWND, wt.UINT, ctypes.c_size_t, wt.DWORD)

    @TIMERPROC
    def on_timer(h, m, i, t):
        try:
            tick()
        except Exception:   # noqa: BLE001
            pass
    u.SetTimer(hwnd, 1, 16, ctypes.cast(on_timer, P))
    msg = wt.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u.DispatchMessageW(ctypes.byref(msg))
    sock.close()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["serve"]:
        serve()
    elif a[:1] in (["move"], ["click"]) and len(a) >= 3:
        print(show(a[0], float(a[1]), float(a[2]), *(a[3:4] or ["SeeU"])))
    elif a[:1] == ["toast"] and len(a) >= 2:
        toast(a[1], a[2] if len(a) > 2 else "", float(a[3]) if len(a) > 3 else 6.0, a[4] if len(a) > 4 else None)
    elif a[:1] == ["hide"]:
        hide()
    elif a[:1] == ["quit"]:
        quit()
    else:
        print(__doc__)
