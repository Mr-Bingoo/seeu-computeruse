# -*- coding: utf-8 -*-
"""SeeU 第一级:用辅助功能(AX)在后台直接操作 Mac 原生 App 的控件 —— 不挪鼠标、不抢前台。

只用系统公开接口(ApplicationServices 的 AXUIElement*)。本机 pyobjc 没装 ApplicationServices 包,
照 10-07 实测的办法用 objc.loadBundleFunctions 直接加载。

用法(命令行):
  python3 -m seeu.ax apps                       # 列出有窗口的 App
  python3 -m seeu.ax list  <App> [--all]        # 列出前台窗口(没有就第一个窗口)+ 菜单栏里的控件,带编号
  python3 -m seeu.ax press <App> <编号|文字>     # 按下按钮/菜单项
  python3 -m seeu.ax type  <App> <编号|文字> <字> # 在文本控件光标处插入文字(中文直接进,不走输入法/剪贴板)
  python3 -m seeu.ax set   <App> <编号|文字> <字> # 整个替换文本控件内容
  python3 -m seeu.ax selall <App> <编号|文字>    # 全选文本控件
  python3 -m seeu.ax menu  <App> 文件 新建        # 按菜单路径点菜单
编号每次重新遍历生成,界面没变就稳定;界面变了先重新 list。

🔴 安全底线(照官方):目标是密码框、系统处于密码输入状态 → 拒绝(AXRefused)。
   C-0.5 起验证码框、新密码框(看标题/说明/占位字认)同样拒绝,判断在 secret_kind(),网页那边同一套词。
   窗口上弹着对话框(sheet)而目标不在对话框里 → 拒绝,不点被挡住的地方。
🔴 动作返回成功不等于真生效(官方实测"粗体"假成功):type/set 会读回内容核实;press 的核实交给调用方
   (截图比对用 seeu_lib.wait.act_and_verify,或 list 看状态变化)。
"""
import re
import sys
import time

import objc
from Foundation import NSBundle

_AX = {}
objc.loadBundleFunctions(
    NSBundle.bundleWithPath_("/System/Library/Frameworks/ApplicationServices.framework"), _AX, [
        ("AXIsProcessTrusted", b"Z"),
        ("AXUIElementCreateApplication", b"@i"),
        ("AXUIElementCopyAttributeValue", b"i@@o^@"),
        ("AXUIElementCopyAttributeNames", b"i@o^@"),
        ("AXUIElementCopyActionNames", b"i@o^@"),
        ("AXUIElementSetAttributeValue", b"i@@@"),
        ("AXUIElementIsAttributeSettable", b"i@@o^Z"),
        ("AXUIElementPerformAction", b"i@@"),
        ("AXUIElementSetMessagingTimeout", b"i@f"),
        ("AXValueCreate", b"@in^{CFRange=qq}"),
        ("AXUIElementGetPid", b"i@o^i"),
        ("AXUIElementCopyElementAtPosition", b"i@ffo^@"),
    ])

MSG_TIMEOUT = 2.0          # 单次 AX 调用最多等几秒(App 卡死时不陪着卡)
MAX_NODES = 3000           # 遍历硬上限
MAX_DEPTH = 40
kAXValueCFRangeType = 4

# 列出来给人/模型看的控件:能按、能写、能选的;纯布局容器不列(--all 才列)
INTERESTING = {
    "AXButton", "AXMenuItem", "AXMenuBarItem", "AXCheckBox", "AXRadioButton", "AXPopUpButton",
    "AXMenuButton", "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXSlider",
    "AXIncrementor", "AXLink", "AXTab", "AXDisclosureTriangle", "AXCell", "AXRow", "AXSecureTextField",
    "AXStaticText", "AXImage",
}
TEXT_ROLES = {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}


