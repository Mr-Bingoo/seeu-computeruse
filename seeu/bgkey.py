# -*- coding: utf-8 -*-
"""SeeU(实验中):后台把键盘事件直接投给目标进程 —— 不抢前台、不影响用户正在打的字。

做法照开源 Cua(libs/cua-driver/rust/crates/platform-macos/src/input/keyboard.rs):
  - 键盘事件经 SLEventPostToPid 投递,默认附"事件认证"(auth);
  - 文字两种发法:unicode = 键码 0 + 直接带文字(普通 App);physical = 按美式键盘的物理键码 + Shift
    (Cua 对"屏幕共享"这种转发输入的程序就这么做;iPhone 镜像也是转发输入,预计要走这条)。
🔴 私有接口只当加速层,失效退回真键盘(激活窗口 + 让路)。中文走不了物理键,用剪贴板粘贴。
"""
import time

import Quartz

from seeu import bgclick as bg

# 美式键盘虚拟键码
KEYCODE = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12,
    "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34,
    "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46,
    ".": 47, "`": 50, "return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53,
    "left": 123, "right": 124, "down": 125, "up": 126,
    # 10-31 Codex App 实测按 end 报「不认识的键」→ 只好全选重打;补上常用导航/编辑键和 F 键,外加几个常见别名
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121, "forwarddelete": 117,
    "enter": 36, "esc": 53, "backspace": 51,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101,
    "f10": 109, "f11": 103, "f12": 111,
}
SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
           '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
           '~': '`'}
SHIFT_CODE = 56
FLAG = {"cmd": Quartz.kCGEventFlagMaskCommand, "shift": Quartz.kCGEventFlagMaskShift,
        "alt": Quartz.kCGEventFlagMaskAlternate, "ctrl": Quartz.kCGEventFlagMaskControl}
GAP = 0.012


def _send(pid, ev, auth):
    p = ev.__c_void_p__().value
    if auth:
        bg._attach_auth(p, pid)
    bg.SLEventPostToPid(pid, p)


def _key(pid, code, down, flags=0, auth=True, text=None, flags_changed=False):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    ev = Quartz.CGEventCreateKeyboardEvent(src, code, down)
    if flags_changed:
        Quartz.CGEventSetType(ev, Quartz.kCGEventFlagsChanged)
    if text is not None:
        Quartz.CGEventKeyboardSetUnicodeString(ev, len(text), text)
    Quartz.CGEventSetFlags(ev, flags)  # 一律覆盖,别继承用户真按着的修饰键
    _send(pid, ev, auth)


MOD_CODE = {"cmd": 55, "shift": 56, "alt": 58, "ctrl": 59}
MOD_ALIAS = {"command": "cmd", "meta": "cmd", "super": "cmd", "win": "cmd", "option": "alt", "opt": "alt",
             "control": "ctrl", "ctl": "ctrl"}       # 11-06:常见别名(跟 safety.MOD_ALIAS 同一套)


def _safety(pid, key=None, mods=(), text=None):
    """安全底线硬拦(seeu/safety.py):目标程序、危险快捷键、危险打字内容。长进程里没有这个模块就跳过。"""
    try:
        from seeu import safety
    except ImportError:
        return
    safety.check_pid(pid)
    if key is not None:
        safety.check_keys(key, mods)
    if text is not None:
        safety.check_text(text)


def _called_out(pid):
    """隐身浏览器被叫出来过 → 抛 bgclick.CalledOut,不发(10-24 C-0.9,见 bgclick.CALLED_OUT)。长进程里旧版 bgclick 没有就跳过。"""
    fn = getattr(bg, "check_called_out", None)
    if fn:
        fn(pid)


def _set_step(step):
    """step= 参数:同 bgclick.set_step(长进程里旧版 bgclick 没有就跳过)。"""
    if step:
        fn = getattr(bg, "set_step", None)
        if fn:
            fn(step)


