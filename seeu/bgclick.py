# -*- coding: utf-8 -*-
"""SeeU 第二级(实验中):后台把鼠标点击直接投给目标窗口 —— 不挪真鼠标、不抢前台。

🔴 用的是 SkyLight 私有接口,只当"加速层":系统升级可能失效,失效就退回真鼠标 + 让路 + 桌面锁。
做法照开源项目 Cua(trycua/cua,libs/cua-driver/rust/crates/platform-macos/src/input/{skylight,mouse}.rs)的公开代码,
不逆向任何闭源程序(10-13 用户定)。

一次点击 = mouseMoved(先让窗口知道指针在哪)→ mouseDown → mouseUp,每个事件都盖上:
  窗口内坐标(CGEventSetWindowLocation)、f1 点击次数、f3 按键号、f7 子类型、f51/f91/f92 窗口号、f58 点击组号、f40 目标 pid,
再用 SLEventPostToPid 投给目标进程。可选:附"事件认证"(auth)、先发"只聚焦不置前"记录(focus)。

用法:python3 -m seeu.bgclick <App 名> <屏幕x> <屏幕y> [--auth] [--raw]   (默认走 tap():聚焦 + 标题栏垫一下 + 点)
"""
import ctypes
import re
import ctypes.util
import json
import os
import sys
import time
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)

