"""隐身浏览器:一句话拉起、打字前自检、退出(SeeU C-0.7,10-23 用户定「隐身 Safari 只给 SeeU 用」后做)。

用法:
    from seeu import stealth
    h = stealth.launch("Safari", "https://docs.qq.com/…")      # 隐身拉起 + 开页面;返回 Handle(app, pid, wid, tab)
    stealth.safe_type(h, "abc")                                  # 打字前自检:浏览器被叫到前台 / 焦点不在输入框 → 抛 StealthStop,不打
    stealth.quit(h)                                              # 干完退出(只退 SeeU 自己拉起的)
    h = stealth.adopt("Safari")                                  # 自己拉起的隐身浏览器交给 SeeU 看着
    h = stealth.restart(h)                                       # 被叫出来后:关掉、隐身重开、标签照原样开回来
    with stealth.pause(h): web.open(h.app, url2)                 # SeeU 自己开标签等会让窗口露一下的动作,包起来(看门狗暂停,做完藏好)

被叫出来就停手(10-24 C-0.9):launch / adopt 会开一个看门狗,浏览器一露面(用户点程序坞图标、看画面)就:
记下 pid → 之后 bgclick / bgkey 往它点击、按键一律抛 bgclick.CalledOut(藏回去也不放行,实测藏回去还会抢键盘,只能重开)
→ 悬浮标卡片写卡住 + 提示条 → 后台跑一次取证(seeu/参考/取证/)。不自动重开(你可能正在看它),
看完运行 `python3 -m seeu.stealth restart Safari`(或程序里 stealth.restart(h))。

约定与实测(详见 SeeU-相关要点.md 10-22 / 10-23 各节):
- **Safari**:AppleScript `count windows` 拉起 = 不开窗口;再隐藏 App、`web.open` 开页面。只给 SeeU 用:拉起时 Safari 已经开着 → 抛 StealthBusy,不碰(你的窗口)。
- **Chrome**:没有"不开窗口"的拉起法(实测);`open -n -j -g` 拉起 + 马上 System Events 藏,窗口露约 0.2~0.4 秒,不抢前台。
  用 SeeU 专用配置 `~/.seeu/seeu_chrome_profile`(不碰你自己的 Chrome)。C-1.0 起拉起时带调试端口(随机、只绑 127.0.0.1,见 seeu/cdp.py),
  web.see/tap/type 先走它读写页面,不用再手动开「允许 Apple 事件中的 JavaScript」(开着也照样当后备)。
- 藏用 System Events `set visible false`;`NSRunningApplication.hide()` 对 Chrome 没用。
- 打字前自检只在能问到时才拦(开关没开 = 问不到 = 照常打,记在 last_check)。
"""
import json, os, subprocess, sys, time
from dataclasses import dataclass
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)

CHROME_PROFILE = home("seeu_chrome_profile")
HIDE_TRIES = 4

last_check = None     # 最近一次自检结果:dict(ok, reason, note)


class StealthBusy(RuntimeError):
    """浏览器已经开着(多半是用户自己在用),SeeU 不碰,调用方告诉用户或换办法。"""


from seeu.bgclick import CalledOut      # noqa: E402  被叫出来过,SeeU 已停手(见 guard)


class StealthStop(RuntimeError):
    """打字前自检没过:浏览器被叫到前台,或页面焦点不在输入框。不打,免得字落到用户眼前/别处。"""


@dataclass
class Handle:
    app: str            # "Safari" / "Google Chrome"
    pid: int
    wid: int            # bgclick 用的窗口号
    tab: object = None  # web.open 返回的标签信息(Safari);Chrome 没有


def _osa(s, timeout=15):
    """跑一句 AppleScript,返回输出;出错 / 超时返回空串(11-06 体检:原来超时异常直接往外抛,launch / precheck 都没接)。"""
    try:
        return subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def _running(app):
    try:
        return subprocess.run(["pgrep", "-x", app], capture_output=True, timeout=5).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _front():
    return _osa('tell application "System Events" to get name of first process whose frontmost is true')