# 认"不碰的框"的词(C-0.5,参照 Codex:验证码、改密码这类最后一步交给用户)。
# 🔴 web/extension/background.js 里 secretKind() 抄了同一套词,改这里要一起改。顺序有讲究:先新密码、再验证码(含"动态密码")、最后普通密码。
SECRET_WORDS = [
    ("新密码框", r"新密码|确认密码|重复密码|再次输入密码|new[ _-]?pass(word)?|confirm[ _-]?pass(word)?|re-?type[ _-]?pass(word)?|repeat[ _-]?pass(word)?"),
    ("验证码框", r"验证码|校验码|动态码|动态密码|短信码|一次性密码|captcha|verif(y|ication)[ _-]?code|sms[ _-]?code|"
                r"one[ _-]?time[ _-]?(code|pass)|\botp\b|security[ _-]?code|auth(entication)?[ _-]?code|\b2fa\b|two[ _-]?factor|vcode|checkcode"),
    ("密码框", r"密码|口令|pass(word|code)|\bpwd\b"),
]
_SECRET_RES = [(k, re.compile(w, re.I)) for k, w in SECRET_WORDS]


def secret_kind(role, subrole=None, *texts):
    """这个控件是不是 SeeU 不碰的框:返回「密码框 / 新密码框 / 验证码框」,不是返回 None。
    系统密码框(AXSecureTextField)一定是;普通文本框看标题/说明/占位字里有没有上面的词。"""
    if role == "AXSecureTextField" or subrole == "AXSecureTextField":
        t = " ".join(str(x) for x in texts if x)
        return "新密码框" if _SECRET_RES[0][1].search(t) else "密码框"
    if role not in ("AXTextField", "AXComboBox"):
        return None
    t = " ".join(str(x) for x in texts if x)
    for k, rx in _SECRET_RES:
        if rx.search(t):
            return k
    return None


class AXError(RuntimeError):
    pass


class AXRefused(AXError):
    """安全底线拒绝(密码框/密码输入状态/被对话框挡住)。调用方别换路硬点。"""


class AXRetry(AXRefused):
    """这次不做、但不是拒绝(复查 11-17 C-2.7):别的任务正占着打字、焦点在别的窗口 —— AI 应该稍后 / 先点一下再试,
    不该停手去找用户。outcome / code 给 act._ladder 报结果用。是 AXRefused 的子类:老的调用方照旧当「别硬做」处理。"""
    def __init__(self, msg, outcome="failed", code=None):
        super().__init__(msg)
        self.outcome, self.code = outcome, code


# ---------- 底层 ----------

def trusted():
    return bool(_AX["AXIsProcessTrusted"]())


def attr(el, name):
    err, v = _AX["AXUIElementCopyAttributeValue"](el, name, None)
    return v if err == 0 else None


def element_at(app_el, x, y):
    """这个 App 在屏幕点 (x, y) 处的控件(只读,不动任何东西);问不到返回 None。11-07:act.tap 按位置点之前用它认「是不是粘贴」。"""
    fn = _AX.get("AXUIElementCopyElementAtPosition")
    if fn is None or app_el is None:
        return None
    try:
        err, el = fn(app_el, float(x), float(y), None)
    except Exception:
        return None
    return el if not err else None


def attr_names(el):
    err, v = _AX["AXUIElementCopyAttributeNames"](el, None)
    return list(v) if err == 0 and v else []


def action_names(el):
    err, v = _AX["AXUIElementCopyActionNames"](el, None)
    return list(v) if err == 0 and v else []


def settable(el, name):
    err, ok = _AX["AXUIElementIsAttributeSettable"](el, name, None)
    return err == 0 and bool(ok)


def set_attr(el, name, value):
    err = _AX["AXUIElementSetAttributeValue"](el, name, value)
    if err:
        raise AXError(f"写 {name} 失败(错误码 {err})")


def perform(el, action):
    err = _AX["AXUIElementPerformAction"](el, action)
    if err:
        raise AXError(f"{action} 失败(错误码 {err})")


