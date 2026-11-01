#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
input_guard.py —— 真实鼠标/键盘输入之前的"把关层"。

适用场景:点击要对着 Mac 窗口走真实鼠标的情形(如 iPhone 镜像)。ADB 控制的安卓设备/模拟器不挪 Mac 鼠标,用不上。
只用苹果公开接口,只读检查,本模块自己不发任何输入事件。2026-10-01 新建(3.0 输入层第一步),
设计参考官方 Computer Use 的把关思路:用户在用就等、目标被挡就不点、密码框不打字、能试运行。

用法(坐标一律是桌面点坐标,原点主屏左上,跟 mac_input.px_to_pt() 输出一致):
    from seeu_lib import input_guard as g
    g.preflight(x, y, owner="iPhone Mirroring")   # 不通过抛 GuardBlocked / GuardTimeout
    if not g.dry_run():
        ...真的发点击...
    g.note_injected()                              # 发完记一笔,不然下次会把自己的点击当成用户在动

    或者一步到位: g.guarded(x, y, owner, do=lambda: 发点击())

    with g.FrontState(avoid_owner="iPhone Mirroring"):   # 一整段流程结束后,把前台应用和鼠标还原
        ...一串点击...

命令行(都是只读,不点任何东西):
    python3 -m seeu_lib.input_guard status               用户空闲秒数/是否在用/密码框/前台应用/鼠标位置
    python3 -m seeu_lib.input_guard hit <x> <y> [owner]  这个点上最上层是哪个窗口;给了 owner 就判能不能点
    python3 -m seeu_lib.input_guard wait [min_idle] [timeout]  等到用户停手,超时退出码 2
    python3 -m seeu_lib.input_guard modal <应用名|pid>     这个应用有没有弹窗/表单、焦点控件是什么(读 AX)

试运行:环境变量 SEEU_INPUT_DRYRUN=1(老名字 PSLIB_INPUT_DRYRUN 也认),guarded() 走完所有检查但不调用 do()。
两档接手灵敏度:默认 manual(用户一碰就抛 UserTakeover);程序自动跑时设 SEEU_INPUT_MODE=script(老名字 PSLIB_INPUT_MODE 也认)
(碰一下不算,连续操作 1.5s 才算接手,接手后暂停、用户停手 3s 自动继续),详见 yield_to_user()。

10-07 补(借鉴官方 Computer Use,拆解文档 8.3 第 3~7 条):
  拒绝原因码 + 处理分类(REASONS / handling())、用户在打字先让(keyboard_busy)、目标应用有弹窗/表单不点
  (modal_sheet,读 AX)、打字前核对焦点在目标应用(focus_mismatch)、动作硬上限(check_limits / limit_exceeded)。
  动态让路可调(yield_to_user 的 resume_idle_s / on_waiting / log),suspend_yield() 临时关掉让路。

