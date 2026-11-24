# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 网页(第 2 段,11-18):SeeU 专用的那份 Chrome / Chromium,无界面运行(--headless=new),走调试端口。

为什么要它:Linux 上 Chrome / Electron 的输入框不给 AT-SPI「改文字」接口(第 1 段实测),用户自己的 Chrome 里写不进字;
专用那份走调试端口,直接读网页结构、按编号点和填、读回核对,完全不碰桌面、不抢前台,也不需要借键盘。
整份照抄 Windows 版 seeu/win/web.py(同一套调试端口 + 网页脚本 + 允许名单),只换了 Linux 的部分:
找浏览器(google-chrome / chromium,snap 版也认)、配置放哪(snap 版只能写 ~/snap/chromium/common)、
找 / 关占着配置的进程(/proc)、脱离启动它的程序(新会话)。改 Windows 那份时记得看这边要不要跟。
"""
import builtins
import json
import os
import signal
import socket
import subprocess
import time

from seeu_lib import home
from seeu import cdp
from seeu.web import aejs
from seeu import web as _mweb
from seeu.linux import safety

BROWSERS = {
    "chrome": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome",
               "/usr/bin/chromium", "/usr/bin/chromium-browser", "/snap/bin/chromium"],
}
LAUNCH_WAIT = 30
CallErr = cdp.CDPError
_fopen = builtins.open      # 下面定义了 open(网址):读写状态文件要用内置的(Windows 版 11-11 真机栽过)


class WebError(cdp.CDPError):
    pass


def _exe(browser):
    for p in BROWSERS.get(browser, []):
        if os.path.exists(p):
            return p
    return None


def _snap(exe):
    return bool(exe) and exe.startswith("/snap/")


def _profile(browser):
    """snap 版 Chromium 只能写家目录里不带点的文件夹和它自己的 ~/snap/chromium/(~/.seeu 写不进,起来就退)。"""
    if _snap(_exe(browser)):
        return os.path.expanduser("~/snap/chromium/common/seeu-cdp")
    return os.path.normpath(home("cdp", f"linux-{browser}"))


def _state_file(browser):
    return os.path.normpath(home("cdp", f"linux-{browser}.json"))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _load(browser):
    try:
        with _fopen(_state_file(browser), encoding="utf-8") as f:       # 🔴 本文件有个 open(网址),文件要用内置的
            d = json.load(f)
        cdp._http(d["port"], "/json/version", timeout=2)
        return d
    except Exception:
        return None


def _save(browser, d):
    os.makedirs(os.path.dirname(_state_file(browser)), exist_ok=True)
    with _fopen(_state_file(browser), "w", encoding="utf-8") as f:
        json.dump(d, f)


def _profile_pids(browser):
    """还占着专用配置的进程(命令行里带这份配置的路径)。同一份配置只许一个主进程,旧的还在新的就起不来(Windows 版 11-11 踩过)。"""
    prof = "--user-data-dir=" + _profile(browser)
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == os.getpid():
            continue
        try:
            with _fopen(f"/proc/{d}/cmdline", "rb") as f:
                cmd = f.read().split(b"\0")
        except OSError:
            continue
        if any(a.decode("utf-8", "replace") == prof for a in cmd):
            out.append(int(d))
    return out


def _kill_profile(browser):
    pids = _profile_pids(browser)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if pids:
        time.sleep(1.0)


def start(browser="chrome", visible=False):
    """起专用那份(已经在跑就接上)。visible=False:无界面,不出窗口、不抢前台。返回 {port, pid, visible}。"""
    d = _load(browser)
    if d and bool(d.get("visible")) == bool(visible):
        return d
    if d:
        stop(browser)
    exe = _exe(browser)
    if not exe:
        from seeu.linux import distro
        raise WebError(f"没找到 Chrome / Chromium(装一个:{distro.browser_cmd()},或装 Google Chrome)", "no_app")
    _kill_profile(browser)
    port = _free_port()
    args = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={_profile(browser)}",
            "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    if not visible:
        args += ["--headless=new", "--window-size=1280,900"]
    else:
        args += ["--ozone-platform-hint=auto"]          # 用户要登录时开成普通窗口:Wayland 下原生显示
    args.append("about:blank")
    os.makedirs(_profile(browser), exist_ok=True)
    # 新会话 + 不接输入输出:脱离启动它的程序(MCP 服务、prlctl exec 一结束就收掉整组的),浏览器的日志也不混进协议
    p = subprocess.Popen(args, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    t0 = time.time()
    while time.time() - t0 < LAUNCH_WAIT:          # 硬上限
        try:
            cdp._http(port, "/json/version", timeout=1)
            d = dict(port=port, pid=p.pid, visible=bool(visible), browser=browser)
            _save(browser, d)
            return d
        except Exception:
            time.sleep(0.3)
    code = p.poll()
    raise WebError(f"{browser} {LAUNCH_WAIT} 秒没起来" + (f"(进程退出了,代码 {code})"
                                                         if code is not None else ""), "timeout")


def stop(browser="chrome"):
    d = _load(browser)
    if not d:
        return False
    try:
        with cdp.Session(cdp._http(d["port"], "/json/version")["webSocketDebuggerUrl"]) as s:
            s.call("Browser.close", timeout=5)
    except Exception:
        pass
    try:
        os.remove(_state_file(browser))
    except OSError:
        pass
    t0 = time.time()
    while time.time() - t0 < 8 and _profile_pids(browser):     # 等它真退出(有上限),退不掉就强关
        time.sleep(0.5)
    _kill_profile(browser)
    return True


def show(browser="chrome"):
    """用户要登录时:把专用那份开成普通窗口(会出现在桌面上,只在用户要求时调)。"""
    return start(browser, visible=True)


def hide(browser="chrome"):
    """登录完:关掉窗口,无界面重开。"""
    stop(browser)
    time.sleep(1.0)
    return start(browser, visible=False)


def _pages(d):
    return [t for t in cdp._http(d["port"], "/json/list") if t.get("type") == "page"
            and not str(t.get("url", "")).startswith("devtools://")]


def _page(d, tab):
    ps = _pages(d)
    if tab:
        p = next((t for t in ps if t["id"] == tab), None)
        if not p:
            raise WebError("这个标签页已经没了,用 tabs 重新看编号", "stale")
        return p
    if not ps:
        raise WebError("专用浏览器里没有页面,先 open 一个网址", "no_page")
    return ps[0]


def _allowed(url):
    from seeu import isee
    return isee.active() or aejs.is_allowed(url)


def _not_allowed(url):
    o = aejs.origin(url) or url
    return WebError(f"这个网站({o})不在 SeeU 允许名单里,没碰。AI 问你时答应就行,也可以运行 python -m seeu allow {o}", "not_allowed")


def _session(d, tab):
    return cdp.Session(_page(d, tab)["webSocketDebuggerUrl"])


def _fn(d, tab, fn, args):
    code = ("(function(){try{return (" + aejs._page_fn(fn) + ").apply(null," + json.dumps(args, ensure_ascii=False) +
            ")}catch(e){return {__err:String(e),code:'page'}}})()")
    with _session(d, tab) as s:
        s.call("Emulation.setFocusEmulationEnabled", {"enabled": True})    # 让页面以为自己有焦点(不然输入框不收字)
        r = s.eval(code)
    if r is None:
        raise WebError("网页脚本没回话(页面可能正在跳转)", "script")
    if isinstance(r, dict) and r.get("__err"):
        raise WebError(*aejs.page_err(r))      # 11-23 C-3.9 整体复查:网页说的话不当 SeeU 的提示(见 seeu/web/aejs.page_err)
    return r


def _wait_loaded(d, tab, timeout=10.0):
    # 新标签页先是 about:blank(它的 readyState 一上来就是 complete),要等地址换掉再看;
    # 11-12 旧 Intel Mac 的 Win10(2 核)上没等到就返回,see 读到 0 项。
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with _session(d, tab) as s:
                st = s.eval("document.readyState + '|' + location.href") or ""
                state, _, href = st.partition("|")
                if state == "complete" and href != "about:blank":
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------- 对外

def open(url, browser="chrome"):
    """在专用那份里开一个新标签页(无界面,不出窗口)。名单外的网站不开。返回标签页编号。
    专用那份正被用户叫出来(show,登录用)时就在那个看得见的窗口里开,不重启它。"""
    u = str(url or "").strip()
    if not u.lower().startswith(("http://", "https://")) or aejs.origin(u) is None:
        raise WebError("只能打开 http / https 网址", "bad_url")
    if not _allowed(u):
        raise _not_allowed(u)
    # 11-23 C-3.9 整体复查:原来固定 start(无界面)→ 用户正在叫出来的窗口里登录时,AI 一调 open 就把那个窗口关掉重启成无界面
    # (登录到一半没了)。现在:专用那份正以「看得见」的样子开着就直接用它,等用户说登完(hide)再回无界面
    d = _load(browser)
    if not (d and d.get("visible")):
        d = start(browser)
    with cdp.Session(cdp._http(d["port"], "/json/version")["webSocketDebuggerUrl"]) as s:
        tid = s.call("Target.createTarget", {"url": u})["targetId"]
    _wait_loaded(d, tid)
    # 第一次开会留着 about:blank 那页,关掉它,省得 tabs 里多一页
    for p in _pages(d):
        if p["id"] != tid and p.get("url") == "about:blank":
            try:
                cdp._http(d["port"], f"/json/close/{p['id']}")
            except Exception:
                pass
    return tid


def tabs(browser="chrome"):
    d = _load(browser)
    if not d:
        return []
    return [dict(id=p["id"], title=p.get("title", ""), url=p.get("url", "")) for p in _pages(d)]


_last = {}


def see(tab=None, browser="chrome", max_items=400):
    d = _load(browser)
    if not d:
        raise WebError("专用浏览器没开,先 open 一个网址", "no_app")
    p = _page(d, tab)
    if not _allowed(p.get("url")):
        raise _not_allowed(p.get("url"))
    r = _fn(d, p["id"], "pageSnapshot", [max_items, 20000])
    v = dict(route="调试端口", items=_mweb._items(r), text=r["text"], url=r["url"], title=r["title"],
             tab=dict(id=p["id"], title=p.get("title", ""), url=p.get("url", "")))
    _last[p["id"]] = v
    return v


def describe(items):
    return _mweb.describe(items)


def read(tab=None, browser="chrome"):
    v = see(tab, browser)
    return {k: v[k] for k in ("text", "url", "title")}


def _pick(tab, target, browser):
    cur = _last.get(tab) if tab else None
    if cur is None or not (isinstance(target, int) or str(target).isdigit()):
        cur = see(tab, browser)
    items = cur["items"]
    if isinstance(target, int) or str(target).isdigit():
        it = next((i for i in items if i["id"] == int(target)), None)
        if not it:
            raise WebError(f"没有编号 {target},先 see 一次", "not_found")
        return cur, it
    t = str(target)
    hits = [i for i in items if i["text"] == t] or [i for i in items if t in i["text"]] or \
        [i for i in items if t in (i.get("hint") or "")]
    if not hits:
        raise WebError(f"页面上没找到「{t}」", "not_found")
    return cur, hits[0]


def _act(d, cur, it, action, value=None, mode="replace"):
    return _fn(d, cur["tab"]["id"], "pageAct", [it["id"] - 1 if it else -1, action, value, mode])


def _res(outcome, reason=None, **kw):
    r = dict(outcome=outcome, route="调试端口")
    if reason:
        r["reason"] = reason
    r.update(kw)
    return r


def tap(target, tab=None, browser="chrome"):
    d = _load(browser) or start(browser)
    cur, it = _pick(tab, target, browser)
    tid = cur["tab"]["id"]
    before = _fn(d, tid, "pageRead", [20000])
    st = _act(d, cur, it, "click")
    _last.pop(tid, None)
    if it.get("checked") is not None:
        ok = st.get("checked") != it["checked"] or it["role"] == "input:radio" and st.get("checked")
        return _res("delivered" if ok else "ineffective", None if ok else "点了但勾选状态没变")
    time.sleep(0.6)
    _wait_loaded(d, tid)
    try:
        after = _fn(d, tid, "pageRead", [20000])
    except Exception:
        after = {}
    changed = after.get("url") != before.get("url") or after.get("text") != before.get("text")
    return _res("delivered" if changed else "unverified", None if changed else "点了,页面文字没变化(有的按钮本来就不变,没法核实)")


def type(target, text, tab=None, browser="chrome", mode="replace", enter=False):
    """往输入框写字(replace 清空再写 / append 接在后面)。enter=True 写完核对对了再按回车。"""
    try:
        safety.check_text(text)
    except safety.Refused as ex:
        return _res("refused", str(ex))
    d = _load(browser) or start(browser)
    cur, it = _pick(tab, target, browser)
    if it.get("secret"):
        return _res("refused", f"{_mweb._secret_name(it)},SeeU 不碰")
    st = _act(d, cur, it, "type", str(text), mode)
    _last.pop(cur["tab"]["id"], None)
    ok = _mweb._typed_ok(st, text)
    r = _res("delivered" if ok else "ineffective", None if ok else "写完读回没看到这段字")
    if enter:
        if ok:
            key("return", tab=cur["tab"]["id"], browser=browser)
            r["enter"] = "sent"
        else:
            r["enter"] = "skipped"
    return r


def key(name, *mods, tab=None, browser="chrome"):
    """往页面发一个键(调试端口原生的按键事件,Ctrl 组合也认)。焦点在密码框里时改内容的键不按。"""
    m = [safety.MOD_ALIAS.get(str(x).lower(), str(x).lower()) for x in mods]
    safety.check_keys(name, m)
    d = _load(browser) or start(browser)
    k, code, vk, text = cdp._key_spec(safety.norm_key(name))
    flag = sum({"alt": 1, "ctrl": 2, "shift": 8}.get(x, 0) for x in m)
    p = _page(d, tab)
    if not _allowed(p.get("url")):
        raise _not_allowed(p.get("url"))
    with _session(d, p["id"]) as s:
        s.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
        if safety.key_enters(name, m):
            kind = s.eval(cdp._SECRET_JS)
            if kind:
                return _res("refused", f"光标在{kind}里,SeeU 不碰(这一步请你自己来)")
        base = dict(key=k.upper() if (flag & 8 and len(k) == 1) else k, code=code, windowsVirtualKeyCode=vk,
                    nativeVirtualKeyCode=vk, modifiers=flag)
        # 跟 Mac 版 cdp.key 同一个写法:带字符、没有 Ctrl / Alt 的发 keyDown(带 text);别的发 rawKeyDown
        down = dict(base, type="keyDown", text=text, unmodifiedText=text) if text and not (flag & 3) else dict(base, type="rawKeyDown")
        s.call("Input.dispatchKeyEvent", down)
        s.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
    return _res("unverified", "按了;要确认就 see 一下")


def scroll(dy, tab=None, browser="chrome"):
    """网页里滚(dy 负 = 往下,跟别的工具一样)。"""
    d = _load(browser) or start(browser)
    p = _page(d, tab)
    if not _allowed(p.get("url")):
        raise _not_allowed(p.get("url"))
    cur = _last.get(p["id"]) or see(p["id"], browser)
    _act(d, cur, None, "scroll", -float(dy) if dy else None)
    _last.pop(p["id"], None)
    return _res("delivered")


def close_tab(tab, browser="chrome"):
    d = _load(browser)
    if d:
        cdp._http(d["port"], f"/json/close/{tab}")


# 11-17 C-2.8(照 Mac web/__init__.py 末尾):专用浏览器里打字(含写完按回车)同一个浏览器一次一个任务,
# 别的任务的回车 / 打字插进来会落到别的框里。占用键「web:chrome」(没有可找的窗口,见 sched._win_key)。调度模块出问题就不排。
try:
    from seeu import sched as _sched
    _type_raw = type
    _type_s = _sched.scheduled("web_type")(lambda app, *a, **k: _type_raw(*a, **k))

    def type(target, text, tab=None, browser="chrome", mode="replace", enter=False):      # noqa: A001
        return _type_s(_sched.WEB_KEY + str(browser), target, text, tab=tab, browser=browser, mode=mode, enter=enter)
    type.__doc__ = _type_raw.__doc__

    # 复查 11-17:按键(回车等)也按标签页投给网页里当前的框,别的任务正在打字时插进来会落进它的框 → 同一把(Mac 浏览器按键也跟打字同一个占用键)
    _key_raw = key
    _key_s = _sched.scheduled("web_press")(lambda app, *a, **k: _key_raw(*a, **k))

    def key(name, *mods, tab=None, browser="chrome"):
        return _key_s(_sched.WEB_KEY + str(browser), name, *mods, tab=tab, browser=browser)
    key.__doc__ = _key_raw.__doc__
except Exception:   # noqa: BLE001
    pass