_NUM = r"(-?[\d.]+)"


def _axvalue(v, keys):
    """AXValue 在 pyobjc 里是不透明对象,从它的描述串里取数(公开的 description,不碰私有结构)。"""
    if v is None:
        return None
    s = str(v)
    out = []
    for k in keys:
        m = re.search(k + r":" + _NUM, s)
        if not m:
            return None
        out.append(float(m.group(1)))
    return tuple(out)


def frame(el):
    """(x, y, w, h) 屏幕点坐标,取不到 None。"""
    p = _axvalue(attr(el, "AXPosition"), ["x", "y"])
    s = _axvalue(attr(el, "AXSize"), ["w", "h"])
    return (p + s) if p and s else None


def _short(v, n=60):
    if v is None:
        return ""
    s = str(v).replace("\n", "⏎")
    return s if len(s) <= n else s[:n] + "…"


# ---------- 找 App / 窗口 ----------

def _gui_apps():
    """正在运行的、有界面的 App(NSRunningApplication)。"""
    from AppKit import NSWorkspace
    from Foundation import NSRunLoop, NSDate
    # 长驻进程(MCP 服务)不转消息循环,这张名单停在启动那一刻,之后打开的 App 找不到(11-01 Trae 实测)
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    return [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.activationPolicy() == 0]


def running_apps():
    return [(a.localizedName(), a.processIdentifier(), a.bundleIdentifier()) for a in _gui_apps()]


_base_cache = {}   # App 包路径 -> 不随系统语言变的名字(包文件名、CFBundleName、可执行文件名)
_local_cache = {}  # 名字 -> (时间, 系统现在叫它的名字)


def _bases(a):
    """11-22 中文系统 Intel Mac 实测:系统语言是中文时,正在运行的 App 叫「文本编辑」「计算器」「Safari浏览器」,
    AI 和 SeeU 代码里写的是 TextEdit / Calculator / Safari,按显示名对不上 → 「没找到正在运行的 App」。
    这里取不随语言变的名字:包文件名(TextEdit.app)、Info.plist 里的 CFBundleName / CFBundleExecutable。"""
    try:
        url = a.bundleURL()
        path = str(url.path()) if url is not None else ""
    except Exception:
        path = ""
    if not path:
        return set()
    if path in _base_cache:
        return _base_cache[path]
    import os
    import plistlib
    out = {os.path.basename(path)[:-4] if path.endswith(".app") else os.path.basename(path)}
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        for k in ("CFBundleName", "CFBundleExecutable"):
            v = info.get(k)
            if isinstance(v, str) and v:
                out.add(v)
    except Exception:
        pass
    out.discard("")
    _base_cache[path] = out
    return out


def local_name(name):
    """英文 / 包里的名字 → 系统现在显示的名字(中文系统里 TextEdit → 文本编辑、Safari → Safari浏览器)。
    已经是显示名、对不上任何正在运行的 App、或不是字符串,原样返回。结果记 2 秒(按窗口逐个比对时别每次都查一遍)。"""
    owner = str(name or "")
    if not owner or owner.isdigit():
        return name
    if owner.casefold() == "bluestacks":
        # 11-25 C-4.1:主程序没开、只有同包名的 HD-DiskCompaction 在跑时,会被归成那个名字,设备锁(认 BlueStacks)就没查。它不分语言,不换名
        return "BlueStacks"
    import time
    hit = _local_cache.get(owner)
    if hit and time.time() - hit[0] < 2:
        return hit[1]
    out = owner
    try:
        apps = _gui_apps()
        if not any(str(a.localizedName() or "") == owner for a in apps):
            low = owner.casefold()
            for a in apps:
                if any(b.casefold() == low for b in _bases(a)):
                    out = str(a.localizedName() or owner)
                    break
    except Exception:
        pass
    # 对上了记 2 秒;没对上(App 可能正在启动)只记 0.3 秒,免得刚开的 App 2 秒内都认不出(11-23 复查)
    _local_cache[owner] = (time.time() - (0 if out != owner else 1.7), out)
    return out


