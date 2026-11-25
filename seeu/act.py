# -*- coding: utf-8 -*-
"""SeeU 统一入口(动作层,外面用 `import seeu` 直接调,不用写 act):用的人只说"对哪个 App、做什么",SeeU 自己挑路、自己核实、失效自动往下退。

    import seeu
    v = seeu.see("TextEdit")                 # 截图 + 编号清单(原生 App 用辅助功能控件;镜像用识字)
    seeu.tap("TextEdit", "bold")             # 按文字找;也可以传编号(上一次 see 的)或屏幕点 (x, y)
    seeu.type("iPhone Mirroring", "淘宝", enter=True)
    seeu.scroll("iPhone Mirroring", dy=-600) # 不给点就在窗口中间
    seeu.menu("iPhone Mirroring", "View", "Spotlight")

每个动作返回 dict:outcome = delivered(核实生效)| unverified(做了,没窗口可核实)| ineffective(做了但画面没变)| refused(安全底线/锁被占/用户在用)
| failed(出错);route = 最后走的那条路;tried = 依次试过的路和结果;png = 最后一张截图。

退路(前一条没生效自动试下一条):
  原生 App 点击:辅助功能按控件(先聚焦)→ 后台点击 → 真鼠标(拿桌面锁 + input_guard 让路 + 用完还原前台和鼠标)
  镜像点击:    后台点击 → 真鼠标
  打字:        后台 → 前台打字(拿桌面锁 + 让路 + 切到前台投给目标进程 + 还原前台;BlueStacks 不走,见 NO_FRONT_TYPING)
  长按/滚动:   后台
  拖动:         直接真鼠标(macOS 没有后台拖动的路)
命令行:python3 -m seeu see|tap|type|scroll|press|menu|base|home|open <App> ...
镜像:默认不动窗口大小(10-28 改:钉 391×859 只是个别调用方要的,它们自己调尺寸);要每个进程第一次动作前自动钉,设 SEEU_BASELINE=1。
"""
import os
import re
import sys
import tempfile
import threading
import time

from seeu_lib import mac_input as mi
from seeu import ax, bgclick as bg, bgkey as bk

ICON_ABOVE_LABEL = 30   # 镜像基准尺寸下,主屏图标中心在名字上方约 30 点
# 画面是视频流、辅助功能看不到里面按钮的 App:用识字代替控件清单
CANVAS_APPS = {"iPhone Mirroring", "BlueStacks"}   # BlueStacks:安卓画面,同样只能识字(10-14)
PROJECT = os.environ.get("SEEU_PROJECT", "SeeU")
_TMP = [None]
KEEP_SHOTS = 300    # 一个进程里只留最近这么多张截图(11-06 体检:原来只涨不落,长驻的 MCP 服务攒到十几 MB)。
#                     库调用方拿到的截图路径只短期有效(一个动作核实要截 2~7 张),要留就自己拷走。


def _tmp():
    """截图临时目录:第一次截图才建(原来一 import 就建,只跑「设置」这类命令也留个空目录);
    顺手删掉一天前别的进程留下的 seeu_* 目录(命令行打印的截图路径 AI 还要读,所以退出时不删,隔天再清)。"""
    if _TMP[0] is None:
        root = tempfile.gettempdir()
        try:
            import shutil
            for n in os.listdir(root):
                d = os.path.join(root, n)
                if not (n.startswith("seeu_") and os.path.isdir(d) and time.time() - os.path.getmtime(d) > 86400):
                    continue
                m = re.match(r"seeu_(\d+)_", n)          # 目录名带进程号:那个进程还活着就不删(长驻的 MCP 服务一天没截图也别删它的)
                if m and _pid_alive(int(m.group(1))):
                    continue
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
    if _TMP[0] is None or not os.path.isdir(_TMP[0]):    # 万一被别人删了(系统清临时目录等)就重建,别从此截不到图
        _TMP[0] = tempfile.mkdtemp(prefix=f"seeu_{os.getpid()}_")
    return _TMP[0]


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _ocr(png):
    """认字。seeu_lib.ocr 读不到图 / 识别失败抛的是 SystemExit(不是 Exception),
    没人接就把整个进程带走(11-06 体检:MCP 服务认字失败一次就退出)→ 这里转成普通错误。"""
    from seeu_lib import ocr
    try:
        return ocr.ocr(png)
    except SystemExit as ex:
        raise RuntimeError(f"认字失败:{ex}")
_last = {}   # app -> 上一次 see() 的清单(按编号点用)
_seen_modals = {}   # app -> 上一次 see() 时弹着的表单 / 对话框框(11-16:只有 AI 看过的弹窗才允许借鼠标往里点)
_n = [0]


def _is_canvas(app):
    return bg.split_target(app)[0] in CANVAS_APPS


def _pid(app):
    """目标的进程号:带「窗口标题」的按那个窗口找(同名多实例),否则按应用名。"""
    g = bg.main_window(app)
    if g:
        return g["pid"]
    return ax.app_element(app)[1]


def _activate(app, wait_front_s=1.5):
    """真鼠标前把目标提到前台。一律按进程号激活:按名字激活分不清多实例;11-23 中文系统里前台名叫「iPhone镜像」,
    按英文名核对前台永远对不上(白等 1.5 秒还报没到前台)。"""
    import AppKit
    from seeu_lib import input_guard as ig
    pid = _pid(app)
    fa = ig.frontmost_app()
    if fa and fa["pid"] == pid:
        return True                   # 已经在前台:不再激活,免得窗口一闪
    ra = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if ra is None:
        return False
    ra.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
    try:                              # 11-23 复查:macOS 14 起后台进程发起的激活可能被系统忽略 → 按包名 AppleScript 兜底
        time.sleep(0.3)
        fa = ig.frontmost_app()
        if not (fa and fa["pid"] == pid) and ra.bundleIdentifier():
            import subprocess
            subprocess.run(["osascript", "-e", f'tell application id "{ra.bundleIdentifier()}" to activate'],
                           capture_output=True, timeout=10)
    except Exception:   # noqa: BLE001
        pass
    t0 = time.time()
    while time.time() - t0 < wait_front_s:
        time.sleep(0.2)
        fa = ig.frontmost_app()       # 🔴 别直接问 NSWorkspace:没事件循环时一直返回旧值(10-14 C-1.1 又踩到)
        if fa and fa["pid"] == pid:
            time.sleep(0.2)
            return True
    return False


# ---------------------------------------------------------------- 镜像基准尺寸
# 用户定的基准视图(09-15 起一直这么用):⌘0 实际尺寸 → ⌘+ 放大一档 = 391×859 点(截图 782×1718)。
# 所有截图坐标/模板都按这个量,所以镜像动作前先钉一次。SeeU 走菜单项(后台、不发真按键、不抢前台)。
MIRROR_BASE = (391, 859)
_based = set()


def _wait_base(app, g):
    for _ in range(10):  # 最多等 3 秒窗口动画
        time.sleep(0.3)
        g = bg.main_window(app) or g
        if (g["w"], g["h"]) == MIRROR_BASE:
            break
    return g


def mirror_baseline(app="iPhone Mirroring", force=False):
    """把镜像窗口钉成基准尺寸。已经是基准就跳过(⌘0/⌘+ 会让画面流关了重开、菜单栏紫图标闪,09-26 踩过)。
    退路:后台点菜单(实际尺寸 → 放大)→ 真按键 ⌘0、⌘+(拿桌面锁、让路、用完还原前台)。
    返回 {ok, route, before, after}。"""
    g0 = bg.main_window(app)
    if not g0:
        raise RuntimeError(f"找不到 {app} 的窗口")
    if not force and (g0["w"], g0["h"]) == MIRROR_BASE:
        _based.add(app)
        return {"ok": True, "route": "已是基准", "before": g0, "after": g0}
    g, route = g0, None
    try:
        ax.menu(app, "View", "Actual Size")
        time.sleep(0.6)
        ax.menu(app, "View", "Zoom In")
        g, route = _wait_base(app, g0), "后台菜单"
    except Exception:
        pass
    if (g["w"], g["h"]) != MIRROR_BASE and not real_allowed():
        route = "后台菜单没调到基准大小;按设置没借真键盘"
    elif (g["w"], g["h"]) != MIRROR_BASE:
        def keys(ig):
            ig.preflight(g0["x"] + g0["w"] / 2, g0["y"] + 20, ax.local_name(app), check_modal=False)   # 11-23 中文系统进程名
            mi.key_cmd(app, "0")
            time.sleep(0.6)
            mi.key_cmd(app, "+")
            ig.note_injected()
        try:
            _real_mouse(app, keys)()
            g, route = _wait_base(app, g), "真按键"
        except Exception as ex:
            route = f"真按键失败:{ex}"
    ok = (g["w"], g["h"]) == MIRROR_BASE
    if ok:
        _based.add(app)
    return {"ok": ok, "route": route, "before": g0, "after": g}


class BaselineError(RuntimeError):
    """镜像钉不成基准尺寸。用存好的坐标/模板的调用方必须停;SeeU 自己现量坐标的动作可以设 SEEU_ALLOW_UNSIZED=1 放行。"""


def _ensure_base(app):
    """设了 SEEU_BASELINE=1 才钉:镜像每个进程第一次动作前钉一次基准尺寸;钉不上(菜单、真按键都不行)抛 BaselineError 停手。
    10-28 起默认不钉(以前默认钉、SEEU_NO_BASELINE 关)。"""
    if app == "iPhone Mirroring" and app not in _based and os.environ.get("SEEU_BASELINE"):
        r = mirror_baseline(app)
        if not r["ok"]:
            msg = (f"镜像钉不成基准尺寸 {MIRROR_BASE[0]}×{MIRROR_BASE[1]}(现在 {r['after']['w']}×{r['after']['h']},"
                   f"{r['route']})")
            if not os.environ.get("SEEU_ALLOW_UNSIZED"):
                raise BaselineError(msg)
            print("⚠️ " + msg + ",按 SEEU_ALLOW_UNSIZED 继续", file=sys.stderr)


def _geo(app, by_title=False):
    """App 的目标窗口(屏幕点 + 窗口号)。原生 App 取辅助功能里的焦点窗口(多窗口时不会截错),取不到再按面积挑最大的。
    写了「标题」或 by_title(按键指明了浏览器窗口):框一样的几个里认标题;没指明照旧取最上面那个(点击、聚焦也是落在它上面,要一致)。"""
    if not _is_canvas(app):
        try:
            import Quartz
            el, pid = ax.app_element(app)
            mw = ax.main_window(el, ax.split_window(app)[1])            # 11-01:写了「窗口标题」就截那个窗口
            f = ax.frame(mw)
            # 11-25 C-4.2 复查:同 App 两个窗口位置大小一模一样(都最大化)时只比框会拿到上面那个 → 框一样的里面先认标题
            by_title = by_title or ax.split_window(app)[1] is not None
            want = _browser_title(ax.attr(mw, "AXTitle")) if mw is not None and by_title else None
            same = []
            for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
                b = w.get("kCGWindowBounds") or {}
                if f and w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer", 0) == 0 and \
                        (round(b["X"]), round(b["Y"]), round(b["Width"]), round(b["Height"])) == tuple(round(v) for v in f):
                    same.append((_browser_title(w.get("kCGWindowName")) == want,
                                 dict(x=int(b["X"]), y=int(b["Y"]), w=int(b["Width"]), h=int(b["Height"]),
                                      id=int(w["kCGWindowNumber"]))))
            if same:
                return next((g for hit, g in same if hit), same[0][1])
        except Exception:
            pass
    g = bg.main_window(app)   # 含不在当前桌面的窗口
    if not g:
        raise RuntimeError(f"找不到 {app} 的窗口")
    return g


def _app_hidden(pid):
    from AppKit import NSRunningApplication
    ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
    return bool(ra and ra.isHidden())


def shoot(app):
    """截 App 主窗口(ScreenCaptureKit,不触发 iOS 截屏弹窗)。每次新文件。"""
    from seeu_lib import sck_capture as sc
    g = _geo(app)
    if g.get("onscreen") is False and g.get("pid") and _app_hidden(g["pid"]):
        raise RuntimeError("App 藏着,截不到图")   # 10-29:藏着的 App 截图要干等 10 秒超时才失败,直接跳过(别的桌面上的窗口照截)
    if g.get("onscreen") is False and min(g.get("w", 0), g.get("h", 0)) < 100:
        # 10-30:App 没开窗口(访达实测)时挑到的是屏幕外 64×64 的占位小窗,截它同样干等 10 秒 → 直接跳过
        raise RuntimeError("App 没开窗口,截不到图")
    _n[0] += 1
    png = os.path.join(_tmp(), f"s{_n[0]}.png")
    old = os.path.join(_tmp(), f"s{_n[0] - KEEP_SHOTS}.png")
    if _n[0] > KEEP_SHOTS and os.path.exists(old):
        try:
            os.remove(old)
        except OSError:
            pass
    if not sc.capture_window(g["id"], png):
        raise RuntimeError("截图失败")
    return png


def _scale(app, png):
    import cv2
    h, w = cv2.imread(png).shape[:2]
    g = _geo(app)
    return g, w / g["w"]


def _verify_box(app, png):
    """核实时比对的区域:镜像避开顶部状态栏(时钟会自己变)。"""
    if not _is_canvas(app):
        return None
    import cv2
    h, w = cv2.imread(png).shape[:2]
    return (0, int(h * 0.12), w, h)


# ---------------------------------------------------------------- 看

def see(app, _note_modals=True):
    """返回 {png, items}。items 每项:id、kind(ax|ocr)、text、x/y(屏幕点中心)、以及 ax 项带 el/role。
    浏览器(Chrome / Safari …)转给 seeu.web:返回 {route, items, text, url, title, tab},没有 png。"""
    from seeu import web, safety
    app = web.canon(app)
    # 11-06 体检:看画面也过安全底线(原来终端、密码 App、隐私设置页都能被截图 + 读文字发给 AI;probe 是跳过的)。
    # 被拦抛 safety.Refused(= ax.AXRefused)。
    safety.check_app(app)
    if web.is_browser(app) or web.is_cdp(app):     # C-1.0:SeeU 专用那份网页壳 App(调试端口)也转过去
        return web.see(app)
    _ensure_base(app)
    canvas = _is_canvas(app)
    try:
        png = shoot(app)
    except RuntimeError:
        if canvas:                      # 镜像/模拟器靠截图认字,截不到就没法看
            raise
        png = None                      # 10-30:原生 App 藏着截不到图,照样按辅助功能读控件(Codex 实测 see 直接报错)
    items = []
    if canvas:
        g, s = _scale(app, png)
        for e in _ocr(png):
            items.append(dict(kind="ocr", text=e["text"], x=g["x"] + e["x"] / s, y=g["y"] + e["y"] / s,
                              rx=e["x"] / s, ry=e["y"] / s))
    else:
        for e in ax.elements(app):
            f = e["frame"]
            if not f or f[2] <= 0:
                continue
            text = " ".join(t for t in (e["title"], e["desc"], e["value"]) if t)
            items.append(dict(kind="ax", text=text, role=e["role"], x=f[0] + f[2] / 2, y=f[1] + f[3] / 2,
                              ax=e))
    for i, it in enumerate(items, 1):
        it["id"] = i
    _last[app] = items
    if not canvas and _note_modals:      # 按编号点时顺手补的那次 see 不算「AI 看过」(11-16 复查二)
        try:
            _seen_modals[app] = [f for f in (_modal_frames(_pid(app)) or []) if f]
        except Exception:
            _seen_modals[app] = []
    wins = []
    if not canvas and bg.split_target(app)[1] is None:
        try:                            # 11-01:App 开着好几个窗口(如 Gemini 的设置)时告诉 AI 怎么指定
            wins = ax.window_titles(ax.app_element(app)[0])
        except Exception:
            pass
    stale = stale_why(app) if png else None        # 11-15 C-2.0:Chrome / Electron 窗口看不见,截图可能是旧的
    return {"png": png, "items": items, "windows": wins, "stale": stale}


