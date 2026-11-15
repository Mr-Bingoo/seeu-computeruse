# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 网页(第 2 段,11-11):SeeU 专用的那份 Chrome / Edge,无界面运行(--headless=new),走调试端口。

为什么这样(依据见 SeeU-相关要点「11-11 C-1.1.5」):Windows 上给用户自己的 Chrome 发消息能用(第 1 段),但核实靠截图 / UIA,
窗口被挡住时 Chrome 不重画;专用那份走调试端口,直接读网页结构、按编号点和填、读回核对,完全不碰桌面、不抢前台。
- 单独配置(<SEEU_HOME>\\cdp\\win-chrome)、随机端口、只连 127.0.0.1;用户自己的 Chrome 不受影响(配置不同,互不相干)。
- 只碰允许名单里的网站(跟 Mac 版同一份名单 ~/.seeu/seeu_web/allow.json;I See 开着不限);密码 / 验证码 / 银行卡框不打字。
- 要登录的网站:show() 把同一份配置开成普通窗口让用户自己登录,hide() 关掉再无界面重开(登录状态留在配置里)。

复用 Mac 版的:cdp.WS / Session(自己实现的 WebSocket)、网页脚本 pageSnapshot / pageAct / pageRead、允许名单、清单格式。
"""
import builtins
import json
import os
import socket
import subprocess
import time

from seeu_lib import home
from seeu import cdp
from seeu.web import aejs
from seeu import web as _mweb
from seeu.win import safety

BROWSERS = {
    "chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
    "edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
}
LAUNCH_WAIT = 30
CallErr = cdp.CDPError
_fopen = builtins.open      # 下面定义了 open(网址):11-11 真机就栽在这,读写状态文件调到了它,报错被当成「还没起来」一直等到超时


class WebError(cdp.CDPError):
    pass


def _exe(browser):
    for p in BROWSERS.get(browser, []):
        p = os.path.expandvars(p)
        if os.path.exists(p):
            return p
    return None


def _profile(browser):
    return os.path.normpath(home("cdp", f"win-{browser}"))


def _state_file(browser):
    return os.path.normpath(home("cdp", f"win-{browser}.json"))


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
    """还占着专用配置的进程(命令行里带这份配置的路径)。Chrome 同一份配置只许一个主进程:旧的还在,新起的会把活交给它、自己退出,
    端口就永远等不到(11-11 真机:上一次没起成功留下的进程把后面全堵了)。"""
    prof = _profile(browser).lower()
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | "
                            "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                           capture_output=True, text=True, timeout=20, creationflags=0x08000000)
    except Exception:
        return []
    out = []
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition("\t")
        if prof in cmd.lower() and pid.strip().isdigit():
            out.append(int(pid))
    return out


def _kill_profile(browser):
    pids = _profile_pids(browser)
    for pid in pids:
        subprocess.run(["taskkill", "/pid", str(pid), "/t", "/f"], capture_output=True, timeout=10, creationflags=0x08000000)
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
        raise WebError(f"没找到 {browser}(Chrome / Edge 没装?)", "no_app")
    _kill_profile(browser)
    port = _free_port()
    args = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={_profile(browser)}",
            "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    if not visible:
        args += ["--headless=new", "--window-size=1280,900"]
    args.append("about:blank")
    # DETACHED | BREAKAWAY_FROM_JOB | NEW_PROCESS_GROUP:脱离启动它的程序,prlctl exec 那种一结束就收掉整组的才活得下来。
    # 11-12 Codex 实测:Codex 拉起的 SeeU 在一个不许脱离的作业里,带 BREAKAWAY 直接「拒绝访问」(WinError 5)
    # → 被拒就不带它再起一次(浏览器跟着 Codex 走,Codex 关掉时一起没,下次用再起)。
    try:
        p = subprocess.Popen(args, creationflags=0x00000008 | 0x01000000 | 0x00000200, close_fds=True)
    except PermissionError:
        p = subprocess.Popen(args, creationflags=0x00000008 | 0x00000200, close_fds=True)
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
    raise WebError(f"{browser} {LAUNCH_WAIT} 秒没起来" + (f"(进程退出了,代码 {code};21 = 这份配置被别的 {browser} 进程占着)"
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
        raise WebError(r["__err"], r.get("code") or "page")
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
    """在专用那份里开一个新标签页(无界面,不出窗口)。名单外的网站不开。返回标签页编号。"""
    u = str(url or "").strip()
    if not u.lower().startswith(("http://", "https://")) or aejs.origin(u) is None:
        raise WebError("只能打开 http / https 网址", "bad_url")
    if not _allowed(u):
        raise _not_allowed(u)
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