def same_app(shown, name):
    """系统给的名字(显示名 / 窗口的进程名)是不是这个 App(name 可以是英文名)。"""
    if not shown or not name:
        return False
    return shown == name or shown == local_name(name)


_loc_names = {}   # App 包路径 -> 各语言的显示名集合(读一次就记住)


def _bundle_local_names(path):
    """App 包里写的各语言显示名(CFBundleDisplayName / CFBundleName)。
    苹果自带 App 放 InfoPlist.loctable(一个 plist,按语言分);别家多是 <语言>.lproj/InfoPlist.strings。"""
    if path in _loc_names:
        return _loc_names[path]
    import glob
    import os
    import plistlib
    names = set()
    res = os.path.join(path, "Contents", "Resources")
    try:
        with open(os.path.join(res, "InfoPlist.loctable"), "rb") as f:
            for d in plistlib.load(f).values():
                if isinstance(d, dict):
                    names.update(v for k, v in d.items() if k in ("CFBundleDisplayName", "CFBundleName") and isinstance(v, str))
    except Exception:
        pass
    for fn in glob.glob(os.path.join(res, "*.lproj", "InfoPlist.strings")):
        try:
            raw = open(fn, "rb").read()
            try:
                d = plistlib.loads(raw)           # 二进制 / XML 写法
            except Exception:                     # 老的文本写法 "CFBundleName" = "备忘录";(UTF-16 或 UTF-8)
                txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "ignore")
                d = dict(re.findall(r'"?(CFBundle(?:Display)?Name)"?\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', txt))
            names.update(v for k, v in d.items() if k in ("CFBundleDisplayName", "CFBundleName") and isinstance(v, str))
        except Exception:
            pass
    _loc_names[path] = names
    return names


def _mirror_names():
    """iPhone 镜像各语言的名字(iPhone镜像、iPhone鏡像輸出、iPhoneミラーリング…)。没装返回空集。"""
    return _bundle_local_names("/System/Applications/iPhone Mirroring.app")


_canon_cache = {}


def canon_name(app):
    """同 _canon_name,结果记 3 秒。11-23 C-3.9:排队算占用键(sched._key)也要归一名字,一步里会调好几次;
    名字对不上正在运行的 App 时要翻一遍装着的 App 包(约 35 毫秒),不记的话每步多花零点几秒。"""
    import time
    k = str(app or "")
    hit = _canon_cache.get(k)
    if hit and time.time() - hit[0] < 3:
        return hit[1]
    out = _canon_name(app)
    if len(_canon_cache) > 200:
        _canon_cache.clear()
    _canon_cache[k] = (time.time(), out)
    return out