_SL = ctypes.CDLL("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight")
_CG = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
_OBJC = ctypes.CDLL(ctypes.util.find_library("objc"))
_CARBON = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_vp = ctypes.c_void_p
_CG.CGEventCreateMouseEvent.restype = _vp
_CG.CGEventCreateMouseEvent.argtypes = [_vp, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
_CG.CFRelease.argtypes = [_vp]


def _sym(lib, name, res, args):
    try:
        f = getattr(lib, name)
    except AttributeError:
        return None
    f.restype = res
    f.argtypes = args
    return f


SLEventPostToPid = _sym(_SL, "SLEventPostToPid", None, [ctypes.c_int, _vp])
SLEventSetIntegerValueField = _sym(_SL, "SLEventSetIntegerValueField", None, [_vp, ctypes.c_uint32, ctypes.c_int64])
CGEventSetWindowLocation = _sym(_SL, "CGEventSetWindowLocation", None, [_vp, CGPoint]) \
    or _sym(_CG, "CGEventSetWindowLocation", None, [_vp, CGPoint])
SLEventSetAuthenticationMessage = _sym(_SL, "SLEventSetAuthenticationMessage", None, [_vp, _vp])
SLPSPostEventRecordTo = _sym(_SL, "SLPSPostEventRecordTo", ctypes.c_int32, [_vp, _vp])
GetProcessForPID = _sym(_CARBON, "GetProcessForPID", ctypes.c_int32, [ctypes.c_int, _vp])

_OBJC.objc_getClass.restype = _vp
_OBJC.objc_getClass.argtypes = [ctypes.c_char_p]
_OBJC.sel_registerName.restype = _vp
_OBJC.sel_registerName.argtypes = [ctypes.c_char_p]
_OBJC.class_respondsToSelector.restype = ctypes.c_bool
_OBJC.class_respondsToSelector.argtypes = [_vp, _vp]
_msg_factory = ctypes.CFUNCTYPE(_vp, _vp, _vp, _vp, ctypes.c_int, ctypes.c_uint32)(
    ctypes.cast(_OBJC.objc_msgSend, _vp).value)

MOVED, LDOWN, LUP, LDRAG = 5, 1, 2, 6


def available():
    return bool(SLEventPostToPid and SLEventSetIntegerValueField and CGEventSetWindowLocation)


def _attach_auth(ev, pid):
    """附"事件认证":用 SkyLight 自己公开导出的工厂方法造(Cua 键盘路径的做法)。造不出来就不附。"""
    cls = _OBJC.objc_getClass(b"SLSEventAuthenticationMessage")
    sel = _OBJC.sel_registerName(b"messageWithEventRecord:pid:version:")
    if not cls or not SLEventSetAuthenticationMessage or not _OBJC.class_respondsToSelector(cls, sel):
        return False
    for off in (24, 32, 16):  # __CGEvent 里 SLSEventRecord* 的位置(Cua 注释:按系统版本探这几个偏移)
        rec = ctypes.c_void_p.from_address(ev + off).value
        if rec:
            msg = _msg_factory(cls, sel, rec, pid, 0)
            if msg:
                SLEventSetAuthenticationMessage(ev, msg)
                return True
            return False
    return False


def focus_without_raise(pid, wid):
    """给目标进程发一条"窗口获得焦点"记录,不把它提到前面(Cua/yabai 的公开做法)。"""
    if not (SLPSPostEventRecordTo and GetProcessForPID):
        return False
    psn = (ctypes.c_uint8 * 8)()
    if GetProcessForPID(pid, psn) != 0:
        return False
    buf = (ctypes.c_uint8 * 0xF8)()
    buf[0x04] = 0xF8
    buf[0x08] = 0x0D
    for i in range(4):
        buf[0x3C + i] = (wid >> (8 * i)) & 0xFF
    buf[0x8A] = 0x01
    return SLPSPostEventRecordTo(psn, buf) == 0


DRAG_SUBTYPE = {"down": 3, "drag": 0}   # 实验中:f7 子类型(3=触控,0=普通)


def _subtype(etype, drag):
    if etype == MOVED:
        return 0
    if etype == LDRAG:
        return DRAG_SUBTYPE["drag"]
    return DRAG_SUBTYPE["down"] if drag else 3


def _post(etype, pid, wid, sx, sy, wx, wy, click_state, group, auth, drag=False, delta=None):
    ev = _CG.CGEventCreateMouseEvent(None, etype, CGPoint(sx, sy), 0)
    if not ev:
        raise RuntimeError("建事件失败")
    try:
        CGEventSetWindowLocation(ev, CGPoint(wx, wy))
        for f, v in ((1, click_state), (3, 0), (7, _subtype(etype, drag)), (51, wid), (58, group),
                     (91, wid), (92, wid), (40, pid)):
            SLEventSetIntegerValueField(ev, f, v)
        if delta:  # f4/f5 = kCGMouseEventDeltaX/Y:真实拖动每步带位移
            SLEventSetIntegerValueField(ev, 4, int(round(delta[0])))
            SLEventSetIntegerValueField(ev, 5, int(round(delta[1])))
        if auth:
            _attach_auth(ev, pid)
        SLEventPostToPid(pid, ev)
    finally:
        _CG.CFRelease(ev)


# ---------------------------------------------------------------- 监看悬浮窗钩子
# 10-15 C-1.2:有的程序直接调这里(不走 seeu.act),悬浮窗要接在最底层才看得到。纯显示、有节流,任何异常吞掉。
# 关:seeu/设置.json「监看小窗」= 关,或环境变量 SEEU_NO_WATCH=1。
_W = {"on_t": 0.0, "on": True, "show_t": {}, "geo": {}}
WATCH_SHOW_EVERY_S = 1.0     # 同一窗口最多每秒发一次 show(高频连点约 7 下/秒,不能每下都查)


def set_step(text=None):
    """调用方说一句现在在做什么(如「录入第 5 行」),之后浏览器卡片上写「正在录入第 5 行」,换一句或传 None 才变回默认
    (正在点击 / 正在打字)。只影响浏览器的卡片(SeeU C-0.5,10-22:直接调 bgkey/bgclick 的程序卡片上看不到进度)。"""
    _W["user_step"] = str(text).strip() if text and str(text).strip() else None


def _watch_on():
    import json
    import os
    now = time.time()
    if now - _W["on_t"] > 2.0:
        _W["on_t"] = now
        try:
            with open(os.path.join(os.path.dirname(__file__), "设置.json"), encoding="utf-8") as f:
                v = str(json.load(f).get("监看小窗", "开")).strip()
        except Exception:
            v = "开"
        _W["on"] = not os.environ.get("SEEU_NO_WATCH") and v not in ("关", "off")
    return _W["on"]


# 10-21 C-0.2:浏览器窗口不弹画面框,弹浏览器卡片写这一步(直接调 bgclick/bgkey 填网页文档时,用户看到的是画面框、没有步骤)
BROWSERS = {"Safari", "Safari Technology Preview", "Google Chrome", "Microsoft Edge", "Brave Browser", "Arc",
            "Chromium", "Vivaldi", "Firefox", "Orion"}
_W["owner"] = {}       # 窗口号 -> App 名
_W["owner_pid"] = {}   # 进程号 -> App 名
_W["step_t"] = {}


def _owner_of_wid(wid):
    if wid not in _W["owner"]:
        import Quartz
        info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
        _W["owner"][wid] = info[0].get("kCGWindowOwnerName", "") if info else ""
    return _W["owner"][wid]


def watch_step(app, step, wid=None):
    """浏览器上的后台动作:悬浮标卡片写「正在 step」(同一步每秒最多发一次)。不是浏览器返回 False。纯显示,异常吞掉。
    wid = 正在操作的浏览器窗口号(SeeU C-0.3:卡片上「看画面」就播这个窗口;不知道就不传,按钮变灰)。"""
    if app not in BROWSERS:
        return False
    step = _W.get("user_step") or step          # 调用方 set_step 说过就用它的话
    try:
        if not _watch_on():
            return True
        now = time.time()
        last_step, last_t = _W["step_t"].get(app, (None, 0))
        # 同一步每秒最多一次;换了步骤也至少隔 0.3 秒(打字里夹着空格/回车别来回刷)
        if now - last_t > (WATCH_SHOW_EVERY_S if step == last_step else 0.3):
            _W["step_t"][app] = (step, now)
            from seeu_lib import watch_window as ww
            fn = getattr(ww, "browser", None)      # 长进程里可能是旧版 watch_window
            if fn and wid and "wid" in fn.__code__.co_varnames:
                fn(app, step, wid=int(wid))
            elif fn:
                fn(app, step)
            # 10-21:屏幕光圈也要亮(悬浮窗「被控提示」开着,或设置里光圈 = 全部);以前只有 seeu.act 和个别调用方自己点亮,直接调这层的没有
            from seeu import act
            act._halo("bg")
    except Exception:
        pass
    return True


def watch_pid(pid, step):
    """bgkey 用:按进程号找 App 名,是浏览器就写卡片步骤。"""
    try:
        if pid not in _W["owner_pid"]:
            from AppKit import NSRunningApplication
            a = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
            _W["owner_pid"][pid] = (a.localizedName() or "") if a else ""
        app = _W["owner_pid"][pid]
        wid = None
        if app in BROWSERS:      # 后台打字也知道是哪个窗口(打字前 tap 过的那个 = 主窗口)
            try:
                mw = main_window(app)
                wid = mw["id"] if mw else None
            except Exception:
                wid = None
        watch_step(app, step, wid)
    except Exception:
        pass


def _watch(wid, sx=None, sy=None, win_xy=None, step="点击"):
    try:
        if not _watch_on():
            return
        if watch_step(_owner_of_wid(wid), step, wid):
            return
        from seeu_lib import watch_window as ww
        now = time.time()
        if now - _W["show_t"].get(wid, 0) > WATCH_SHOW_EVERY_S or _W.get("mode") != "bg":
            _W["show_t"][wid] = now
            _W["mode"] = "bg"
            ww.show(wid, "bg") if "mode" in ww.show.__code__.co_varnames else ww.show(wid)
            import Quartz
            info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
            if info:
                b = info[0]["kCGWindowBounds"]
                _W["geo"][wid] = (b["X"], b["Y"], b["Width"], b["Height"])
        g = _W["geo"].get(wid)
        if sx is not None and g and g[2] and g[3]:
            fx, fy = (sx - g[0]) / g[2], (sy - g[1]) / g[3]
            if fy * g[3] > 30:                # 标题栏"垫一下"那下不画
                ww.mark("click", fx, fy)
    except Exception:
        pass


# ---------------------------------------------------------------- 让路:用户开着的系统浮层
# 10-20 C-0.2:我们发的「按下」会被系统当成"在浮层外点了一下",把用户开着的 Apps 面板(Siri 进程层 23)、菜单等收掉
# (实测见 SeeU-相关要点.md 10-20 节)。所以按下前查一眼:有就等它关,最多 OVERLAY_WAIT_S 秒,超时照点并记进 last_overlay。
# 查一次约 1ms,高频连点也能每下查。超时的那个窗口记住,以后不再为它等(防常驻的高层窗口每下都卡)。
# 10-24 C-0.7 用户在场实测:只有 Apps、Spotlight(都是 Siri 进程层 23)会被后台点击收掉;控制中心、通知中心(含横幅)、
# 音量/蓝牙/专注模式/天气等顶部菜单都不受影响 → 只等 OVERLAY_OWNERS 里的,其余白等(曾因通知横幅停手)。
OVERLAY_WAIT_S = 15.0
OVERLAY_LAYERS = (8, 999)          # 模态面板 8 … 弹出菜单 101 …;3=浮动面板(悬浮窗等常驻)、1000+=屏保层(代理光标)、输入法超高层都不算
OVERLAY_BASELINE = {("Dock", "Dock"), ("Window Server", "Menubar")}   # (进程, 窗口名):平时就在
OVERLAY_OWNERS = {"Siri", "Spotlight"}   # 只等这些进程的浮层(Apps、Spotlight;老系统 Spotlight 是自己的进程)
_OV = {"ignore": set()}
last_overlay = None                 # 最近一次等浮层的结果:dict(waited=秒, overlays=[...], timeout=bool);没等过是 None


def user_overlays(exclude_pid=None):
    """屏幕上用户开着的系统浮层:[(进程名, 窗口名, 层级, 窗口号)]。"""
    import Quartz
    me = os.getpid()
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
        lv = w.get("kCGWindowLayer", 0)
        if not (OVERLAY_LAYERS[0] <= lv <= OVERLAY_LAYERS[1]) or w.get("kCGWindowAlpha", 1) <= 0:
            continue
        owner, name, wn = w.get("kCGWindowOwnerName") or "", w.get("kCGWindowName") or "", int(w["kCGWindowNumber"])
        pid = int(w.get("kCGWindowOwnerPID", 0))
        if owner not in OVERLAY_OWNERS or (owner, name) in OVERLAY_BASELINE or pid in (me, exclude_pid) or wn in _OV["ignore"]:
            continue
        b = w.get("kCGWindowBounds") or {}
        if b.get("Width", 0) < 8 or b.get("Height", 0) < 8:
            continue
        out.append((owner, name, lv, wn))
    return out


OVERLAY_SNAP_DIR = home("seeu_overlay")   # 等浮层时的取证(截图 + 窗口信息),10-23 加
OVERLAY_SNAP_KEEP = 40                                           # 最多留这么多个文件,超了删最旧的


def snap_overlays(ov):
    """🔴 10-23 C-0.6:开始等浮层时,把每个浮层窗口单独截一张(只截它自己,不截整屏)+ 记 App/层级/范围/进程号,
    存 OVERLAY_SNAP_DIR,打印路径,好事后知道是镜像转发的手机通知还是 Mac 上哪个 App。任何异常吞掉,绝不影响点击。"""
    try:
        import Quartz
        from seeu_lib import sck_capture
        os.makedirs(OVERLAY_SNAP_DIR, exist_ok=True)
        info = {int(w["kCGWindowNumber"]): w for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []}
        stamp = time.strftime("%m%d-%H%M%S")
        for owner, name, lv, wn in ov:
            base = os.path.join(OVERLAY_SNAP_DIR, f"{stamp}-{re.sub(r'[^0-9A-Za-z]+', '_', owner)}-{wn}")
            w = info.get(wn, {})
            meta = dict(time=stamp, owner=owner, name=name, layer=lv, window=wn, pid=w.get("kCGWindowOwnerPID"),
                        bounds=w.get("kCGWindowBounds") and dict(w["kCGWindowBounds"]), alpha=w.get("kCGWindowAlpha"),
                        shot=None)
            try:
                if sck_capture.capture_window(wn, base + ".png"):
                    meta["shot"] = base + ".png"
            except Exception as e:
                meta["shot_error"] = str(e)
            json.dump(meta, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
            print(f"[SeeU] 浮层取证:{owner}「{name}」层级{lv} → {base}.json" + (" + .png" if meta["shot"] else "(截图失败)"),
                  file=sys.stderr, flush=True)
        files = sorted(os.listdir(OVERLAY_SNAP_DIR))
        for f in files[:-OVERLAY_SNAP_KEEP]:
            os.remove(os.path.join(OVERLAY_SNAP_DIR, f))
    except Exception:
        pass


def wait_overlays(exclude_pid=None, timeout=None):
    """有用户开着的系统浮层就等它关,最多 timeout 秒(默认 OVERLAY_WAIT_S)。返回等了多少秒;查不了就当没有。"""
    global last_overlay
    try:
        ov = user_overlays(exclude_pid)
    except Exception:
        return 0.0
    if not ov:
        return 0.0
    timeout = OVERLAY_WAIT_S if timeout is None else timeout
    t0 = time.time()
    from seeu.i18n import T
    print(T("overlay.wait", what=", ".join(o[0] + (("「" + o[1] + "」") if o[1] else "") for o in ov), secs=f"{timeout:.0f}"),
          file=sys.stderr, flush=True)
    snap_overlays(ov)
    while ov and time.time() - t0 < timeout:
        time.sleep(0.2)
        try:
            ov = user_overlays(exclude_pid)
        except Exception:
            ov = []
    waited = time.time() - t0
    last_overlay = dict(waited=round(waited, 1), overlays=[o[:3] for o in ov], timeout=bool(ov))
    if ov:
        _OV["ignore"].update(o[3] for o in ov)
        print(T("overlay.timeout", secs=f"{waited:.0f}", what=", ".join(o[0] for o in ov)), file=sys.stderr, flush=True)
    return waited


# 10-24 C-0.9:隐身浏览器被用户叫出来(程序坞图标 / 看画面)以后会抢键盘,藏回去也救不回来,只能重开(10-22 实测)。
# seeu.stealth 的看门狗发现被叫出来,就把 pid 记进来;之后往这个 pid 点击/按键一律抛 CalledOut,等 stealth.restart 重开。
CALLED_OUT = {}             # pid -> (App 名, 发现时间)


class CalledOut(RuntimeError):
    """隐身浏览器被叫出来过,SeeU 已停手。重开:python3 -m seeu.stealth restart <浏览器>。"""


def _safety(pid):
    """安全底线硬拦(终端、系统权限弹窗、Claude 自己…,见 seeu/safety.py)。长进程里没有这个模块就跳过。"""
    try:
        from seeu import safety
    except ImportError:
        return
    safety.check_pid(pid)


def check_called_out(pid):
    hit = CALLED_OUT.get(pid)
    if hit:
        b = "Chrome" if "Chrome" in hit[0] else hit[0]
        raise CalledOut(f"卡在:往 {hit[0]} 点击/按键 原因:{hit[0]} 被叫出来过(藏回去也会抢键盘),SeeU 已停手 "
                        f"怎么办:运行 python3 -m seeu.stealth restart {b} 重开(标签照原样开回来)")


def click(pid, wid, win_xy, sx, sy, auth=False, focus=False, hold=0.05):
    """在屏幕点 (sx,sy) 处后台点一下。win_xy = 目标窗口左上角屏幕坐标(算窗口内坐标用)。
    按下前先等用户开着的系统浮层关掉(wait_overlays,有上限)。"""
    check_called_out(pid)
    _safety(pid)
    if not available():
        raise RuntimeError("SkyLight 私有接口不可用(系统可能升级改了),退回真鼠标")
    wait_overlays(pid)
    _watch(wid, sx, sy, win_xy)
    wx, wy = sx - win_xy[0], sy - win_xy[1]
    group = int(time.time() * 1000) & 0x7FFFFFFF
    if focus:
        focus_without_raise(pid, wid)
        time.sleep(0.03)
    _post(MOVED, pid, wid, sx, sy, wx, wy, 0, group, auth)
    time.sleep(0.02)
    _post(LDOWN, pid, wid, sx, sy, wx, wy, 1, group, auth)
    time.sleep(hold)
    _post(LUP, pid, wid, sx, sy, wx, wy, 1, group, auth)


class TapNoEffect(RuntimeError):
    """verify=True 时点完画面一点没变:后台点击多半被丢了(SLEventPostToPid 没有返回值,发出去 ≠ 点进去)。
    调用方接住后退回系统鼠标;现场已存进 TAP_FAIL_DIR。"""


def tap(app_name, sx, sy, prime=None, auth=False, step=None, verify=False, settle=False):
    """推荐入口:后台点 App 窗口里的屏幕点 (sx,sy)。step = 这一步在做什么(浏览器卡片上写,同 set_step)。
    verify(10-27 C-1.0 Beta1,实测「假成功」):点前截一张,点完最多等 TAP_VERIFY_S 秒看画面变没变;
    一点没变 → 记现场、抛 TapNoEffect(调用方退回系统鼠标)。只给「点了画面肯定会变」的按钮开(翻页、进入);
    🔴 页面慢到超时才动的,退回系统鼠标会再点一下,点第二下有害的地方别开。截不到图就不核实(照旧当成功)。
    settle(10-30 实测:刚关完弹窗/面板马上点,两次「假成功」):点前每 SETTLE_GAP_S 截一张,前后两张几乎一样(< SETTLE_STILL)
    才点;最多等 SETTLE_MAX_S 秒,一直在动(转盘灯、视频)也照点。给「刚关弹窗、页面还在收」的那一下开。截不到图就直接点。
    prime(默认按 PRIME_APPS 定):先"只聚焦不置前" + 在标题栏(窗口顶部正中,内容区外)垫一下,吃掉"激活点击",再点目标。
    10-13 实测 iPhone 镜像:不垫的话聚焦后第一下点击会被吃掉(跟真鼠标点没激活的窗口一样);垫了之后 3/3 一次点进。
    auth 实测对镜像点击不需要。返回 (pid, wid)。"""
    if step:
        set_step(step)
    pid, wid, xy = _prepare(app_name, sx, sy, prime)
    before = _wait_settled(wid) if settle else None
    if verify and before is None:
        before = _grab_gray(wid)
    elif not verify:
        before = None
    click(pid, wid, xy, sx, sy, auth=auth, focus=True)
    if before is not None:
        _verify_tap(app_name, pid, wid, sx, sy, before)
    if split_target(app_name)[0] in PRIME_APPS:
        _tapped_mark(pid)   # 10-23 C-0.6:点过 → 下次滚动前要先"小拖动"(见 scroll)
    if split_target(app_name)[0] in BROWSERS:     # 10-21:记下来,第一次打字前 bgkey 核实焦点进没进(没进就在这再点一次)
        PENDING_TAP[pid] = (app_name, sx, sy, time.time())
    return pid, wid


TAP_VERIFY_S = 2.0          # 点完最多等这么久看画面动没动
SETTLE_MAX_S = 1.5          # 点前等画面稳定最多这么久(硬上限,到了照点)
SETTLE_GAP_S = 0.15         # 隔这么久截一张比
SETTLE_STILL = 0.002        # 前后两张变化像素比例低于这个算稳定(没点进的图互相 0.0000%,弹窗收起动画远大于这个)
TAP_CHANGE_MIN = 0.003      # 变化像素比例超过这个算点进去了。10-27 实测:没点进的 3 张图互相 0.0000%,点进去 48%
TAP_FAIL_DIR = home("seeu_tapfail")   # 没点进的现场(前后图 + 诊断),只留最近 TAP_FAIL_KEEP 组
TAP_FAIL_KEEP = 10


def _wait_settled(wid):
    """点前等画面稳定(tap settle=True):返回最后一张灰度图(给 verify 当「点前」那张);截不到图返回 None(调用方直接点)。"""
    t0 = time.time()
    prev = _grab_gray(wid)
    while prev is not None and time.time() - t0 < SETTLE_MAX_S:
        time.sleep(SETTLE_GAP_S)
        cur = _grab_gray(wid)
        if cur is None:
            return prev
        r = _change_ratio(prev, cur)
        prev = cur
        if r is not None and r < SETTLE_STILL:
            return cur
    if prev is not None:
        print(f"[SeeU] 点前等画面稳定 {SETTLE_MAX_S} 秒还在动,照点")
    return prev


def _verify_tap(app_name, pid, wid, sx, sy, before):
    t0, ratio, after = time.time(), None, None
    while time.time() - t0 < TAP_VERIFY_S:
        time.sleep(0.25)
        after = _grab_gray(wid)
        if after is None:
            return                                  # 截不到就不判(别因为截图坏了把好点击当失败)
        ratio = _change_ratio(before, after)
        if ratio is None or ratio >= TAP_CHANGE_MIN:
            return
    path = _tap_fail_snap(app_name, pid, wid, sx, sy, before, after, ratio)
    raise TapNoEffect(f"后台点了 ({sx:.0f},{sy:.0f}) 等 {TAP_VERIFY_S:.0f} 秒画面没变"
                      f"(变化 {ratio * 100:.2f}%),多半没点进;现场 {path}")


def _tap_diag(pid, wid, sx, sy):
    """没点进时的现场:目标窗口在不在屏、点上最上层是谁、前台 App、显示器。"""
    import Quartz
    d = dict(t=time.strftime("%Y-%m-%d %H:%M:%S"), pt=[round(sx), round(sy)], pid=pid, wid=wid)

    def brief(w):
        b = w.get("kCGWindowBounds") or {}
        return dict(owner=w.get("kCGWindowOwnerName"), pid=w.get("kCGWindowOwnerPID"), id=w.get("kCGWindowNumber"),
                    name=w.get("kCGWindowName"), layer=w.get("kCGWindowLayer"), alpha=w.get("kCGWindowAlpha"),
                    onscreen=bool(w.get("kCGWindowIsOnscreen")),
                    bounds=[int(b.get(k, 0)) for k in ("X", "Y", "Width", "Height")])
    try:
        tw = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
        d["target"] = brief(tw[0]) if tw else None
        top = []
        for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
            b = w.get("kCGWindowBounds") or {}
            if b.get("X", 0) <= sx < b.get("X", 0) + b.get("Width", 0) and b.get("Y", 0) <= sy < b.get("Y", 0) + b.get("Height", 0) \
                    and w.get("kCGWindowAlpha", 1) > 0:
                top.append(brief(w))
            if len(top) >= 3:
                break
        d["at_point"] = top                         # 从上往下前 3 个
    except Exception as e:
        d["win_err"] = repr(e)
    try:
        from AppKit import NSWorkspace
        fa = NSWorkspace.sharedWorkspace().frontmostApplication()
        d["front"] = str(fa.localizedName()) if fa else None
    except Exception as e:
        d["front_err"] = repr(e)
    try:
        err, ids, n = Quartz.CGGetActiveDisplayList(8, None, None)
        d["displays"] = [dict(id=int(i), w=int(Quartz.CGDisplayPixelsWide(i)), h=int(Quartz.CGDisplayPixelsHigh(i)),
                              main=bool(Quartz.CGDisplayIsMain(i)), asleep=bool(Quartz.CGDisplayIsAsleep(i)))
                         for i in list(ids)[:n]]
    except Exception as e:
        d["disp_err"] = repr(e)
    try:
        d["overlays"] = [dict(owner=o.get("owner"), layer=o.get("layer")) if isinstance(o, dict) else str(o)
                         for o in (user_overlays(pid) or [])]
    except Exception as e:
        d["ov_err"] = repr(e)
    return d


def _tap_fail_snap(app_name, pid, wid, sx, sy, before, after, ratio):
    """存一组没点进的现场,返回文件夹;任何异常吞掉。"""
    import json
    base = os.path.join(TAP_FAIL_DIR, time.strftime("%m%d-%H%M%S"))
    try:
        os.makedirs(base, exist_ok=True)
        d = _tap_diag(pid, wid, sx, sy)
        d.update(app=app_name, ratio=ratio, wait_s=TAP_VERIFY_S)
        with open(os.path.join(base, "diag.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        import cv2
        cv2.imwrite(os.path.join(base, "before.png"), before)
        if after is not None:
            cv2.imwrite(os.path.join(base, "after.png"), after)
        print(f"[SeeU] 后台点击没点进,现场存在 {base}", file=sys.stderr, flush=True)
        olds = sorted(os.listdir(TAP_FAIL_DIR))
        import shutil
        for x in olds[:-TAP_FAIL_KEEP]:
            shutil.rmtree(os.path.join(TAP_FAIL_DIR, x), ignore_errors=True)
    except Exception:
        pass
    return base


# 10-21 C-0.2:浏览器上点完,焦点偶尔没进输入框(自动测试 7 次有 2 次),后面打字全落空。
# tap() 记下"刚点过哪";bgkey 第一次打字前核实,没进就原地再点一次,还不行就报错停手。按过别的键就作废(免得点回旧格子)。
PENDING_TAP = {}            # pid -> (app_name, sx, sy, 时间)
PENDING_TAP_S = 15.0        # 点完多久内的第一次打字才核实

# 要"标题栏垫一下"的 App:聚焦后第一下点击会被吃掉、且标题栏是空的(点了没副作用)。
# 🔴 普通文档类 App 别垫:「文本编辑」标题栏正中是文档名,点了会弹改名小窗(10-13 踩过);它们只聚焦就够。
PRIME_APPS = {"iPhone Mirroring"}
TAPPED_FILE = home("seeu_tapped.json")   # {pid: 最近一次点击时间};有的调用方点/滚各开子进程,标记得落文件


def _tapped_mark(pid):
    try:
        os.makedirs(os.path.dirname(TAPPED_FILE), exist_ok=True)
        try:
            d = json.load(open(TAPPED_FILE))
        except Exception:
            d = {}
        now = time.time()
        d = {k: v for k, v in d.items() if now - v < 3600}      # 一小时前的旧记录丢掉(进程早没了)
        d[str(pid)] = now
        json.dump(d, open(TAPPED_FILE, "w"))
    except Exception:
        pass


def _tapped_take(pid):
    """点过且还没解开过 → True 并清掉标记(只在"点过之后第一次滚"返回 True)。"""
    try:
        d = json.load(open(TAPPED_FILE))
        if str(pid) in d:
            del d[str(pid)]
            json.dump(d, open(TAPPED_FILE, "w"))
            return True
    except Exception:
        pass
    return False


def _wait_mouse_up(timeout=3.0):
    """用户正按着鼠标键时,别往标题栏发"按下":系统可能把两者混成"拖标题栏",把窗口拖到用户鼠标那儿
    (10-14 跨桌面实测疑似:镜像闪到用户桌面一下、位置被挪)。等松开,最多 timeout 秒,超时照做。"""
    import Quartz
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not any(Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState, b) for b in (0, 1, 2)):
            return True
        time.sleep(0.05)
    return False


def _prepare(app_name, sx, sy, prime=None):
    """找窗口 + 聚焦(+ PRIME_APPS 里的再在标题栏垫一下)。返回 (pid, wid, 窗口左上角)。"""
    if prime is None:
        prime = split_target(app_name)[0] in PRIME_APPS
    hit = window_of(app_name, sx, sy)
    if not hit:
        raise RuntimeError(f"{app_name} 在 ({sx:.0f},{sy:.0f}) 没有窗口")
    pid, wid, xy = hit
    check_called_out(pid)
    _safety(pid)
    _watch(wid)
    if prime and not _wait_mouse_up():
        # 🔴 SeeU C-0.4(10-22 用户报:拖悬浮标时镜像窗口被一起拖走):用户按着鼠标 3 秒还没松 = 多半在拖东西,
        # 这时往标题栏发"按下"会被系统混成"拖标题栏" → 不垫了,只聚焦(第一下点击可能被吃掉,调用方核实会重试)
        print("[SeeU] 你正按着鼠标,这次不在镜像标题栏垫一下", file=sys.stderr)
        prime = False
    if prime:
        import Quartz
        b = next(w["kCGWindowBounds"] for w in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll, 0) if int(w["kCGWindowNumber"]) == wid)
        click(pid, wid, xy, b["X"] + b["Width"] / 2, b["Y"] + 12, focus=True)
        time.sleep(0.3)
    else:
        focus_without_raise(pid, wid)
        time.sleep(0.03)
    return pid, wid, xy


def drag(app_name, pts, hold_ms=0, step_ms=280, prime=None):
    """🔴 10-13 实测镜像里不生效(macOS 没有后台拖动的路,Cua 也拒绝),拖动请走真鼠标;留着做对照。
    后台沿路径拖(屏幕点坐标)。hold_ms=0 快速划(翻页/上划);>0 先长按再拖(拖图标、手势解锁)。
    事件节奏照 seeu_lib.mac_input.qdrag(真鼠标版已在镜像里验证过)。"""
    x0, y0 = pts[0]
    pid, wid, xy = _prepare(app_name, x0, y0, prime)
    group = int(time.time() * 1000) & 0x7FFFFFFF
    last = [x0, y0]

    def P(t, x, y, cs=1):
        d = (x - last[0], y - last[1]) if t == LDRAG else None
        _post(t, pid, wid, x, y, x - xy[0], y - xy[1], cs, group, False, drag=True, delta=d)
        last[:] = [x, y]
    wait_overlays(pid)
    P(MOVED, x0, y0, 0)
    time.sleep(0.2)
    P(LDOWN, x0, y0)
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
        for _ in range(3):
            P(LDRAG, x0, y0)
            time.sleep(0.05)
    cx, cy = x0, y0
    for nx, ny in pts[1:]:
        frames = max(6, int(max(abs(nx - cx), abs(ny - cy), 1) / 12))
        for i in range(1, frames + 1):
            t = i / frames
            P(LDRAG, cx + (nx - cx) * t, cy + (ny - cy) * t)
            time.sleep((step_ms / 1000.0) / frames)
        if hold_ms:
            for _ in range(2):
                P(LDRAG, nx, ny)
                time.sleep(0.06)
        cx, cy = nx, ny
    time.sleep(0.08)
    P(LUP, cx, cy)
    return pid, wid


def long_press(app_name, sx, sy, ms=900, prime=None):
    """后台长按。"""
    pid, wid, xy = _prepare(app_name, sx, sy, prime)
    click(pid, wid, xy, sx, sy, hold=ms / 1000.0)
    return pid, wid


def scroll(app_name, sx, sy, dy, dx=0, steps=6, prime=None, prime_at=None):
    """后台在 (sx,sy) 处滚动,dy 像素(负数 = 内容往上走 = 往下翻)。分 steps 次发,像触控板。
    🔴 镜像被切到前台过、再切走之后,某些 App 里的弹出面板滚动会卡死:后台发的、往系统发的、借真光标瞬移过去发的全不动,
    等两分钟也不好;用户亲手滚能滚,而且滚过之后后台也恢复。SeeU C-0.4(10-22)查清:缺的是"鼠标从窗口外移进来"——
    往镜像进程发一串从窗口外到滚动点的鼠标移动就解开(3/3,不碰真光标)。所以滚镜像前先 _move_in。
    (补发滚动取消/惯性结束、后台点面板都没用;关面板重开也能解。)调用方滚完照样要核实画面变没变。
    prime_at=(x,y)(屏幕点,10-24 C-0.8):"点过之后第一次滚"补的那下小拖动默认落在滚动点上,起终点同一处 = 对列表就是一次点击
    (10-24 实测:弹出面板里误点了任务行、跳进别的 App)。调用方给一个面板里**没有可点东西的空白点**,补拖动就落在那里;不给 = 落滚动点。
    10-24 起补拖动只在"点过之后第一次滚、而且滚完画面没变"时才做(见下);能滚的列表不补,不会误点。"""
    pid, wid, xy = _prepare(app_name, sx, sy, prime)
    if split_target(app_name)[0] not in PRIME_APPS:
        _wheel(pid, wid, xy, sx, sy, dy, dx, steps)
        return pid, wid
    _move_in(pid, wid, xy, sx, sy)
    if not _tapped_take(pid):
        _wheel(pid, wid, xy, sx, sy, dy, dx, steps)
        return pid, wid
    # 🔴 SeeU C-0.6(10-23 真机复现):某些 App 的弹出面板里后台点过任何一下,之后后台滚动全卡死(关面板重开才好)——
    # 10-14 起面板滚不动的真因(打开面板后点过里面的标签)。补一个来回小触摸拖动就解开(2/2),长按一下也行,
    # 按住时长、补 LUP、再移动、再移入都没用。
    # 🔴 10-24 C-0.8(实测 + 用户定):那下补拖动起终点同一处,对列表 = 一次点击,弹出面板里误点任务行跳进了别的 App。
    # 改成"点过之后第一次滚"先正常滚,滚前滚后截图对比;画面变了 = 没卡,不补拖动;没变才补拖动(落 prime_at 或滚动点)再滚一次。
    # 截不到图就不补(宁可滚不动交给调用方的兜底,也不冒误点的险)。
    before = _grab_gray(wid)
    _wheel(pid, wid, xy, sx, sy, dy, dx, steps)
    if before is None:
        print("[SeeU] 点过后第一次滚:截不到图,不补拖动", file=sys.stderr)
        return pid, wid
    time.sleep(SCROLL_SETTLE_S)
    after = _grab_gray(wid)
    ratio = _change_ratio(before, after) if after is not None else None
    _scroll_snap(before, after, ratio)
    print(f"[SeeU] 点过后第一次滚:画面变化 {'?' if ratio is None else f'{ratio * 100:.2f}%'}"
          f"(≥{SCROLL_CHANGE_MIN * 100:.0f}% 算滚动了)", file=sys.stderr, flush=True)
    if ratio is None or ratio >= SCROLL_CHANGE_MIN:
        return pid, wid
    px, py = prime_at if prime_at else (sx, sy)
    print(f"[SeeU] 点过后第一次滚画面没变,补一下小拖动解卡({'调用方给的空白点' if prime_at else '滚动点'})再滚", file=sys.stderr)
    drag(app_name, [(px, py), (px, py - 40), (px, py)], step_ms=80)
    time.sleep(0.3)
    _move_in(pid, wid, xy, sx, sy)
    _wheel(pid, wid, xy, sx, sy, dy, dx, steps)
    return pid, wid


SCROLL_SETTLE_S = 0.5        # 滚完等画面停下再截(滚动有惯性)
SCROLL_CHANGE_MIN = 0.02     # 变化像素比例超过这个算"滚动了"。10-24 弹出面板实测:两张没滚的图只差 0.01%;
                             # 原来用 0.3%(同 act._ladder)可能被面板上的小动画/点按高亮顶过去,误判成滚了、不补拖动。真滚几百像素整片都变。
SCROLL_SNAP_DIR = home("seeu_scroll")   # 点过后第一次滚的前后对比图(排查用,只留最近 SCROLL_SNAP_KEEP 组)
SCROLL_SNAP_KEEP = 10


def _wheel(pid, wid, xy, sx, sy, dy, dx, steps):
    import Quartz
    for _ in range(steps):
        ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2,
                                                  int(dy / steps), int(dx / steps))
        Quartz.CGEventSetLocation(ev, (sx, sy))
        p = ev.__c_void_p__().value
        CGEventSetWindowLocation(p, CGPoint(sx - xy[0], sy - xy[1]))
        for f, v in ((51, wid), (91, wid), (92, wid), (40, pid)):
            SLEventSetIntegerValueField(p, f, v)
        SLEventPostToPid(pid, p)
        time.sleep(0.03)


def _grab_gray(wid):
    """截窗口(ScreenCaptureKit,不触发 iOS 截屏弹窗)→ 灰度图,去掉顶部 12%(状态栏时钟会自己变)。失败返回 None。"""
    try:
        import cv2
        import tempfile
        from seeu_lib import sck_capture
        fd, png = tempfile.mkstemp(suffix=".png", prefix="seeu_scroll_")
        os.close(fd)
        try:
            if not sck_capture.capture_window(wid, png):
                return None
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
        finally:
            try:
                os.remove(png)
            except OSError:
                pass
        if img is None:
            return None
        return img[int(img.shape[0] * 0.12):]
    except Exception:
        return None


def _change_ratio(a, b):
    """两张灰度图变化像素的比例;尺寸不同算全变(1.0);出错返回 None。"""
    try:
        import cv2
        import numpy as np
        if a.shape != b.shape:
            return 1.0
        return float(np.count_nonzero(cv2.absdiff(a, b) > 25)) / a.size
    except Exception:
        return None


def _scroll_snap(before, after, ratio):
    """存一组前后图 + 变化比例,任何异常吞掉。"""
    try:
        import cv2
        os.makedirs(SCROLL_SNAP_DIR, exist_ok=True)
        base = os.path.join(SCROLL_SNAP_DIR, time.strftime("%m%d-%H%M%S") + ("" if ratio is None else f"-{ratio * 100:.2f}pct"))
        cv2.imwrite(base + "-a.png", before)
        if after is not None:
            cv2.imwrite(base + "-b.png", after)
        files = sorted(os.listdir(SCROLL_SNAP_DIR))
        for f in files[:-2 * SCROLL_SNAP_KEEP]:
            os.remove(os.path.join(SCROLL_SNAP_DIR, f))
    except Exception:
        pass


def _move_in(pid, wid, xy, sx, sy, n=15):
    """往进程发一串"鼠标从窗口左边外面移到 (sx,sy)"(不碰真光标),让镜像当成鼠标刚进来(SeeU C-0.4,见 scroll)。约 0.3 秒。"""
    import Quartz
    ox = xy[0] - 60
    for i in range(n + 1):
        x = ox + (sx - ox) * i / n
        ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x, sy), 0)
        p = ev.__c_void_p__().value
        CGEventSetWindowLocation(p, CGPoint(x - xy[0], sy - xy[1]))
        for f, v in ((51, wid), (91, wid), (92, wid), (40, pid)):
            SLEventSetIntegerValueField(p, f, v)
        SLEventPostToPid(pid, p)
        time.sleep(0.02)
    time.sleep(0.03)