def describe(items):
    return "\n".join(f"{it['id']:>3}. {it.get('role', 'OCR')[2:] if it.get('role') else '字'}  {it['text']}  "
                     f"({it['x']:.0f},{it['y']:.0f})" for it in items)


class Stale(RuntimeError):
    """按编号操作时发现画面已经不是 see 那时候的样子(那个控件不在了)。不点,让调用方重新 see。"""


def _still_there(app, it):
    """按编号点之前核对(11-14):see 的时候那个控件还在不在、现在在哪。返回现在的中心点 (x, y);不在了抛 Stale。
    原来直接用 see 时记下的位置:之后列表滚了、弹了框、界面换了都不知道,会点到别的东西上。
      - 控件还在:用它**现在**的位置(滚动、挪窗口后也点得准),顺手更新清单里记的位置。
      - 控件对象失效:有的 App 每读一次就换一批对象、界面其实没变 → 看原位置上现在是不是同一种、同名的控件,是就照点。
      - 都不是:抛 Stale(不退回去点老位置)。
    只有画面的项(镜像、模拟器,靠认字)没有控件可问,这里不核对(11-14 用户定:先做控件类)。"""
    e = it.get("ax")
    if not e:
        return it["x"], it["y"]
    el = e["el"]
    if (ax.attr(el, "AXRole") or "") == e["role"]:
        f = ax.frame(el)
        if f and f[2] > 0 and f[3] > 0:
            e["frame"] = f
            it["x"], it["y"] = f[0] + f[2] / 2, f[1] + f[3] / 2
            return it["x"], it["y"]
    now = None
    if e.get("title") or e.get("desc"):          # 没名字的控件认不出「是不是同一个」,不走这条
        try:
            now = ax.element_at(ax.app_element(app)[0], it["x"], it["y"])
        except Exception:   # noqa: BLE001
            now = None
    if (now is not None and (ax.attr(now, "AXRole") or "") == e["role"]
            and ax._short(ax.attr(now, "AXTitle") or "") == e["title"]
            and ax._short(ax.attr(now, "AXDescription") or "") == e["desc"]):
        it["ax"] = dict(e, el=now, actions=ax.action_names(now), frame=ax.frame(now) or e["frame"])
        return it["x"], it["y"]
    raise Stale(f"画面变了:第 {it['id']} 项「{(it.get('text') or '')[:20]}」已经不在 see 时的位置,先 see 一次再操作")


def _resolve(app, target):
    """target → (x, y, ax项或None)。"""
    if isinstance(target, (tuple, list)) and len(target) == 2:
        return float(target[0]), float(target[1]), None
    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
        items = _last.get(app) or see(app, _note_modals=False)["items"]
        n = int(target)
        it = next((i for i in items if i["id"] == n), None)
        if not it:
            raise RuntimeError(f"没有编号 {n},先 see 一次")
        x, y = _still_there(app, it)
        return x, y, it.get("ax")
    t = str(target)
    if not _is_canvas(app):
        e = ax.find(app, t)
        f = e["frame"]
        return f[0] + f[2] / 2, f[1] + f[3] / 2, e
    items = see(app)["items"]
    hits = [i for i in items if i["text"] == t] or [i for i in items if t in i["text"]]
    if not hits:
        raise RuntimeError(f"画面上没找到「{t}」")
    return hits[0]["x"], hits[0]["y"], None


def _rel(app, x, y):
    """屏幕点 → 相对窗口左上角的偏移(窗口可能被挪,点之前要按当时位置换算回来)。"""
    g = _geo(app)
    return x - g["x"], y - g["y"]


def _abs(app, rx, ry):
    g = _geo(app)
    return g["x"] + rx, g["y"] + ry


# ---------------------------------------------------------------- 截图不可信(11-15 C-2.0)
# Chrome / Electron 内核的 App 窗口看不见时(整个被盖住、在别的桌面、缩进程序坞)不重画,截图停在旧画面;
# 11-15 Mac 实测 VS Code:后台按 Cmd+B,页面里侧栏 1 秒就变了,截图 20 秒一动不动,露出来才跟上(被盖住、别的桌面两种都是)。
# 这类 App 网页里的控件辅助功能又读不到,AI 只能照截图按位置点 → 会点到已经不在那儿的东西上。照 Windows win/act.stale_why 做:
# 看不见就不按截图位置点。按编号 / 菜单 / 按键照常。露出一部分的没测,不拦(Chromium 自己也只在整个盖住时才停画)。
COVER_WHY = "它整个被别的窗口盖住了,Chrome / Electron 这类程序被盖住时不重画"
DESK_WHY = "它不在当前桌面上(在别的桌面、缩进了程序坞,或被隐藏了),Chrome / Electron 这类程序这时不重画"
LOCK_WHY = "Mac 锁着屏或显示器睡着了,Chrome / Electron 这类程序这时不重画"     # Chromium 官方文档:锁屏、关屏一律算遮挡
STALE_PIXEL = ("这个窗口的截图现在不可信:{why}。按截图位置操作会照着旧画面点到别的东西"
               "(11-15 实测:页面已经变了,截图 20 秒没变),SeeU 没做。{tip}")
STALE_TIP = ("改用 see 列表里的编号、菜单(menu)或快捷键(press);都不行的话,请用户{how},再 see。"
             "要全程藏着操作,可以改用 SeeU 专用的那份(Python:from seeu import cdp; cdp.launch(\"{app}\")),它藏着也能读清页面")
COVER_HOW = "把这个窗口露出来一块(比如一个角,别只露一条缝)"
DESK_HOW = "切到那个桌面,或把窗口挪到当前桌面"
LOCK_HOW = "解锁 Mac、唤醒显示器"
STALE_DONE = ("已经做了,但没法核实:{why},截图不会变。没有换别的办法再做一遍(免得重复)。"
              "先 see 看列表里的文字有没有变来核对;别凭截图判断,也别马上重做")
VISIBLE_MIN = 0.5        # 露出不到百分之几算「整个盖住」(菜单栏阴影、圆角缝隙那点不算露出)
_KIND = {}               # App 包路径 → Chromium 内核 App 的包名(如「Visual Studio Code」,cdp.launch 用它),不是就 None


def _chromium(pid):
    # 11-15 复查:原来按进程号缓存 → 进程号被别的 App 复用会认错;刚启动读不到包路径也会一直记成「不是」。
    #   改成每次现查包路径(便宜),只按路径缓存内核判断;读不到不缓存。
    try:
        from AppKit import NSRunningApplication
        ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        path = str(ra.bundleURL().path()) if ra and ra.bundleURL() else None
    except Exception:   # noqa: BLE001
        return None
    if not path:
        return None
    if path not in _KIND:
        try:
            from seeu import cdp
            k = cdp.kind(path)
        except Exception:   # noqa: BLE001
            return None
        _KIND[path] = os.path.basename(path.rstrip("/"))[:-4] if k and path.rstrip("/").endswith(".app") else None
    return _KIND[path]


def _visible_pct(wid, wins):
    """窗口号 wid 露出来的百分比:wins = 当前桌面的窗口(从前往后);排在它前面的普通窗口(层 0、不透明)算盖住。不在 wins 里返回 None。"""
    me = next((w for w in wins if int(w.get("kCGWindowNumber", -1)) == int(wid)), None)
    if me is None:
        return None
    import numpy as np
    b = me["kCGWindowBounds"]
    k = 4.0                                       # 按 4 点一格算,够准、也快
    W_, H_ = max(1, int(b["Width"] / k)), max(1, int(b["Height"] / k))
    mask = np.zeros((H_, W_), bool)
    for w in wins:
        if w is me:
            break
        if w.get("kCGWindowLayer", 0) != 0 or float(w.get("kCGWindowAlpha", 1)) < 0.9:
            continue
        r = w["kCGWindowBounds"]
        x0, y0 = max(int((r["X"] - b["X"]) / k), 0), max(int((r["Y"] - b["Y"]) / k), 0)
        x1 = min(int((r["X"] + r["Width"] - b["X"]) / k), W_)
        y1 = min(int((r["Y"] + r["Height"] - b["Y"]) / k), H_)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return 100.0 - float(mask.mean()) * 100.0


def _screen_off():
    """锁着屏或主显示器睡着了(11-15 C-2.0)。读不到当没有。"""
    try:
        import Quartz
        d = Quartz.CGSessionCopyCurrentDictionary() or {}
        if d.get("CGSSessionScreenIsLocked"):
            return True
        return bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))
    except Exception:   # noqa: BLE001
        return False


def stale_why(app):
    """这个 App 的截图现在可不可信:不可信返回原因,可信 / 不适用返回 None。只管 Chrome / Electron 内核的 App(镜像、模拟器、原生 App 不管)。"""
    try:
        if _is_canvas(app):
            return None
        pid = _pid(app)
        if not pid or not _chromium(pid):
            return None
        if _screen_off():
            return LOCK_WHY
        g = _geo(app)
        if not g.get("id"):
            return None
        import Quartz
        wins = list(Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or [])
        v = _visible_pct(g["id"], wins)
        if v is None:
            return DESK_WHY
        return COVER_WHY if v < VISIBLE_MIN else None
    except Exception:   # noqa: BLE001 —— 判断不了就当可信,不挡正常操作(跟原来一样)
        return None


def _stale_pixel(app):
    """按截图位置操作之前查一次:截图不可信返回一个「没做」的结果(failed + 原因),可信返回 None。"""
    why = stale_why(app)
    if not why:
        return None
    how = {DESK_WHY: DESK_HOW, LOCK_WHY: LOCK_HOW}.get(why, COVER_HOW)
    try:
        name = _chromium(_pid(app)) or app
    except Exception:   # noqa: BLE001 —— 11-15 复查:App 刚好退出时 _pid 会抛错,别让整个 tap 失败
        name = app
    tip = STALE_TIP.format(how=how, app=name)
    return dict(outcome="failed", route=None, tried=[], png=None, stale=True, reason=STALE_PIXEL.format(why=why, tip=tip))


# ---------------------------------------------------------------- 核实 + 退路

FINE_PIX_THR = 12      # 彩色原尺寸比时,算「变了」的色差(11-06 真机静止帧:12 以上只剩光标闪动,没有画面噪声)
FINE_TAP_PT2 = 12      # 点击处附近变了多大算有反应(平方点;光标约 2×20)
FINE_NEAR = (90, 50)   # 点击处左右、上下各看多远(点)
FINE_KEY_PCT = 0.002   # 按键:整块区域变了多少算有反应


def _fine_area(before, after, box, at=None, scale=1.0):
    """彩色、不缩小地比两张图,返回变了的面积(平方点)。给了 at(图上像素)只看它附近。"""
    import cv2
    import numpy as np
    a, b = cv2.imread(before), cv2.imread(after)
    if a is None or b is None or a.shape != b.shape:
        return float("inf")
    x0, y0, x1, y1 = box or (0, 0, a.shape[1], a.shape[0])
    if at:
        x0, x1 = max(x0, int(at[0] - FINE_NEAR[0] * scale)), min(x1, int(at[0] + FINE_NEAR[0] * scale))
        y0, y1 = max(y0, int(at[1] - FINE_NEAR[1] * scale)), min(y1, int(at[1] + FINE_NEAR[1] * scale))
    d = cv2.absdiff(a[y0:y1, x0:x1], b[y0:y1, x0:x1]).max(axis=2)
    return float(np.count_nonzero(d > FINE_PIX_THR)) / (scale * scale)


def _fine_expect(app, at=None, min_change=0.003):
    """镜像、模拟器专用的核实:原来的「整块画面变多少」之外,再看小变化(光标、选中高亮)。
    at = 相对窗口的点击位置(点);不给 = 按键,看整块。普通 App 返回 None,照旧。"""
    if not _is_canvas(app):
        return None
    import shutil
    from seeu_lib import wait

    def factory():
        first = shoot(app)
        # 每次覆盖,不留一堆文件。11-07:放进本进程的截图临时目录(原来直接放系统临时目录,每个进程留一张、没人清)
        keep = os.path.join(_tmp(), "fine_keep.png")
        shutil.copyfile(first, keep)
        box = _verify_box(app, keep)
        g = _geo(app)
        import cv2
        scale = cv2.imread(keep).shape[1] / g["w"]

        def expect(png):
            if wait.frame_change(keep, png, box) >= min_change:
                return True
            if at:
                return _fine_area(keep, png, box, (at[0] * scale, at[1] * scale), scale) >= FINE_TAP_PT2
            total = (box[2] - box[0]) * (box[3] - box[1]) / (scale * scale)
            return _fine_area(keep, png, box, None, scale) >= total * FINE_KEY_PCT
        expect.rebase = lambda: shutil.copyfile(shoot(app), keep)    # 11-17 复查:排完队重拍,比的是这张(见 _act_and_verify)
        return expect
    return factory

_REBASE = threading.local()      # 11-17 C-2.8:借真鼠标排完队、真要动手前,重拍「动作前」那张图(见 _act_and_verify、_real_mouse)


def _rebase():
    f = getattr(_REBASE, "f", None)
    if f:
        try:
            f()
        except Exception:   # noqa: BLE001 —— 重拍不成就用原来那张(跟以前一样)
            pass


def _act_and_verify(app, act, expect=None, box=None, min_change=0.003, timeout=2.5, interval=0.4):
    """同 seeu_lib.wait.act_and_verify(做 → 反复截图比「动作前」),多一条:act 里排队等过(借真鼠标等别的任务、等用户停手),
    真动手前调 _rebase() 重拍「动作前」—— 原来那张是排队前拍的,等的这段时间画面自己变了会被当成「点成了」(复查 11-17 第三批)。"""
    import shutil
    import tempfile
    from seeu_lib import wait
    tmpdir = tempfile.mkdtemp(prefix="verify_")
    before = os.path.join(tmpdir, "before.png")
    try:
        shutil.copyfile(shoot(app), before)
        def rebase():
            shutil.copyfile(shoot(app), before)
            rb = getattr(expect, "rebase", None)      # 11-17 复查:给了 expect(镜像 / 模拟器的精细核实、文字核实)时比的是它自己记的那张
            if rb:
                rb()
        _REBASE.f = rebase
        try:
            result = act()
        finally:
            _REBASE.f = None
        t0 = time.time()
        while True:
            time.sleep(interval)
            png = shoot(app)
            change = wait.frame_change(before, png, box)
            ok = bool(expect(png)) if expect else change >= min_change
            if ok:
                return {"outcome": "delivered", "png": png, "change": change, "result": result}
            if time.time() - t0 + interval > timeout:
                return {"outcome": "ineffective", "png": png, "change": change, "result": result}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _try(app, act, min_change, expect=None):
    from seeu_lib import wait
    try:
        first = shoot(app)
    except RuntimeError:  # 没窗口可截(比如菜单新建前):照做,但没法核实
        from seeu_lib import input_guard as ig
        try:
            act()
        finally:
            ig.note_injected()
        return "unverified", None
    done = []

    def act_once():
        from seeu_lib import input_guard as ig
        try:
            act()
        finally:
            # 10-30:后台点击(SkyLight 发的事件)也会刷新系统"最近有输入"的时间;不登记成自己的,
            # 下一条路(真鼠标)先让路时会把自己刚点的这一下当成用户在用 → 误报 user_takeover(Codex 实测)
            ig.note_injected()
        done.append(1)
    try:
        r = _act_and_verify(app, act_once, expect=expect, box=_verify_box(app, first), min_change=min_change,
                            timeout=2.5, interval=0.4)
    except RuntimeError:
        if not done:
            raise
        # 10-29:动作做完窗口没了/被藏回去(备忘录菜单拉前台后 _keep_front 藏回)→ 截不到图 = 没法核实,
        # 不能当成这条路失败,否则 _ladder 会换下一条路把同一个动作再做一遍
        return "unverified", None
    return r["outcome"], r["png"]