def _canon_name(app):
    """11-15 千问实测:AI 写中文名「备忘录」,英文系统里正在跑的叫 Notes,SeeU 找不到。
    名字(去掉「窗口标题」)对不上任何正在运行的 App 时,再看各 App 包里写的别的语言的名字,对上就换成系统现在叫它的名字;
    「窗口标题」原样接回去。纯英文、数字(进程号)、包名照旧不动;找不到也原样返回(后面照常报找不到)。"""
    s = str(app or "")
    owner, title = split_window(s)
    owner = str(owner or "").strip()
    if not owner or owner.isdigit():
        return app                          # 进程号不动
    if owner.casefold() == "iphone mirroring":
        # 镜像代码里到处按标准英文名认,不换成本地名;小写写法也归回标准写法(11-23 复查:中文系统里小写会被换成「iPhone镜像」)
        return "iPhone Mirroring" if title is None else f"iPhone Mirroring「{title}」"
    if not owner.isascii() and owner in _mirror_names():
        # 11-23:中文系统里镜像叫「iPhone镜像」,AI 照列表写中文名 → 归回英文名(镜像的那套判断按英文名认,
        # 往下找窗口、比对进程名时再经 local_name / same_app 换成系统显示名)
        return "iPhone Mirroring" if title is None else f"iPhone Mirroring「{title}」"
    if owner.isascii():
        # 11-22:中文系统里 AI 写 TextEdit,正在跑的叫「文本编辑」→ 换成系统现在叫它的名字(后面按显示名、窗口进程名找都对得上)。
        # 浏览器换成「Safari浏览器」也没事,网页层 web.canon 按包名再归回 Safari。包名(com.xxx)对不上任何 App 名,原样回去。
        n = local_name(owner)
        if n == owner:
            return app
        return n if title is None else f"{n}「{title}」"
    try:
        from AppKit import NSWorkspace
        from Foundation import NSRunLoop, NSDate
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))   # 长驻进程不转一下拿到的是旧名单
        apps = [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.activationPolicy() == 0]
        if any(a.localizedName() == owner for a in apps):
            return app
        for a in apps:
            url = a.bundleURL()
            if url is not None and owner in _bundle_local_names(str(url.path())):
                n = str(a.localizedName())
                return n if title is None else f"{n}「{title}」"
        # 没在运行:再翻装着的 App,换成它的名字(后面报「Notes 没在运行」比报「找不到 备忘录」好懂)
        import glob
        import os
        from Foundation import NSFileManager
        fm = NSFileManager.defaultManager()
        for p in sorted(glob.glob("/System/Applications/*.app") + glob.glob("/System/Applications/Utilities/*.app")
                        + glob.glob("/Applications/*.app") + glob.glob("/Applications/Utilities/*.app")
                        + glob.glob("/System/Library/CoreServices/Applications/*.app")):   # 钥匙串访问在这里
            if owner in _bundle_local_names(p):
                n = str(fm.displayNameAtPath_(p) or os.path.basename(p))
                n = n[:-4] if n.endswith(".app") else n
                return n if title is None else f"{n}「{title}」"
    except Exception:
        pass
    return app


def app_element(name_or_pid):
    """按显示名 / bundle id / pid 找 App,返回 (AX 元素, pid)。"""
    if not trusted():
        raise AXError("本进程没有辅助功能权限(系统设置 → 隐私与安全性 → 辅助功能;新版 macOS 英文界面里叫 Device Control and Data Access)")
    pid = None
    if isinstance(name_or_pid, int) or str(name_or_pid).isdigit():
        pid = int(name_or_pid)
    else:
        owner, title = split_window(name_or_pid)
        if title is not None:        # 11-01:"App「窗口标题」"按那个窗口的进程找(同名多实例也分得清)
            pid = _pid_of_window(owner, title)
        if pid is None:
            shown = local_name(owner)        # 11-22:英文名在中文系统里也认(网页层传进来的是 Safari,系统里叫 Safari浏览器)
            for n, p, b in running_apps():
                if owner in (n, b) or n == shown:
                    pid = p
                    break
    if pid is None:
        raise AXError(f"没找到正在运行的 App:{name_or_pid}")
    el = _AX["AXUIElementCreateApplication"](pid)
    _AX["AXUIElementSetMessagingTimeout"](el, MSG_TIMEOUT)
    return el, pid


def split_window(name):
    """"应用名「窗口标题」" → (应用名, 标题);没写「」→ (应用名, None)。跟 bgclick.split_target 同一写法。"""
    m = re.match(r"^(.*?)「(.*)」$", str(name or ""))
    return (m.group(1), m.group(2)) if m else (name, None)


def _pid_of_window(owner, title):
    import Quartz
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, 0) or []:
        if same_app(w.get("kCGWindowOwnerName"), owner) and (w.get("kCGWindowName") or "") == title:
            return int(w["kCGWindowOwnerPID"])
    return None


