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
import sys
import tempfile
import time

from seeu_lib import mac_input as mi
from seeu import ax, bgclick as bg, bgkey as bk

ICON_ABOVE_LABEL = 30   # 镜像基准尺寸下,主屏图标中心在名字上方约 30 点
# 画面是视频流、辅助功能看不到里面按钮的 App:用识字代替控件清单
CANVAS_APPS = {"iPhone Mirroring", "BlueStacks"}   # BlueStacks:安卓画面,同样只能识字(10-14)
PROJECT = os.environ.get("SEEU_PROJECT", "SeeU")
_TMP = tempfile.mkdtemp(prefix="seeu_")
_last = {}   # app -> 上一次 see() 的清单(按编号点用)
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
    """真鼠标前把目标提到前台。带「标题」的按进程号激活(按名字激活分不清多实例)。"""
    owner, title = bg.split_target(app)
    if title is None:
        return mi.activate(owner, wait_front_s=wait_front_s)
    import AppKit
    pid = _pid(app)
    ra = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if ra is None:
        return False
    ra.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
    t0 = time.time()
    from seeu_lib import input_guard as ig
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
            ig.preflight(g0["x"] + g0["w"] / 2, g0["y"] + 20, app, check_modal=False)
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


def _geo(app):
    """App 的目标窗口(屏幕点 + 窗口号)。原生 App 取辅助功能里的焦点窗口(多窗口时不会截错),取不到再按面积挑最大的。"""
    if not _is_canvas(app):
        try:
            import Quartz
            el, pid = ax.app_element(app)
            f = ax.frame(ax.main_window(el, ax.split_window(app)[1]))   # 11-01:写了「窗口标题」就截那个窗口
            for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
                b = w.get("kCGWindowBounds") or {}
                if f and w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer", 0) == 0 and \
                        (round(b["X"]), round(b["Y"]), round(b["Width"]), round(b["Height"])) == tuple(round(v) for v in f):
                    return dict(x=int(b["X"]), y=int(b["Y"]), w=int(b["Width"]), h=int(b["Height"]),
                                id=int(w["kCGWindowNumber"]))
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
    png = os.path.join(_TMP, f"s{_n[0]}.png")
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

def see(app):
    """返回 {png, items}。items 每项:id、kind(ax|ocr)、text、x/y(屏幕点中心)、以及 ax 项带 el/role。
    浏览器(Chrome / Safari …)转给 seeu.web:返回 {route, items, text, url, title, tab},没有 png。"""
    from seeu import web
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
        from seeu_lib import ocr
        g, s = _scale(app, png)
        for e in ocr.ocr(png):
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
    wins = []
    if not canvas and bg.split_target(app)[1] is None:
        try:                            # 11-01:App 开着好几个窗口(如 Gemini 的设置)时告诉 AI 怎么指定
            wins = ax.window_titles(ax.app_element(app)[0])
        except Exception:
            pass
    return {"png": png, "items": items, "windows": wins}


def describe(items):
    return "\n".join(f"{it['id']:>3}. {it.get('role', 'OCR')[2:] if it.get('role') else '字'}  {it['text']}  "
                     f"({it['x']:.0f},{it['y']:.0f})" for it in items)


def _resolve(app, target):
    """target → (x, y, ax项或None)。"""
    if isinstance(target, (tuple, list)) and len(target) == 2:
        return float(target[0]), float(target[1]), None
    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
        items = _last.get(app) or see(app)["items"]
        n = int(target)
        it = next((i for i in items if i["id"] == n), None)
        if not it:
            raise RuntimeError(f"没有编号 {n},先 see 一次")
        return it["x"], it["y"], it.get("ax")
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