def _ladder(app, steps, min_change=0.003, expect_factory=None):
    """expect_factory:每条路动手前调一次,返回 expect(png) 函数(给了就不比截图,按它核实)。"""
    from seeu import safety
    try:
        safety.check_app(app)        # 安全底线:终端、系统权限弹窗、Claude 自己(借真鼠标那条路也拦住)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    _ensure_base(app)
    stale = stale_why(app)   # 11-15 复查:截图不可信时「截图没变」不代表没生效,不能换下一条路再做一遍
    tried = []
    png = None
    for name, act in steps:
        try:
            outcome, png = _try(app, act, min_change, expect_factory() if expect_factory else None)
        except ax.AXRetry as ex:          # 复查 11-17(C-2.7):暂时忙 / 窗口不对 —— 不是拒绝,AI 稍后或先点一下再试
            done_before = bool(tried)     # 前面已经走过一条路(后台点 / 打字可能已经发出去了)
            tried.append((name, f"{ex.outcome}:{ex}"))
            if ex.outcome == "busy" and done_before:
                # 二次复查:后台那一下其实发出去了,报 busy 会让 AI 再来一遍(字打两遍、开关点两次)→ 报 ineffective,让它先看
                return dict(outcome="ineffective", route=name, tried=tried, png=png, reason=str(ex), code="busy_after_try",
                            note=AFTER_TRY_NOTE)
            return dict(outcome=ex.outcome, route=name, tried=tried, png=png, reason=str(ex), code=ex.code)
        except ax.AXRefused as ex:
            tried.append((name, f"refused:{ex}"))
            r = dict(outcome="refused", route=name, tried=tried, png=png, reason=str(ex))
            if str(ex) == OTHER_DESKTOP:      # 11-24 C-4.1:跟「问我」档、Windows 一样带上 code
                r["code"] = "other_desktop"
            return r
        except _SelfVerified as ex:       # 11-14:这条路自己核实过了(控件的值变了),不再比截图、不再换下一条路
            tried.append((name, "delivered"))
            return dict(outcome="delivered", route=name, tried=tried, png=png, note=str(ex))
        except Exception as ex:  # 这条路走不通(私有接口没了、控件不支持…)→ 下一条
            if _user_busy(ex):
                # 11-06 体检:借真鼠标前让路,发现用户正在用电脑。原来记成 failed(AI 的规矩是「先看再试」,会反复跟用户抢)
                why = f"用户正在用电脑,SeeU 先不借鼠标(等用户停手再试):{ex}"
                tried.append((name, f"refused:{why}"))
                return dict(outcome="refused", route=name, tried=tried, png=png, reason=why, code="user_busy")
            tried.append((name, f"error:{ex}"))
            continue
        tried.append((name, outcome))
        if outcome in ("delivered", "unverified"):
            return dict(outcome=outcome, route=name, tried=tried, png=png)
        if outcome == "ineffective" and stale:
            # 窗口看不见(Chrome / Electron 不重画):做了,但截图核实不了。原来会换后台点击、借真鼠标再点两次
            return dict(outcome="unverified", route=name, tried=tried, png=png, note=STALE_DONE.format(why=stale))
    last = tried[-1][1] if tried else "failed"
    out = "refused" if str(last).startswith("refused") else ("ineffective" if last == "ineffective" else "failed")
    return dict(outcome=out, route=tried[-1][0] if tried else None, tried=tried, png=png)


AFTER_TRY_NOTE = "后台已经试过一次(可能已经生效、只是画面没变),借真鼠标那一步排不上;先看一眼(see)再决定要不要再做"


def _user_busy(ex):
    """这个异常是不是「让路时发现用户在用电脑」(seeu_lib.input_guard.GuardBlocked 一族)。"""
    try:
        from seeu_lib import input_guard as ig
        # 只认这两种;GuardBlocked 的其它情况(被别的窗口挡住、有弹窗、点落在窗口外…)照旧算这条路出错
        return isinstance(ex, (ig.UserTakeover, ig.GuardTimeout))
    except Exception:
        return False


class _SelfVerified(Exception):
    """这条路已经用控件自己的状态核实过生效了(不用再比截图)。只在 _ladder 里接。"""


def _press_seen(app, e):
    """按下 see / find 时拿到的那个控件本身。11-06 体检:原来传编号让 ax.press 重新遍历后按序号取,
    see 和 tap 之间界面多一行、焦点窗口一换就按到另一个控件,而且多半报 delivered。
    控件已经不在了会报错 → 阶梯换下一条路(按当时的位置后台点击)。"""
    ax.check_safe(e)
    if e["role"] != "AXMenuBarItem":
        try:
            ax._focus(app, e)
        except Exception:
            pass
    acts = e["actions"]
    act = "AXPress" if "AXPress" in acts else ("AXPick" if "AXPick" in acts else None)
    if not act:
        raise ax.AXError(f"{ax.describe(e)} 不支持按下")
    v0 = ax.attr(e["el"], "AXValue")
    ax.perform(e["el"], act)
    # 11-14:勾选框、单选、开关这类「按一下值就变」的控件,按完读一下它自己的值,变了就是生效了。
    #   原来只比截图:窗口在后面 / 变化太小时看不出来 → 判没生效 → 换下一条路再点一次 → 把勾又点了回去
    #   (文本编辑 bold 实测:辅助功能按下 0→1,后台点击又 1→0,还报 ineffective)。
    if v0 is not None and not isinstance(v0, str):
        for _ in range(6):
            time.sleep(0.05)
            v1 = ax.attr(e["el"], "AXValue")
            if v1 is not None and v1 != v0:
                raise _SelfVerified(f"控件自己的值变了({v0} → {v1})")


OTHER_DESKTOP = ("目标窗口不在当前桌面上(在别的桌面,或窗口被收起来了):后台做不成,借鼠标 / 切前台可能把用户整个切到那个桌面,SeeU 没借。"
                 "请用户切到那个桌面,或把窗口挪到 / 打开在现在的桌面,再 see 一次接着做")
# 11-15 真机只读核对:收进菜单栏的 App(Clash Verge、UU远程)窗口关着也是「有窗口、都不在屏上」,分不清是不是在别的桌面
#   (辅助功能只列当前桌面的窗口,私有接口不用)。这种借鼠标也点不到,一起拦下,原因写成两种都包括。


def _other_desktop(app):
    """目标窗口在别的桌面(Space)上:有窗口,但没有一个在当前桌面;藏起来的(⌘H)、缩进程序坞的不算(激活它们不会切桌面)。
    11-15 C-2.0 照 Windows `_gate`:借鼠标 / 前台打字前查,在别的桌面就不借(激活会把用户切过去)。判断不了当不在。"""
    try:
        g = bg.main_window(app)
        if not g or g.get("onscreen") is not False or min(g.get("w", 0), g.get("h", 0)) < 100:
            return False
        if _app_hidden(g["pid"]):
            return False
        el = ax.app_element(g["pid"])[0]
        ws = ax.attr(el, "AXWindows") or []
        if ws and all(ax.attr(w, "AXMinimized") for w in ws):
            return False
        return True
    except Exception:   # noqa: BLE001
        return False


def _desk_refused(r, app):
    """在别的桌面:把结果改成 refused(停下告诉用户),不先问用户、也不借。不在返回 None。"""
    if not _other_desktop(app):
        return None
    r.update(outcome="refused", code="other_desktop", reason=OTHER_DESKTOP)
    return r


def _modal_frames(pid):
    """pid 这个 App 弹着的每个表单 / 对话框的屏幕框 [(x, y, w, h) 或 None…];认法跟 input_guard.modal_state 一样
    (表单 AXSheet、AXModal 窗口、不是主窗口的 AXDialog,红黄绿那种小窗不算)。读不到整张表返回 None。"""
    try:
        el, _ = ax.app_element(int(pid))
        wins = ax.attr(el, "AXWindows")
        if wins is None:
            return None
        out = []
        for w in wins:
            sheets = list(ax.attr(w, "AXSheets") or []) + [
                c for c in (ax.attr(w, "AXChildren") or []) if ax.attr(c, "AXRole") == "AXSheet"]
            if sheets:
                out += [ax.frame(s) for s in sheets]
                continue
            if ax.attr(w, "AXModal"):
                out.append(ax.frame(w))
            elif ax.attr(w, "AXSubrole") in ("AXDialog", "AXSystemDialog") and ax.attr(w, "AXMain") is False:
                f = ax.frame(w)
                if f and f[2] < 120 and f[3] < 40:
                    continue
                out.append(f)
        return out
    except Exception:
        return None


def _same_frame(a, b, tol=2):
    return bool(a and b) and all(abs(p - q) <= tol for p, q in zip(a, b))


def _under(el, f, depth=40):
    """控件 el 顺着 AXParent 往上,先碰到的表单 / 窗口是不是框 f 那个(表单在窗口之前碰到;对话框本身就是窗口)。"""
    for _ in range(depth):
        if el is None:
            return False
        role = ax.attr(el, "AXRole") or ""
        if role in ("AXSheet", "AXWindow"):
            if _same_frame(ax.frame(el), f):
                return True
            if role == "AXWindow":
                return False
        el = ax.attr(el, "AXParent")
    return False


def _in_modal(app, pts, e=None):
    """11-16 用户定:AI 明确指着对话框 / 表单里面的位置 → 借鼠标照常点(原来一律被「弹着对话框」拦住)。
    11-16 复查后收紧,下面全满足才算:
      ① 所有点落在**同一个**弹窗框里(往里收 1 点;同一个框里两点连线不出框,拖动中间不会划过主窗口);
      ② 这个弹窗 AI 上次 see 时就已经在了(_seen_modals 记着同样的框)—— 后来冒出来的意外弹窗照旧拦;
      ③ 每个点上最上面的控件确实属于这个弹窗(同 App 别的窗口叠在框上面就不算);
      ④ 按编号点的,那个控件本身也在这个弹窗里(不是被弹窗挡住的主窗口控件)。
    读不到任何一样都不算(照旧拦)。"""
    try:
        pid = _pid(app)
        frames = [f for f in (_modal_frames(pid) or []) if f]
    except Exception:
        return False
    if not frames or not pts:
        return False

    def inside(p, f):
        return f[0] + 1 <= p[0] <= f[0] + f[2] - 1 and f[1] + 1 <= p[1] <= f[1] + f[3] - 1
    box = next((f for f in frames if all(inside(p, f) for p in pts)), None)
    if box is None or not any(_same_frame(box, g) for g in (_seen_modals.get(app) or [])):
        return False
    try:
        app_el = ax.app_element(int(pid))[0]
        if not all(_under(ax.element_at(app_el, p[0], p[1]), box) for p in pts):
            return False
        if e is not None and not _under(e.get("el"), box):
            return False
    except Exception:
        return False
    return True


def _has_modal(app):
    """目标现在弹着表单 / 对话框没有(同 input_guard.modal_state;读不到当没有,交给老规矩)。"""
    from seeu_lib import input_guard as ig
    try:
        return bool(ig.modal_state(_pid(app))[0])
    except Exception:
        return False


def _modal_recheck(app, pts, e=None):
    """真点下去之前再核一次(让路可能等了几秒,弹窗换了):不在了就按「弹着对话框」拦。"""
    from seeu_lib import input_guard as ig
    if not _in_modal(app, pts, e):
        raise ig.GuardBlocked("modal_sheet", "目标应用的弹窗变了(跟 see 时不一样),不点,先 see 一次", pid=None)


def _real_mouse(app, fn, modal=False):
    """真鼠标兜底:拿桌面锁 → 让路检查 → 激活窗口 → 做 → 还原前台和鼠标 → 放锁。
    modal=True:fn 里会查「目标弹着对话框 / 表单就不点」(ig.guarded)的,激活前先查一遍。
    modal 也可以是返回 (要点的屏幕点列表, 按编号点的控件或 None) 的函数:AI 明确指着看过的弹窗里面(_in_modal)就不拦
    (fn 里自己也要按同样办法放开)。"""
    from seeu_lib import desktop_lock as dl, input_guard as ig

    def act():
        if _other_desktop(app):          # 11-15 C-2.0:激活会把用户切到那个桌面 → 不借(_ladder 收成 refused)
            raise ax.AXRefused(OTHER_DESKTOP)
        # 10-30:先让路再激活。原来激活后才在 fn 里查用户在不在用 → 用户在用就停手,
        # 但前台已经被抢、还原又因"用户在用"跳过,目标 App 一直挂在前台(Chrome 实测抢了用户桌面)
        ig.yield_to_user()
        if modal:
            # 11-14:弹窗 / 表单这条规则原来只在激活之后(fn 里的 ig.guarded)才查 → 注定被拦的也先把目标拉到前台
            # (Parallels 设置的表单里点下拉框:没点,但窗口被激活变亮)。它按进程号读,不用在前台 → 提到激活前。
            # 读不到进程号就留给后面那次查;被拦抛的错跟后面那次一样。
            try:
                pid = _pid(app)
            except Exception:
                pid = None
            if pid:
                try:
                    getattr(ig, "check_no_modal", lambda _p: None)(pid)
                except ig.GuardBlocked:
                    # 先按老规矩查(没弹窗时不多读一遍);弹着的话,AI 明确指着弹窗里面(_in_modal)才放过
                    if not (callable(modal) and _in_modal(app, *modal())):
                        raise
        try:            # 11-17:占着的是别的 SeeU 任务就排队等它借完(最多 15 秒);别的项目占着照协议直接拒
            from seeu import sched as _sc
            r = _sc.real_wait(lambda: dl.acquire(PROJECT, f"SeeU 真鼠标:{app}", attended=True),
                              lambda h: bool(h) and str(h.get("label", "")).startswith("SeeU 真鼠标"))
        except ImportError:
            r = dl.acquire(PROJECT, f"SeeU 真鼠标:{app}", attended=True)
        if not r["ok"]:
            msg = "桌面锁被占:" + dl.describe(r["held"]) + (f"(排队等了 {r['waited']:.0f} 秒还没轮到)" if r.get("waited") else "")
            if str((r.get("held") or {}).get("label", "")).startswith("SeeU 真鼠标"):
                raise ax.AXRetry(msg, "busy", "busy")     # 复查 11-17(C-2.7):别的 SeeU 任务借着 = 暂时忙,稍后再试(不是拒绝)
            raise ax.AXRefused(msg)
        _rebase()                         # 11-17 C-2.8:让路、排队都等完了,真动手前重拍「动作前」
        try:
            _halo("real", 5)              # 借用系统鼠标期间亮光圈(按档位);结束后 0.8 秒淡出
            with ig.FrontState(avoid_owner=ax.local_name(bg.split_target(app)[0]) if _is_canvas(app) else None):
                _activate(app)
                fn(ig)
        finally:
            _halo("real", 0.8)
            if not r.get("reentrant"):    # 11-23 C-3.9 整体复查:调用方(同一个进程)自己先拿着桌面锁时,这把锁是它的,SeeU 点完不能替它放掉
                dl.release()
    return act


