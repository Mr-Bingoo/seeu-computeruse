"""SeeU · 浏览器「开关」这条路(SeeU C-0.1,10-20)

浏览器自带的开关「允许来自 Apple 事件的 JavaScript」打开后,SeeU 用 osascript 在网页里跑脚本:
不用装插件,能读后台标签页、选下拉框、窗口最小化/在别的桌面也能操作(10-20 Safari、Chrome 实测全过)。
网页里跑的程序跟插件同一套(从 extension/background.js 里取 pageSnapshot / pageAct / pageRead),两条路行为一致。

  Safari:设置 → 高级 → 勾「为网页开发者显示功能」→ 开发者 → 勾「允许来自 Apple 事件的 JavaScript」(要密码)
  Chrome:菜单 显示 → 开发者 → 允许来自 Apple 事件的 JavaScript(Edge / Brave 等同内核的没实测)

🔴 这个开关是浏览器全局的,没有网站范围:SeeU 自己守一份允许名单(allow.json,I See 模式下不查),密码框/银行卡框不碰。
🔴 Chrome 用 AppleScript 新开标签/窗口会抢前台、连桌面一起切(10-20 实测);Safari 不会。开标签见 web.open。
标签页编号:"窗口id:标签" 字符串(Safari 标签 = 序号,Chrome 标签 = 标签 id),跟插件的整数 id 分开。
"""
import json
import os
import re
import subprocess
import time
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.expanduser("~/.seeu/seeu_web")   # 不跟 SEEU_HOME:中转程序是浏览器拉起的,读不到用户的环境变量,三处要对得上就都写死(11-01)
ALLOW_FILE = os.path.join(DIR, "allow.json")
SAFARI = {"Safari", "Safari Technology Preview"}
CHROME_LIKE = {"Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium", "Vivaldi"}   # Arc 没有这个开关
TIMEOUT = 20        # 第一次控制某个浏览器系统会弹授权框;没人点就卡在这,到点按「没授权」处理(定时任务别无限等)

HOWTO = {
    "safari": "Safari 设置 → 高级 → 勾「为网页开发者显示功能」→ 开发者 → 勾「允许来自 Apple 事件的 JavaScript」",
    "chrome": "Chrome 菜单栏 显示 → 开发者 → 点「允许来自 Apple 事件的 JavaScript」",
}


class AEError(RuntimeError):
    def __init__(self, msg, code="error"):
        super().__init__(msg)
        self.code = code


def supported(app):
    return app in SAFARI or app in CHROME_LIKE


def howto(app):
    return HOWTO["safari"] if app in SAFARI else HOWTO["chrome"].replace("Chrome", app if app in CHROME_LIKE else "Chrome")


def running(app):
    """只查不启动(osascript tell 一个没开的 App 会把它打开)。"""
    try:
        from seeu.ax import running_apps
        return any(n == app for n, _, _ in running_apps())
    except Exception:
        return subprocess.run(["pgrep", "-xq", app]).returncode == 0


def _instances(app):
    """这个浏览器现在开着几个(按 App 名数)。认不出时当 1 个。"""
    try:
        from seeu.ax import running_apps
        return sum(n == app for n, _, _ in running_apps())
    except Exception:
        return 1


def _single(app):
    """🔴 同时开着两个同名浏览器(如别的项目用自动化程序起了个临时 Chrome 导出页面)时,系统命令会被那个临时的接走,
    读到的标签页全不对(C-0.5 实测踩到:别的程序起的 Chrome)。这时开关这条路不用,报 multi_instance。"""
    n = _instances(app)
    if n > 1:
        raise AEError(f"现在同时开着 {n} 个 {app}(可能是别的程序临时起的),开关这条路分不清该找哪个,先不用", "multi_instance")