def _proc(app, pid=None):
    """System Events 里的进程:给了 pid 按 pid 找(C-1.0:VS Code 进程名是 Code、跟 App 名对不上,同名多份也不会藏错)。"""
    if not pid and app == "Google Chrome":
        # 11-06 体检:Chrome 一律先按 SeeU 专用那份的进程号找。原来按名字,用户后来又开了自己的 Chrome 时,
        # 藏 / 查的可能是用户那一份。
        pid = _chrome_pid()
    return f"(first process whose unix id is {int(pid)})" if pid else f'process "{app}"'


def is_hidden(app, pid=None):
    """藏好了没有。🔴 只有明确读到「不可见」才算藏着。11-06 体检:原来是「读到的不是 true 就算藏着」,
    osascript 出错(没给 System Events 自动化授权、进程没了)输出是空的也算藏好 → 打字前自检形同虚设。"""
    return _visible(app, pid) == "false"


def _visible(app, pid=None):
    """System Events 读到的可见性:"true" / "false" / ""(读不到:出错、超时、进程没了)。"""
    return _osa(f'tell application "System Events" to get visible of {_proc(app, pid)}')


def is_shown(app, pid=None):
    """明确读到「可见」才算露着。看门狗用这个:读不到那一轮跳过,别因为一次 osascript 出错就判成被叫出来
    (打字前自检、adopt 用 is_hidden:明确读到「不可见」才放行。两边都往保守的方向偏)。"""
    return _visible(app, pid) == "true"


def hide(app, tries=HIDE_TRIES, pid=None):
    """把 App 藏起来(System Events),多藏几次等它真藏好。返回是否藏好。"""
    for _ in range(tries):
        _osa(f'tell application "System Events" to set visible of {_proc(app, pid)} to false')
        time.sleep(0.4)
        if is_hidden(app, pid):
            return True
    return is_hidden(app, pid)


def _chrome_pid():
    try:
        r = subprocess.run(["pgrep", "-f", f"Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir={CHROME_PROFILE}"],
                           capture_output=True, text=True, timeout=5).stdout.split()
    except subprocess.TimeoutExpired:
        return None
    return int(r[0]) if r else None


def _quit_chrome():
    """只退 SeeU 专用那份 Chrome(按进程号发退出信号,再按专用配置目录兜底)。11-06 体检:原来用
    「tell application "Google Chrome" to quit」按名字退,用户自己也开着 Chrome 时可能关到用户那份。"""
    import signal
    pid = _chrome_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        t0 = time.time()
        while _chrome_pid() and time.time() - t0 < 5:
            time.sleep(0.2)
    subprocess.run(["pkill", "-f", f"user-data-dir={CHROME_PROFILE}"], timeout=5)


def launch(browser="Safari", url=None, wait_s=20, watch=True, restore=False):
    """隐身拉起浏览器并(可选)开页面。浏览器已经开着 → 抛 StealthBusy(不碰用户的)。返回 Handle。
    watch=True:顺手开看门狗(被叫出来就停手,见 guard)。"""
    h = _launch(browser, url, wait_s, restore)
    if watch:
        guard(h)
    return h


def _user_clicked_within(secs):
    """用户最近 secs 秒内有没有亲手点过鼠标 / 按过键(只晃鼠标不算)。读不到当作没有。"""
    try:
        import Quartz
        st = Quartz.kCGEventSourceStateHIDSystemState
        return min(Quartz.CGEventSourceSecondsSinceLastEventType(st, t) for t in (
            Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown, Quartz.kCGEventKeyDown)) < secs
    except Exception:
        return False


def _give_front_back(before, t_start, own_pid=None, watch_s=1.6):
    """拉起隐身浏览器之后:前台被换了就还给原来的程序。
    11-06 实测(用户全程没碰电脑):隐身 Chrome 一拉起,前台从 Claude 变成访达 / BlueStacks,而且不还回来 ——
    Chrome 启动时自己抢了前台,被我们藏掉后系统把前台交给了「下一个」,不一定是原来那个。
    盯 watch_s 秒(变化是藏完之后才发生的);这段时间里用户亲手点过 / 按过键,就当是用户自己切的,不动。"""
    if not before:
        return
    try:
        from seeu_lib import input_guard as ig
        end = time.time() + watch_s
        while time.time() < end:
            now = ig.frontmost_app()
            if now and now["pid"] != before["pid"]:
                if now["pid"] != own_pid and _user_clicked_within(time.time() - t_start):
                    return
                ig._activate_pid(before["pid"], before.get("bundle"))
            time.sleep(0.2)
    except Exception:
        pass