def window_titles(app):
    """App 开着的各个窗口标题(没标题的、小于 100×60 的不列,如 Gemini 那个 66×20 的「Window」)。"""
    out = []
    for w in attr(app, "AXWindows") or []:
        t, f = attr(w, "AXTitle"), frame(w)
        if t and (not f or (f[2] >= 100 and f[3] >= 60)):
            out.append(t)
    return out


def main_window(app, title=None):
    """不给标题 = 焦点窗口(没有就主窗口/第一个);给标题 = 只认那个标题的窗口,找不到返回 None。
    11-01 Gemini 实测:设置是单独的窗口,原来只看焦点窗口,AI 没法指定看设置。"""
    if title is not None:
        for w in attr(app, "AXWindows") or []:
            if attr(w, "AXTitle") == title:
                return w
        return None
    w = attr(app, "AXFocusedWindow") or attr(app, "AXMainWindow")
    if w is None:
        ws = attr(app, "AXWindows") or []
        w = ws[0] if ws else None
    return w


# ---------- 遍历成控件清单 ----------

def _walk(root, path, out, depth, all_roles, budget):
    if depth > MAX_DEPTH or budget[0] <= 0:
        return
    budget[0] -= 1
    role = attr(root, "AXRole") or ""
    if all_roles or role in INTERESTING:
        title = attr(root, "AXTitle") or ""
        desc = attr(root, "AXDescription") or ""
        val = attr(root, "AXValue")
        if role == "AXSecureTextField" or (role in TEXT_ROLES and secret_kind(
                role, None, title, desc, attr(root, "AXPlaceholderValue"))):
            val = "•••"  # 密码框/验证码框不读值
        if role != "AXStaticText" or val:  # 没字的静态文本没意义
            out.append(dict(el=root, role=role, title=_short(title), desc=_short(desc), value=_short(val),
                            path=path, frame=frame(root), actions=action_names(root),
                            enabled=attr(root, "AXEnabled")))
    for i, ch in enumerate(attr(root, "AXChildren") or []):
        _walk(ch, f"{path}/{i}", out, depth + 1, all_roles, budget)


def elements(app_name, all_roles=False, include_menu=True):
    """前台窗口(+ 菜单栏)的控件清单,按遍历顺序编号。返回 list[dict],每项带 id、el 等。"""
    app, _pid = app_element(app_name)
    out = []
    budget = [MAX_NODES]
    title = split_window(app_name)[1]
    w = main_window(app, title)
    if title is not None and w is None:
        raise AXError(f"没找到窗口「{title}」,开着的有:{'、'.join(window_titles(app)) or '(都没标题)'}")
    if w is not None:
        _walk(w, "W", out, 0, all_roles, budget)
    if include_menu:
        mb = attr(app, "AXMenuBar")
        if mb is not None:
            for i, item in enumerate(attr(mb, "AXChildren") or []):  # 只列顶层菜单,展开用 menu()
                out.append(dict(el=item, role="AXMenuBarItem", title=_short(attr(item, "AXTitle")), desc="",
                                value="", path=f"M/{i}", frame=frame(item), actions=action_names(item),
                                enabled=attr(item, "AXEnabled")))
    for i, e in enumerate(out, 1):
        e["id"] = i
    return out


def describe(e):
    f = e["frame"]
    pos = f"({f[0]:.0f},{f[1]:.0f} {f[2]:.0f}×{f[3]:.0f})" if f else ""
    txt = " ".join(x for x in (e["title"], e["desc"], f"=「{e['value']}」" if e["value"] else "") if x)
    off = "" if e["enabled"] in (None, True) else " [灰]"
    return f"{e['id']:>3}. {e['role'][2:]:<14} {txt} {pos}{off}"