def press(pid, key, mods=(), auth=True, step=None):
    """按一个键(可带 cmd/shift/alt/ctrl)。step = 这一步在做什么(浏览器卡片上写,同 bgclick.set_step)。
    🔴 10-15 C-1.2:修饰键要先单独发"按下"(flagsChanged)、最后发"松开",只把标记挂在字母上的话,
    iPhone 镜像这类转发输入的程序不认 —— 后台 ⌘A 清框变成打了个 "a"(拼音输入法里挂着候选「啊 阿」)。"""
    # 11-06 体检:发任何事件之前先把键名、修饰键全部认一遍。原来 mods 里写错一个(AI 常写 option / command),
    # 前面的修饰键已经「按下」、KeyError 又在 try 外面 → 永远不松开,目标程序以为 ⌘ 一直按着。别名一并收下。
    key = str(key)
    code = KEYCODE.get(key.lower())
    if code is None:
        raise ValueError(f"不认识的键:{key}")
    if isinstance(mods, str):
        mods = [mods]
    mods = [MOD_ALIAS.get(str(m).strip().lower(), str(m).strip().lower()) for m in (mods or ())]
    bad = [m for m in mods if m not in FLAG]
    if bad:
        raise ValueError(f"不认识的修饰键:{'、'.join(bad)}(只认 cmd / shift / alt / ctrl)")
    _called_out(pid)
    _safety(pid, key=key, mods=mods)
    _set_step(step)
    _watch(pid, "按键")
    getattr(bg, "PENDING_TAP", {}).pop(pid, None)     # 按过键(Tab/方向键…)就不再自动重点,免得点回旧格子
    flags = 0
    held = []
    for m in mods:
        flags |= FLAG[m]
        _key(pid, MOD_CODE[m], True, flags, auth, flags_changed=True)
        held.append(m)
        time.sleep(GAP)
    try:
        _key(pid, code, True, flags, auth)
        time.sleep(GAP)
        _key(pid, code, False, flags, auth)
        time.sleep(GAP)
    finally:
        for m in reversed(held):           # 倒序松开,一定松,别让目标程序以为 ⌘ 还按着
            flags &= ~FLAG[m]
            _key(pid, MOD_CODE[m], False, flags, auth, flags_changed=True)
            time.sleep(GAP)


def _watch(pid, step):
    """浏览器上打字/按键时悬浮标卡片写这一步(10-21;镜像等不是浏览器的照旧不画)。长进程里旧版 bgclick 没这个函数就跳过。"""
    fn = getattr(bg, "watch_pid", None)
    if fn:
        fn(pid, step)


class FocusError(RuntimeError):
    """点了输入框但焦点没进去(浏览器),不往下打字。"""


FOCUS_JS = ("(function(){var a=document.activeElement;while(a&&a.shadowRoot&&a.shadowRoot.activeElement)a=a.shadowRoot.activeElement;"
            "return a&&(a.isContentEditable||/^(INPUT|TEXTAREA)$/.test(a.tagName))?'1':'0'})()")


def _focus_ok(app):
    """浏览器当前标签页的焦点在不在可输入的框里:True / False / None(问不到:开关没开、没授权等)。"""
    try:
        from seeu.web import aejs
        if not aejs.supported(app):
            return None
        return aejs.js(app, FOCUS_JS).strip() == "1"
    except Exception:
        return None


last_focus = None      # 最近一次核实结果:dict(ok, retried, note);没核实过是 None


def verify_focus(pid):
    """10-21:浏览器上刚 tap 过、这是第一次打字 → 核实焦点进了输入框;没进原地再点一次;还不行抛 FocusError。
    问不到(开关没开等)就照常打,last_focus 里记「没核实」。只核实一次(用掉就作废)。"""
    global last_focus
    pend = getattr(bg, "PENDING_TAP", {}).pop(pid, None)
    if not pend or time.time() - pend[3] > getattr(bg, "PENDING_TAP_S", 15.0):
        return
    app_name, sx, sy, _t = pend
    app = bg.split_target(app_name)[0]
    ok = _focus_ok(app)
    if ok is None:
        last_focus = dict(ok=None, retried=False, note="没核实(浏览器开关没开或没授权)")
        return
    if ok:
        last_focus = dict(ok=True, retried=False, note="")
        return
    bg.tap(app_name, sx, sy)                          # 原地再点一次
    bg.PENDING_TAP.pop(pid, None)
    time.sleep(0.4)
    if _focus_ok(app):
        last_focus = dict(ok=True, retried=True, note="第一下没点上,再点一次进了")
        return
    last_focus = dict(ok=False, retried=True, note="点了两次焦点都没进输入框")
    raise FocusError(f"卡在:往 {app} 打字前 原因:点了 ({sx:.0f},{sy:.0f}) 两次,光标都没进输入框,打下去会落空。"
                     f"怎么办:确认点的位置是输入框/表格格子;网页可能还没加载完,稍等再试")


# 有真键位、不用 Shift 的字符(数字、小写字母、部分符号):按真键位发,网页看到的 keyCode/code 才对(10-21 测:原来一律是 A 键)。
# 10-24 C-0.7:大写字母、要 Shift 的符号也走真键位 + Shift(隐身 Chrome 实测文字不变、网页看到的键和 Shift 都对;
# 百度输入法中/英两种状态下发都不会被切换)。🔴 iPhone 镜像没测过,照旧走键位 0 + 附带文字;中文照旧。
# 出问题把 SHIFT_REAL 改 False 就回到老做法。
_PLAIN = {ch: c for ch, c in KEYCODE.items() if len(ch) == 1 and not ch.isupper()}
SHIFT_REAL = True
SHIFT_SKIP_APPS = {"iPhone Mirroring"}


def _shifted_code(ch):
    """要 Shift 的 ASCII 字符 → 真键位;别的返回 None。"""
    if ch in SHIFTED:
        return KEYCODE[SHIFTED[ch]]
    if ch.isascii() and ch.isupper() and ch.lower() in KEYCODE:
        return KEYCODE[ch.lower()]
    return None