# ---------------------------------------------------------------- 代理光标(纯显示)
# 10-14 用户要:跟别家 Computer Use 一样,动手时在那个位置画个光标给人看;位置被别的窗口挡住、或窗口不在当前桌面,就不画。
# 用 seeu_lib.cursor_overlay(纯显示,不碰真鼠标)。任何异常都吞掉,绝不影响动作本身。不想要光标设 SEEU_NO_CURSOR=1。
# 用名牌 + 颜色区分(用户 10-14 定):后台模式 = 「SeeU」紫色;让路模式(借用系统鼠标)= 署名(设置.json,没写就 SeeU)亮橙(10-15 改,原蓝色);
# 用户自己的鼠标 = 系统黑色指针、无名牌。
from seeu.where import settings_file as _sf
_SETTINGS = _sf()  # 11-22 C-3.7:插件版存用户文件夹(seeu/where.py)


def _hex(v, default):
    try:
        v = v.lstrip("#")
        return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return default


def _settings():
    import json
    try:
        with open(_SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _default_sign():
    """没写署名时用这台 Mac 的系统账号名(10-31 用户定,开源后别人装了显示他自己):全名 → 短名 → 都拿不到才用默认名。"""
    n = ""
    try:
        from Foundation import NSFullUserName, NSUserName
        n = str(NSFullUserName() or "").strip() or str(NSUserName() or "").strip()
    except Exception:
        pass
    n = n or os.environ.get("USER", "").strip()
    return "@" + n.lstrip("@") if n else "@SeeU"


def _cursor_style(mode):
    """mode = bg(后台)| real(让路模式)→ (名牌, 颜色)。每次现读设置文件,改了立刻生效。"""
    st = _settings()
    if mode == "real":
        return str(st.get("署名") or "").strip() or _default_sign(), _hex(st.get("让路模式颜色", ""), (1.0, 0.624, 0.039))
    return "SeeU", _hex(st.get("后台模式颜色", ""), (0.50, 0.47, 0.87))


SEE_THROUGH = ("Screenshot", "screencaptureui")
_HALO_ALIAS = {"关": "off", "off": "off", "仅让路模式": "real", "real": "real", "全部": "all", "all": "all"}


_ON = ("开", "on", "1", "true", "yes")
_OFF = ("关", "off", "0", "false", "no")
_ASK = ("问我", "ask")
ALLOW_ONCE = ("once", "仅此一次")
ALLOW_AUTO = ("auto", "自动使用")
_SESSION_AUTO = [False]       # 「问我」时用户选了「自动使用」:本进程(这一轮任务 / 这个 MCP 服务)不再问
NO_REAL_NOTE = ("后台做了但画面没变;按设置没借用户的鼠标键盘(设置.json「借用鼠标」= 关)。"
                "先 see 看是不是其实已经生效(点输入框常常画面不变);真没生效就换个目标或写法再试一次,还不行停手告诉用户卡在哪")
ASK_NOTE = ("这一步后台做不到,要借用户的鼠标键盘几秒(设置.json「借用鼠标」= 问我)。"
            "请问用户三选一:仅此一次 / 自动使用(这一轮都不再问)/ 拒绝;选前两个就带上 allow_real=once 或 auto 再做一次这一步,拒绝就停手告诉用户卡在哪")


def real_mode():
    """借用鼠标的档位:on(默认)| off | ask。环境变量 SEEU_REAL_MOUSE 优先(1/0/ask),否则设置.json「借用鼠标」= 开 / 关 / 问我。
    11-01 用户定:默认开(关着无人值守容易卡住);上午 Trae 那种「点输入框画面不变被当没效果」由 tap 里先查焦点挡住,不白借。"""
    v = os.environ.get("SEEU_REAL_MOUSE")
    if v is None:
        v = _settings().get("借用鼠标") or "开"
    v = str(v).strip().lower()
    if v in _OFF:
        return "off"
    if v in _ASK:
        return "ask"
    return "on"


def real_allowed(allow=None):
    """现在能不能借真鼠标/真键盘。allow = 用户在「问我」时的回答:once(仅此一次)/ auto(自动使用,本轮不再问)。"""
    a = str(allow or "").strip().lower()
    if a in ALLOW_AUTO:
        _SESSION_AUTO[0] = True
    if a in ALLOW_ONCE or a in ALLOW_AUTO:
        return True
    m = real_mode()
    return m == "on" or (m == "ask" and _SESSION_AUTO[0])


SETTABLE = {"借用鼠标": {"开": "开", "on": "开", "问我": "问我", "ask": "问我", "关": "关", "off": "关"}}
SET_ALIAS = {"borrow-mouse": "借用鼠标"}     # 11-02:英文文档写 set borrow-mouse on|ask|off,设置.json 里照旧存中文
EN_VAL = {"开": "on", "问我": "ask", "关": "off"}


def settings_cmd(args):
    """python3 -m seeu 设置 [借用鼠标 开|问我|关]:不带参数列出现在的值;带了就改 设置.json(只认 SETTABLE 里的键和值)。"""
    from seeu.i18n import lang
    en = lang() == "en"
    if not args:
        v = _settings().get('借用鼠标') or '开'
        print(f"borrow-mouse: {EN_VAL[v]}  (on / ask / off)" if en else f"借用鼠标: {v}  (开 = on / 问我 = ask / 关 = off)")
        return 0
    args = [SET_ALIAS.get(args[0].lower(), args[0])] + list(args[1:])
    if len(args) != 2 or args[0] not in SETTABLE or args[1].lower() not in SETTABLE[args[0]]:
        print("Usage: python3 -m seeu set borrow-mouse on|ask|off" if en else "用法:python3 -m seeu 设置 借用鼠标 开|问我|关")
        return 2
    import json
    from collections import OrderedDict
    with open(_SETTINGS, encoding="utf-8") as f:
        d = json.load(f, object_pairs_hook=OrderedDict)
    d[args[0]] = SETTABLE[args[0]][args[1].lower()]
    tmp = f"{_SETTINGS}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, _SETTINGS)
    print(f"Set: borrow-mouse = {EN_VAL[d[args[0]]]}" if en else "已改:借用鼠标 = " + d[args[0]])
    return 0


def _ask_user(r, what, app=None):
    """「问我」档:不借,结果改成 ask_user 交给 AI 去问;屏幕上弹提示条提醒用户回对话里选。
    目标在别的桌面:借了也会把用户切走 → 直接 refused,不先问(11-15 C-2.0,照 Windows)。"""
    if app and _desk_refused(r, app):
        return r
    r.update(outcome="ask_user", reason=ASK_NOTE)
    try:
        from seeu_lib import cursor_overlay as co
        from seeu.i18n import T
        co.toast(T("ask.title"), T("ask.body", what=T(what)), 12)
    except Exception:
        pass
    return r


def _focus_at(app, x, y, pad=6):
    """点完画面没变时查一下:焦点是不是已经进了点的那个输入框(点输入框常常画面不变,11-01 Trae 实测被当成没效果)。"""
    if _is_canvas(app):
        return False
    try:
        el, _ = ax.app_element(app)
        f = ax.attr(el, "AXFocusedUIElement")
        if f is None or (ax.attr(f, "AXRole") or "") not in ax.TEXT_ROLES:
            return False
        fr = ax.frame(f)
        return bool(fr) and fr[0] - pad <= x <= fr[0] + fr[2] + pad and fr[1] - pad <= y <= fr[1] + fr[3] + pad
    except Exception:
        return False


def _halo_policy():
    """被CU提示(屏幕四周光圈)档位:环境变量 SEEU_HALO 优先(接入方自己定),否则设置.json,默认仅让路模式。"""
    v = os.environ.get("SEEU_HALO") or _settings().get("被CU提示") or "仅让路模式"
    return _HALO_ALIAS.get(str(v).strip(), "real")


def _halo(mode, secs=2.5):
    """按档位亮光圈;动作持续就反复调来续时。异常吞掉。
    10-15:悬浮窗上的「抢占/被控」开关(seeu_lib.watch_window.halo_allowed)设过就以它为准,没设过才看环境变量/设置文件。"""
    try:
        from seeu_lib import watch_window as ww
        ok = getattr(ww, "halo_allowed", lambda m: None)(mode)
        if ok is None:
            pol = _halo_policy()
            ok = not (pol == "off" or (pol == "real" and mode != "real"))
        if not ok:
            return
        from seeu_lib import cursor_overlay as co
        _cursor_serve()
        co.glow(_cursor_style(mode)[1], secs)
    except Exception:
        pass


_cursor_up = [False]


def _cursor_serve():
    import socket
    import subprocess
    from seeu_lib import cursor_overlay as co
    if _cursor_up[0] and time.time() - _cursor_up[0] < 20:     # 复查 11-17:原来一个进程只拉起一次,显示进程退了以后再也不画
        return
    _cursor_up[0] = time.time()
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", co.PORT))   # 绑得上 = 没人在监听 → 拉起(名牌/颜色每条消息自带)
        probe.close()
        subprocess.Popen(["/usr/bin/python3", co.__file__, "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(0.8)
    except OSError:
        probe.close()


def _cursor_visible(app, x, y):
    """(x,y) 这一点上用户看得见 app 的窗口吗:在屏幕可用区内,且最上层窗口就是它(不在当前桌面时屏上列表里没它)。"""
    from seeu_lib import input_guard as ig
    if not any(ig._inside(x, y, r) for r in ig._screens_visible_rects()):
        return False
    # 截图工具(⌘⇧4/5)会挂一个全屏、报不透明的透明层,只影响"画不画",不算挡住(10-14 紫色光标因它没出来)
    top = ig.window_at(x, y, skip=SEE_THROUGH)
    owner, title = bg.split_target(app)
    return bool(top and ax.same_app(top["owner"], owner) and (title is None or (top.get("name") or "") == title))


def _watch(app, kind=None, x=None, y=None):
    """监看悬浮窗(seeu_lib.watch_window,10-15 用户定):SeeU 动手时自动出现,停手 60 秒收起;动作位置画在小窗里。
    设置.json「监看小窗」= 关 / 环境变量 SEEU_NO_WATCH=1 就不开。不管窗口在不在当前桌面都显示(就是为了这个)。异常吞掉。"""
    if os.environ.get("SEEU_NO_WATCH") or str(_settings().get("监看小窗", "开")).strip() in ("关", "off"):
        return
    try:
        from seeu_lib import watch_window as ww
        g = bg.main_window(app)
        if not g:
            return
        mode = "real" if kind is not None else "bg"     # 只有真鼠标那条路会带 kind 进来(见 _cursor)
        try:
            ww.show(g["id"], mode)
        except TypeError:                               # 长进程里是旧版 watch_window
            ww.show(g["id"])
        try:                                            # 11-17:灵动岛那行的圆点用这个任务的光标色
            from seeu import sched as _sc
            getattr(ww, "tint", lambda *a, **k: None)(_sc.cursor_hex(_cursor_style("bg")[1]))
        except Exception:
            pass
        try:
            bg._W["mode"] = mode                          # 下一次后台动作立刻切回紫色
        except Exception:
            pass
        if kind == "click" and x is not None and g["w"] and g["h"]:
            ww.mark("click", (x - g["x"]) / g["w"], (y - g["y"]) / g["h"])
    except Exception:
        pass


def _cursor(app, kind, x, y, mode="bg", force=False):
    """kind = click | move;mode = bg(后台)| real(系统鼠标)。看得见就把光标送过去并等它滑到位(~0.3s,让波纹跟动作对上);
    看不见就藏。force:系统鼠标模式已经把目标窗口切到前台了,不用再判遮挡。"""
    _watch(app, kind if mode == "real" else None, x, y)   # 后台那条路 bgclick.click 自己会画,这里只补真鼠标的
    if os.environ.get("SEEU_NO_CURSOR"):
        return
    try:
        from seeu_lib import cursor_overlay as co
        _halo(mode)
        if force or _cursor_visible(app, x, y):
            _cursor_serve()
            label, color = _cursor_style(mode)
            owner = ax.local_name(bg.split_target(app)[0])   # 11-23:显示进程按系统显示名比对(中文系统「iPhone镜像」)
            # 11-17 C-2.5:一个任务一只光标(key = 任务显示名);后台模式名牌按规则(只剩一只写 SeeU,多只写任务名)
            from seeu import sched as _sc
            key = _sc.cursor_key()
            if mode != "real":
                label, color = key, _sc.cursor_color(color)
            import inspect
            if "key" in inspect.signature(co.show).parameters:
                t = co.show(kind, x, y, label, color, owner=owner, key=key, auto=mode != "real")
            else:                   # 长进程里是旧版 cursor_overlay(没有 key)
                t = co.show(kind, x, y, label, color, owner=owner)   # 显示进程自己每 0.2s 查遮挡,两次动作之间被挡也会藏
            # C-1.3:光标按距离走 0.22~0.65 秒,show 返回要等多久;长进程里是旧版就返回 None,按老的 MOVE_S
            time.sleep(min(1.0, t) if isinstance(t, (int, float)) else co.MOVE_S)
        else:
            try:        # 11-17:只藏自己这只(原来 hide 一藏全藏,会把别的任务的光标也藏掉)
                from seeu import sched as _sc
                getattr(co, "hide", lambda k=None: co.send("hide"))(_sc.cursor_key())
            except Exception:
                co.send("hide")
    except Exception:
        pass


def _shown(app, kind, rx, ry, fn):
    """按窗口当时位置算出屏幕点 → 画光标 → 做 fn(x, y)。"""
    x, y = _abs(app, rx, ry)
    _cursor(app, kind, x, y)
    return fn(x, y)


# ---------------------------------------------------------------- 动作

def tap(app, target, real=True, allow=None):
    from seeu import web
    app = web.canon(app)
    if web.is_browser(app) or web.is_cdp(app):     # 浏览器 / SeeU 专用那份网页壳 App:按网页里的编号/名字点,见 seeu/web
        return web.tap(app, target)
    x, y, e = _resolve(app, target)
    if e is None:                 # 11-15 C-2.0:按截图位置点(不是控件):Chrome / Electron 窗口看不见时截图是旧的,不点
        bad = _stale_pixel(app)
        if bad:
            return bad
    blocked = _tap_secret_block(app, e, x, y)      # 11-07:点「粘贴」按钮 / 右键菜单里的粘贴项 = 粘贴,光标在密码框里就不点
    if blocked:
        return blocked
    blocked = _tap_danger_block(e, app, x, y)       # 11-23 C-3.9:叫「清倒废纸篓 / 关机 / 注销」的按钮、菜单项也不点(原来只有 menu() 查)
    if blocked:
        return blocked
    rx, ry = _rel(app, x, y)   # 窗口被挪了也点得准:每条路动手前按窗口当时位置重算(10-14 跨桌面实测窗口被挪过)
    steps = []
    if e is not None and ("AXPress" in e["actions"] or "AXPick" in e["actions"]):
        steps.append(("辅助功能按下", lambda: _press_seen(app, e)))
    steps.append(("后台点击", lambda: _shown(app, "click", rx, ry, lambda x, y: bg.tap(app, x, y))))
    if _is_canvas(app) and isinstance(target, str) and not target.isdigit():
        # 镜像主屏的 App 名字点不进,要点字上方的图标(10-14 实测「Settings」:点字没反应,上移 30 点就进了)
        steps.append(("后台点击(字上方图标)",
                      lambda: _shown(app, "click", rx, ry - ICON_ABOVE_LABEL, lambda x, y: bg.tap(app, x, y))))
    factory = _fine_expect(app, (rx, ry))     # 镜像、模拟器读不到控件,光标、高亮这种小变化靠看点击处附近
    r = _ladder(app, steps, expect_factory=factory)
    r["xy"] = (round(x), round(y))
    # 11-06 体检:后台那几条路全部「出错」(私有接口失效时 bgclick 抛错)原来直接报 failed,不借真鼠标,
    # 跟「私有接口只当加速层、失效有退路」不符 → 出错跟没生效一样往下走。
    #   「那个位置没有窗口」(按编号点了滚出窗口的控件)、隐身浏览器被叫出来,不算接口失效:借真鼠标也点不到,只会白抢一次前台。
    broke = (r["outcome"] == "failed" and r["tried"] and all(str(t[1]).startswith("error:") for t in r["tried"])
             and not any(k in str(t[1]) for t in r["tried"] for k in ("没有窗口", "叫出来")))
    if r["outcome"] != "ineffective" and not broke:
        return r
    if not broke and _focus_at(app, x, y):
        r.update(outcome="delivered", note="点的是输入框:画面没变,但光标已经进去了")
        return r
    if not real:
        return r
    if real_allowed(allow):
        def real_tap(ig):
            ax_, ay_ = _abs(app, rx, ry)
            _cursor(app, "click", ax_, ay_, mode="real", force=True)
            from seeu import safety
            safety.check_point(ax_, ay_)      # 10-30:位置盖着 SeeU 自己的浮标(没让路)就不点
            # 11-16:点的位置就在 AI 看过的对话框 / 表单里面 = AI 明确要点它 → 不按「弹着对话框」拦(_in_modal 的四条);
            #   别的照旧拦。放过的,点下去前再核一次(让路可能等了几秒)
            inside = _has_modal(app) and _in_modal(app, [(ax_, ay_)], e)

            def do():
                if inside:
                    _modal_recheck(app, [(ax_, ay_)], e)
                    _seen_modals.pop(app, None)     # 往弹窗里点过一次就作废:同样大小的下一个弹窗要 AI 再看一次才算看过
                mi.qtap(ax_, ay_)
            ig.guarded(ax_, ay_, ax.local_name(bg.split_target(app)[0]), do=do, check_modal=not inside)
        r2 = _ladder(app, [("真鼠标", _real_mouse(app, real_tap, modal=lambda: ([_abs(app, rx, ry)], e)))],
                     expect_factory=factory)
        r2["tried"] = r["tried"] + r2["tried"]
        r2["xy"] = r["xy"]
        return r2
    if real_mode() == "ask":
        return _ask_user(r, "ask.tap", app)
    r["reason"] = NO_REAL_NOTE
    return r


def long_press(app, target, ms=1000):
    from seeu import web
    app = web.canon(app)
    if web.is_browser(app):
        # 11-06 C-1.1.3(二次复查第 4 条):浏览器上的长按原来直接走下面的原生路线,按屏幕位置能对名单外的页面
        # (含 SeeU 专用的隐身 Chrome)发后台点击,也点得到工具栏上的插件图标(「允许这个网站」= AI 替自己批准)。
        # 网页层的点击本来就只收编号、不收坐标(tap 给坐标会报找不到),长按跟它对齐:浏览器里一律不做。
        # 按编号长按浏览器原来是 KeyError(网页清单里没有屏幕位置),现在也是这句。
        return dict(outcome="refused", route=None, tried=[], png=None,
                    reason="浏览器里不能长按(长按是按屏幕位置点,会绕开网页的允许名单);点网页上的东西用 tap,按编号")
    x, y, e = _resolve(app, target)
    if e is None:                 # 11-15 C-2.0:同 tap
        bad = _stale_pixel(app)
        if bad:
            return bad
    blocked = _tap_secret_block(app, e, x, y)      # 11-07 复查:长按 50 毫秒就是一次点击,跟 tap 查同一条
    if blocked:
        return blocked
    blocked = _tap_danger_block(e, app, x, y)       # 11-23 C-3.9:同 tap
    if blocked:
        return blocked
    rx, ry = _rel(app, x, y)
    return _ladder(app, [("后台长按", lambda: _shown(app, "click", rx, ry,
                                                  lambda x, y: bg.long_press(app, x, y, ms=ms)))])


def _center(app):
    g = _geo(app)
    return g["x"] + g["w"] / 2, g["y"] + g["h"] * 0.55


def scroll(app, dy=0, dx=0, at=None, safe=None):
    """dy 负 = 往下翻;dx 负 = 往左翻页(镜像主屏)。🔴 镜像主屏上竖向往下滚会打开 Spotlight。
    safe=(x,y)(屏幕点,同 at 的坐标):点过之后第一次滚会先补一下小拖动,默认落在滚动点上(对列表 = 一次点击,可能误点任务行);
    给一个面板里没有可点东西的空白点,补拖动就落那里(10-24 实测:弹出面板里误点了任务行)。"""
    rx, ry = _rel(app, *(at if at else _center(app)))
    return _ladder(app, [("后台滚动", lambda: _shown(app, "move", rx, ry, lambda x, y: bg.scroll(app, x, y, dy, dx, prime_at=safe)))])


def type(app, text, enter=False, fallback=True, allow=None):
    """先后台打字;画面没变就走 SeeU 兜底:拿桌面锁 → 让路 → 把目标切到前台打 → 还原前台。
    fallback=False 只走后台(调用方自己有退路、不想被抢前台时用)。都不行报 ineffective,交给项目自己的办法。
    🔴 后台那次如果其实打进去了但画面没变(核实不到),兜底会再打一遍,看到重复字就是这种情况。"""
    from seeu import web as _web
    app = _web.canon(app)
    from seeu_lib import input_guard as ig
    from seeu import safety
    pid = ig.secure_input_pid()
    if pid:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=f"系统处于密码输入状态(pid {pid})")
    try:
        safety.check_text(text)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    h = _cdp_handle(app)
    # 11-07 第二轮复查:有 SeeU 专用那份(调试端口)在跑时不走辅助功能这一查 —— 按名字找到的多半是用户自己那份同名浏览器,
    # 查的不是要打字的那个进程(还会给用户那份开网页结构开关、白等);专用那份由 cdp._chrome_guard 把关。
    kind = None if h else _focus_secret(app)
    if kind:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=f"光标在{kind}里,SeeU 不往里打字(这一步请你自己来)")
    if h:                               # C-1.0:SeeU 专用那份(调试端口)藏着打,回车也走它
        from seeu import cdp
        r = cdp.type(h, text)
        # 这条路是例外:cdp.type 直接把字交给页面、恒返回 unverified,所以 unverified 也按回车(下面普通那条路只在 delivered 时按)
        if enter and r["outcome"] in ("delivered", "unverified"):
            time.sleep(0.3)
            r["enter"] = "sent" if cdp.key(h, "enter")["outcome"] in ("delivered", "unverified") else "failed"
        return r
    _watch(app)
    tail = _tail(text)
    factory = _text_changed_factory(app)
    # 🔴 回车一律单独按:先只打字、核实打进去了,再按一次回车。
    #   10-15 C-1.2 Codex:打字+回车一起核实,发出后框空了 → 判没生效 → 兜底再打 → 重复发送。
    #   C-1.3 Codex:空格后面的字全丢了,截图有变化就报成功,回车照按 → 差点把半句话发出去。
    from seeu import web
    browser = web.is_browser(app)
    wcheck = _focus_window_check(app)

    def _bg_type():
        with _TypeLock(app):
            if wcheck:          # 老的长进程可能 import 了没有 check 参数的 bgkey,没有就照旧打
                try:
                    return bk.type_to(app, text, enter=False, check=wcheck)
                except TypeError as ex:
                    if "check" not in str(ex):
                        raise
            return bk.type_to(app, text, enter=False)
    steps = [("后台打字", _bg_type)]
    # 10-30:浏览器不走前台兜底——藏着/在后面的窗口截图看不出字变,后台其实打进去了也判"没变",
    # 兜底就把浏览器拉到前台(实测抢了用户桌面)、还会叠出重复字。网页填表按编号用 web.type 才核实得了。
    if fallback and not real_allowed(allow):
        fallback = None                  # None = 本来要兜底,按设置没借(结果里写原因 / 「问我」档交给 AI 去问)
    if fallback and not browser and bg.split_target(app)[0] not in NO_FRONT_TYPING:
        steps.append(("前台打字", _real_mouse(app, lambda ig: _front_type(app, ig, text, False))))
    before_txt = _focused_text(app)
    _TYPED_WIN.pop(app, None)
    r = _ladder(app, steps, min_change=0.001, expect_factory=factory)
    if browser and r["outcome"] == "ineffective":
        r.update(outcome="unverified", reason="后台打了,但浏览器画面核实不到(可能已经打进去)。"
                 "先 see 看框里的字;网页填表用 seeu.web.type(App, 编号, 文字) 才能核实,别重打")
    elif fallback is None and r["outcome"] == "ineffective":
        if real_mode() == "ask":
            return _ask_user(r, "ask.type", app)
        r["reason"] = NO_REAL_NOTE + "(打字落空多半是输入框没聚焦:先点一下输入框再打)"
    # "动了"不等于打全了:读得到框里文字的直接看,读不到的(网页做的框、镜像画面)截图识字,找最后几个字;
    # 找不到 = 只打进一部分 → 报 partial、不按回车、也不兜底重打(重打会叠出重复字)
    if r["outcome"] == "delivered" and tail:
        if factory is not None:
            seen = tail in "".join(c for c in (_focused_text(app) or "") if c.isalnum())
        else:
            seen = _ocr_has_tail(app, text)
        if seen is False:
            r.update(outcome="partial", reason=f"画面变了,但没认到最后几个字「{tail}」,可能只打进一部分;没按回车")
            return r
    # 11-06 体检:截不到图(App 藏着)= unverified,但读得到输入框文字的可以直接核对结尾 → 对上了算 delivered
    if r["outcome"] == "unverified" and tail and not browser:
        txt = _focused_text(app)        # 要「跟打字前不一样」而且结尾对得上(框里原本就有同样结尾的字不算)
        if txt is not None and txt != before_txt and tail in "".join(c for c in txt if c.isalnum()):
            r.update(outcome="delivered", note="截不到图,按输入框里读到的文字核实")
    # 🔴 回车只在核实打进去(delivered)时按。11-06 体检:原来 unverified 也按,浏览器核实不到、App 藏着截不到图时
    # 可能把半句话发出去,跟上面「核实打进去了再按回车」的规矩相反。
    if enter and r["outcome"] == "delivered":
        from seeu_lib import input_guard as ig
        time.sleep(0.3)
        rec = _TYPED_WIN.get(app)
        pid = rec[0] if rec else _pid(app)      # 打字时的那个进程(打完标题可能变了,再按名字找会找错)
        why = _enter_block(app, pid)
        if why:
            r["enter"] = "skipped"
            r["reason"] = ((r.get("reason") or "") + ";字打进去了,但没按回车:" + why).lstrip(";")
            return r
        try:
            bk.press(pid, "return")             # 投给目标进程,不抢前台;只按这一次,不核实不重试
        finally:
            ig.note_injected()
        r["enter"] = "sent"
    elif enter and r["outcome"] == "unverified":
        r["enter"] = "skipped"
        r["reason"] = ((r.get("reason") or "") + ";没核实到字打进去,所以没按回车(先 see 看一眼,字在就单独按一次回车)").lstrip(";")
    return r


def _tail(text, n=4):
    """核实用的"最后几个字":只取汉字/字母/数字(标点空格识字常认错),最多 n 个。"""
    keep = [c for c in str(text) if c.isalnum()]
    return "".join(keep[-n:])


def _edit_tail(body, have):
    """body 跟 have 的某段「结尾贴着 have 末尾」的文字最少差几个字(多、少、错各算 1)。"""
    row = []        # 反过来比,开头不限:每多比一个字记一次「整个 body 比完差几个」
    rb, rh = body[::-1], have[::-1]
    prev = list(range(len(rb) + 1))
    for c in rh:
        cur = [0]
        for j, d in enumerate(rb, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (c != d)))
        prev = cur
        row.append(cur[-1])
    return min([len(rb)] + row)