def _osa(script, *argv, timeout=TIMEOUT):
    try:
        r = subprocess.run(["osascript", "-e", script, *map(str, argv)], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AEError(f"等了 {timeout} 秒没回音(可能卡在系统授权弹窗「允许控制」上,没人点)", "timeout")
    if r.returncode == 0:
        return r.stdout.rstrip("\n")
    err = r.stderr.strip()
    if "-1743" in err or "Not authorized" in err:
        raise AEError("系统没授权 SeeU 控制这个浏览器(系统设置 → 隐私与安全性 → 自动化 里打开)", "denied")
    if "Allow JavaScript from Apple Events" in err or "turned off" in err:
        raise AEError("浏览器的「允许来自 Apple 事件的 JavaScript」开关没开", "switch_off")
    if "-600" in err or "isn’t running" in err or "isn't running" in err:
        raise AEError("浏览器没在运行", "no_app")
    if "-1719" in err or "Invalid index" in err or "Can’t get" in err or "Can't get" in err:
        raise AEError("没有这个窗口/标签页(可能已经关了)", "no_tab")
    raise AEError("osascript 出错:" + err[-200:], "error")


# ---------------------------------------------------------------- 标签页

# 🔴 tell 块里 tab 会被认成浏览器的「标签页」类(10-20 踩到:输出里全是字面 "tab"),分隔符用 character id 9

def _safari_tabs_script(app):
    return f'''set TB to (character id 9)
tell application "{app}"
  set out to ""
  repeat with w in windows
    try
      set wid to id of w
      set ct to index of current tab of w
      set i to 0
      repeat with t in tabs of w
        set i to i + 1
        set u to ""
        try
          set u to (URL of t) as text
        end try
        set n to ""
        try
          set n to (name of t) as text
        end try
        set out to out & wid & TB & i & TB & (i = ct) & TB & u & TB & n & linefeed
      end repeat
    end try
  end repeat
  return out
end tell'''


def _chrome_tabs_script(app):
    return f'''set TB to (character id 9)
tell application "{app}"
  set out to ""
  repeat with w in windows
    try
      set wid to id of w
      set aid to id of active tab of w
      repeat with t in tabs of w
        set out to out & wid & TB & (id of t) & TB & ((id of t) = aid) & TB & (URL of t) & TB & (title of t) & linefeed
      end repeat
    end try
  end repeat
  return out
end tell'''


def tabs(app):
    """所有窗口的所有标签页:[{id:"窗口id:标签", title, url, active, window}],窗口按前→后排。"""
    if not running(app):
        raise AEError("浏览器没在运行", "no_app")
    _single(app)
    raw = _osa(_safari_tabs_script(app) if app in SAFARI else _chrome_tabs_script(app))
    out = []
    for line in raw.splitlines():
        p = line.split("\t", 4)
        if len(p) < 5:
            continue
        out.append(dict(id=f"{p[0]}:{p[1]}", window=int(p[0]), title=p[4], url=p[3], active=p[2] == "true"))
    return out


def current(app):
    """最前面窗口当前显示的标签页。"""
    for t in tabs(app):
        if t["active"]:
            return t
    raise AEError("浏览器没有打开的窗口", "no_tab")


def find_tab(app, tab):
    if tab is None:
        return current(app)
    for t in tabs(app):
        if t["id"] == str(tab):
            return t
    raise AEError("没有这个标签页(可能已关掉)", "no_tab")


# ---------------------------------------------------------------- 跑网页脚本

def js(app, code, tab=None):
    """在标签页里跑一段 JS,返回最后一个表达式的值(字符串)。tab=None 是最前面窗口的当前标签页。"""
    if not running(app):
        raise AEError("浏览器没在运行", "no_app")
    _single(app)
    if tab is None:
        if app in SAFARI:
            s = f'on run argv\ntell application "{app}" to return do JavaScript (item 1 of argv) in current tab of window 1\nend run'
        else:
            s = f'on run argv\ntell application "{app}" to return execute active tab of window 1 javascript (item 1 of argv)\nend run'
        return _osa(s, code)
    w, t = str(tab).split(":")
    if app in SAFARI:
        s = (f'on run argv\ntell application "{app}" to return do JavaScript (item 1 of argv) in tab {int(t)} of '
             f'(first window whose id is {int(w)})\nend run')
    else:
        s = (f'on run argv\ntell application "{app}" to return execute (first tab of (first window whose id is {int(w)}) '
             f'whose id is {int(t)}) javascript (item 1 of argv)\nend run')
    return _osa(s, code)


def state(app):
    """开关状态:on / switch_off / denied / timeout / no_app / no_tab(没窗口,判断不了)/ unsupported。
    🔴 第一次对某个浏览器调用会弹系统授权框(I See 开启体检时集中弹掉)。不会把没开的浏览器打开。"""
    if not supported(app):
        return "unsupported"
    if not running(app):
        return "no_app"
    try:
        js(app, "1")
        return "on"
    except AEError as ex:
        return ex.code


_FN = {}


def _page_fn(name):
    """从插件的 background.js 里取出注入网页的函数源码(两条路共用一份)。"""
    if not _FN:
        src = open(os.path.join(HERE, "extension", "background.js"), encoding="utf-8").read()
        for m in re.finditer(r"^function (page\w+)\(", src, re.M):
            nxt = re.search(r"^function \w+\(", src[m.end():], re.M)
            _FN[m.group(1)] = src[m.start(): m.end() + nxt.start() if nxt else len(src)].strip()
    return _FN[name]


def page(app, fn, args, tab=None):
    """跑插件同款的网页函数(pageSnapshot / pageAct / pageRead),返回解析好的结果。"""
    code = ("JSON.stringify((function(){try{return (" + _page_fn(fn) + ").apply(null," +
            json.dumps(args, ensure_ascii=False) + ")}catch(e){return {__err:String(e),code:'page'}}})())")
    raw = js(app, code, tab)
    try:
        r = json.loads(raw) if raw and raw != "missing value" else None
    except ValueError:
        raise AEError("网页脚本回的东西看不懂:" + raw[:100], "script")
    if r is None:
        raise AEError("网页脚本没回话(页面可能正在跳转)", "script")
    if isinstance(r, dict) and r.get("__err"):
        raise AEError(r["__err"], r.get("code") or "page")
    return r


def wait_loaded(app, tab=None, timeout=10.0):
    """等 document.readyState == complete(有上限,到点不报错,返回 False)。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if js(app, "document.readyState", tab) == "complete":
                return True
        except AEError:
            pass
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------- SeeU 自己的允许名单(开关没有网站范围,靠自觉)
# C-0.5:跟插件合成一份。插件那边 = Chrome 授权 且 在这份名单里才碰;读写见 host.py 的 load_allow / edit_allow。

def origin(url):
    u = urlsplit(url or "")
    if u.scheme not in ("http", "https", "file"):
        return None
    return f"{u.scheme}://{u.netloc}" if u.scheme != "file" else "file://"


def _load_allow():
    try:
        return json.load(open(ALLOW_FILE, encoding="utf-8"))
    except Exception:
        return []


def allowed_list():
    return _load_allow()


def is_allowed(url):
    o = origin(url)
    return bool(o) and o in _load_allow()


def allow(url, on=True):
    """把网址所在网站(协议 + 域名 + 端口)加进 / 移出允许名单。返回改完的名单。"""
    o = origin(url if "://" in url else "https://" + url)
    if not o:
        raise AEError("只能允许 http / https 网站", "bad_url")
    lst = [x for x in _load_allow() if x != o]
    if on:
        lst.append(o)
    os.makedirs(DIR, exist_ok=True)
    tmp = ALLOW_FILE + ".tmp"           # 插件的中转程序(host.py)也会写这个文件,先写临时文件再换,不留半截
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lst, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ALLOW_FILE)
    return lst


# ---------------------------------------------------------------- 开标签页

def open_tab(app, url):
    """后台开一个新标签页,返回它的编号。Safari:AppleScript 加到最前窗口末尾(不抢前台,实测)。
    Chrome:用 open -g(AppleScript 开会抢前台切桌面);开完前台被换了就切回去。"""
    if app in SAFARI:
        if not tabs(app):
            subprocess.run(["open", "-g", "-a", app, url], check=False)
            time.sleep(1.5)
            return current(app)["id"]
        s = (f'on run argv\ntell application "{app}" to tell window 1\nset t to make new tab at end of tabs with '
             f'properties {{URL:item 1 of argv}}\nreturn ((id of it) as text) & ":" & ((count of tabs) as text)\nend tell\nend run')
        return _osa(s, url)
    before = {t["id"] for t in tabs(app)} if running(app) else set()
    front = _frontmost()
    subprocess.run(["open", "-g", "-a", app, url], check=False)
    new = None
    for _ in range(20):
        time.sleep(0.25)
        try:
            new = next((t["id"] for t in tabs(app) if t["id"] not in before), None)
        except AEError:
            new = None
        if new:
            break
    _restore_front(front)
    if not new:
        raise AEError("开了网址,但没找到新标签页", "no_tab")
    return new


def _frontmost():
    try:
        import AppKit
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def _restore_front(app_obj):
    """前台被浏览器抢了就还给原来的 App(桌面会跟着切回去)。"""
    try:
        now = _frontmost()
        if app_obj is not None and now is not None and now.processIdentifier() != app_obj.processIdentifier():
            app_obj.activateWithOptions_(0)
    except Exception:
        pass