def _app_of(pid):
    try:
        from AppKit import NSRunningApplication
        a = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        return str(a.localizedName()) if a else ""
    except Exception:
        return ""


TYPE_WAIT_USER_S = 3.0      # 后台打字前等用户停手的上限;到点照打,不卡流程(11-01 用户定)
_MOD_MASK = 0x20000 | 0x40000 | 0x80000 | 0x100000   # Shift / Control / Option / Command 按着


def _wait_user_keys(limit=TYPE_WAIT_USER_S):
    """11-01 实测:用户同时在 Mac 上打字,后台打的字没打进(撞车)。用户 0.5 秒内按过键、或正按着修饰键,
    就等一下;最多 limit 秒,到点照打。返回等了几秒。拿不到状态就不等。"""
    try:
        import Quartz
        from seeu_lib import input_guard as ig
    except Exception:
        return 0.0
    t0 = time.time()
    while time.time() - t0 < limit:
        busy = ig.user_typing()[0]
        mods = int(Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)) & _MOD_MASK
        if not busy and not mods:
            break
        time.sleep(0.1)
    return time.time() - t0


def type_unicode(pid, text, auth=True, step=None):
    """打字。step = 这一步在做什么(如「录入第 5 行」,浏览器卡片上写「正在录入第 5 行」;同 bgclick.set_step)。"""
    _safety(pid, text=text)
    _set_step(step)
    _watch(pid, "打字")
    verify_focus(pid)
    _wait_user_keys()
    shift_ok = SHIFT_REAL and _app_of(pid) not in SHIFT_SKIP_APPS
    for ch in text:
        _called_out(pid)       # 每个字前查一次:打到一半被叫出来也马上停(整组按下/松开不拆开)
        if ch in "\n\r":
            press(pid, "return", auth=auth)
            continue
        sc = _shifted_code(ch) if shift_ok else None
        if sc is not None:
            fl = FLAG["shift"]
            _key(pid, SHIFT_CODE, True, fl, auth, flags_changed=True)
            time.sleep(GAP)
            _key(pid, sc, True, fl, auth, text=ch)
            time.sleep(GAP)
            _key(pid, sc, False, fl, auth, text=ch)
            time.sleep(GAP)
            _key(pid, SHIFT_CODE, False, 0, auth, flags_changed=True)
            time.sleep(GAP)
            continue
        # 🔴 C-1.3 Codex(网页做的输入框)实测:空格走"键位 0 + 附带文字"会从空格起后面全丢,空格改用真空格键位 49
        code = 49 if ch == " " else _PLAIN.get(ch, 0)
        _key(pid, code, True, 0, auth, text=ch)
        time.sleep(GAP)
        _key(pid, code, False, 0, auth, text=ch)
        time.sleep(GAP)


def type_physical(pid, text, auth=True, step=None):
    """按物理键打 ASCII(美式键盘)。中文等打不了 → 抛错,让调用方改走粘贴。"""
    _safety(pid, text=text)
    _set_step(step)
    _watch(pid, "打字")
    verify_focus(pid)
    for ch in text:
        _called_out(pid)       # 每个字前查一次:打到一半被叫出来也马上停(整组按下/松开不拆开)
        if ch in "\n\r":
            press(pid, "return", auth=auth)
            continue
        if ch == " ":
            press(pid, "space", auth=auth)
            continue
        shift = ch.isupper() or ch in SHIFTED
        base = SHIFTED.get(ch, ch.lower())
        if base not in KEYCODE:
            raise ValueError(f"物理键打不了「{ch}」,改走粘贴")
        code = KEYCODE[base]
        fl = FLAG["shift"] if shift else 0
        if shift:
            _key(pid, SHIFT_CODE, True, fl, auth, flags_changed=True)
            time.sleep(GAP)
        _key(pid, code, True, fl, auth, text=ch)
        time.sleep(GAP)
        _key(pid, code, False, fl, auth, text=ch)
        time.sleep(GAP)
        if shift:
            _key(pid, SHIFT_CODE, False, 0, auth, flags_changed=True)
            time.sleep(GAP)


def type_to(app_name, text, enter=False, prime=None):
    """推荐入口:后台往 App 当前焦点输入框打字(中英文都行,走 unicode),可选最后回车。
    先聚焦 + 标题栏垫一下(同 bgclick.tap)。10-13 镜像 Spotlight 实测:中英文、回车开 App 都通,前台不变。"""
    g = bg.main_window(app_name)
    if not g:
        raise RuntimeError(f"找不到 {app_name} 的窗口")
    pid, _wid, _xy = bg._prepare(app_name, g["x"] + g["w"] / 2, g["y"] + g["h"] / 2, prime)
    type_unicode(pid, text)
    if enter:
        time.sleep(0.3)
        press(pid, "return")
    return pid