# ---------------------------------------------------------------- 核实 + 退路

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
        r = wait.act_and_verify(lambda: shoot(app), act_once, expect=expect, box=_verify_box(app, first),
                                min_change=min_change, timeout=2.5, interval=0.4)
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
    tried = []
    png = None
    for name, act in steps:
        try:
            outcome, png = _try(app, act, min_change, expect_factory() if expect_factory else None)
        except ax.AXRefused as ex:
            tried.append((name, f"refused:{ex}"))
            return dict(outcome="refused", route=name, tried=tried, png=png, reason=str(ex))
        except Exception as ex:  # 这条路走不通(私有接口没了、控件不支持…)→ 下一条
            tried.append((name, f"error:{ex}"))
            continue
        tried.append((name, outcome))
        if outcome in ("delivered", "unverified"):
            return dict(outcome=outcome, route=name, tried=tried, png=png)
    last = tried[-1][1] if tried else "failed"
    out = "refused" if str(last).startswith("refused") else ("ineffective" if last == "ineffective" else "failed")
    return dict(outcome=out, route=tried[-1][0] if tried else None, tried=tried, png=png)


class _Refused(Exception):
    pass


def _real_mouse(app, fn):
    """真鼠标兜底:拿桌面锁 → 让路检查 → 激活窗口 → 做 → 还原前台和鼠标 → 放锁。"""
    from seeu_lib import desktop_lock as dl, input_guard as ig

    def act():
        # 10-30:先让路再激活。原来激活后才在 fn 里查用户在不在用 → 用户在用就停手,
        # 但前台已经被抢、还原又因"用户在用"跳过,目标 App 一直挂在前台(Chrome 实测抢了用户桌面)
        ig.yield_to_user()
        r = dl.acquire(PROJECT, f"SeeU 真鼠标:{app}", attended=True)
        if not r["ok"]:
            raise ax.AXRefused("桌面锁被占:" + dl.describe(r["held"]))
        try:
            _halo("real", 5)              # 借用系统鼠标期间亮光圈(按档位);结束后 0.8 秒淡出
            with ig.FrontState(avoid_owner=bg.split_target(app)[0] if _is_canvas(app) else None):
                _activate(app)
                fn(ig)
        finally:
            _halo("real", 0.8)
            dl.release()
    return act


# ---------------------------------------------------------------- 代理光标(纯显示)
# 10-14 用户要:跟别家 Computer Use 一样,动手时在那个位置画个光标给人看;位置被别的窗口挡住、或窗口不在当前桌面,就不画。
# 用 seeu_lib.cursor_overlay(纯显示,不碰真鼠标)。任何异常都吞掉,绝不影响动作本身。不想要光标设 SEEU_NO_CURSOR=1。
# 用名牌 + 颜色区分(用户 10-14 定):后台模式 = 「SeeU」紫色;让路模式(借用系统鼠标)= 署名(设置.json,没写就 SeeU)亮橙(10-15 改,原蓝色);
# 用户自己的鼠标 = 系统黑色指针、无名牌。
_SETTINGS = os.path.join(os.path.dirname(__file__), "设置.json")


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