def split_target(app_name):
    """目标写法:"应用名" 或 "应用名「窗口标题」"(10-14:同一应用开了好几个窗口/实例时指定其中一个,
    如 BlueStacks 多开里的 "BlueStacks「助手」")。返回 (应用名, 标题或 None)。"""
    m = re.match(r"^(.*?)「(.*)」$", app_name or "")
    return (m.group(1), m.group(2)) if m else (app_name, None)


def _match(w, app_name):
    owner, title = split_target(app_name)
    return w.get("kCGWindowOwnerName") == owner and w.get("kCGWindowLayer", 0) == 0 and \
        (title is None or (w.get("kCGWindowName") or "") == title)


def main_window(app_name, min_w=50, min_h=50):
    """App 的主窗口(面积最大的普通窗口),**包括不在当前桌面的**。返回 dict(x,y,w,h,id,pid,onscreen) 或 None。
    app_name 可写 "应用名「窗口标题」" 只认那个标题的窗口。"""
    import Quartz
    cand = []
    owner, title = split_target(app_name)
    from seeu_lib import mac_input as _mi
    # 跑到一半的长进程可能早 import 了旧版 mac_input(没有这个常量),带默认值兜底(10-15 撞上过)
    HIDDEN_WINDOWS = getattr(_mi, "HIDDEN_WINDOWS", {"Welcome to iPhone Mirroring"})
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, 0) or []:
        if not _match(w, app_name) or (w.get("kCGWindowName") or "") in HIDDEN_WINDOWS:
            continue
        b = w.get("kCGWindowBounds") or {}
        if b.get("Width", 0) < min_w or b.get("Height", 0) < min_h:
            continue
        cand.append(dict(x=int(b["X"]), y=int(b["Y"]), w=int(b["Width"]), h=int(b["Height"]),
                         id=int(w["kCGWindowNumber"]), pid=int(w["kCGWindowOwnerPID"]),
                         onscreen=bool(w.get("kCGWindowIsOnscreen")), name=w.get("kCGWindowName") or ""))
    if not cand:
        return None
    # 镜像还有个隐藏的「Welcome to iPhone Mirroring」大窗,同名窗口优先
    # 🔴 10-15:同名窗口排最前(隐藏的「Welcome」大窗有时报在屏,见 seeu_lib.mac_input.win_geo)
    cand.sort(key=lambda d: (d["name"] == (title or owner), d["onscreen"], d["w"] * d["h"]), reverse=True)
    return cand[0]