def _tail_seen(text, got, n=12):
    """画面认到的字 got 里有没有 text 的结尾。认字常认错、多认或漏认个别字(11-06 实测 Indiana → Indliana),
    前面允许差 1/5;但最后 3 个字必须一字不差,这样漏打的结尾不会被放过(打一半不能按回车)。"""
    want = "".join(c.lower() for c in str(text) if c.isalnum())[-n:]
    have = "".join(c.lower() for c in str(got) if c.isalnum())
    if len(want) < 5:
        return want in have
    body, end = want[:-3], want[-3:]
    i = have.find(end)
    while i >= 0:
        if _edit_tail(body, have[max(0, i - len(body) - 3):i]) <= len(want) // 5:
            return True
        i = have.find(end, i + 1)
    return False


def _ocr_has_tail(app, text):
    """截图识字,看 text 的结尾在不在画面上。认不了(识字出错)返回 None = 不确定,按原来的结果走。"""
    try:
        from seeu_lib import ocr
        png = shoot(app)
        got = "".join(str(it[0] if isinstance(it, (list, tuple)) else it.get("text", "")) for it in ocr.ocr(png))
        return _tail_seen(text, got)
    except (Exception, SystemExit):   # seeu_lib.ocr 认不出会 SystemExit
        return None


_AX_WEB_ON = {}           # 进程号 → 上次替它打开「网页结构」开关的时间
AX_WEB_WAIT_S = 4.0       # 开关打开后网页结构要一两秒才出来(11-07 实测 Chrome 约 2 秒;页面重、机器忙会更久),最多等这么久
AX_WEB_RETRY_S = 45.0     # 开关会被关回去(浏览器一阵没人读就自己关、窗口管理工具也会改):又读不到时隔这么久再开一次
_GENERIC_FOCUS = {None, "AXWebArea", "AXGroup", "AXScrollArea", "AXWindow", "AXApplication", "AXUnknown"}


def _is_chromium_browser(pid):
    """Chromium 内核的浏览器(Chrome、Edge、Brave、Arc…):网页里的控件默认不交给辅助功能,要先打开开关才读得到。
    只认浏览器。Electron 做的 App 不替它开(11-07 第二轮复查:开了以后 VS Code 这类会当成读屏软件接入、可能切模式或弹提示,
    打字核实的路也会跟着变)—— 那里跟镜像、模拟器一样认不出是什么框,靠 AI 遵守。"""
    try:
        from AppKit import NSRunningApplication
        from seeu import web
        a = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        n = web._by_bundle(str(a.bundleIdentifier() or "")) if a is not None else None
        return bool(n) and n not in web.OTHERS            # Safari、Firefox 这几个不用开关
    except Exception:
        return False


def _focus_vague(f):
    """焦点没读到具体控件:空的,或只是外壳。外壳是网页区而且里面已经有内容 = 网页结构已经交出来了,只是光标不在哪个框里,不算。"""
    if f is None:
        return True
    role = ax.attr(f, "AXRole")
    if role == "AXWebArea" and (ax.attr(f, "AXChildren") or []):
        return False
    return role in _GENERIC_FOCUS