def find(app_name, target, all_roles=False):
    """target:编号(int/数字串)或文字(先完全匹配标题/描述,再包含)。返回清单里的那一项。"""
    els = elements(app_name, all_roles=all_roles)
    if isinstance(target, int) or str(target).isdigit():
        n = int(target)
        for e in els:
            if e["id"] == n:
                return e
        raise AXError(f"没有编号 {n}(共 {len(els)} 个,界面可能变了,重新 list)")
    t = str(target)
    exact = [e for e in els if t in (e["title"], e["desc"])]
    part = [e for e in els if t in e["title"] or t in e["desc"] or t in e["value"]]
    hits = exact or part
    if not hits:
        raise AXError(f"没找到「{t}」")
    return hits[0]


# ---------- 安全底线 ----------

def _window_of(el):
    return attr(el, "AXWindow")


def _inside(el, ancestor):
    cur, n = el, 0
    while cur is not None and n < MAX_DEPTH:
        if cur == ancestor:
            return True
        cur = attr(cur, "AXParent")
        n += 1
    return False


def _safety_el(el):
    """安全底线硬拦(seeu/safety.py):按控件所属进程查。"""
    try:
        from seeu import safety
    except ImportError:
        return
    err, pid = _AX["AXUIElementGetPid"](el, None) if "AXUIElementGetPid" in _AX else (1, None)
    if not err and pid:
        safety.check_pid(pid)


def check_safe(e, typing=False):
    el = e["el"]
    _safety_el(el)
    kind = secret_kind(e["role"], attr(el, "AXSubrole"), attr(el, "AXTitle"), attr(el, "AXDescription"),
                       attr(el, "AXPlaceholderValue"), attr(el, "AXHelp"))
    if kind:
        raise AXRefused(f"目标是{kind},拒绝(这一步请你自己来)")
    if typing:
        try:
            from seeu_lib.input_guard import secure_input_pid
            pid = secure_input_pid()
        except Exception:
            pid = None
        if pid:
            raise AXRefused(f"系统处于密码输入状态(pid {pid}),拒绝打字")
    w = _window_of(e["el"])
    if w is not None:
        sheets = [c for c in (attr(w, "AXChildren") or []) if attr(c, "AXRole") == "AXSheet"]
        if sheets and not any(_inside(e["el"], s) for s in sheets):
            raise AXRefused("窗口上弹着对话框,目标被挡住,拒绝(先处理对话框)")


# ---------- 动作 ----------

def _focus(app_name, e):
    """先"只聚焦不置前"目标所在窗口:格式类操作只对焦点窗口生效(10-13「文本编辑」粗体实测),不聚焦会假成功。"""
    w = _window_of(e["el"])
    f = frame(w) if w is not None else None
    if not f:
        return False
    import Quartz
    from seeu import bgclick
    _, pid = app_element(app_name)
    for info in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, 0) or []:
        b = info.get("kCGWindowBounds") or {}
        if info.get("kCGWindowOwnerPID") == pid and info.get("kCGWindowLayer", 0) == 0 and \
                (round(b.get("X", -1)), round(b.get("Y", -1)), round(b.get("Width", -1)), round(b.get("Height", -1))) == \
                tuple(round(v) for v in f):
            ok = bgclick.focus_without_raise(pid, int(info["kCGWindowNumber"]))
            time.sleep(0.1)
            return ok
    return False


def press(app_name, target, focus=True):
    e = find(app_name, target)
    check_safe(e)
    if focus and e["role"] != "AXMenuBarItem":
        try:
            _focus(app_name, e)
        except Exception:
            pass  # 聚焦是加速层,失败不挡按下
    acts = e["actions"]
    act = "AXPress" if "AXPress" in acts else ("AXPick" if "AXPick" in acts else None)
    if not act:
        raise AXError(f"{describe(e)} 不支持按下(动作:{acts}),这个控件要走下一级(真鼠标)")
    perform(e["el"], act)
    return e


def _text_el(app_name, target):
    e = find(app_name, target)
    check_safe(e, typing=True)
    if e["role"] not in TEXT_ROLES:
        raise AXError(f"{describe(e)} 不是文本控件")
    return e