🔴 这里不管桌面输入锁,多个程序抢桌面时调用方照旧先拿锁(见 seeu_lib.desktop_lock)。
"""
import json
import os
import subprocess
import sys
import time

STATE_DIR = os.path.expanduser("~/Library/Caches/seeu_lib")
STATE_FILE = os.path.join(STATE_DIR, "input_last_inject.json")

DEFAULT_MIN_IDLE = 2.0      # 用户停手多少秒才算"没在用"
DEFAULT_WAIT_TIMEOUT = 60.0  # 硬上限:等用户停手最多等多久,到点抛 GuardTimeout
POLL_S = 0.25

# 两档接手灵敏度(用户 10-01 定):
#   manual(默认,LLM 一步步操作):用户一碰就停,抛 UserTakeover 交还给用户
#   script(程序自动跑,环境变量 SEEU_INPUT_MODE=script,老名字 PSLIB_INPUT_MODE 也认):碰一下不算,持续操作 ≥ TAKEOVER_HOLD_S 才算接手,
#           接手后暂停,等用户停手 RESUME_IDLE_S 秒自动继续;暂停最多 MAX_PAUSE_S(硬上限)
MANUAL_RECENT_S = 1.0       # manual:这么短时间内有用户动静就算在用
TAKEOVER_HOLD_S = 1.5       # script:连续操作多久才算接手
TAKEOVER_GAP_S = 0.6        # script:动作间隔超过这么久 = 停手了(只是碰一下)
RESUME_IDLE_S = 3.0         # script:用户停手多久后自动继续
MAX_PAUSE_S = 600.0         # script:最多暂停 10 分钟,超了抛 GuardTimeout
OWN_EVENT_SLACK = 0.15      # 自己发完事件后这么短时间内的动静,算自己的
KEY_YIELD_TRIES = 6         # 用户在打字:最多让 6 次 × 0.4s,还在打就放弃(照官方)
KEY_YIELD_STEP_S = 0.4
KEY_RECENT_S = 0.5          # 这么短时间内有按键 = 正在打字
# 动作硬上限(照官方:单次文本 ≤4000 字、拖动 ≤20 点;点击连击、滚动格数是我们补的)
LIMITS = {"text_chars": 4000, "drag_points": 20, "click_count": 3, "scroll_ticks": 60}
SKIP_OWNERS = {"Dock"}      # Dock 的窗口号称占满全屏,实际只有底部一条挡点击(交给 visibleFrame 判)
OVERLAY_LEVEL = 1000        # NSScreenSaverWindowLevel:seeu_lib.cursor_overlay 在这层,且不拦鼠标


# 拒绝原因码 → 处理分类(照官方"block / 可降级 / 没登记的一律拒绝"):
#   wait   = 等一会儿/让一让再试(都有上限,上限到了就当 stop)
#   retry  = 调用方先补救(重新激活目标窗口、重新定位)再试一次,还不行就 stop
#   stop   = 停手交给人/LLM,别自己猜着继续
# 新增原因码必须在这里登记;没登记的 handling() 一律返回 stop。
REASONS = {
    "user_active":           ("wait",  "用户正在用电脑"),
    "user_takeover":         ("stop",  "用户接手了"),
    "keyboard_busy":         ("wait",  "用户正在打字"),
    "occluded":              ("retry", "目标点被别的窗口挡住"),
    "focus_mismatch":        ("retry", "焦点不在目标应用"),
    "no_window":             ("stop",  "目标点上没有窗口"),
    "under_menubar_or_dock": ("stop",  "目标点在菜单栏/Dock/屏幕外"),
    "modal_sheet":           ("stop",  "目标应用弹着对话框/表单"),
    "secure_input":          ("stop",  "焦点在密码框"),
    "limit_exceeded":        ("stop",  "超过动作硬上限"),
    "stop_requested":        ("stop",  "调用方的停止标记"),
}


def handling(code):
    """原因码 → 'wait' / 'retry' / 'stop';没登记的一律 'stop'。"""
    return REASONS.get(code, ("stop", ""))[0]


class GuardBlocked(RuntimeError):
    def __init__(self, code, message, **detail):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.detail = detail

    @property
    def handling(self):
        return handling(self.code)


class GuardTimeout(GuardBlocked):
    @property
    def handling(self):
        return "stop"      # 等的上限已经到了,不再等


class UserTakeover(GuardBlocked):
    pass


def _env(name):
    """环境变量新名字 SEEU_<name> 优先,老名字 PSLIB_<name> 照旧认。"""
    v = os.environ.get("SEEU_" + name)
    return v if v is not None else os.environ.get("PSLIB_" + name)


def dry_run():
    return _env("INPUT_DRYRUN") == "1"


def input_mode():
    return "script" if _env("INPUT_MODE") == "script" else "manual"


# ---------------------------------------------------------------- 用户在不在用

def _cursor_pos():
    import Quartz
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return float(p.x), float(p.y)


def user_idle_seconds():
    """距离上一个任何输入事件多少秒。注意:我们自己合成的事件也会把它清零(10-01 实测),
    所以判断用户在不在用要走 user_active(),别直接拿这个数。"""
    import Quartz
    return float(Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType))


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def note_injected():
    """发完合成事件后调用:记下时间和鼠标留在哪,供 user_active() 区分"自己的动静"和"用户的动静"。"""
    x, y = _cursor_pos()
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + f".{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump({"t": time.time(), "x": x, "y": y, "pid": os.getpid()}, f)
    os.replace(tmp, STATE_FILE)


def user_active(min_idle=DEFAULT_MIN_IDLE):
    """用户最近 min_idle 秒内有没有自己动过鼠标键盘。返回 (True/False, 原因)。
    判据:最近一次输入事件发生在我们最后一次 note_injected() 之后,才算用户的。
    已知盲区:用户动了之后我们紧接着又发了事件,那次用户动作会被我们的盖掉(只影响紧挨着的那一下)。"""
    idle = user_idle_seconds()
    if idle >= min_idle:
        return False, f"已空闲 {idle:.1f}s"
    st = _load_state()
    now = time.time()
    if st and (now - idle) <= st["t"] + OWN_EVENT_SLACK:
        return False, f"最近的动静是本机脚本自己的({now - st['t']:.1f}s 前)"
    return True, f"{idle:.1f}s 前有鼠标/键盘动静"


def wait_user_idle(min_idle=DEFAULT_MIN_IDLE, timeout=DEFAULT_WAIT_TIMEOUT, on_waiting=None):
    """等到用户停手 min_idle 秒。有硬上限,到点抛 GuardTimeout,不无限等。返回实际等了多少秒。
    on_waiting:等的期间每轮(约 POLL_S 秒)调一次,比如查调用方的停止标记,要停就在里面抛异常。"""
    t0 = time.time()
    while True:
        active, why = user_active(min_idle)
        if not active:
            return time.time() - t0
        if time.time() - t0 >= timeout:
            raise GuardTimeout("user_active", f"等了 {timeout:.0f}s 用户还在用电脑({why}),停手",
                               waited=timeout)
        if on_waiting:
            on_waiting()
        time.sleep(POLL_S)


def user_typing(recent_s=KEY_RECENT_S):
    """用户最近 recent_s 秒内按过键(且不是我们自己合成的)。返回 (True/False, 原因)。"""
    import Quartz
    idle = float(Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGEventKeyDown))
    if idle >= recent_s:
        return False, f"键盘已空闲 {idle:.1f}s"
    st = _load_state()
    if st and (time.time() - idle) <= st["t"] + OWN_EVENT_SLACK:
        return False, "最近的按键是本机脚本自己的"
    return True, f"{idle:.1f}s 前用户按过键"


def yield_to_typing(tries=KEY_YIELD_TRIES, step_s=KEY_YIELD_STEP_S):
    """打字前用:用户正在打字就让 step_s 秒再看,最多 tries 次;还在打抛 GuardBlocked(keyboard_busy)。
    返回让了多少秒。(照官方:键盘单独判,免得我们的字跟用户的字混在一起)"""
    t0 = time.time()
    for _ in range(tries):
        busy, why = user_typing()
        if not busy:
            return time.time() - t0
        time.sleep(step_s)
    busy, why = user_typing()
    if busy:
        raise GuardBlocked("keyboard_busy", f"让了 {tries} 次用户还在打字({why}),放弃这次输入")
    return time.time() - t0


def user_takeover(hold_s=TAKEOVER_HOLD_S, gap_s=TAKEOVER_GAP_S):
    """脚本模式用:用户是"碰了一下"还是"真要接手"。有动静就盯 hold_s 秒,中途停手超过 gap_s 就算碰一下。
    返回 (True/False, 原因)。最多阻塞 hold_s 秒。"""
    active, why = user_active(min_idle=gap_s)
    if not active:
        return False, why
    t0 = time.time()
    while time.time() - t0 < hold_s:
        time.sleep(0.1)
        if user_idle_seconds() > gap_s:
            return False, f"只碰了一下({time.time() - t0:.1f}s 后就停了),不算接手"
    return True, f"连续操作超过 {hold_s:.1f}s,算接手"


_suspended = 0


class suspend_yield:
    """with suspend_yield(): ... —— 这段里 yield_to_user() 直接放行(不判接手、不暂停)。
    给高频点击、自己的事件可能被误判成用户接手的场景用(如连点小游戏);其他检查(挡没挡、密码框)照做。"""

    def __enter__(self):
        global _suspended
        _suspended += 1
        return self

    def __exit__(self, *exc):
        global _suspended
        _suspended -= 1
        return False


def yield_to_user(mode=None, on_takeover=None, resume_idle_s=None, on_waiting=None, log=None,
                  max_pause_s=None):
    """发输入前给用户让路,返回为此等了多少秒。
    manual:用户刚动过就抛 UserTakeover(交还给用户,别跟用户抢)。
    script:碰一下不管;真接手了 → 先调 on_takeover()(比如查调用方的停止标记,要停就在里面抛异常)
            → 等用户停手 resume_idle_s 秒(默认 RESUME_IDLE_S;可给 (lo, hi) 每次随机取)后继续,最多等 max_pause_s(默认 MAX_PAUSE_S,
            到点抛 GuardTimeout);等的期间每轮调 on_waiting()。
    log:给了就在暂停/继续时各调一次 log(文字),文字带固定词「🟡 让路暂停」「▶️ 让路继续」(方便盯日志时过滤)。
    suspend_yield() 里直接放行。"""
    if _suspended:
        return 0.0
    mode = mode or input_mode()
    if mode == "manual":
        active, why = user_active(min_idle=MANUAL_RECENT_S)
        if active:
            raise UserTakeover("user_takeover", f"用户正在操作电脑({why}),停下交还给用户")
        return 0.0
    t0 = time.time()
    took, why = user_takeover()
    if not took:
        return time.time() - t0
    resume = RESUME_IDLE_S if resume_idle_s is None else resume_idle_s
    if isinstance(resume, (tuple, list)):
        import random
        resume = random.uniform(*resume)     # 调用方传区间才随机,默认固定
    if log:
        log(f"🟡 让路暂停:检测到你在用鼠标/键盘,停手 {resume:.0f} 秒后继续")
    if on_takeover:
        on_takeover()
    wait_user_idle(resume, MAX_PAUSE_S if max_pause_s is None else max_pause_s, on_waiting)
    if log:
        log(f"▶️ 让路继续:你已停手 {resume:.0f} 秒(共暂停 {time.time() - t0:.0f} 秒)")
    return time.time() - t0


# ---------------------------------------------------------------- 密码框(安全输入)

def secure_input_pid():
    """系统处于安全输入状态(焦点在密码框之类)时返回占用的进程 pid,否则 None。
    这时合成键盘事件会被系统吞掉或打进不该打的地方,打字前必须拒绝。"""
    import Quartz
    d = Quartz.CGSessionCopyCurrentDictionary() or {}
    pid = d.get("kCGSSessionSecureInputPID")
    return int(pid) if pid else None


# ---------------------------------------------------------------- 弹窗/表单、焦点(读辅助功能 AX,只读)

_AX = {}


def _ax():
    """本机 pyobjc 没装 ApplicationServices 包,直接从系统框架加载这几个 C 函数(10-07 实测可用)。"""
    if not _AX:
        import objc
        from Foundation import NSBundle
        b = NSBundle.bundleWithPath_("/System/Library/Frameworks/ApplicationServices.framework")
        objc.loadBundleFunctions(b, _AX, [("AXUIElementCreateApplication", b"@i"),
                                          ("AXUIElementCopyAttributeValue", b"i@@o^@"),
                                          ("AXIsProcessTrusted", b"Z")])
    return _AX


def _ax_app(pid):
    return _ax()["AXUIElementCreateApplication"](int(pid))


def _ax_get(el, attr):
    err, v = _ax()["AXUIElementCopyAttributeValue"](el, attr, None)
    return v if err == 0 else None


def modal_state(pid):
    """pid 这个应用的窗口有没有弹着表单(AXSheets)或模态对话框(AXModal)。
    返回 (True/False/None, 说明);None = 读不到(没给辅助功能权限、应用不配合),调用方当作"不知道"放行。"""
    try:
        if not _ax()["AXIsProcessTrusted"]():
            return None, "没有辅助功能权限"
        wins = _ax_get(_ax_app(pid), "AXWindows")
        if wins is None:
            return None, "读不到窗口列表(辅助功能权限?)"
        for w in wins:
            sheets = list(_ax_get(w, "AXSheets") or []) + [
                c for c in (_ax_get(w, "AXChildren") or []) if _ax_get(c, "AXRole") == "AXSheet"]
            if sheets:
                return True, f"窗口「{_ax_get(w, 'AXTitle') or ''}」弹着表单"
            if _ax_get(w, "AXModal"):
                return True, f"「{_ax_get(w, 'AXTitle') or ''}」是模态对话框"
            if _ax_get(w, "AXSubrole") in ("AXDialog", "AXSystemDialog") and _ax_get(w, "AXMain") is False:
                # 10-13(SeeU 实测「文本编辑」):新版 macOS 应用在前台时,左上角红黄绿三个按钮是一个单独的
                # 66×20 小窗,也报 AXDialog。比真对话框小得多的不算弹窗。
                sz = _ax_get(w, "AXSize")
                import re as _re
                m = _re.search(r"w:([\d.]+) h:([\d.]+)", str(sz)) if sz is not None else None
                if m and float(m.group(1)) < 120 and float(m.group(2)) < 40:
                    continue
                return True, f"「{_ax_get(w, 'AXTitle') or ''}」是对话框"
        return False, f"{len(wins)} 个窗口,没有弹窗/表单"
    except Exception as e:
        return None, f"AX 读取出错: {e}"


def check_no_modal(pid):
    m, why = modal_state(pid)
    if m:
        raise GuardBlocked("modal_sheet", f"目标应用有弹窗/表单({why}),不点,交给人看", pid=pid)
    return why


def focused_role(pid):
    """pid 应用里当前焦点控件的 (AXRole, AXSubrole);读不到返回 (None, None)。"""
    try:
        el = _ax_get(_ax_app(pid), "AXFocusedUIElement")
        if el is None:
            return None, None
        return _ax_get(el, "AXRole"), _ax_get(el, "AXSubrole")
    except Exception:
        return None, None


def check_focus(pid):
    """打字前:前台应用必须是目标应用,焦点控件不能是密码框。"""
    fa = frontmost_app()
    if not fa or fa["pid"] != pid:
        raise GuardBlocked("focus_mismatch", f"前台是「{(fa or {}).get('name')}」,不是目标应用(pid {pid}),"
                           "字会打到别处", frontmost=fa, pid=pid)
    role, sub = focused_role(pid)
    if sub == "AXSecureTextField":
        raise GuardBlocked("secure_input", "焦点在密码框,拒绝打字", pid=pid)
    return role, sub


# ---------------------------------------------------------------- 动作硬上限

def check_limits(text=None, drag_points=None, click_count=None, scroll_ticks=None):
    """超了 LIMITS 抛 GuardBlocked(limit_exceeded)。只给要查的那几项。"""
    for key, v in (("text_chars", len(text) if text is not None else None), ("drag_points", drag_points),
                   ("click_count", click_count), ("scroll_ticks", scroll_ticks)):
        if v is not None and v > LIMITS[key]:
            raise GuardBlocked("limit_exceeded", f"{key}={v} 超过上限 {LIMITS[key]}", key=key, value=v)


# ---------------------------------------------------------------- 目标有没有被挡住

SCREENS_CACHE = os.path.join(STATE_DIR, "screens_visible.json")
SCREENS_TTL_S = 3600.0     # 屏幕可用区域缓存最多用 1 小时;显示器变了 / Dock 设置改了立刻重查
_SCREENS_JS = """ObjC.import('AppKit');
var s = $.NSScreen.screens, out = [];
for (var i = 0; i < s.count; i++) { var f = s.objectAtIndex(i).frame, v = s.objectAtIndex(i).visibleFrame;
  out.push([f.size.height, v.origin.x, v.origin.y, v.size.width, v.size.height]); }