def _focus_secret(app, pid=None):
    """目标 App 当前焦点是不是密码框 / 新密码框 / 验证码框(是 → 返回叫法,不是或读不到 → None)。
    11-06 体检:原来打字只查系统的「密码输入状态」,验证码框是普通文本框、不触发那个状态,
    后台点进去之后照打。镜像、模拟器读不到控件,查不了。
    11-07 复查(真机实测):Chrome 在后台时焦点控件读出来是空的,网页里的密码框 / 验证码框等于没查 ——
    要先写「网页结构」那两个开关(跟 web._ax_app 同一招),约 2 秒后才读得到。读得到就不等;又读不到时隔 AX_WEB_RETRY_S 再开一次。"""
    if _is_canvas(app):
        return None
    try:
        el, pid = ax.app_element(pid or _pid(app))
        f = ax.attr(el, "AXFocusedUIElement")
        if _focus_vague(f) and time.time() - _AX_WEB_ON.get(pid, 0) > AX_WEB_RETRY_S and _is_chromium_browser(pid):
            _AX_WEB_ON[pid] = time.time()
            for k in ("AXManualAccessibility", "AXEnhancedUserInterface"):
                try:
                    ax.set_attr(el, k, True)              # 都会报「不支持」,但会生效(10-20 实测)
                except Exception:
                    pass
            t0 = time.time()
            while time.time() - t0 < AX_WEB_WAIT_S:
                time.sleep(0.25)
                f = ax.attr(el, "AXFocusedUIElement")
                if not _focus_vague(f):
                    break
        if f is None:
            return None
        return ax.secret_kind(ax.attr(f, "AXRole"), ax.attr(f, "AXSubrole"), ax.attr(f, "AXTitle"),
                              ax.attr(f, "AXDescription"), ax.attr(f, "AXPlaceholderValue"), ax.attr(f, "AXHelp"))
    except Exception:
        return None


WRONG_WINDOW = ("输入框不在「{want}」这个窗口里(现在焦点在「{got}」):可能刚才那一下没点上,或者别的任务把焦点点走了。"
                "SeeU 没打,免得写进别的窗口;先点一下「{want}」里的输入框再打")
WRONG_WINDOW_KEY = ("键盘焦点不在「{want}」这个窗口里(现在在「{got}」),SeeU 没按,免得按到别的窗口;"
                    "先点一下「{want}」里要按键的地方再按;要按的是对话框的话,先 see 确认是它,再只写 App 名按")
KEY_NO_REPLY = ("按键前读不到「{want}」所在 App 的窗口(App 可能正卡着),认不出键会进哪个窗口,SeeU 没按;等几秒先 see 看一眼再试;一直这样就只写 App 名按")
KEY_REPLY_S = 1.5          # 读一次窗口超过这么久还什么都没有 = App 卡住没回话(单次上限 ax.MSG_TIMEOUT 2 秒)
ENTER_MOVED = "打完字以后键盘焦点换到别的窗口了,所以没按回车(先 see 看一眼再决定)"
TYPE_LOCK_WAIT_S = 10      # 等别的任务往同一个 App 打完字最多这么久,超时报忙(不无限等)


def _focus_window_check(app):
    """11-17 C-2.5 两任务实测:后台打字只认 App 当前焦点框,「App「标题」」的标题没核对 → 两个任务交错时字写进对方窗口,
    点没生效时也会写进同 App 的别的窗口,还报 delivered。带标题时返回 check(pid):焦点控件所在窗口标题不是目标就 AXRefused。
    不带标题、画布类、读不到焦点或窗口标题(镜像、自绘界面)→ 不查(返回 None / 放过),跟原来一样。"""
    title = bg.split_target(app)[1]
    if title is None or _is_canvas(app):
        return None

    def focus_title(el):
        f = ax.attr(el, "AXFocusedUIElement")
        w = ax.attr(f, "AXWindow") if f is not None else None
        seen[0] = w              # 核对的和记下来的是同一次读数
        return ax.attr(w, "AXTitle") if w is not None else None
    seen = [None]

    def check(pid):
        try:
            el, _ = ax.app_element(pid)
            got = focus_title(el)
        except Exception:
            return
        if got is None or got == title:
            if got is not None:
                _TYPED_WIN[app] = (pid, _sheet_owner(seen[0]))
            return
        # 先在后台把目标窗口设成这个 App 的主窗口(11-17 实测:文本编辑在后台时焦点跟着过去、前台不变),再核一次。
        # 复查 11-17:目标 App 正在前台时不换(用户可能正在它另一个窗口里打字,换了等于抢用户的窗口),直接报窗口不对
        try:
            from seeu_lib import input_guard as _ig
            fa = _ig.frontmost_app()
            w = None if (fa and fa.get("pid") == pid) else ax.main_window(el, title)
            if w is not None:
                ax.set_attr(w, "AXMain", True)
                time.sleep(0.15)
                got = focus_title(el)
        except Exception:
            pass
        if got is not None and got != title:
            raise ax.AXRetry(WRONG_WINDOW.format(want=title, got=got or "没标题的窗口"), "failed", "wrong_window")
        if got is not None:
            _TYPED_WIN[app] = (pid, _sheet_owner(seen[0]))
    return check


_TYPED_WIN = {}            # 打字那一刻核对过的(进程号, 窗口元素):打完按回车前比的是它(打了字标题会变,不能比标题)


def _enter_block(app, pid):
    """打完字单独按回车之前(11-25 C-4.2 复查:核实打字要等一两秒,这中间焦点可能换了窗口 / 进了密码框)。
    不能按 → 原因,能按 → None。没指明窗口的只查密码框。"""
    r = _secret_block(app, "按键", pid)
    if r:
        return r["reason"]
    check = _key_window_check(app)
    if not check:
        return None
    rec = _TYPED_WIN.get(app)
    if rec and rec[1] is not None:
        try:
            if _key_window(ax.app_element(pid)[0]) == rec[1]:
                return None
        except Exception:
            pass
        return ENTER_MOVED
    try:
        check(pid)
    except ax.AXRefused as ex:
        return str(ex)
    return None


def _key_window(el):
    """App 的键盘焦点现在在哪个窗口(元素);读不到 None。表单(存储面板这类)算在它所在的窗口上。"""
    f = ax.attr(el, "AXFocusedUIElement")
    w = ax.attr(f, "AXWindow") if f is not None else None
    if w is None:
        w = ax.attr(el, "AXFocusedWindow") or ax.attr(el, "AXMainWindow")
    return _sheet_owner(w)


def _sheet_owner(w):
    for _ in range(4):
        if w is None or ax.attr(w, "AXRole") != "AXSheet":
            break
        w = ax.attr(w, "AXParent")
    return w


def _other_titled_window(pid, title):
    """这个进程在屏幕上还有没有别的、有标题的普通窗口(辅助功能什么都读不到时用窗口表数)。查不了算有。"""
    try:
        import Quartz
        for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
            b = w.get("kCGWindowBounds") or {}
            if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer", 0) == 0 and b.get("Width", 0) >= 100 \
                    and b.get("Height", 0) >= 60 and (w.get("kCGWindowName") or "") not in ("", title):
                return True
        return False
    except Exception:
        return True


def _browser_title(t):
    """去掉浏览器在窗口标题后面加的「- Google Chrome」这类后缀。"""
    return re.sub(r"\s+[-–—]\s+(Google Chrome|Chromium|Microsoft\u200b? Edge|Brave|Arc|Vivaldi|Opera)(\s+[-–—].*)?$", "", str(t or "")).strip()


def _key_window_check(app, window=None):
    """按键指明了窗口时:返回 check(pid),键盘焦点不在那个窗口就 AXRetry(wrong_window)。没指明 / 画布类 → None。
    键盘事件不带窗口号,进哪个窗口全看 App 那一刻的当前窗口(11-25 真机:指明 B,键进了主窗口 C;1.6.0 就有)。
    🔴 只核对、不换窗口(第三轮复查):换窗口会迟到、会把焦点记录发给别的窗口,换完密码框检查也作废。
    window = 浏览器的「标题」(入口归一时会去掉,单独传)。先定目标窗口,再比是不是同一个窗口:
      完全同名 → (浏览器)去掉后缀同名 → (浏览器)只有一个包含它的;包含的有几个就算认不出,不按。
    焦点读不到:App 只有一个窗口 → 放过(没得按错);有几个 → 再读两次,还不行就不按。"""
    title = bg.split_target(app)[1] or window
    if title is None or _is_canvas(app):
        return None
    browser = bool(window) and not bg.split_target(app)[1]

    def targets(ws, part=True):
        t = [(w, str(ax.attr(w, "AXTitle") or "")) for w in ws]
        hit = [w for w, x in t if x == title]
        if not hit and browser:
            want = _browser_title(title)
            hit = [w for w, x in t if _browser_title(x) == want]
            if part and not hit and len(want) >= 4:
                hit = [w for w, x in t if want in _browser_title(x)]
                hit = hit if len(hit) == 1 else []
        return hit

    def check(pid):
        try:
            el, _ = ax.app_element(pid)
        except Exception:
            raise ax.AXRetry(KEY_NO_REPLY.format(want=title), "failed", "no_reply")
        for n in range(3):
            t0 = time.time()
            ws = list(ax.attr(el, "AXWindows") or [])
            w = _key_window(el)
            slow = time.time() - t0 >= KEY_REPLY_S
            if w is not None:
                got = ax.attr(w, "AXTitle")
                if any(w == x for x in targets(ws)):
                    return
                # 窗口名单没读全(别的桌面上的不在名单里):焦点窗口自己就叫这个名也算;「包含」的认法不在这里用
                if not any(w == x for x in ws) and targets([w], part=False):
                    return
                if got is not None:
                    break
            elif not ws:
                # 🔴 C-4.2 复查:卡住没回话(超时)跟「自绘界面、没有控件」读出来都是空,原来一律放过 → 键排在卡住的 App 里,
                #   醒过来进当时的窗口。慢 = 没回话,不按;快而空 = 自绘界面,屏幕上没有它别的窗口才放过
                if slow:
                    raise ax.AXRetry(KEY_NO_REPLY.format(want=title), "failed", "no_reply")
                if n == 2:
                    if _other_titled_window(pid, title):
                        raise ax.AXRetry(KEY_NO_REPLY.format(want=title), "failed", "no_reply")
                    return
            elif len(ws) == 1 and ws == targets(ws):      # 只有一个窗口、就是要按的那个
                return
            if slow:
                break
            time.sleep(0.15)
        got = ax.attr(w, "AXTitle") if w is not None else None
        if slow and got is None:
            raise ax.AXRetry(KEY_NO_REPLY.format(want=title), "failed", "no_reply")
        raise ax.AXRetry(WRONG_WINDOW_KEY.format(want=title, got=got or "没标题的窗口"), "failed", "wrong_window")
    return check


class _TypeLock:
    """同一个 App 同一时间只让一个 SeeU 进程后台打字(聚焦 → 核对窗口 → 打字 这一段不被别的任务插进来)。
    锁 ~/.seeu/seeu_typelock/<App>.lock(flock,进程退出自动放);等 TYPE_LOCK_WAIT_S 秒拿不到就 AXRefused 报忙。"""
    def __init__(self, app):
        import hashlib
        d = os.path.expanduser("~/.seeu/seeu_typelock")
        try:                                  # 11-23 C-3.9 整体复查:名字先归一(中文系统里 TextEdit / 文本编辑 要落到同一把锁)
            name = bg.split_target(ax.canon_name(app))[0]
        except Exception:
            name = bg.split_target(app)[0]
        self.path = os.path.join(d, hashlib.md5(name.encode("utf-8")).hexdigest()[:12] + ".lock")
        self.app, self.f = app, None

    def __enter__(self):
        import fcntl
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.f = open(self.path, "a")
        except Exception:
            self.f = None               # 锁文件开不了就不锁(跟原来一样),不因为这个打不了字
            return self
        t0 = time.time()
        while True:
            try:
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() - t0 > TYPE_LOCK_WAIT_S:
                    self.f.close()
                    self.f = None
                    raise ax.AXRetry(f"另一个任务正在往「{bg.split_target(self.app)[0]}」打字,等了 {TYPE_LOCK_WAIT_S} 秒还没完,这次没打;稍后再试",
                                     "busy", "busy")
                time.sleep(0.1)

    def __exit__(self, *a):
        if self.f:
            try:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            finally:
                self.f.close()


def _focused_text(app):
    """目标 App 当前焦点输入框里的文字(辅助功能读,App 在后台也能读);读不到返回 None。"""
    if _is_canvas(app):
        return None
    try:
        el, _ = ax.app_element(_pid(app))
        f = ax.attr(el, "AXFocusedUIElement")
        v = ax.attr(f, "AXValue") if f is not None else None
        return str(v) if v is not None else None
    except Exception:
        return None


def _text_changed_factory(app):
    """普通 App 打字按"输入框文字变没变"核实:10-14 C-1.1 实测「文本编辑」打两个字,整窗截图变化太小被判没生效,
    兜底再打一遍就会重复。读不到文字(镜像、模拟器、网页做的框)返回 None,照旧比截图。
    C-1.3:变了之后 type() 还会再核对"最后几个字在不在",打进一半报 partial。"""
    if _focused_text(app) is None:
        return None

    def factory():
        st = {"before": _focused_text(app)}

        def expect(png):
            return _focused_text(app) not in (None, st["before"])
        expect.rebase = lambda: st.update(before=_focused_text(app))      # 11-17 复查:排完队重读「动作前」的文字
        return expect
    return factory


# 前台打字兜底救不了的 App(10-14 C-1.1 实测):BlueStacks 打不进是安卓里输入连接断了,真键盘也进不去;
# 而且窗口在别的桌面时激活它只会"应用到前台、窗口不过来",白抢一次前台。→ 直接报 ineffective,交给项目自己的办法。
NO_FRONT_TYPING = {"BlueStacks"}


def _front_type(app, ig, text, enter):
    """SeeU 兜底第二层:目标已被 _real_mouse 激活到前台。再让一次正在打字的用户、查密码框,
    确认前台真是目标才打(投给目标进程,不走全局键盘,中途前台被换也不会打到别的 App 里)。"""
    pid = _pid(app)
    ig.yield_to_user()
    ig.yield_to_typing()
    if ig.secure_input_pid():
        raise ax.AXRefused("系统处于密码输入状态")
    fa = ig.frontmost_app()
    if not fa or fa["pid"] != pid:
        raise RuntimeError(f"没能把 {app} 切到前台(现在是 {fa and fa['name']})")
    wcheck = _focus_window_check(app)
    if wcheck:
        wcheck(pid)
    try:
        bk.type_unicode(pid, text)
        if enter:
            time.sleep(0.3)
            bk.press(pid, "return")
    finally:
        ig.note_injected()


def _cdp_handle(app):
    """SeeU 专用那份(调试端口)在跑 → Handle;长进程里没有 cdp 模块就 None。"""
    try:
        from seeu import cdp
        return cdp.running(bg.split_target(app)[0])
    except Exception:
        return None


_ENTER_KEYS = {"space", "return", "enter", "delete", "forwarddelete"}
PASTE_MENU = re.compile(r"粘贴|粘貼|貼上|贴上|\bpaste\b", re.I)


def _key_enters(key, mods=()):
    """这个按键会不会往当前输入框里放东西 / 改它 / 提交它。规则在 safety.key_enters(调试端口那条路也用同一份)。"""
    from seeu import safety
    return safety.key_enters(key, mods)


def _edit_shortcut(item):
    """菜单项自己的快捷键是不是 ⌘V / ⌘X / ⌘Z(跟界面语言无关)。是 → "粘贴" / "按键",不是 → None。"""
    ch = str(ax.attr(item, "AXMenuItemCmdChar") or "").upper()
    try:
        no_cmd = int(ax.attr(item, "AXMenuItemCmdModifiers") or 0) & 8
    except (TypeError, ValueError):
        no_cmd = 0
    if ch in ("V", "X", "Z") and not no_cmd:
        return "粘贴" if ch == "V" else "按键"
    return None