def window_of(app_name, sx, sy):
    """找 App 在 (sx,sy) 那一点上的窗口:返回 (pid, wid, (x,y))。"""
    import Quartz
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
        if not _match(w, app_name):
            continue
        b = w["kCGWindowBounds"]
        if b["X"] <= sx < b["X"] + b["Width"] and b["Y"] <= sy < b["Y"] + b["Height"]:
            return int(w["kCGWindowOwnerPID"]), int(w["kCGWindowNumber"]), (b["X"], b["Y"])
    # 不在当前桌面(切了桌面)时屏上列表里没有它 → 用全部窗口里的主窗口(点要落在它范围内)
    m = main_window(app_name)
    if m and m["x"] <= sx < m["x"] + m["w"] and m["y"] <= sy < m["y"] + m["h"]:
        return m["pid"], m["id"], (m["x"], m["y"])
    return None


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 3:
        print(__doc__)
        return 2
    auth, raw = "--auth" in a, "--raw" in a
    a = [x for x in a if not x.startswith("--")]
    app, sx, sy = a[0], float(a[1]), float(a[2])
    try:
        if raw:  # 只发一次点击,不聚焦不垫(调试用)
            hit = window_of(app, sx, sy)
            if not hit:
                raise RuntimeError(f"{app} 在 ({sx:.0f},{sy:.0f}) 没有窗口")
            pid, wid, xy = hit
            click(pid, wid, xy, sx, sy, auth=auth)
        else:
            pid, wid = tap(app, sx, sy, auth=auth)
    except RuntimeError as ex:
        print("失败:", ex)
        return 1
    print(f"已后台点 {app} pid={pid} 窗口={wid} 屏幕({sx:.0f},{sy:.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