JSON.stringify(out);"""


def _display_key():
    """显示器布局 + Dock 设置的指纹,变了缓存就作废。只用 Quartz,不会让本进程注册成应用。"""
    import Quartz
    err, ids, n = Quartz.CGGetActiveDisplayList(16, None, None)
    disp = []
    for d in (ids or [])[:n]:
        r = Quartz.CGDisplayBounds(d)
        disp.append([round(r.origin.x), round(r.origin.y), round(r.size.width), round(r.size.height)])
    try:
        dock = os.path.getmtime(os.path.expanduser("~/Library/Preferences/com.apple.dock.plist"))
    except OSError:
        dock = 0
    return [disp, dock]


def _screens_visible_rects():
    """各屏幕去掉菜单栏和 Dock 后的可用区域,换成原点左上的桌面点坐标。
    🔴 Python 里直接用 NSScreen 会把进程登记成前台应用,Dock 冒图标/闪一下(调用方每次点都起子进程时,
    Dock 会一直跳);先 setActivationPolicy 也晚了(sharedApplication 本身就登记)。改成:让 osascript
    (系统登记为纯后台,不进 Dock)查 NSScreen,结果按"显示器布局 + Dock 设置"缓存,约 0.25 秒/次只在缓存失效时付。"""
    key = _display_key()
    try:
        with open(SCREENS_CACHE) as f:
            c = json.load(f)
        if c["key"] == key and time.time() - c["t"] < SCREENS_TTL_S:
            return [tuple(r) for r in c["rects"]]
    except (OSError, ValueError, KeyError):
        pass
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", _SCREENS_JS],
                       capture_output=True, text=True, timeout=10)
    raw = json.loads(r.stdout)
    main_h = raw[0][0]
    rects = [(vx, main_h - (vy + vh), vw, vh) for _, vx, vy, vw, vh in raw]
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = SCREENS_CACHE + f".{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump({"key": key, "t": time.time(), "rects": rects}, f)
        os.replace(tmp, SCREENS_CACHE)
    except OSError:
        pass
    return rects


def _inside(x, y, r):
    rx, ry, rw, rh = r
    return rx <= x < rx + rw and ry <= y < ry + rh


def window_at(x, y, skip=()):
    """(x,y) 上最上层、真正会接住点击的窗口,返回 dict(owner/pid/id/name/layer/bounds);没有返回 None。
    跳过:全透明窗口(输入法候选等)、Dock 的全屏窗口、seeu_lib 代理光标(屏保层、Python 进程、不拦鼠标)、skip 里的应用名、
    正在让路的 SeeU 悬浮窗/悬浮标/多任务岛(借真鼠标那几秒不接鼠标,点击穿下去;10-30 SeeU 报:不跳会误判成被挡住)。"""
    import Quartz
    try:
        from seeu_lib.watch_window import passthrough_wids
        passing = passthrough_wids()
    except Exception:
        passing = set()
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowAlpha", 1.0) <= 0.01:
            continue
        owner = w.get("kCGWindowOwnerName", "") or ""
        layer = int(w.get("kCGWindowLayer", 0))
        if owner in SKIP_OWNERS or owner in skip:
            continue
        if layer >= OVERLAY_LEVEL and owner.lower().startswith("python"):
            continue
        if int(w.get("kCGWindowNumber", 0)) in passing:
            continue
        b = w.get("kCGWindowBounds") or {}
        r = (b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0))
        if _inside(x, y, r):
            return {"owner": owner, "pid": int(w.get("kCGWindowOwnerPID", 0)),
                    "id": int(w.get("kCGWindowNumber", 0)), "name": w.get("kCGWindowName"),
                    "layer": layer, "bounds": r}
    return None


def check_target_at(x, y, owner, window_id=None):
    """确认点下去真的落在 owner 的窗口上(调用方应已激活目标窗口)。不是就抛 GuardBlocked。"""
    if not any(_inside(x, y, r) for r in _screens_visible_rects()):
        raise GuardBlocked("under_menubar_or_dock", f"({x:.0f},{y:.0f}) 落在菜单栏/Dock 上或屏幕外",
                           x=x, y=y)
    top = window_at(x, y)
    if top is None:
        raise GuardBlocked("no_window", f"({x:.0f},{y:.0f}) 上没有任何窗口", x=x, y=y)
    if top["owner"] != owner or (window_id is not None and top["id"] != window_id):
        raise GuardBlocked("occluded", f"({x:.0f},{y:.0f}) 最上层是「{top['owner']}」"
                           f"(层 {top['layer']}),不是「{owner}」,点下去会点错", top=top)
    return top


# ---------------------------------------------------------------- 组合入口

def preflight(x, y, owner, window_id=None, typing=False, mode=None, on_takeover=None,
              text=None, check_modal=True, **yield_kw):
    """发输入前的全套检查:动作上限 → 给用户让路(两档灵敏度,见 yield_to_user;yield_kw 原样传过去)
    → 要打字时先让正在打字的用户、查密码框 → 查目标没被挡 → 目标应用没弹窗/表单 → 要打字时核对焦点。
    不通过抛 GuardBlocked(GuardTimeout / UserTakeover 是它的子类;e.handling 给出 wait/retry/stop);
    通过返回检查结果 dict。text:要打的字(查长度上限,给了就当 typing)。"""
    typing = typing or text is not None
    if text is not None:
        check_limits(text=text)
    waited = yield_to_user(mode, on_takeover, **yield_kw)
    if typing:
        waited += yield_to_typing()
        pid = secure_input_pid()
        if pid:
            raise GuardBlocked("secure_input", f"系统处于密码输入状态(pid {pid}),拒绝打字", pid=pid)
    top = check_target_at(x, y, owner, window_id)
    modal = check_no_modal(top["pid"]) if check_modal else None
    focus = check_focus(top["pid"]) if typing else None
    return {"waited_s": round(waited, 2), "window": top, "modal": modal, "focus": focus,
            "dry_run": dry_run(), "mode": mode or input_mode()}


def guarded(x, y, owner, do, **kw):
    """preflight 通过后执行 do()(试运行时不执行),执行完自动 note_injected()。返回 preflight 结果。"""
    info = preflight(x, y, owner, **kw)
    if not info["dry_run"]:
        try:
            do()
        finally:
            note_injected()
    return info


# ---------------------------------------------------------------- 还原前台应用和鼠标

def frontmost_app():
    """当前前台应用。🔴 NSWorkspace 在没有事件循环的脚本里会缓存第一次查到的值(10-01 实测:
    切到别的应用后还一直返回旧的),查之前先让事件循环跑 20ms 收一下系统通知,才是最新值。"""
    from AppKit import NSWorkspace, NSRunLoop, NSDate
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    a = NSWorkspace.sharedWorkspace().frontmostApplication()
    if a is None:
        return None
    return {"name": a.localizedName(), "pid": int(a.processIdentifier()), "bundle": a.bundleIdentifier()}


def _activate_pid(pid, bundle):
    from AppKit import NSRunningApplication
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return False
    app.activateWithOptions_(0)
    time.sleep(0.3)
    fa = frontmost_app()
    if fa and fa["pid"] == pid:
        return True
    if bundle:
        subprocess.run(["osascript", "-e", f'tell application id "{bundle}" to activate'],
                       capture_output=True, timeout=10)
        time.sleep(0.3)
        fa = frontmost_app()
    return bool(fa and fa["pid"] == pid)


def _owner_rects(owner):
    import Quartz
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowOwnerName") == owner:
            b = w.get("kCGWindowBounds") or {}
            out.append((b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)))
    return out


class FrontState:
    """包住一整段操作:进入时记下前台应用和鼠标位置,退出时还原。
    按"一段流程"用,别每点一下就包一次——反复切前台会让窗口一闪一闪(09-26 用户反馈过)。
    avoid_owner:鼠标原位置在这个应用的窗口里就不放回去(iPhone 镜像里停着鼠标会被当长按)。
    用户中途自己切了应用/挪了鼠标,就不还原,尊重用户当前的操作。"""

    def __init__(self, avoid_owner=None):
        self.avoid_owner = avoid_owner
        self.app = None
        self.pos = None
        self.restored = {}

    def __enter__(self):
        self.app = frontmost_app()
        self.pos = _cursor_pos()
        return self

    def __exit__(self, *exc):
        self.restored = self.restore()
        return False

    def restore(self):
        import Quartz
        res = {"app": False, "mouse": False}
        active, _ = user_active()
        if active:
            res["skipped"] = "用户正在操作,不打扰"
            return res
        if self.app:
            cur = frontmost_app()
            if cur and cur["pid"] != self.app["pid"]:
                res["app"] = _activate_pid(self.app["pid"], self.app["bundle"])
        if self.pos:
            x, y = self.pos
            if not (self.avoid_owner and any(_inside(x, y, r) for r in _owner_rects(self.avoid_owner))):
                Quartz.CGWarpMouseCursorPosition((x, y))
                Quartz.CGAssociateMouseAndMouseCursorPosition(True)
                note_injected()
                res["mouse"] = True
        return res


# ---------------------------------------------------------------- 命令行

def _status():
    active, why = user_active()
    st = _load_state()
    x, y = _cursor_pos()
    return {
        "idle_s": round(user_idle_seconds(), 2),
        "user_active": active,
        "reason": why,
        "last_inject_ago_s": round(time.time() - st["t"], 1) if st else None,
        "secure_input_pid": secure_input_pid(),
        "frontmost": frontmost_app(),
        "cursor": [round(x, 1), round(y, 1)],
        "dry_run": dry_run(),
        "mode": input_mode(),
        "user_typing": user_typing()[0],
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "status":
        print(json.dumps(_status(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "hit" and len(argv) in (3, 4):
        x, y = float(argv[1]), float(argv[2])
        top = window_at(x, y)
        print(json.dumps({"window": top}, ensure_ascii=False, default=str))
        if len(argv) == 4:
            try:
                check_target_at(x, y, argv[3])
                print(f"✅ 可以点:({x:.0f},{y:.0f}) 最上层就是「{argv[3]}」")
            except GuardBlocked as e:
                print(f"❌ {e}")
                return 2
        return 0
    if cmd == "modal" and len(argv) == 2:
        fa = None
        if argv[1].isdigit():
            pid = int(argv[1])
        else:
            rects = [w for w in __import__("Quartz").CGWindowListCopyWindowInfo(
                1, 0) or [] if w.get("kCGWindowOwnerName") == argv[1]]
            if not rects:
                print(f"❌ 没找到「{argv[1]}」的窗口")
                return 2
            pid = int(rects[0]["kCGWindowOwnerPID"])
        m, why = modal_state(pid)
        print(json.dumps({"pid": pid, "modal": m, "reason": why, "focused": focused_role(pid)},
                         ensure_ascii=False))
        return 0
    if cmd == "wait":
        min_idle = float(argv[1]) if len(argv) > 1 else DEFAULT_MIN_IDLE
        timeout = float(argv[2]) if len(argv) > 2 else DEFAULT_WAIT_TIMEOUT
        try:
            print(f"✅ 用户已停手(等了 {wait_user_idle(min_idle, timeout):.1f}s)")
            return 0
        except GuardTimeout as e:
            print(f"❌ {e}")
            return 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