_LABEL_ROLES = {"AXStaticText", "AXImage", "AXCell", "AXGroup", "AXUnknown"}   # 点到的多半是按钮 / 菜单项里面的字、图标、小分组:再往上看
_UP_STOP = {"AXWindow", "AXSheet", "AXDrawer", "AXApplication", "AXWebArea", "AXScrollArea", "AXToolbar", "AXTabGroup", "AXSplitGroup",
            "AXMenu", "AXMenuBar", "AXList", "AXTable", "AXOutline", "AXBrowser"}   # 往上找到这些大容器就停(窗口标题里有 paste 不算)
PASTE_UP = 3             # 往上最多看几层


def _paste_like(el, name=None):
    """按下这个控件是不是等于粘贴 / 剪切 / 撤销:名字写着粘贴,或是带那几个快捷键的菜单项。返回 "粘贴" / "按键" / None。
    名字 = 标题 + 描述;纯文字控件(按钮里那行字)再带上它显示的字。输入框里的内容不算名字。"""
    role = ax.attr(el, "AXRole")
    if name is None:
        name = f'{ax.attr(el, "AXTitle") or ""} {ax.attr(el, "AXDescription") or ""}'
        if role == "AXStaticText":
            name += f' {ax.attr(el, "AXValue") or ""}'
    if PASTE_MENU.search(name):
        return "粘贴"
    if role == "AXMenuItem":
        return _edit_shortcut(el)
    return None


def _paste_target(el, name=None):
    """点这个控件是不是等于粘贴:先看它自己;它只是字 / 图标 / 小分组时,再往上看 PASTE_UP 层(到窗口这类大容器就停)。
    11-07 复查:网页视图、自绘界面里按钮常常是「按钮(叫粘贴)套一行字」,清单里两项都有,只看自己的话点里面那行字就绕过去了。"""
    what = _paste_like(el, name)
    if what or ax.attr(el, "AXRole") not in _LABEL_ROLES:
        return what
    cur = el
    for _ in range(PASTE_UP):
        cur = ax.attr(cur, "AXParent")
        if cur is None or ax.attr(cur, "AXRole") in _UP_STOP:
            return None
        what = _paste_like(cur)
        if what:
            return what
    return None


def _tap_secret_block(app, e, x, y):
    """11-07 C-1.1.4(复查留下的):点击也可能等于粘贴 —— 工具栏上叫「粘贴」的按钮、右键菜单里展开的粘贴项,都不经过 act.menu。
    目标是这类控件、而光标在密码框 / 验证码框里 → 返回 refused 结果,否则 None。
    按编号 / 名字点的直接看那个控件;按位置点的先问辅助功能那个位置是什么(只读)。
    镜像、模拟器读不到控件,查不了;问不到是什么控件的照旧放行(在别处点一下本来就是离开密码框的办法)。"""
    if _is_canvas(app):
        return None
    what = None
    try:
        if e is not None:
            name = f'{e.get("title") or ""} {e.get("desc") or ""}'
            if e.get("role") == "AXStaticText":
                name += f' {e.get("value") or ""}'
            what = _paste_target(e["el"], name)
        else:
            el = ax.element_at(ax.app_element(_pid(app))[0], x, y)
            what = _paste_target(el) if el is not None else None
    except Exception:
        what = None
    return _secret_block(app, what) if what else None


DANGER_TAP_ROLES = ("AXButton", "AXMenuItem", "AXMenuBarItem", "AXMenuButton")


def _danger_names_at(app, x, y):
    """11-23 C-4.0 Fable 复查:按位置点时,问辅助功能那个位置是什么控件(只读);是字 / 图标就往上找 PASTE_UP 层,
    碰到按钮 / 菜单项就返回它的名字。读不到返回 []。"""
    try:
        el = ax.element_at(ax.app_element(_pid(app))[0], x, y)
    except Exception:
        return []
    cur = el
    for _ in range(PASTE_UP + 1):
        if cur is None:
            return []
        role = ax.attr(cur, "AXRole")
        if role in DANGER_TAP_ROLES:
            return [v for v in (ax.attr(cur, "AXTitle"), ax.attr(cur, "AXDescription")) if v]
        if role in _UP_STOP:
            return []
        cur = ax.attr(cur, "AXParent")
    return []


def _tap_danger_block(e, app=None, x=None, y=None):
    """11-23 C-3.9 整体复查:访达废纸篓窗口右上角的「清倒」、确认框里的「清倒废纸篓」、苹果菜单展开后的「关机…」,
    按编号 / 名字点时不经过 act.menu,原来没人查(Linux 11-20 补过,Mac 漏了)。按钮、菜单项的名字过一遍菜单那张词表。
    11-23 C-4.0 Fable 复查:按位置点的原来直接放行(按编号被拒后换位置点同一个按钮就过了)→ 先问那个位置是什么控件再查;
    镜像 / 模拟器(画面类)里读不到控件的查不了,照旧。"""
    if e is not None:
        if e.get("role") not in DANGER_TAP_ROLES:
            return None
        names = [x_ for x_ in (e.get("title"), e.get("desc")) if x_]
    elif app is not None and x is not None and not _is_canvas(app):
        names = _danger_names_at(app, x, y)
    else:
        return None
    from seeu import safety
    try:
        safety.check_menu(names)
        if app is not None and _is_finder(app):
            safety.check_finder_button(names)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    return None


def _is_finder(app):
    try:
        n = ax.canon_name(bg.split_target(app)[0]) if hasattr(bg, "split_target") else str(app)
    except Exception:
        n = str(app)
    return str(n).split("「")[0].strip().lower() in ("finder", "访达")


ACTIVATE_KEYS = {"return", "enter", "space"}     # 会「按下」当前焦点所在按钮的键


PAGE_SCHEMES = {"http", "https", "file"}                 # 网页区的地址是这几种才算「网页里」
NEUTRAL_SCHEMES = {"", "about-blank", "blob", "data", "javascript"}   # 说明不了是谁的页(内嵌的空白框等):接着往上找
FOCUS_WALK_MAX = 200                                     # 从焦点往上最多找几层(实测简单网页 11 层;很深的网页也到不了这个数)


def _web_scheme(webarea):
    """网页区地址的协议(小写)。about: 分两种:about:blank / about:srcdoc(网页里嵌的空白框)记成 "about-blank",
    其余 about:(Firefox 的 about:addons、about:preferences 这类浏览器自己的页)照原样返回 "about"。"""
    url = str(ax.attr(webarea, "AXURL") or "").strip()
    m = re.match(r"([a-z][a-z0-9+.-]*):", url, re.I)
    sc = m.group(1).lower() if m else ""
    if sc == "about" and re.match(r"about:(blank|srcdoc)\b", url, re.I):
        return "about-blank"
    return sc


def _el_name(el, default="按钮"):
    name = str(ax.attr(el, "AXTitle") or ax.attr(el, "AXDescription") or "").strip()
    return name[:40] or str(ax.attr(el, "AXRole") or "")[2:] or default


def _browser_ui_focus(app, key="return"):
    """浏览器里按回车 / 空格之前:键盘焦点是不是落在**不是网页**的地方,按下去等于替用户点了浏览器自己的按钮。
    是 → 返回那个东西的名字,否则 None(放行)。
    11-07 C-1.1.4(复查留下的老问题,跟「浏览器里不长按」同理):把焦点挪到工具栏的插件图标上再回车,
    等于点了「允许这个网站」这类按钮 = AI 替自己批准。
    从焦点往上找网页区,看它的地址:
      http / https / file 的网页里 → 放行;
      浏览器自己的页(插件弹出页 / 侧边栏、设置页、扩展管理页:chrome-extension://、chrome:// …)→ 拒(11-07 复查:这些也是「网页区」,只看角色会放行);
      根本不在网页区里(工具栏、弹窗等原生控件):输入框(地址栏、查找栏)和读不到 / 只读到外壳的放行,其余拒;
      另外:不在网页里、而所在窗口 / 对话框有「默认按钮」时,回车会直接触发它(不管焦点在哪)→ 回车也拒(空格不触发,不管)。
    往上找满 FOCUS_WALK_MAX 层还没结果 = 没看清,放行(不拿「不在网页里」去误导)。
    浏览器自己的界面是原生控件,不用开「网页结构」开关也读得到;读不到的基本就是网页里面。"""
    try:
        app_el = ax.app_element(_pid(app))[0]
        f = ax.attr(app_el, "AXFocusedUIElement")
        cur, n, in_web = f, 0, False
        while cur is not None and n < FOCUS_WALK_MAX:
            if ax.attr(cur, "AXRole") == "AXWebArea":
                sc = _web_scheme(cur)
                if sc in PAGE_SCHEMES:
                    return None
                if sc not in NEUTRAL_SCHEMES:
                    return f"{_el_name(f)}({sc} 页)"
                in_web = True
            cur = ax.attr(cur, "AXParent")
            n += 1
        if cur is not None:
            return None                                   # 找满上限还没到顶:没看清,放行
        if in_web:
            return None                                   # 在网页区里,只是地址说明不了是谁的(about:blank、读不到地址):照旧放行
        role = ax.attr(f, "AXRole") if f is not None else None
        if key in ("return", "enter"):
            for w in ((ax.attr(f, "AXTopLevelUIElement"), ax.attr(f, "AXWindow")) if f is not None else ()) + (ax.attr(app_el, "AXFocusedWindow"),):
                d = ax.attr(w, "AXDefaultButton") if w is not None else None
                if d is not None:
                    return f"{_el_name(d)}(对话框的默认按钮)"
        if f is None or role in ax.TEXT_ROLES or role in _GENERIC_FOCUS:
            return None
        return _el_name(f)
    except Exception:
        return None



def _secret_block(app, what, pid=None):
    """光标在密码框 / 新密码框 / 验证码框里 → 返回一条 refused 结果,否则 None。
    认法:辅助功能读目标 App 的焦点控件(同 type());读不到时再看系统的「密码输入状态」是不是这个 App 占着。
    镜像、模拟器读不到控件,查不了(跟打字一样)。pid = 已经知道键要发给哪个进程(同名多进程时查的就是它)。"""
    kind = _focus_secret(app, pid)
    if not kind and not _is_canvas(app):
        try:
            from seeu_lib import input_guard as ig
            sp = ig.secure_input_pid()
            if sp and sp == (pid or _pid(app)):
                kind = "密码框"
        except Exception:
            pass
    if kind:
        return dict(outcome="refused", route=None, tried=[], png=None,
                    reason=f"光标在{kind}里,SeeU 不往里{what}(这一步请你自己来)")
    return None


KEY_NO_CHANGE = "按了,但画面没看出变化(这不等于没生效:一个字、回车提交、挪光标常常看不出来)。先 see 看一眼,别直接重按"


def _key_state(app):
    """按键前后各读一次、拿来比的东西(只读):焦点控件、框里的文字、选区 / 光标位置、焦点窗口和它的标题。
    画面类(镜像、模拟器)和读不到的返回 None。"""
    if _is_canvas(app):
        return None
    try:
        app_el = ax.app_element(_pid(app))[0]
        f = ax.attr(app_el, "AXFocusedUIElement")
        w = ax.attr(app_el, "AXFocusedWindow")
        v = ax.attr(f, "AXValue") if f is not None else None
        sel = ax.attr(f, "AXSelectedTextRange") if f is not None else None
        return dict(focus=f, role=ax.attr(f, "AXRole") if f is not None else None,
                    text=None if v is None else str(v), sel=_range(sel),
                    win=w, title=ax.attr(w, "AXTitle") if w is not None else None)
    except Exception:
        return None


def _range(v):
    """选区的 AXValue → (起点, 长度);读不出 None。不能直接 str():里面带内存地址,每次读都不一样。"""
    m = re.search(r"location[:=]\s*(\d+)[,\s]+length[:=]\s*(\d+)", str(v)) if v is not None else None
    return (int(m[1]), int(m[2])) if m else None


def _key_change(a, b, text_only=False):
    """text_only = 往输入框打一个普通字:只认同一个框里的文字变了(换窗口、光标动、标题变都可能是别的原因)。
    两次 _key_state 之间变了什么(一句话),没变 / 读不到返回 None。读到一半没了的(None)不算变。"""
    if not a or not b:
        return None
    def moved(k):
        return a[k] is not None and b[k] is not None and a[k] != b[k]
    if text_only:
        return "框里的文字变了" if a["focus"] == b["focus"] and moved("text") else None
    if moved("win"):
        return "换了窗口"
    if moved("focus"):
        return "光标换了地方"
    if moved("text"):
        return "框里的文字变了"
    if moved("sel"):
        return "光标 / 选中的位置变了"
    if moved("title"):
        return "窗口标题变了"
    return None


def _key_verify(app, r, before, key, mods):
    """11-24 C-4.1:原来只看画面变了 0.1% 没有 —— 大窗口里打一个字才 0.02%,字进去了却报 ineffective,AI 照规矩会重按
    (重打一个字、重发一次)。截图看不出来的,再比按键前后的文字、光标、焦点:变了 = delivered;
    没变的也只报 unverified,除非是往原生输入框打一个字、文字和光标都读得到却都没动 = 真没进去,照旧 ineffective。"""
    if r.get("outcome") not in ("ineffective", "unverified") or _is_canvas(app):
        return r
    after = _key_state(app)
    plain = (len(key) == 1 or key == "space") and not {"cmd", "ctrl", "alt"} & set(_norm_mods(mods))
    what = _key_change(before, after, text_only=bool(plain and before and before["role"] in ax.TEXT_ROLES))
    if what:
        r.update(outcome="delivered", note=f"画面没看出来,按控件读到的核实:{what}")
        if r.get("tried"):
            r["tried"][-1] = (r["tried"][-1][0], "delivered")
        return r
    if r["outcome"] == "unverified":
        return r
    if plain and before and after and before["focus"] == after["focus"] and before["sel"] == after["sel"] and before["role"] in ax.TEXT_ROLES and not _chromium(_pid(app)) and not _in_web(after["focus"]) \
            and before["text"] is not None and before["sel"] is not None and after["text"] is not None and after["sel"] is not None:
        return r
    r.update(outcome="unverified", reason=KEY_NO_CHANGE)
    if r.get("tried"):
        r["tried"][-1] = (r["tried"][-1][0], "unverified")
    return r


def _norm_mods(mods):
    from seeu import safety
    return safety.norm_mods(mods)


def _in_web(el):
    """焦点在网页视图里吗(那里的文字读数会慢半拍或读不全,不拿「没变」下结论)。"""
    for _ in range(FOCUS_WALK_MAX):
        if el is None:
            return False
        if ax.attr(el, "AXRole") == "AXWebArea":
            return True
        el = ax.attr(el, "AXParent")
    return False