def type_text(app_name, target, text):
    """在光标处插入(有选中就替换选中)。读回核实,没进去抛错。"""
    e = _text_el(app_name, target)
    from seeu import safety
    safety.check_text(text)
    before = attr(e["el"], "AXValue") or ""
    set_attr(e["el"], "AXSelectedText", text)
    time.sleep(0.05)
    after = attr(e["el"], "AXValue") or ""
    if text not in after or after == before:
        raise AXError("写入后读回没看到新字(AXSelectedText 不生效),这个控件要走下一级")
    e["value"] = _short(after)
    return e


def set_text(app_name, target, text):
    e = _text_el(app_name, target)
    from seeu import safety
    safety.check_text(text)
    set_attr(e["el"], "AXValue", text)
    time.sleep(0.05)
    if (attr(e["el"], "AXValue") or "") != text:
        raise AXError("写入后读回不一致")
    e["value"] = _short(text)
    return e


def select_all(app_name, target):
    e = _text_el(app_name, target)
    n = len(attr(e["el"], "AXValue") or "")
    rng = _AX["AXValueCreate"](kAXValueCFRangeType, (0, n))
    set_attr(e["el"], "AXSelectedTextRange", rng)
    got = _axvalue(attr(e["el"], "AXSelectedTextRange"), ["location", "length"])
    if got != (0, n):
        raise AXError(f"全选后读回选中范围是 {got},不是 (0, {n})")
    return e


def menu(app_name, *path, guard=None):
    """按菜单路径点:menu("文本编辑", "文件", "新建")。逐级展开的是 AX 子元素,不弹真菜单。
    guard(菜单项):按下之前调一次,要拦就抛 AXRefused(11-07:act.menu 用它按快捷键认「粘贴」)。"""
    app, pid = app_element(app_name)
    from seeu import safety
    safety.check_menu(path)
    safety.check_pid(pid)
    cur = attr(app, "AXMenuBar")
    if cur is None:
        raise AXError("没有菜单栏")
    for i, name in enumerate(path):
        items = attr(cur, "AXChildren") or []
        if i > 0 and len(items) == 1 and attr(items[0], "AXRole") == "AXMenu":
            items = attr(items[0], "AXChildren") or []
        hit = next((it for it in items if (attr(it, "AXTitle") or "") == name), None)
        if hit is None:
            have = [attr(it, "AXTitle") for it in items if attr(it, "AXTitle")]
            raise AXError(f"菜单里没有「{name}」,有:{have}")
        cur = hit
    if attr(cur, "AXEnabled") is False:
        raise AXError(f"菜单「{'>'.join(path)}」是灰的")
    if guard:
        guard(cur)
    perform(cur, "AXPress")


# ---------- 命令行 ----------

def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = a.pop(0)
    try:
        if cmd == "apps":
            for n, p, b in running_apps():
                print(f"{p:>7}  {n}  ({b})")
        elif cmd == "list":
            all_roles = "--all" in a
            a = [x for x in a if x != "--all"]
            for e in elements(a[0], all_roles=all_roles):
                print(describe(e))
        elif cmd == "press":
            print("已按:", describe(press(a[0], a[1])))
        elif cmd == "type":
            print("已写入:", describe(type_text(a[0], a[1], a[2])))
        elif cmd == "set":
            print("已替换:", describe(set_text(a[0], a[1], a[2])))
        elif cmd == "selall":
            print("已全选:", describe(select_all(a[0], a[1])))
        elif cmd == "menu":
            menu(a[0], *a[1:])
            print("已点菜单:", " > ".join(a[1:]))
        else:
            print("不认识的命令:", cmd)
            return 2
    except AXRefused as ex:
        print("拒绝:", ex)
        return 3
    except AXError as ex:
        print("失败:", ex)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
