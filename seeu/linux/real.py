# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 最后一档退路:借用户的真鼠标 / 真键盘(第 3 段,11-18;跟 Mac / Windows 的「借用鼠标」同一个设置管)。

Wayland 不让普通程序给别的窗口发键鼠,只能走系统「远程操作」授权(xdg-desktop-portal RemoteDesktop):
  - 第一次要用户在系统框里打开「允许远程操作」再点共享(python3 -m seeu 检查 --fix 带着做),系统给一个「下次免问」令牌;
    之后带令牌 0.01 秒拿到、不弹框。🔴 令牌每用一次换新,每次都要存(旧的作废)。
  - 借的时候系统右上角亮「远程操作中」,借完关掉会话就灭 —— 用户看得见,SeeU 不长期占着。
流程(照 Windows 版 win/real.py):
  1. 先查:锁屏不借;窗口最小化 / 在别的工作区不借(拉过来会改窗口状态、把用户切走)。
  2. 排队:几个 SeeU 任务同时要借 → sched.real_slot 一次一个。
  3. 让路:用户最近 1 秒内动过鼠标键盘就先等,最多 6 秒;一直在用就不借(user_busy)。空闲时间问 GNOME(Mutter IdleMonitor)。
  4. 亮出来:屏幕四周橙色光圈 + 橙色代理光标(带署名)+ 悬浮标写「借用鼠标」。
  5. 小插件把目标窗口拉到前台,核对那一点最上面确实是它;小插件挪指针(没挪准就用相对挪动一步步对准);点 / 按 / 滚 / 打字。
  6. 还原:指针放回原处、前台还给原来的窗口、光圈灭、关掉远程操作会话。