def _launch(browser, url, wait_s, restore=False):
    """拉起并藏好,然后把前台还给原来的程序(见 _give_front_back)。"""
    before = None
    t_start = time.time()
    try:
        from seeu_lib import input_guard as ig
        before = ig.frontmost_app()
    except Exception:
        pass
    h = _launch0(browser, url, wait_s, restore)
    _give_front_back(before, t_start, getattr(h, "pid", None))
    return h


def _launch0(browser, url, wait_s, restore=False):
    """restore=True:restart 把原来开着的标签开回来,不再过「名单外先问」那一关。"""
    from seeu import bgclick as bg
    if url and not restore:
        # 11-06:拉起之前先过「只开网页网址 + 名单外先问」这一关(原来 Safari 是拉起来之后才被拒,留下一个没人管的隐藏 Safari;
        # Chrome 的启动网址则什么都不查)。restore = restart 把原来的标签开回来,不查。
        from seeu import isee, web
        from seeu.web import aejs
        aejs._check_url(url)
        if not isee.active() and not aejs.is_allowed(url):
            o = aejs.origin(url)
            raise RuntimeError(f"{o} 不在 SeeU 允许名单里,没拉起浏览器。怎么办:{web.allow_how(o)},然后再来;或开 I See 模式")
    if browser in ("Safari",):
        if _running("Safari"):
            raise StealthBusy("Safari 已经开着(多半是你在用),隐身 Safari 只给 SeeU 用,不碰它。先退出 Safari,或改用 Chrome 隐身")
        _osa('tell application "Safari" to count windows')       # 拉起但不开窗口
        time.sleep(2)
        hide("Safari")
        tab = None
        if url:
            from seeu import web
            tab = web.open("Safari", url, ask=not restore)
            if isinstance(tab, dict) and tab.get("outcome") == "refused":    # 11-06:名单外的网站现在是「先问再开」
                raise RuntimeError(tab.get("reason") or "这个网址没打开")
            hide("Safari")
            # 隐身拉起的 Safari 当前标签是 Start Page,web.open 开的标签不是当前标签 → 切过去(踩过)
            _osa(f'tell application "Safari" to set current tab of front window to (last tab of front window)')
        mw = bg.main_window("Safari")
        if not mw:
            raise RuntimeError("隐身 Safari 拉起后找不到窗口(没开页面?给个 url)")
        return Handle("Safari", mw["pid"], mw["id"], tab)
    if browser in ("Chrome", "Google Chrome"):
        if _running("Google Chrome") and _chrome_pid() is None:
            raise StealthBusy("Chrome 已经开着(你自己的),SeeU 用专用配置另起一份会和它混在一起;先退出你的 Chrome")
        os.makedirs(CHROME_PROFILE, exist_ok=True)
        from seeu import cdp                              # C-1.0:隐身 Chrome 带调试端口(随机端口、只绑本机),读写页面不用再开 Apple 事件开关
        port = cdp._free_port()
        args = ["open", "-n", "-j", "-g", "-a", "Google Chrome", "--args", f"--user-data-dir={CHROME_PROFILE}",
                "--no-first-run", "--no-default-browser-check",
                f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"] + ([url] if url else [])
        subprocess.Popen(args)
        t0 = time.time(); pid = None
        while time.time() - t0 < wait_s:                  # 窗口一出现就藏(实测露约 0.2~0.4 秒)
            pid = pid or _chrome_pid()
            if pid and _has_window(pid):
                hide("Google Chrome", tries=1, pid=pid)
                break
            time.sleep(0.05)
        if pid is None:
            raise RuntimeError("Chrome 没拉起来")
        hide("Google Chrome")
        t0 = time.time()
        while not cdp._port_ok(port) and time.time() - t0 < 10:
            time.sleep(0.3)
        if cdp._port_ok(port):
            cdp.register("Google Chrome", pid, port, CHROME_PROFILE)
        else:
            print("[SeeU] 隐身 Chrome 调试端口没开,读页面退回 Apple 事件开关那条路", file=sys.stderr)
        mw = bg.main_window("Google Chrome")
        if not mw:
            raise RuntimeError("隐身 Chrome 拉起后找不到窗口(没开页面?给个 url)")
        return Handle("Google Chrome", pid, mw["id"])
    raise ValueError(f"不认识的浏览器 {browser}(Safari / Chrome)")


def _has_window(pid):
    import Quartz
    return any(w["kCGWindowOwnerPID"] == pid and w.get("kCGWindowLayer") == 0
               for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or [])


def precheck(h):
    """打字前自检。返回 (ok, reason)。reason: "" / "front"(浏览器在前台) / "visible"(窗口露着) / "no_focus"(页面焦点不在输入框)。
    问不到焦点(开关没开等)不拦,note 里记下。结果也写进 last_check。"""
    global last_check
    from seeu import bgclick as bg
    if h.pid in bg.CALLED_OUT:
        last_check = dict(ok=False, reason="called_out", note=f"{h.app} 被叫出来过,藏回去也会抢键盘,要重开")
        return False, "called_out"
    if _front() == h.app:
        last_check = dict(ok=False, reason="front", note=f"{h.app} 在前台,可能你在用,不打")
        return False, "front"
    if not is_hidden(h.app, h.pid):
        last_check = dict(ok=False, reason="visible", note=f"{h.app} 的窗口露在桌面上(或读不到它藏没藏好),不打")
        return False, "visible"
    from seeu import bgkey
    ok = bgkey._focus_ok(h.app)
    if ok is False:
        last_check = dict(ok=False, reason="no_focus", note="页面焦点不在输入框")
        return False, "no_focus"
    last_check = dict(ok=True, reason="", note="" if ok else "没核实焦点(开关没开或没授权)")
    return True, ""


def safe_type(h, text, **kw):
    """自检通过才打(bgkey.type_unicode);没过抛 StealthStop。"""
    from seeu import bgkey
    ok, why = precheck(h)
    if not ok:
        todo = {"front": "等你离开浏览器再继续", "visible": "把它藏回去(stealth.hide)再继续", "no_focus": "先点输入框(bgclick.tap)再打",
                "called_out": "跟 AI 说一声就能重开(也可以终端 python3 -m seeu.stealth restart %s)" % _short(h.app)}.get(why, "")
        raise StealthStop(f"卡在:往 {h.app} 打字前 原因:{last_check['note']}。怎么办:{todo}")
    from seeu import bgclick as bg
    bg.focus_without_raise(h.pid, h.wid)
    return bgkey.type_unicode(h.pid, text, **kw)


def _short(app):
    return "Chrome" if "Chrome" in app else app


def _app_name(b):
    return "Google Chrome" if b in ("Chrome", "Google Chrome", "chrome") else "Safari"


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


GUARD_EVERY_S = 0.3          # 查窗口露没露面(Quartz,本进程内,很便宜)
GUARD_ASK_EVERY = 5          # 每几次再用 System Events 问一次 visible(窗口在别的桌面时 Quartz 看不到)
_guards = {}                 # pid -> 线程
_paused = set()              # pid:SeeU 自己在动它(开标签等会让窗口露一下),看门狗这段时间不算
_evidence = {}               # App 名 -> 取证进程。🔴 重开前要等它跑完:它在读标签,浏览器一退它又把浏览器叫起来(10-24 实测卡 15 秒)
EVIDENCE_WAIT_S = 30


def guard(h, on_called_out=None):
    """看门狗(后台线程,进程退出自动停;浏览器退出就停):浏览器一露面就停手。
    on_called_out(h) 可选:调用方自己还想做的事(如记日志、让主循环退出)。同一个 pid 只开一个。"""
    import threading
    if h.pid in _guards and _guards[h.pid].is_alive():
        return _guards[h.pid]

    def run():
        n = 0
        while _alive(h.pid):
            n += 1
            if h.pid in _paused:
                time.sleep(GUARD_EVERY_S)
                continue
            try:
                out = _has_window(h.pid) or (n % GUARD_ASK_EVERY == 0 and is_shown(h.app, h.pid))
            except Exception:
                out = False
            if out:
                _called_out(h)
                if on_called_out:
                    try:
                        on_called_out(h)
                    except Exception:
                        pass
                return
            time.sleep(GUARD_EVERY_S)

    t = threading.Thread(target=run, name=f"seeu-stealth-guard-{h.pid}", daemon=True)
    _guards[h.pid] = t
    t.start()
    return t


class pause:
    """SeeU 自己要动隐身浏览器、可能让窗口露一下时(Chrome 开新标签会露),包起来:看门狗暂停,做完先藏好再接着看。
        with stealth.pause(h):
            web.open(h.app, url)
    10-25 实测:AppleScript 给隐身 Chrome 开标签,窗口露出来,看门狗当成被叫出来了。"""

    def __init__(self, h):
        self.h = h

    def __enter__(self):
        _paused.add(self.h.pid)
        return self.h

    def __exit__(self, *exc):
        try:
            hide(self.h.app, pid=self.h.pid)
        finally:
            _paused.discard(self.h.pid)
        return False


CALLED_FILE = home("seeu_called_out.json")    # 11-02:被叫出来记一笔;AI 代重开只认这里记过的(防关掉用户自己开的浏览器)


def mark_called(app, on=True):
    try:
        d = json.load(open(CALLED_FILE, encoding="utf-8")) if os.path.exists(CALLED_FILE) else {}
    except Exception:
        d = {}
    if on:
        d[app] = time.time()
    else:
        d.pop(app, None)
    try:
        with open(CALLED_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(CALLED_FILE + ".tmp", CALLED_FILE)
    except Exception:
        pass


def was_called_out(app, hours=24):
    try:
        t = json.load(open(CALLED_FILE, encoding="utf-8")).get(app)
    except Exception:
        return False
    return bool(t) and time.time() - t < hours * 3600


def _called_out(h):
    """记下被叫出来 → bgclick/bgkey 停手;卡片 + 提示条;后台取证。"""
    from seeu import bgclick as bg
    bg.CALLED_OUT[h.pid] = (h.app, time.time())
    mark_called(h.app)
    cmd = getattr(h, "restart_cmd", "") or f"python3 -m seeu.stealth restart {_short(h.app)}"   # 调试端口那份(VS Code 等)有自己的重开命令
    todo = f"SeeU 已停手。你看完后跟 AI 说一声就能重开" + ("(标签照原样开回来)" if "stealth" in cmd else "") + f";也可以终端 {cmd}"
    try:
        from seeu import isee
        isee.stuck(h.app, "隐身干活", f"{h.app} 被叫到桌面上了(藏回去也会抢你的键盘)", todo=todo)
    except Exception:
        pass
    try:                     # 当场取证(只读,几秒);10-22 那次一直没拿到现场
        _evidence[h.app] = subprocess.Popen([sys.executable, "-m", "seeu", "取证"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    print(f"[SeeU] {h.app} 被叫出来了,已停手;{todo}", file=sys.stderr, flush=True)


def adopt(browser="Safari", watch=True):
    """接管一个已经隐身开着的浏览器(调用方自己拉起的),开看门狗。没开着 / 现在露着 → 抛错。"""
    from seeu import bgclick as bg
    app = _app_name(browser)
    if not _running(app):
        raise RuntimeError(f"{app} 没开着,用 stealth.launch 拉起")
    if not is_hidden(app):
        raise StealthStop(f"{app} 现在露在桌面上,不是隐身状态;要隐身干活先重开(跟 AI 说一声,或终端 python3 -m seeu.stealth restart {_short(app)})")
    mw = bg.main_window(app)
    if not mw:
        raise RuntimeError(f"{app} 开着但找不到窗口(没开页面?)")
    pid = _chrome_pid() if app == "Google Chrome" else mw["pid"]
    h = Handle(app, pid or mw["pid"], mw["id"])
    if watch:
        guard(h)
    return h


def tab_urls(app):
    """所有标签页网址(只要 http/https/file),外加当前那个。问不到返回 ([], None)。隐身 Chrome 先问调试端口。"""
    if app == "Google Chrome":
        try:
            from seeu import cdp
            ch = cdp.running(app, fresh=True)
            if ch:
                ps = [t for t in cdp.pages(ch) if t.get("url", "").split(":", 1)[0] in ("http", "https", "file")]
                urls = [t["url"] for t in reversed(ps)]        # /json/list 新开的在前,反过来 = 标签顺序(近似)
                return urls, (ps[0]["url"] if ps else None)
        except Exception:
            pass
    try:
        from seeu.web import aejs
        ts = aejs.tabs(app)
    except Exception:
        return [], None
    urls = [t["url"] for t in ts if t["url"].split(":", 1)[0] in ("http", "https", "file")]
    cur = next((t["url"] for t in ts if t["active"] and t["url"] in urls), None)
    return urls, cur


QUIT_WAIT_S = 15


def restart(target="Safari", urls=None):
    """被叫出来后一键重开:记下标签 → 退出 → 隐身拉起 → 标签照原样开回来、切回原来那个 → 开看门狗。返回新 Handle。
    target = Handle 或浏览器名。urls 不给就自己读(读不到就只拉起空的)。🔴 会关掉这个浏览器的所有窗口(隐身 Safari 只给 SeeU 用,用户 10-23 定)。"""
    from seeu import bgclick as bg
    app = target.app if isinstance(target, Handle) else _app_name(target)
    cur = None
    if urls is None:
        urls, cur = tab_urls(app) if _running(app) else ([], None)
    urls = list(dict.fromkeys(urls))
    # 11-06:现在只开 http / https;原来开着的本地文件标签(file://)开不回来,先说一声,别让重开卡在半路
    skip = [u for u in urls if not u.lower().startswith(("http://", "https://"))]
    if skip:
        print(f"[SeeU] 这些标签不是网页网址,重开后不会开回来:{skip}", file=sys.stderr)
        urls = [u for u in urls if u not in skip]
    if cur in skip:
        cur = None
    first = cur or (urls[0] if urls else None)
    ev = _evidence.pop(app, None)
    if ev:
        try:
            ev.wait(EVIDENCE_WAIT_S)
        except subprocess.TimeoutExpired:
            ev.kill()
    if _running(app):
        if isinstance(target, Handle):
            quit(target)
        elif app == "Google Chrome":
            _quit_chrome()
        else:
            _osa(f'tell application "{app}" to quit')
        t0 = time.time()
        while (_running(app) if app == "Safari" else _chrome_pid()) and time.time() - t0 < QUIT_WAIT_S:
            time.sleep(0.3)
        if (_running(app) if app == "Safari" else _chrome_pid()):
            raise RuntimeError(f"{app} {QUIT_WAIT_S} 秒没退出(可能弹了「要不要关掉 N 个标签」之类的框),请手动退出后再运行一次")
    for pid in [p for p, v in bg.CALLED_OUT.items() if v[0] == app]:
        bg.CALLED_OUT.pop(pid, None)
    mark_called(app, False)
    h = launch(app, first, watch=False, restore=True)
    rest = [u for u in urls if u != first]
    if rest:
        from seeu import web
        with pause(h):                    # 开标签 Chrome 会露一下窗口,别让看门狗当成被叫出来
            for u in rest:
                try:
                    r = web.open(app, u, ask=False)
                    if isinstance(r, dict) and r.get("outcome") == "refused":     # 不是网页网址(如 file://、浏览器自带页)
                        print(f"[SeeU] 没重开这个标签 {u}: {r.get('reason')}", file=sys.stderr)
                except Exception as e:
                    print(f"[SeeU] 重开标签失败 {u}: {e}", file=sys.stderr)
            if first and app == "Safari":     # 切回原来那个标签(web.open 开的会抢成当前标签时)
                esc = first.replace("\\", "\\\\").replace('"', '\\"')
                _osa(f'tell application "Safari" to set current tab of front window to '
                     f'(first tab of front window whose URL is "{esc}")')
            elif first:
                _osa(f'tell application "Google Chrome" to set active tab index of front window to 1')
    guard(h)
    return h


def quit(h):
    """退出 SeeU 自己拉起的那份。"""
    if h.app != "Google Chrome":
        _osa(f'tell application "{h.app}" to quit')
        time.sleep(2)
    if h.app == "Google Chrome":
        _quit_chrome()
        time.sleep(1)
        try:
            from seeu import cdp
            cdp.unregister("Google Chrome")
        except Exception:
            pass
        # 11-06 体检:只清 SeeU 专用那份留下的崩溃上报进程。原来 pkill -f chrome_crashpad_handler 会把
        # VS Code、Edge、Slack 等所有 Chromium 内核 App 的同名进程一起杀掉。
        subprocess.run(["pkill", "-f", f"chrome_crashpad_handler.*{os.path.basename(CHROME_PROFILE)}"], timeout=5)


def main(argv=None):
    """python3 -m seeu.stealth restart [Safari|Chrome]  —— 被叫出来后一键重开(标签照原样开回来)
    python3 -m seeu.stealth status  [Safari|Chrome]  —— 看它藏没藏、开着哪些标签
    python3 -m seeu.stealth demo    [Safari|Chrome]  —— 自测:拉起、自检、打 3 个字、退出"""
    argv = argv or sys.argv[1:]
    if argv and argv[0] in ("restart", "重开"):
        app = _app_name(argv[1] if len(argv) > 1 else "Safari")
        if not (_running(app) if app == "Safari" else _chrome_pid()):
            print(f"{app} 没开着,不用重开(干活的程序会自己 stealth.launch 拉起)"); return
        urls, cur = tab_urls(app)
        print(f"要重开 {app},标签 {len(urls)} 个:" + "".join(f"\n  {'→ ' if u == cur else '  '}{u}" for u in urls), flush=True)
        h = restart(app, urls=urls)
        print(f"已隐身重开:{h.app} pid={h.pid},藏着={is_hidden(h.app)};标签 {len(tab_urls(h.app)[0])} 个", flush=True)
        print("注意:这是命令行重开,看门狗跟着这个命令一起结束;干活的程序要自己 stealth.adopt 接着看。")
        return
    if argv and argv[0] in ("status", "状态"):
        app = _app_name(argv[1] if len(argv) > 1 else "Safari")
        if not _running(app):
            print(f"{app} 没开着"); return
        urls, cur = tab_urls(app)
        print(f"{app}:{'藏着' if is_hidden(app) else '露在桌面上'};在前台={_front() == app};标签 {len(urls)} 个"
              + "".join(f"\n  {'→ ' if u == cur else '  '}{u}" for u in urls))
        return
    if not argv or argv[0] != "demo":
        print(main.__doc__); return
    b = argv[1] if len(argv) > 1 else "Safari"
    here = os.path.dirname(os.path.abspath(__file__))
    srv = None
    if b == "Safari":      # Safari 只开放行的网站:用本机测试页
        srv = subprocess.Popen([sys.executable, "-m", "http.server", "8777", "--bind", "127.0.0.1", "--directory",
                                os.path.join(here, "web", "testpages")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        page = "http://127.0.0.1:8777/typing.html"
    else:
        page = "file://" + os.path.join(here, "参考", "隐藏Chrome测试", "page.html")
    h = launch(b, page)
    print("拉起:", h, "隐藏=", is_hidden(h.app), flush=True)
    try:
        if b == "Safari":      # 测试页不自动放焦点:先不放,演示自检会拦;再放了,演示放行
            from seeu.web import aejs
            print("没放焦点时自检:", precheck(h), last_check, flush=True)
            aejs.js("Safari", "document.getElementById('t').focus(); 1")
        print("自检:", precheck(h), last_check, flush=True)
        safe_type(h, "abc")
        print("打了 abc,自检记录:", last_check, flush=True)
        if b == "Safari":
            from seeu.web import aejs
            print("页面输入框:", aejs.js("Safari", "document.getElementById('t').value"), flush=True)
        else:
            print("页面标题:", _osa('tell application "Google Chrome" to get title of active tab of front window'), flush=True)
    finally:
        quit(h)
        srv and srv.terminate()
        print("已退出", flush=True)


if __name__ == "__main__":
    main()
