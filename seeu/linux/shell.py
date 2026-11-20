# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 跟 GNOME 小插件(seeu@seeu-computeruse)打交道:窗口位置、鼠标位置、锁屏、提示条 / 代理点、安装。

小插件只在 GNOME 上有(Wayland 下普通程序拿不到别的窗口在哪,只能靠它)。没装 / 没加载 / 锁屏时 available() 是 False。
锁屏判断两道:① 小插件的名字不在(GNOME 锁屏时自动停用小插件);② logind 的 LockedHint。任何一道说锁着就当锁着。
"""
import json
import os
import shutil
import subprocess

UUID = "seeu@seeu-computeruse"
NAME, PATH, IFACE = "org.seeu.SeeU", "/org/seeu_lib/SeeU", "org.seeu.SeeU"
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ext", UUID)
CALL_MS = 2000


class NoHelper(RuntimeError):
    """小插件不在(没装、装了还没重新登录、锁屏、不是 GNOME)。"""


def _bus():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    return Gio, Gio.bus_get_sync(Gio.BusType.SESSION)


# 只读的问话:GNOME 一时卡住(没显卡加速的机器上,新窗口刚打开那一两秒;11-20 旧 Intel Mac 虚拟机实测)超时了就再问,
# 最多再问 2 次(合计最多约 6 秒)。会动东西的(挪指针、拉前台、写剪贴板…)不重发,免得做两遍。
READ_ONLY = {"Ping", "GetRects", "GetPointer", "GetFocus", "GetClipboard"}
RETRY = 2


def _call(method, args=None, sig=None):
    Gio, bus = _bus()
    from gi.repository import GLib
    params = GLib.Variant(sig, args) if sig else None
    tries = 1 + (RETRY if method in READ_ONLY else 0)
    for i in range(tries):
        try:
            r = bus.call_sync(NAME, PATH, IFACE, method, params, None, Gio.DBusCallFlags.NO_AUTO_START, CALL_MS, None)
            break
        except GLib.Error as ex:
            if "ServiceUnknown" in str(ex) or "NameHasNoOwner" in str(ex):
                raise NoHelper(why_missing()) from None
            if "Timeout" in str(ex) and i + 1 < tries:
                continue
            if "Timeout" in str(ex):
                raise RuntimeError(f"GNOME 一直没回话(问了 {tries} 次、每次等 {CALL_MS // 1000} 秒):桌面可能正卡着,等几秒再试") from None
            raise
    return r.unpack() if r is not None else ()


def available():
    try:
        _call("Ping")
        return True
    except Exception:   # noqa: BLE001
        return False


def ping():
    return json.loads(_call("Ping")[0])


def rects():
    """所有窗口,从下到上(z 越大越靠上)。坐标是屏幕逻辑像素;x/y/w/h 是窗口外框(不含阴影),buf_x/buf_y 含阴影的画布原点。"""
    return json.loads(_call("GetRects")[0])


def pointer():
    return tuple(_call("GetPointer"))


def toast(text, ms=3000):
    try:
        from seeu.linux.lang import tx
        _call("Toast", (tx(str(text)), int(ms)), "(su)")
    except Exception:   # noqa: BLE001   提示条只是显示,出错不影响动作
        pass


NEED_API = 2          # 第 3 段(借真鼠标、代理光标、悬浮标)要小插件第 2 版


def api():
    try:
        return int(ping().get("api") or 1)
    except Exception:   # noqa: BLE001
        return 0


def need_v2():
    """借真鼠标前查:小插件得是第 2 版(第 1 版没有挪指针 / 拉前台)。旧版抛 NoHelper。"""
    a = api()
    if a and a < NEED_API:
        raise NoHelper("SeeU 的 GNOME 小插件是旧版(没有借鼠标要用的功能):运行 python3 -m seeu 检查 --fix 换新版,然后注销重新登录一次")
    if not a:
        raise NoHelper(why_missing())


def warp(x, y):
    _call("Warp", (int(round(x)), int(round(y))), "(ii)")


def focus():
    return int(_call("GetFocus")[0])


def activate(wid):
    return bool(_call("Activate", (int(wid),), "(u)")[0])


def clipboard():
    """(剪贴板里有没有不是文字的东西, 文字)。"""
    other, text = _call("GetClipboard")
    return bool(other), text


def set_clipboard(text):
    _call("SetClipboard", (str(text),), "(s)")


def cursor(x, y, name="SeeU", color="#7F77DD", ms=60000, kind="move", key=None, auto=False):
    """代理光标(跟 Mac / Windows 同一套样子):kind = move | click(到点缩一下 + 波纹);ms = 停下多久淡出,0 = 收起。
    key = 哪个任务的光标(11-18 C-3.0,一个任务一只;不带 = 跟老调用共用一只);auto = 名牌按规则(只剩一只写 SeeU,多只写 name)。
    返回走到位要几秒(调用方可以等这么久再动手)。只是显示,出错返回 0。小插件老版本不认 key 就退回共用一只。"""
    try:
        if key:
            try:
                return float(_call("CursorK", (str(kind), int(round(x)), int(round(y)), str(name), str(color), int(ms), str(key), bool(auto)),
                                   "(siissusb)")[0])
            except NoHelper:
                raise
            except Exception:   # noqa: BLE001     老版本小插件没有 CursorK
                pass
        return float(_call("Cursor", (str(kind), int(round(x)), int(round(y)), str(name), str(color), int(ms)), "(siissu)")[0])
    except Exception:   # noqa: BLE001
        return 0.0


def cursor_wait(key, on=True):
    """排队中:这个任务的光标打瞌睡(飘 z + 变淡);on=False 轮到了收。只是显示。"""
    try:
        _call("CursorWait", (str(key), bool(on)), "(sb)")
    except Exception:   # noqa: BLE001
        pass


def cursor_hide(key=""):
    """藏光标:带 key 只藏那个任务的,不带全藏。"""
    try:
        _call("CursorHide", (str(key or ""),), "(s)")
    except Exception:   # noqa: BLE001
        pass


def badge(title, text="", color="#7F77DD", ms=8000):
    try:
        from seeu.linux.lang import tx
        _call("Badge", (tx(str(title)), tx(str(text)), str(color), int(ms)), "(sssu)")
    except Exception:   # noqa: BLE001
        pass


def halo(color="#FF9F0A", show=True):
    try:
        _call("Halo", (str(color), bool(show)), "(sb)")
    except Exception:   # noqa: BLE001
        pass


def dot(x, y, show=True):
    try:
        _call("Dot", (int(x), int(y), bool(show)), "(iib)")
    except Exception:   # noqa: BLE001
        pass


# ---------------------------------------------------------------- 锁屏
def _logind_locked():
    """logind 的 LockedHint(找当前用户的图形会话)。读不到返回 None。"""
    try:
        Gio, _ = _bus()
        from gi.repository import GLib
        sysbus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        sid = os.environ.get("XDG_SESSION_ID")
        if sid:
            path = sysbus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
                                    "GetSession", GLib.Variant("(s)", (sid,)), None, 0, CALL_MS, None).unpack()[0]
        else:
            path = sysbus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1/user/self",
                                    "org.freedesktop.DBus.Properties", "Get",
                                    GLib.Variant("(ss)", ("org.freedesktop.login1.User", "Display")),
                                    None, 0, CALL_MS, None).unpack()[0][1]
        v = sysbus.call_sync("org.freedesktop.login1", path, "org.freedesktop.DBus.Properties", "Get",
                             GLib.Variant("(ss)", ("org.freedesktop.login1.Session", "LockedHint")),
                             None, 0, CALL_MS, None).unpack()[0]
        return bool(v)
    except Exception:   # noqa: BLE001
        return None


def locked():
    """锁屏 / 屏保开着就是 True。小插件在就信它(GNOME 锁屏时它会被停用,能回话就说明没锁),再拿 logind 核一遍。"""
    lg = _logind_locked()
    if lg:
        return True
    if is_gnome():
        try:
            return bool(ping().get("locked"))
        except NoHelper:
            # 小插件装了、启用了却不在:多半是锁屏(GNOME 锁屏时自动停用它)
            return installed() and enabled()
        except Exception:   # noqa: BLE001
            return False
    return False


# ---------------------------------------------------------------- 安装
def is_gnome():
    return "GNOME" in (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper().split(":") or \
        "gnome" in (os.environ.get("DESKTOP_SESSION") or "").lower()


def dest_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "gnome-shell", "extensions", UUID)


def installed():
    return os.path.isfile(os.path.join(dest_dir(), "extension.js"))


def _enabled_list():
    out = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    import ast
    try:
        return list(ast.literal_eval(out.replace("@as ", "")))
    except Exception:   # noqa: BLE001
        return []


def enabled():
    try:
        return UUID in _enabled_list()
    except Exception:   # noqa: BLE001
        return False


def _version(d):
    try:
        with open(os.path.join(d, "metadata.json"), encoding="utf-8") as f:
            return int(json.load(f).get("version") or 0)
    except Exception:   # noqa: BLE001
        return 0


def _files():
    """小插件的文件:metadata.json + 所有 .js(第 2 版起代理光标单放 cursor.js)。"""
    return ["metadata.json"] + sorted(n for n in os.listdir(SRC) if n.endswith(".js"))


def install():
    """装进用户自己的扩展目录并加进启用列表(不要管理员密码)。返回 {copied, enabled, relogin}。
    GNOME 只在登录时扫一遍扩展 → 第一次装 / 换了新版要注销重新登录一次才生效(Wayland 下没法只重启 Shell)。"""
    d = dest_dir()
    same = installed() and _version(d) == _version(SRC) and all(
        os.path.exists(os.path.join(d, n)) and open(os.path.join(d, n), encoding="utf-8").read() ==
        open(os.path.join(SRC, n), encoding="utf-8").read() for n in _files())
    if not same:
        os.makedirs(d, exist_ok=True)
        for n in _files():
            shutil.copyfile(os.path.join(SRC, n), os.path.join(d, n))
    cur = _enabled_list()
    if UUID not in cur:
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(cur + [UUID])],
                       capture_output=True, timeout=10, check=True)
    try:   # 用户在「扩展」App 里关过全部扩展的话,这个开关也要打开
        subprocess.run(["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"],
                       capture_output=True, timeout=10)
    except Exception:   # noqa: BLE001
        pass
    return {"copied": not same, "enabled": True, "relogin": (not same) or not available()}


def uninstall():
    cur = _enabled_list()
    if UUID in cur:
        cur.remove(UUID)
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(cur)], capture_output=True, timeout=10)
    if os.path.isdir(dest_dir()):
        shutil.rmtree(dest_dir())


def why_missing():
    if not is_gnome():
        return ("现在的桌面不是 GNOME;SeeU Linux 版第一版只支持 GNOME(Ubuntu 默认桌面),"
                "别的桌面拿不到窗口位置")
    if not installed():
        return "SeeU 的 GNOME 小插件还没装:运行 python3 -m seeu 检查 --fix 装上,然后注销重新登录一次"
    if not enabled():
        return "SeeU 的 GNOME 小插件被关掉了:在「扩展」App 里把 SeeU 打开(或运行 python3 -m seeu 检查 --fix)"
    if _logind_locked():
        return "屏幕锁着(锁屏时 GNOME 会停用小插件)"
    return "SeeU 的 GNOME 小插件还没加载:装好后要注销重新登录一次;已经重新登录过的话,看「扩展」App 里它有没有报错"