打字:英文、数字、符号按键;中文等按键打不出的字 → 借剪贴板贴(先存用户原来剪贴板里的字、贴完还回去;剪贴板里是图片 / 文件时不动,报做不到)。
"""
import contextlib
import json
import os
import time

from seeu.linux import safety, shell, window as W

IDLE_NEED = 1.0       # 用户停手多久才借(秒)
WAIT_MAX = 6.0        # 最多等用户停手这么久
START_WAIT = 5.0      # 带令牌拿授权最多等几秒(令牌失效时系统会弹框,不在这里干等)
GRANT_WAIT = 180.0    # 检查 --fix 时等用户在弹框里点允许
ORANGE, PURPLE = "#FF9F0A", "#7F77DD"
PORTAL, OBJ, IF = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", "org.freedesktop.portal.RemoteDesktop"
BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}


class UserBusy(RuntimeError):
    """用户正在用电脑,SeeU 不借。"""


class SeeUBusy(UserBusy):
    """别的 SeeU 任务正在借鼠标键盘,排队等到上限还没轮到。不是被拦:稍后重试。"""


class NeedGrant(RuntimeError):
    """还没有(或失效了)系统「远程操作」授权。"""


GRANT_HOW = ("借真鼠标键盘要先在系统里允许一次「远程操作」:请用户在终端运行 python3 -m seeu 检查 --fix,"
             "在弹出的框里打开「允许远程操作」,再点「共享」。之后 SeeU 借鼠标就不再弹框")


def _home(*p):
    from seeu_lib import home
    return home(*p)


TOKEN = None


def _token_file():
    return _home("seeu_linux_remote_token")


def _load_token():
    try:
        with open(_token_file(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _save_token(tok):
    if not tok:
        return
    p = _token_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # 只有自己读得到
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tok)
    os.replace(tmp, p)


def has_grant():
    return bool(_load_token())


# ─────────────────────────────── 设置(跟 Mac / Windows 同一个「借用鼠标」) ───────────────────────────────

_SETTINGS = os.environ.get("SEEU_SETTINGS_FILE") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "设置.json")
_SESSION_AUTO = [False]


def settings():
    try:
        with open(_SETTINGS, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"借用鼠标": "问我"}
    except FileNotFoundError:
        return {}
    except Exception:   # noqa: BLE001   文件坏了:借用鼠标按「问我」算(同 Windows 版 11-14 复查)
        return {"借用鼠标": "问我"}


def _mode_of(v):
    v = str(v if v is not None else "开").strip().lower() or "开"
    if v in ("关", "off", "0", "false", "no"):
        return "off"
    if v in ("问我", "ask"):
        return "ask"
    return "on"


def mode():
    """借用鼠标:on(默认)| ask | off。环境变量 SEEU_REAL_MOUSE 优先。"""
    v = os.environ.get("SEEU_REAL_MOUSE")
    return _mode_of(v if v is not None else settings().get("借用鼠标"))


def allowed(allow=None):
    a = str(allow or "").strip().lower()
    if a in ("auto", "自动使用"):
        _SESSION_AUTO[0] = True
    if a in ("once", "仅此一次", "auto", "自动使用"):
        return True
    m = mode()
    return m == "on" or (m == "ask" and _SESSION_AUTO[0])


def settings_cmd(args):
    """python3 -m seeu 设置 [借用鼠标 开|问我|关](同 Mac / Windows):不带参数看现在的值;带了就改 设置.json(只改这一项)。"""
    from seeu.linux.lang import say as print   # noqa: A001   打印给人看的走中英文(11-18 C-3.0)
    vals = {"开": "开", "on": "开", "问我": "问我", "ask": "问我", "关": "关", "off": "关"}
    args = list(args)
    if args and args[0].lower() == "borrow-mouse":
        args[0] = "借用鼠标"
    if not args:
        print("借用鼠标: " + {"on": "开", "ask": "问我", "off": "关"}[mode()] + "  (开 = on / 问我 = ask / 关 = off)"
              + ("   (SEEU_REAL_MOUSE overrides it)" if os.environ.get("SEEU_REAL_MOUSE") is not None else ""))
        return 0
    if len(args) != 2 or args[0] != "借用鼠标" or args[1].lower() not in vals:
        print("用法:python3 -m seeu 设置 借用鼠标 开|问我|关")
        return 2
    from collections import OrderedDict
    try:
        with open(_SETTINGS, encoding="utf-8-sig") as f:
            d = json.load(f, object_pairs_hook=OrderedDict)
        if not isinstance(d, dict):
            raise ValueError("不是一组设置")
    except FileNotFoundError:
        d = OrderedDict()
    except (OSError, ValueError) as ex:              # 读不出来就不写:别把用户别的设置盖掉
        print(f"没改:设置文件读不出来({ex}):{_SETTINGS}")
        return 1
    d["借用鼠标"] = vals[args[1].lower()]
    tmp = f"{_SETTINGS}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, _SETTINGS)
    print("已改:借用鼠标 = " + d["借用鼠标"])
    return 0


def signature():
    s = str(settings().get("署名") or "").strip()
    if s:
        return s
    try:
        import getpass
        return "@" + getpass.getuser()
    except Exception:   # noqa: BLE001
        return "SeeU"


def color(kind="real"):
    d = settings()
    return str(d.get("让路模式颜色") or ORANGE) if kind == "real" else str(d.get("后台模式颜色") or PURPLE)


# ─────────────────────────────── 系统「远程操作」会话 ───────────────────────────────

class Session:
    """一次借用 = 一个远程操作会话(用完就关,系统右上角的提示跟着灭)。"""

    def __init__(self, interactive=False):
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.interactive = interactive
        self.handle = None

    def _request(self, method, fmt, args, opts, timeout):
        GLib, Gio = self.GLib, self.Gio
        token = f"seeu{os.getpid()}_{int(time.time() * 1000)}"
        opts = dict(opts)
        opts["handle_token"] = GLib.Variant("s", token)
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        loop, res = GLib.MainLoop(), {}

        def on_resp(conn, snd, p, iface, sig, params):
            code, results = params.unpack()
            res.update(code=code, r=results)
            loop.quit()
        sid = self.bus.signal_subscribe(PORTAL, "org.freedesktop.portal.Request", "Response", path, None,
                                        Gio.DBusSignalFlags.NO_MATCH_RULE, on_resp)
        try:
            self.bus.call_sync(PORTAL, OBJ, IF, method, GLib.Variant(fmt, tuple(args) + (opts,)), None,
                               Gio.DBusCallFlags.NONE, 5000, None)
            GLib.timeout_add(int(timeout * 1000), loop.quit)            # 硬上限
            loop.run()
        finally:
            self.bus.signal_unsubscribe(sid)
        return res

    def open(self):
        GLib = self.GLib
        tok = _load_token()
        if not tok and not self.interactive:
            raise NeedGrant(GRANT_HOW)
        r = self._request("CreateSession", "(a{sv})", [], {"session_handle_token": GLib.Variant("s", f"seeus{os.getpid()}")}, 5)
        if r.get("code") != 0:
            raise RuntimeError(f"系统远程操作会话开不了(代码 {r.get('code')})")
        self.handle = r["r"]["session_handle"]
        opts = {"types": GLib.Variant("u", 1 | 2), "persist_mode": GLib.Variant("u", 2)}
        if tok:
            opts["restore_token"] = GLib.Variant("s", tok)
        r = self._request("SelectDevices", "(oa{sv})", [self.handle], opts, 5)
        if r.get("code") != 0:
            self.close()
            raise RuntimeError(f"系统远程操作选不了设备(代码 {r.get('code')})")
        r = self._request("Start", "(osa{sv})", [self.handle, ""], {}, GRANT_WAIT if self.interactive else START_WAIT)
        if r.get("code") != 0:
            self.close()                                    # 令牌失效时系统会弹框;关掉会话框就收起,不让它挂在用户屏幕上
            if not r:
                raise NeedGrant("系统没有马上给远程操作授权(上次的「下次免问」失效了)。" + GRANT_HOW)
            raise NeedGrant(("用户在系统框里没允许远程操作。" if r.get("code") == 1 else "系统没给远程操作授权。") + GRANT_HOW)
        _save_token((r.get("r") or {}).get("restore_token"))     # 🔴 令牌每次换新,旧的作废
        return self

    def close(self):
        if not self.handle:
            return
        try:
            self.bus.call_sync(PORTAL, self.handle, "org.freedesktop.portal.Session", "Close", None, None,
                               self.Gio.DBusCallFlags.NONE, 3000, None)
        except Exception:   # noqa: BLE001
            pass
        self.handle = None

    def _call(self, m, fmt, args):
        self.bus.call_sync(PORTAL, OBJ, IF, m, self.GLib.Variant(fmt, (self.handle, {}) + tuple(args)), None,
                           self.Gio.DBusCallFlags.NONE, 3000, None)

    def motion(self, dx, dy):
        self._call("NotifyPointerMotion", "(oa{sv}dd)", (float(dx), float(dy)))

    def button(self, btn, down):
        self._call("NotifyPointerButton", "(oa{sv}iu)", (int(btn), 1 if down else 0))

    def axis(self, steps, horizontal=False):
        self._call("NotifyPointerAxisDiscrete", "(oa{sv}ui)", (1 if horizontal else 0, int(steps)))

    def keysym(self, sym, down):
        self._call("NotifyKeyboardKeysym", "(oa{sv}iu)", (int(sym), 1 if down else 0))


def grant():
    """检查 --fix 用:开一次会话让系统弹框,用户点允许后存下令牌。返回 True / 抛 NeedGrant。"""
    s = Session(interactive=True)
    try:
        s.open()
    finally:
        s.close()
    return True


# ─────────────────────────────── 让路、前台、对准 ───────────────────────────────

def idle_seconds():
    """用户多久没动鼠标键盘(问 GNOME)。问不到返回很大的数(不挡)。"""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        r = bus.call_sync("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core", "org.gnome.Mutter.IdleMonitor",
                          "GetIdletime", None, None, Gio.DBusCallFlags.NONE, 1000, None)
        return r.unpack()[0] / 1000.0
    except Exception:   # noqa: BLE001
        return 1e9


def wait_idle():
    t0 = time.time()
    while time.time() - t0 < WAIT_MAX:
        if idle_seconds() >= IDLE_NEED:
            return
        time.sleep(0.1)
    raise UserBusy("用户正在用电脑,SeeU 先不借鼠标键盘(等用户停手再试)")


def _fresh(w):
    """按窗口号重新取一次窗口(位置、前台、工作区都是这一刻的)。"""
    for x in W.list_windows():
        if x["id"] == w["id"]:
            return x
    raise RuntimeError("窗口已经关了")


def check_window(w):
    """借之前先查(查完再让路、再亮光圈:不借就别打扰)。"""
    safety.check_unlocked()
    check_modal()
    safety.check_window(w)
    if w.get("minimized"):
        raise safety.Refused("窗口最小化了,SeeU 不把它拉出来(请先把窗口打开)")
    if not w.get("active_ws", True):
        raise safety.Refused("窗口在另一个工作区:借鼠标要把它拉到前台,系统会把你切到那个工作区,SeeU 不借;请你切过去,或把窗口挪到现在的工作区")


MODAL_WHY = ("系统的弹框开着(密码 / 钥匙环 / 管理员授权框、系统授权确认框、活动概览或运行框),这时键盘鼠标都给它,"
             "SeeU 不借(防止打进密码框);请用户先处理掉那个框")


def check_modal():
    """Shell 自己的弹框开着就不借(11-18 虚拟机实测:登录后 VS Code 要钥匙环密码,弹框盖在所有窗口上、收着键盘)。"""
    p = shell.ping()
    if int(p.get("modal") or 0) > 0 or p.get("overview"):
        raise safety.Refused(MODAL_WHY)


def _bring(w):
    if shell.focus() == w["id"]:
        return
    shell.activate(w["id"])
    t0 = time.time()
    while time.time() - t0 < 1.5:
        if shell.focus() == w["id"]:
            time.sleep(0.12)              # 刚到前台的窗口要一下才收键盘
            return
        time.sleep(0.03)
    raise RuntimeError("没能把目标窗口拉到前台")


def check_point(w, x, y):
    wins = W.list_windows()
    me = next((v for v in wins if v["id"] == w["id"]), None)
    if me is None:
        raise RuntimeError("窗口已经关了")
    if not (me["x"] <= x < me["x"] + me["w"] and me["y"] <= y < me["y"] + me["h"]):
        raise RuntimeError("那个位置不在目标窗口里,SeeU 不点")
    if not W.point_visible(me, x, y, wins):
        top = next((v for v in sorted(wins, key=lambda v: -v["z"]) if v["id"] != me["id"] and v.get("active_ws", True)
                    and not v.get("minimized") and v["x"] <= x < v["x"] + v["w"] and v["y"] <= y < v["y"] + v["h"]), None)
        why = safety.why_not(top) if top else None
        raise RuntimeError("那个位置最上面不是目标窗口" + (f"(是「{(top.get('title') or '')[:20]}」)" if top else "")
                           + (f";而且{why}" if why else "") + ",SeeU 不点")


def move_to(sess, x, y):
    """指针挪到 (x, y):先让小插件直接挪(准、快);没挪准再用相对挪动一步步对准(探路时 8 步到像素)。"""
    try:
        shell.warp(x, y)
        time.sleep(0.02)
    except Exception:   # noqa: BLE001
        pass
    for _ in range(30):                                  # 硬上限
        cx, cy = shell.pointer()
        dx, dy = x - cx, y - cy
        if abs(dx) <= 1 and abs(dy) <= 1:
            return
        sx = dx if abs(dx) <= 3 else dx * 0.5           # GNOME 鼠标加速跟速度有关:远了挪一半,近了一像素一像素挪
        sy = dy if abs(dy) <= 3 else dy * 0.5
        sess.motion(sx, sy)
        time.sleep(0.03)
    raise RuntimeError("鼠标没能对准那个位置")


@contextlib.contextmanager
def _slot():
    try:
        from seeu import sched
        cm = sched.real_slot()
    except Exception:   # noqa: BLE001   调度模块出问题不挡借鼠标
        yield 0
        return
    try:
        waited = cm.__enter__()
    except Exception as ex:   # noqa: BLE001
        if type(ex).__name__ == "Busy":
            raise SeeUBusy(str(ex))
        yield 0
        return
    try:
        yield waited
    finally:
        cm.__exit__(None, None, None)


def task_cursor(mode="bg"):
    """这个任务的光标:(名牌, 颜色 "#RRGGBB", 任务名)。11-18 C-3.0(照 Windows act._cursor):一个任务一只光标,
    任务名 = 调度分的显示名(Claude、Claude2…);后台模式名牌写任务名、颜色用任务色(第 0 号用设置里的后台模式颜色);
    借鼠标照旧是署名 + 让路模式颜色。拿不到任务名 = None(跟老写法共用一只)。"""
    base = color("real" if mode == "real" else "bg")
    try:
        from seeu import sched
        key = sched.cursor_key() or None
    except Exception:   # noqa: BLE001
        return (signature() if mode == "real" else "SeeU"), base, None
    if mode == "real":
        return signature(), base, key
    try:
        rgb = sched.cursor_color(tuple(int(base.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)))
        col = "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in rgb)
    except Exception:   # noqa: BLE001
        col = base
    return (key or "SeeU"), col, key


def _float_borrow(w, kind):
    """告诉悬浮标正在借鼠标 / 键盘,借的这段时间每秒续一次(悬浮标最后一次消息后 2.5 秒自己恢复)。
    返回停止续的开关;小插件是老版本(没有悬浮标)返回 None。只是显示,出错不耽误干活。"""
    try:
        if shell.api() < 3:
            return None
        import threading
        from seeu.linux import floatwin
        app = w.get("app_id") or w.get("wm_class") or w.get("title") or ""
        k = "keyboard" if kind == "keyboard" else "mouse"
        floatwin.borrow(app, k)
        stop = threading.Event()

        def run():
            while not stop.wait(1.0):
                floatwin.borrow(app, k)
        threading.Thread(target=run, daemon=True).start()
        time.sleep(0.05)                     # 让悬浮标先变穿透,再挪指针
        return stop
    except Exception:   # noqa: BLE001
        return None


def borrow(w, act, kind="mouse", at=None):
    """查 → 排队 → 让路 → 亮光圈 → 拉前台 → act(sess) → 还原。返回 dict(held_ms, back, waited)。
    at = (x, y):代理光标先滑过去的位置。"""
    shell.need_v2()
    check_window(w)
    with _slot() as waited:
        sess = Session().open()                         # 没授权在这里就报(不先让路、不亮光圈)
        try:
            wait_idle()
            safety.check_unlocked()
            col, name = color("real"), signature()
            # 11-20 复查:悬浮标续命 / 光圈一亮起来就进 try,中途 pointer / focus / cursor 出错也能在 finally 里收掉(原来会一直橙色、一直穿透)
            beat, old, p0, f0, back = None, False, None, 0, True
            t0 = time.time()
            try:
                beat = _float_borrow(w, kind)        # 11-18 C-3.0:悬浮标变橙、写「正在用你的鼠标」、这几秒穿透;光圈由它按灯光档位亮
                if beat is None:                     # 小插件老版本:老的右上角提示 + 光圈
                    old = True
                    shell.halo(col, True)
                    what = {"mouse": "借用鼠标", "keyboard": "借用键盘", "scroll": "借用鼠标滚动"}.get(kind, "借用鼠标")
                    shell.badge(f"SeeU · {what}", "请先别动鼠标键盘,马上还给你", col, 6000)
                p0, f0 = shell.pointer(), shell.focus()
                if at:
                    t = shell.cursor(at[0], at[1], name, col, 60000, "click" if kind == "mouse" else "move", key=task_cursor("real")[2])
                    if t > 0:
                        time.sleep(min(t, 0.65))
                t0 = time.time()
                _bring(_fresh(w))
                check_modal()                          # 拉完前台再查一次:刚好弹出来的框也拦住
                act(sess)
                time.sleep(0.05)
            finally:
                if p0:
                    try:
                        shell.warp(*p0)
                    except Exception:   # noqa: BLE001
                        pass
                if f0 and f0 != w["id"]:
                    try:
                        shell.activate(f0)
                        time.sleep(0.05)
                        back = shell.focus() == f0
                    except Exception:   # noqa: BLE001
                        back = False
                if old:
                    try:
                        shell.halo(col, False)
                    except Exception:   # noqa: BLE001
                        pass
                elif beat is not None:
                    beat.set()
        finally:
            sess.close()
    r = dict(held_ms=round((time.time() - t0) * 1000), back=back)
    if waited and waited >= 0.5:
        r["waited"] = waited
    return r


# ─────────────────────────────── 动作 ───────────────────────────────

LONG_MAX_MS = 10000      # 长按上限(同 Mac / Windows)


def long_press(w, x, y, ms=1000):
    """借真鼠标长按(11-18 C-3.0,照 Windows real.long_press):挪过去、按下、按住 ms 毫秒、松开。"""
    ms = max(50, min(int(ms), LONG_MAX_MS))

    def act(sess):
        check_point(w, x, y)
        move_to(sess, x, y)
        check_point(w, x, y)                   # 挪过去之后再查一次(悬停弹出的东西之类)
        sess.button(BTN["left"], True)
        try:
            time.sleep(ms / 1000)
        finally:
            sess.button(BTN["left"], False)
    return borrow(w, act, "mouse", at=(x, y))


def drag(w, pts, hold_ms=0):
    """借真鼠标拖动(11-18 C-3.0,照 Windows real.drag):pts = 屏幕点(起点在前),每个点都要在目标窗口上、最上面就是它。
    按住后沿折线一小段一小段挪(每段约 20 像素,用相对挪动 + 读回指针对准,程序看到的是「按着移动」)。"""
    pts = [(float(p[0]), float(p[1])) for p in pts]

    def act(sess):
        for p in pts:
            check_point(w, *p)
        move_to(sess, *pts[0])
        check_point(w, *pts[0])
        sess.button(BTN["left"], True)
        try:
            time.sleep(max(0, hold_ms) / 1000 + 0.05)
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                n = max(2, int(max(abs(bx - ax), abs(by - ay)) / 20))
                for i in range(1, n + 1):
                    _step_to(sess, ax + (bx - ax) * i / n, ay + (by - ay) * i / n)
                    time.sleep(0.012)
            move_to(sess, *pts[-1])              # 终点对准到像素
            time.sleep(0.05)
        finally:
            sess.button(BTN["left"], False)
    return borrow(w, act, "mouse", at=pts[0])


def _step_to(sess, x, y):
    """拖动中间的一小步:只用相对挪动(真的「按着移动」事件),不用小插件直接挪指针(那不算拖)。最多补 3 次。"""
    for _ in range(3):
        cx, cy = shell.pointer()
        dx, dy = x - cx, y - cy
        if abs(dx) <= 2 and abs(dy) <= 2:
            return
        sess.motion(dx, dy)
        time.sleep(0.01)


def click(w, x, y, right=False):
    def act(sess):
        check_point(w, x, y)
        move_to(sess, x, y)
        check_point(w, x, y)                 # 挪过去之后再查一次(悬停弹出的提示框之类)
        b = BTN["right" if right else "left"]
        sess.button(b, True)
        time.sleep(0.04)
        sess.button(b, False)
    return borrow(w, act, "mouse", at=(x, y))


def scroll(w, x, y, dy=0, dx=0):
    """dy 负 = 往下翻(跟别的工具一样)。约 100 = 一格滚轮。"""
    def act(sess):
        check_point(w, x, y)
        move_to(sess, x, y)
        for amount, horiz in ((dy, False), (dx, True)):
            if not amount:
                continue
            steps = max(1, min(30, round(abs(amount) / 100)))
            sign = 1 if amount < 0 else -1           # 滚轮「往下」是正数
            for _ in range(steps):
                sess.axis(sign, horiz)
                time.sleep(0.015)
    return borrow(w, act, "scroll", at=(x, y))


KEYSYM = {"return": 0xff0d, "enter": 0xff0d, "tab": 0xff09, "escape": 0xff1b, "esc": 0xff1b, "backspace": 0xff08,
          "delete": 0xffff, "space": 0x20, "up": 0xff52, "down": 0xff54, "left": 0xff51, "right": 0xff53, "home": 0xff50,
          "end": 0xff57, "pageup": 0xff55, "pagedown": 0xff56, "insert": 0xff63,
          "forwarddelete": 0xffff}      # 11-20 复查:safety.norm_key 把 delete / del 归成 forwarddelete,原来查不到、Delete 按不出
KEYSYM.update({f"f{i}": 0xffbe + i - 1 for i in range(1, 13)})
MODSYM = {"ctrl": 0xffe3, "shift": 0xffe1, "alt": 0xffe9}


def keysym_of(key):
    k = safety.norm_key(key)
    if k in KEYSYM:
        return KEYSYM[k]
    if len(k) == 1 and 0x20 <= ord(k) < 0x7f:
        return ord(k)
    raise RuntimeError(f"不认识的键「{key}」")


def _tap_key(sess, sym, mods=()):
    for m in mods:
        sess.keysym(MODSYM[m], True)
    try:
        sess.keysym(sym, True)
        time.sleep(0.015)
        sess.keysym(sym, False)
    finally:
        for m in reversed(mods):
            sess.keysym(MODSYM[m], False)


def key(w, name, mods=(), click_at=None, check=None):
    """按一个键(可带 ctrl / shift / alt)。click_at=(x, y):先点进那个框再按。
    check:真按之前再核对一次(11-20 复查:排队 + 等用户停手这几秒焦点可能换了),出问题抛 RuntimeError / Refused 就不按。"""
    m = [x for x in safety.norm_mods(mods) if x in MODSYM]
    sym = keysym_of(name)

    def act(sess):
        if click_at:
            _click_in(sess, w, *click_at)
        if check:
            check()
        _tap_key(sess, sym, m)
    return borrow(w, act, "keyboard", at=click_at)


def _click_in(sess, w, x, y):
    check_point(w, x, y)
    move_to(sess, x, y)
    check_point(w, x, y)
    sess.button(BTN["left"], True)
    time.sleep(0.04)
    sess.button(BTN["left"], False)
    time.sleep(0.15)


def _plain(ch):
    # 11-20 复查:\t 不再按成 Tab 键(会把后半段打进下一个框,可能是密码框),当成字贴进去
    return ch == "\n" or 0x20 <= ord(ch) < 0x7f


def type_text(w, text, click_at=None, check=None):
    """借真键盘打字。英文、数字、符号逐个按;别的字(中文等)借剪贴板贴,贴完把用户原来的剪贴板文字还回去。
    check:点进框以后、开打之前核对焦点(11-20 复查:点的是 see 时记下的位置,可能已经滚走了),出问题抛错就不打。"""
    if not all(_plain(c) for c in text):
        other, _ = shell.clipboard()
        if other:
            raise RuntimeError("要打的字里有按键打不出来的字(中文等),得借剪贴板贴;但你的剪贴板里现在是图片或文件,"
                               "SeeU 不动它。清掉剪贴板或先打英文,再试")

    def act(sess):
        if click_at:
            _click_in(sess, w, *click_at)
        if check:
            check()
        if all(_plain(c) for c in text):
            for ch in text:
                _tap_key(sess, KEYSYM["return"] if ch == "\n" else ord(ch))
                time.sleep(0.008)
            return
        other, old = shell.clipboard()
        if other:
            raise RuntimeError("剪贴板里是图片或文件,SeeU 不动它")
        shell.set_clipboard(text)
        time.sleep(0.08)
        try:
            _tap_key(sess, ord("v"), ["ctrl"])
            time.sleep(0.6)                     # 等程序把剪贴板读走再还回去(11-20 复查:0.3 秒慢的程序会贴成用户原来的内容)
        finally:
            shell.set_clipboard(old)
    return borrow(w, act, "keyboard", at=click_at)