def _ask_user(r, what):
    """「问我」档:不借,结果改成 ask_user 交给 AI 去问;屏幕上弹提示条提醒用户回对话里选。"""
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
    if _cursor_up[0]:
        return
    _cursor_up[0] = True
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
    return bool(top and top["owner"] == owner and (title is None or (top.get("name") or "") == title))


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
            t = co.show(kind, x, y, label, color, owner=bg.split_target(app)[0])   # 显示进程自己每 0.2s 查遮挡,两次动作之间被挡也会藏
            # C-1.3:光标按距离走 0.22~0.65 秒,show 返回要等多久;长进程里是旧版就返回 None,按老的 MOVE_S
            time.sleep(min(1.0, t) if isinstance(t, (int, float)) else co.MOVE_S)
        else:
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
    if web.is_browser(app) or web.is_cdp(app):     # 浏览器 / SeeU 专用那份网页壳 App:按网页里的编号/名字点,见 seeu/web
        return web.tap(app, target)
    x, y, e = _resolve(app, target)
    rx, ry = _rel(app, x, y)   # 窗口被挪了也点得准:每条路动手前按窗口当时位置重算(10-14 跨桌面实测窗口被挪过)
    steps = []
    if e is not None and ("AXPress" in e["actions"] or "AXPick" in e["actions"]):
        steps.append(("辅助功能按下", lambda: ax.press(app, e["id"])))
    steps.append(("后台点击", lambda: _shown(app, "click", rx, ry, lambda x, y: bg.tap(app, x, y))))
    if _is_canvas(app) and isinstance(target, str) and not target.isdigit():
        # 镜像主屏的 App 名字点不进,要点字上方的图标(10-14 实测「Settings」:点字没反应,上移 30 点就进了)
        steps.append(("后台点击(字上方图标)",
                      lambda: _shown(app, "click", rx, ry - ICON_ABOVE_LABEL, lambda x, y: bg.tap(app, x, y))))
    r = _ladder(app, steps)
    r["xy"] = (round(x), round(y))
    if r["outcome"] != "ineffective":
        return r
    if _focus_at(app, x, y):
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
            ig.guarded(ax_, ay_, bg.split_target(app)[0], do=lambda: mi.qtap(ax_, ay_))
        r2 = _ladder(app, [("真鼠标", _real_mouse(app, real_tap))])
        r2["tried"] = r["tried"] + r2["tried"]
        r2["xy"] = r["xy"]
        return r2
    if real_mode() == "ask":
        return _ask_user(r, "ask.tap")
    r["reason"] = NO_REAL_NOTE
    return r


def long_press(app, target, ms=1000):
    x, y, _ = _resolve(app, target)
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
    if h:                               # C-1.0:SeeU 专用那份(调试端口)藏着打,回车也走它
        from seeu import cdp
        r = cdp.type(h, text)
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
    steps = [("后台打字", lambda: bk.type_to(app, text, enter=False))]
    # 10-30:浏览器不走前台兜底——藏着/在后面的窗口截图看不出字变,后台其实打进去了也判"没变",
    # 兜底就把浏览器拉到前台(实测抢了用户桌面)、还会叠出重复字。网页填表按编号用 web.type 才核实得了。
    if fallback and not real_allowed(allow):
        fallback = None                  # None = 本来要兜底,按设置没借(结果里写原因 / 「问我」档交给 AI 去问)
    if fallback and not browser and bg.split_target(app)[0] not in NO_FRONT_TYPING:
        steps.append(("前台打字", _real_mouse(app, lambda ig: _front_type(app, ig, text, False))))
    r = _ladder(app, steps, min_change=0.001, expect_factory=factory)
    if browser and r["outcome"] == "ineffective":
        r.update(outcome="unverified", reason="后台打了,但浏览器画面核实不到(可能已经打进去)。"
                 "先 see 看框里的字;网页填表用 seeu.web.type(App, 编号, 文字) 才能核实,别重打")
    elif fallback is None and r["outcome"] == "ineffective":
        if real_mode() == "ask":
            return _ask_user(r, "ask.type")
        r["reason"] = NO_REAL_NOTE + "(打字落空多半是输入框没聚焦:先点一下输入框再打)"
    # "动了"不等于打全了:读得到框里文字的直接看,读不到的(网页做的框、镜像画面)截图识字,找最后几个字;
    # 找不到 = 只打进一部分 → 报 partial、不按回车、也不兜底重打(重打会叠出重复字)
    if r["outcome"] == "delivered" and tail:
        if factory is not None:
            seen = tail in "".join(c for c in (_focused_text(app) or "") if c.isalnum())
        else:
            seen = _ocr_has_tail(app, tail)
        if seen is False:
            r.update(outcome="partial", reason=f"画面变了,但没认到最后几个字「{tail}」,可能只打进一部分;没按回车")
            return r
    if enter and r["outcome"] in ("delivered", "unverified"):
        from seeu_lib import input_guard as ig
        try:
            time.sleep(0.3)
            bk.press(_pid(app), "return")       # 投给目标进程,不抢前台;只按这一次,不核实不重试
        finally:
            ig.note_injected()
        r["enter"] = "sent"
    return r