def press(app, key, *mods, window=None):
    from seeu import safety
    try:
        safety.check_keys(key, mods)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    h = _cdp_handle(app)
    if h:
        from seeu import cdp
        return cdp.key(h, key, *mods)
    # 11-06 C-1.1.3(二次复查第 5 条):原来只有 type() 查密码框 / 验证码框,逐个按键或 ⌘V 粘贴能绕过去
    what = "按键"
    if _key_enters(key, mods):
        paste = safety.norm_key(key) in ("v", "y") and {"cmd", "ctrl"} & set(safety.norm_mods(mods))
        what = "粘贴" if paste else "按键"
        r = _secret_block(app, what)
        if r:
            return r
    from seeu import web
    nk = safety.norm_key(key)
    if nk in ACTIVATE_KEYS and web.is_browser(web.canon(app)):
        name = _browser_ui_focus(app, nk)      # 放在密码框检查后面:那一步已经替 Chrome 开过「网页结构」开关
        if name:
            return dict(outcome="refused", route=None, tried=[], png=None,
                        reason=f"焦点在浏览器自己的按钮「{name}」上(不在网页里),SeeU 不替你按回车 / 空格"
                               f"(这一步请你自己来;只想关掉弹窗可以按 Esc)")

    def act():
        g = _geo(app, by_title=True) if check else _geo(app)
        cx, cy = g["x"] + g["w"] / 2, g["y"] + g["h"] / 2
        hit = bg.window_of(app, cx, cy) if check else None
        if check:
            check(hit[0] if hit else _pid(app))      # 🔴 在 _prepare 之前:它会给窗口发「获得焦点」记录,发了再拒绝就晚了
        if hit and g.get("id") and hit[1] != g["id"]:
            # 中心点上盖着同 App 的另一个窗口:不给它发焦点记录(焦点本来就在要按的窗口里,不用再聚焦)
            pid = hit[0]
            bg.check_called_out(pid)
            bg._safety(pid)
        else:
            pid, _, _ = bg._prepare(app, cx, cy)
        # 独立复查:按键前的样子要在聚焦之后读,不然 SeeU 自己换的焦点会被当成「按键生效」
        if check:
            time.sleep(0.15)
            _rebase()                     # 窗口聚焦会变亮:画面对比的「按键前」也从这时算起
        elif not _is_canvas(app):
            time.sleep(0.15)              # 没指明窗口也等焦点换完再读「按键前」
        box["before"] = _key_state(app)
        if _key_enters(key, mods):        # C-4.2 复查:开头那次查完又截图又聚焦,焦点可能已经到密码框里了 → 发键前再查一次
            b = _secret_block(app, what, pid)
            if b:
                raise ax.AXRefused(b["reason"])
        if check:
            check(pid)                    # 紧贴着发键再核一次
        bk.press(pid, key, mods)
    box, check = {}, _key_window_check(app, window)
    r = _ladder(app, [("后台按键", act)], min_change=0.001, expect_factory=_fine_expect(app, min_change=0.001))
    try:
        return _key_verify(app, r, box.get("before"), nk, mods)
    except Exception as ex:   # noqa: BLE001      键已经发出去了:核实出错不能报 failed(AI 会重按)
        if r.get("outcome") == "ineffective":
            r.update(outcome="unverified", reason=KEY_NO_CHANGE)
            print(f"[SeeU] 按键核实出错:{ex!r}", file=sys.stderr)
        return r


def menu(app, *path):
    from seeu import safety
    try:
        safety.check_menu(path)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    # 11-06 C-1.1.3:菜单里的「粘贴」跟 ⌘V 是同一件事。先按文字认(哪一级写着粘贴都算)……
    if any(PASTE_MENU.search(str(p)) for p in path):
        r = _secret_block(app, "粘贴")
        if r:
            return r

    def guard(item):
        # ……再按菜单项自己的快捷键认(11-07 复查:文字只认中英文,日文、德文界面的「粘贴」认不出;快捷键跟语言无关)。⌘X 剪切同理。
        what = _edit_shortcut(item)
        if what:
            r = _secret_block(app, what)
            if r:
                raise ax.AXRefused(r["reason"])

    who = _pid(app) if bg.split_target(app)[1] else app   # 带「标题」的按进程号找菜单栏(同名多实例)
    return _ladder(app, [("菜单", lambda: _keep_front(app, lambda: ax.menu(who, *path, guard=guard)))], min_change=0.001)


MENU_FRONT_WATCH_S = 1.2   # 菜单按下后盯多久前台(App 自己激活常晚几百毫秒)


def _keep_front(app, fn):
    """10-29 用户实测:备忘录「New Note」菜单会把备忘录拉到前台,用户打的字被抢走。
    做菜单前记下前台和目标藏没藏;做完盯一会儿,目标被拉到前台就马上把前台还给原来的程序,原来藏着的再藏回去。"""
    from AppKit import NSRunningApplication
    from seeu_lib import input_guard as ig
    pid = _pid(app)
    before = ig.frontmost_app()
    ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
    was_hidden = bool(ra and ra.isHidden())
    out = fn()
    if not before or before["pid"] == pid:        # 本来就在前台(用户自己在用它),不管
        return out
    t0 = time.time()
    while time.time() - t0 < MENU_FRONT_WATCH_S:
        fa = ig.frontmost_app()
        if fa and fa["pid"] == pid:
            ig._activate_pid(before["pid"], before.get("bundle"))
            if was_hidden and ra:
                ra.hide()
            print(f"[SeeU] 「{app}」做菜单时自己跑到了前台,已把前台还给「{before['name']}」", file=sys.stderr)
            break
        time.sleep(0.05)
    return out


def drag(app, pts, hold_ms=0, allow=None):
    """拖动:macOS 没有后台拖动的路,直接走真鼠标。pts = 屏幕点列表。"""
    x0, y0 = pts[0]
    from seeu import web as _web
    if _web.is_browser(_web.canon(app)):     # 11-23 C-3.9 整体复查:跟长按同一个口子(起点终点同一处的拖动就是按屏幕位置点一下,绕开允许名单)
        return dict(outcome="refused", route=None, tried=[], png=None,
                    reason="浏览器里不能拖动(拖动是按屏幕位置点,会绕开网页的允许名单);点网页上的东西用 tap,按编号")
    bad = _stale_pixel(app)          # 11-15 C-2.0:拖动全靠截图位置
    if bad:
        return bad
    blocked = _tap_secret_block(app, None, x0, y0)     # 11-07 复查:起点终点同一处的拖动也是一次点击
    if blocked:
        return blocked

    def act(ig):
        _cursor(app, "move", x0, y0, mode="real", force=True)
        from seeu import safety
        safety.check_point(x0, y0)
        # 11-16:起点、终点、中间点全在同一个 AI 看过的弹窗里面(拖对话框里的滑块)才放开;拖进 / 拖出弹窗照旧拦
        inside = _has_modal(app) and _in_modal(app, list(pts))

        def do():
            if inside:
                _modal_recheck(app, list(pts))
                _seen_modals.pop(app, None)
            mi.qdrag(pts, hold_ms=hold_ms)
        ig.guarded(x0, y0, ax.local_name(bg.split_target(app)[0]), do=do, check_modal=not inside)
        _cursor(app, "move", *pts[-1], mode="real", force=True)
    if not real_allowed(allow):
        r = dict(outcome="refused", route=None, tried=[], png=None,
                 reason="拖动只能借用户的鼠标(macOS 没有后台拖动),设置.json「借用鼠标」= 关,没做。要拖请用户自己拖,或请用户把设置改成开")
        return _ask_user(r, "ask.drag", app) if real_mode() == "ask" else r
    return _ladder(app, [("真鼠标拖动", _real_mouse(app, act, modal=lambda: (list(pts), None)))])


# ---------------------------------------------------------------- 镜像固定动作(自带状态检查)
# ⌘1~⌘4 都是开关,状态会被上一次带过来;从 Spotlight 开的 App 按 Home 会落回 Spotlight 结果页(10-14 实测)。
SPOTLIGHT_MARKS = ("Top Hit", "Suggestions", "Siri Suggestions", "Search in App")


def _mirror_texts(app):
    return [i["text"] for i in see(app)["items"]]


def _in_spotlight(t):
    return any(m in x for x in t for m in SPOTLIGHT_MARKS)      # 认字常带尾巴(如「Search in App G」),按包含比


def _typed_in_spotlight(app, name):
    """字进搜索框了吗:打进去后会出搜索结果(空 Spotlight 只有一个 Search 框,没有这些字)。"""
    t = _mirror_texts(app)
    return _in_spotlight(t) or any(name.lower() in x.lower() for x in t)


def mirror_home(app="iPhone Mirroring", tries=3):
    """回主屏并确认不在 Spotlight 上。返回 {outcome, texts}。"""
    t = []
    for _ in range(tries):
        menu(app, "View", "Home Screen")
        time.sleep(1.2)
        t = _mirror_texts(app)
        if _in_spotlight(t):
            menu(app, "View", "Spotlight")
            time.sleep(1.2)
            t = _mirror_texts(app)
        if not _in_spotlight(t):
            return {"outcome": "delivered", "texts": t}
    return {"outcome": "ineffective", "texts": t}


def mirror_open_app(name, app="iPhone Mirroring"):
    """镜像里开 App,全程后台:回主屏 → 开 Spotlight(确认开了)→ 打名字回车(确认离开 Spotlight)。
    名字中英文都行(后台直接塞字,不走剪贴板)。"""
    if mirror_home(app)["outcome"] != "delivered":
        return {"outcome": "failed", "step": "回主屏"}
    home = _mirror_texts(app)
    menu(app, "View", "Spotlight")
    time.sleep(1.2)
    t = _mirror_texts(app)
    if t == home or ("Calendar" in t and "Calendar" in home):
        return {"outcome": "failed", "step": "开 Spotlight(画面没变)"}
    r = type(app, name)
    time.sleep(1.0)
    if not _typed_in_spotlight(app, name):      # 11-05 实测:Spotlight 开着但框没聚焦(没光标)时打不进,点一下再打一次
        hit = [i for i in see(app)["items"] if i["text"].endswith("Search")]
        if not hit:
            return {"outcome": "ineffective", "step": "打不进搜索框,也没找到搜索框", "type": r}
        bg.tap(app, hit[-1]["x"], hit[-1]["y"])      # 11-06 二次复查:bg.tap 要屏幕点(原来传了相对窗口的偏移)
        time.sleep(0.8)
        r = type(app, name)
        time.sleep(1.0)
        if not _typed_in_spotlight(app, name):
            return {"outcome": "ineffective", "step": "点过搜索框还是打不进字", "type": r}
    press(app, "return")
    time.sleep(1.5)
    t = _mirror_texts(app)
    if _in_spotlight(t):
        return {"outcome": "ineffective", "step": "回车后还在 Spotlight", "type": r}
    return {"outcome": "delivered", "texts": t[:10]}


# ---------------------------------------------------------------- 命令行

def _report(r):
    if isinstance(r, Exception):
        if isinstance(r, ax.AXRefused):         # 11-06:安全底线拦的(含 see 被拦)报 refused、退出码 3
            print(f"refused  {r}")
            return 3
        print(f"failed  {r}")
        return 1
    print(f"{r['outcome']}  路线={r.get('route')}  试过={r.get('tried')}  截图={r.get('png')}")
    if r.get("reason"):                 # 10-29 Skill:被拦/做不到时把「卡在…原因…怎么办」也打出来,给 AI 照着转述
        print(f"原因  {r['reason']}")
    return 0 if r["outcome"] == "delivered" else (3 if r["outcome"] == "refused" else 1)


# ---------------------------------------------------------------- 多任务调度(11-17 C-2.5,见 sched.py、SeeU-多任务调度设计.md)
# 对外动作统一包一层:同一个 App 一次一个任务(排队、动完接着占几秒)、排太久按位置点先核画面、记录用时。
# 内部互相调用(mirror_open_app 里调 tap / type)走的也是包过的名字,sched 按「同一进程嵌套」只在最外层占 / 让 / 记。
try:
    from seeu import sched as _sched

    def _by_pos(args, kwargs):
        """按位置点 → 返回那个屏幕点(防过时只比它附近);按编号 / 名字 → None(轮到时会重新找控件)。"""
        t = args[0] if args else kwargs.get("target")
        return tuple(t[:2]) if isinstance(t, (tuple, list)) and len(t) >= 2 else None

    _raw_shoot = shoot

    def shoot(app):                                   # noqa: F811 —— 记截图用时(任务窗口协议的数据)
        t0 = time.time()
        try:
            return _raw_shoot(app)
        finally:
            _sched.add_heavy("shot", time.time() - t0)

    see = _sched.scheduled("see", lease=False)(see)
    tap = _sched.scheduled("tap", positional=_by_pos, lease="focus", focus=True)(tap)
    long_press = _sched.scheduled("long_press", positional=_by_pos, lease="focus", focus=True)(long_press)
    scroll = _sched.scheduled("scroll", lease="focus")(scroll)
    # 外部评审 11-17:打字 / 按键是往「当前焦点」里送 → 上一步之后别的任务动过焦点就不做(MCP 带输入框时整段占着,不查)
    type = _sched.scheduled("type", focus=True, focus_check=lambda a, k: True)(type)          # noqa: A001
    press = _sched.scheduled("press", focus=True, focus_check=lambda a, k: True)(press)
    menu = _sched.scheduled("menu", focus=True)(menu)
    drag = _sched.scheduled("drag", positional=lambda a, k: (lambda p: tuple(p[0][:2]) if p else True)(a[0] if a else k.get("pts")),
                            focus=True)(drag)
    mirror_home = _sched.scheduled("mirror_home", focus=True)(mirror_home)
    _raw_mirror_open = mirror_open_app
    _mirror_open_s = _sched.scheduled("mirror_open_app", focus=True)(lambda app, name: _raw_mirror_open(name, app=app))

    def mirror_open_app(name, app="iPhone Mirroring"):      # noqa: F811 —— 第一个参数是要开的 App 名,目标是镜像
        return _mirror_open_s(app, name)
except Exception:   # noqa: BLE001 —— 调度模块出问题不影响 SeeU 本身
    pass


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2:
        print(__doc__)
        return 2
    cmd, app, rest = a[0], a[1], a[2:]
    try:
        return _main(cmd, app, rest)
    except (RuntimeError, ax.AXError) as ex:
        return _report(ex)


def _main(cmd, app, rest):
    if cmd == "home":
        r = mirror_home(app)
        print(r["outcome"])
        return 0 if r["outcome"] == "delivered" else 1
    if cmd == "open":
        r = mirror_open_app(rest[0], app)
        print(r)
        return 0 if r["outcome"] == "delivered" else 1
    if cmd == "base":
        print(mirror_baseline(app, force="--force" in rest))
        return 0
    if cmd == "see":
        v = see(app)
        if v.get("url"):                   # 浏览器 / 网页壳(转给 seeu.web):没截图,给标题和网址
            print(f"页面: {v.get('title')}  {v.get('url')}  路线={v.get('route')}")
        if "route" not in v:                # 原生/镜像(藏着的原生 App 没截图,10-30)
            print(describe(v["items"]))
        else:
            from seeu import web
            print(web.describe(v["items"]))
        if v.get("png"):
            print("截图:", v["png"])
        if v.get("stale"):
            print("⚠️ 截图可能是旧画面:" + v["stale"] + "。按编号、菜单、按键照常能做,但效果在截图上看不出来(看列表文字核对);按截图位置点会先被拦下。"
                  + {DESK_WHY: "请切到那个桌面再 see", LOCK_WHY: "请解锁 Mac、唤醒显示器再 see"}.get(v["stale"], "请让窗口露出来一块(比如一个角)再 see"))
        return 0
    if cmd == "tap":
        t = (float(rest[0]), float(rest[1])) if len(rest) == 2 and all(
            x.replace(".", "").lstrip("-").isdigit() for x in rest) else rest[0]
        return _report(tap(app, t))
    if cmd == "type":
        return _report(type(app, rest[0], enter="--enter" in rest))
    if cmd == "scroll":
        return _report(scroll(app, dy=float(rest[0]), dx=float(rest[1]) if len(rest) > 1 else 0))
    if cmd == "press":
        return _report(press(app, rest[0], *rest[1:]))
    if cmd == "menu":
        return _report(menu(app, *rest))
    print("不认识的命令:", cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