def _tail(text, n=4):
    """核实用的"最后几个字":只取汉字/字母/数字(标点空格识字常认错),最多 n 个。"""
    keep = [c for c in str(text) if c.isalnum()]
    return "".join(keep[-n:])


def _ocr_has_tail(app, tail):
    """截图识字,看最后几个字在不在画面上。认不了(识字出错)返回 None = 不确定,按原来的结果走。"""
    try:
        from seeu_lib import ocr
        png = shoot(app)
        got = "".join(c for it in ocr.ocr(png) for c in str(it[0] if isinstance(it, (list, tuple)) else
                                                               it.get("text", "")) if c.isalnum())
        return tail in got
    except (Exception, SystemExit):   # seeu_lib.ocr 认不出会 SystemExit
        return None


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
        before = _focused_text(app)
        return lambda png: _focused_text(app) not in (None, before)
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


def press(app, key, *mods):
    from seeu import safety
    try:
        safety.check_keys(key, mods)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    h = _cdp_handle(app)
    if h:
        from seeu import cdp
        return cdp.key(h, key, *mods)

    def act():
        g = _geo(app)
        pid, _, _ = bg._prepare(app, g["x"] + g["w"] / 2, g["y"] + g["h"] / 2)
        bk.press(pid, key, mods)
    return _ladder(app, [("后台按键", act)], min_change=0.001)


def menu(app, *path):
    from seeu import safety
    try:
        safety.check_menu(path)
    except safety.Refused as ex:
        return dict(outcome="refused", route=None, tried=[], png=None, reason=str(ex))
    who = _pid(app) if bg.split_target(app)[1] else app   # 带「标题」的按进程号找菜单栏(同名多实例)
    return _ladder(app, [("菜单", lambda: _keep_front(app, lambda: ax.menu(who, *path)))], min_change=0.001)


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

    def act(ig):
        _cursor(app, "move", x0, y0, mode="real", force=True)
        from seeu import safety
        safety.check_point(x0, y0)
        ig.guarded(x0, y0, bg.split_target(app)[0], do=lambda: mi.qdrag(pts, hold_ms=hold_ms))
        _cursor(app, "move", *pts[-1], mode="real", force=True)
    if not real_allowed(allow):
        r = dict(outcome="refused", route=None, tried=[], png=None,
                 reason="拖动只能借用户的鼠标(macOS 没有后台拖动),设置.json「借用鼠标」= 关,没做。要拖请用户自己拖,或请用户把设置改成开")
        return _ask_user(r, "ask.drag") if real_mode() == "ask" else r
    return _ladder(app, [("真鼠标拖动", _real_mouse(app, act))])


# ---------------------------------------------------------------- 镜像固定动作(自带状态检查)
# ⌘1~⌘4 都是开关,状态会被上一次带过来;从 Spotlight 开的 App 按 Home 会落回 Spotlight 结果页(10-14 实测)。
SPOTLIGHT_MARKS = ("Top Hit", "Suggestions", "Siri Suggestions", "Search in App")


def _mirror_texts(app):
    return [i["text"] for i in see(app)["items"]]


def _in_spotlight(t):
    return any(m in t for m in SPOTLIGHT_MARKS)


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
    r = type(app, name, enter=True)
    time.sleep(1.5)
    t = _mirror_texts(app)
    if _in_spotlight(t):
        return {"outcome": "ineffective", "step": "回车后还在 Spotlight", "type": r}
    return {"outcome": "delivered", "texts": t[:10]}


# ---------------------------------------------------------------- 命令行

def _report(r):
    if isinstance(r, Exception):
        print(f"failed  {r}")
        return 1
    print(f"{r['outcome']}  路线={r.get('route')}  试过={r.get('tried')}  截图={r.get('png')}")
    if r.get("reason"):                 # 10-29 Skill:被拦/做不到时把「卡在…原因…怎么办」也打出来,给 AI 照着转述
        print(f"原因  {r['reason']}")
    return 0 if r["outcome"] == "delivered" else (3 if r["outcome"] == "refused" else 1)


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
