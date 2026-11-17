# -*- coding: utf-8 -*-
"""SeeU 多任务调度(11-17 C-2.5,方案见 SeeU-多任务调度设计.md 第一步)。

几个任务(各个 AI 会话 / 程序)同时用 SeeU 时:
  - 第 ② 层「App 占用」:同一个 App 一次只让一个任务动手(Mac 一个 App 只有一个焦点,交错点 / 打字会写串窗口)。
    任务动完一步后接着占这个 App LEASE_S 秒,同一任务的下一步直接用;别的任务先来先办地排队,最多等 WAIT_APP_S 秒。
  - 第 ① 层「借真鼠标」:SeeU 自己的任务之间排队(real_wait),别的项目占着桌面锁照旧直接拒(在 act._real_mouse 里)。
  - 只记录(第 ③ 层任务窗口协议的数据):每个动作的用时、截图用时、排队等了多久、当时负载、同时有几个任务,
    写 ~/.seeu/seeu_sched/samples.jsonl(超过 SAMPLES_MAX 字节切一次,只留一份旧的)。还不限制同时放行几个。

状态放 ~/.seeu/seeu_sched/state.json,所有「读-判断-写」包在同一把 flock 里(写用临时文件 + rename)。
任何等待都有上限;调度自己出错(文件读写失败等)一律放行,不因为调度挡住动作。
"""
import contextlib
import json
import os
import sys
import threading
import time

LEASE_S = 5.0          # 动完一步后接着占这个 App 多久(同一任务下一步直接用)
WAIT_APP_S = 30.0      # 排队等同一个 App 最多多久
WAIT_REAL_S = 15.0     # 排队等别的 SeeU 任务借完真鼠标最多多久
YIELD_AFTER_S = 10.0   # 有人排队超过这么久,占着的任务做完当前这一步就得让(防止一直续占、后面的永远等不到)
STALE_AFTER_S = 3.0    # 排队超过这么久才轮到的「按位置点」,先核画面变没变
STALE_CHANGE = 0.03    # 排队期间目标窗口画面变了这么多(像素占比)就不点
RECENT_S = 60.0        # 「同时在用 SeeU 的任务」按最近这么久动过算
POLL_S = 0.15
BUSY_MAX_S = 120.0     # 「正在做」超过这么久没报到(见 BEAT_S)当卡死,清掉(某个动作挂住时别把 App 一直占着)
BEAT_S = 20.0          # 11-18 C-2.8:动作做得久(打很长一段字)时,每这么久报一次「还在做」,别被别人当卡死插进来
BUSY_HARD_S = 600.0    # 报到最多报这么久;一个动作超过它就不再报,再过 BUSY_MAX_S 被当卡死清掉
FLOCK_WAIT_S = 5.0     # 等状态文件锁最多这么久;拿不到就不排(放行),不让整个 SeeU 卡住
STALE_BOX_PT = 80      # 防过时只比点击点附近这么大一块(点),画面别处一直在动(镜像、视频)不算
SAMPLES_MAX = 5 * 1024 * 1024
FOCUS_KEEP_S = 600.0   # 「谁最后动过这个 App 的焦点」记多久(外部评审 11-17 第 1 条)
QUEUE_GONE_S = 20.0    # 排队的人这么久没报到(每秒报一次)就当已经走了;要远比 FLOCK_WAIT_S 长(等状态锁、排队前截图时报不了到)
SEEN_EVERY_S = 1.0
RELEASE_TRIES = 2      # 做完让出拿不到状态锁时再试几次(每次最多 FLOCK_WAIT_S 秒)


def _dir():
    return os.environ.get("SEEU_SCHED_DIR") or os.path.expanduser("~/.seeu/seeu_sched")


def _state_path():
    return os.path.join(_dir(), "state.json")


# ---------------------------------------------------------------- 认任务

CLIENT_NAMES = (("claude", "Claude"), ("codex", "Codex"), ("chatgpt", "Codex"), ("cursor", "Cursor"), ("trae", "Trae"),
                ("copilot", "VSCode"), ("visual studio", "VSCode"), ("vscode", "VSCode"), ("workbuddy", "Buddy"),
                ("qwen", "千问"), ("千问", "千问"), ("doubao", "豆包"), ("豆包", "豆包"), ("chatbox", "Chatbox"))


def pretty_client(raw):
    """客户端报的名字 → 短名(灵动岛一行最多 4 个汉字 / 8 个字母,留位置给编号)。认不出取前 6 个字母。"""
    r = str(raw or "").strip()
    low = r.lower()
    for k, v in CLIENT_NAMES:
        if k in low:
            return v
    return "".join(ch for ch in r if ch.isalnum())[:6] or "AI"


def me():
    """(任务号, 基础名)。AI 走工具:mcp_server 启动时设 SEEU_TASK_ID=mcp:<进程号>、SEEU_TASK_CLIENT=客户端名;
    命令行 / 程序:有 SEEU_PROJECT 按它(几条命令算同一个任务),没有就每个进程一个任务。
    显示名(灵动岛、光标名牌用)在基础名上自动编号去重,见 _name_for。"""
    proj = (os.environ.get("SEEU_PROJECT") or "").strip()
    tid = os.environ.get("SEEU_TASK_ID") or (f"proj:{proj}" if proj else f"pid:{os.getpid()}")
    client = os.environ.get("SEEU_TASK_CLIENT")
    name = proj or (pretty_client(client) if client else "") or "SeeU"
    return tid, name


# 光标颜色(用户 11-17 在小样里定「鲜明」):第 0 个是 SeeU 紫;其余跟紫、借鼠标橙、卡住红都拉开
PALETTE = ("#7F77DD", "#2F8BEF", "#13A3A6", "#2FA866", "#E2609C", "#8AA62C", "#A97650", "#5F7F99")


def _hash(s):
    h = 2166136261
    for ch in str(s):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _color_for(st, tid, base):
    """这个任务的光标颜色号:没别的任务在用时拿 0(SeeU 紫,跟一个任务时一样);有就按名字挑 1~7,跟在用的不重复。
    同一任务一直用同一个。存在 st["colors"],跟 names 一起清。"""
    cols = st.setdefault("colors", {})
    used = {v for t, v in cols.items() if t != tid}
    if tid in cols:
        if cols[tid] != 0 and 0 not in used:
            cols[tid] = 0          # 复查 11-17:别的任务都走了 → 换回 SeeU 紫(名牌也会写回 SeeU,颜色跟着统一)
        return cols[tid]
    if 0 not in used:
        k = 0
    else:
        k = _hash(base) % (len(PALETTE) - 1) + 1
        for _ in range(len(PALETTE)):
            if k not in used:
                break
            k = k % (len(PALETTE) - 1) + 1
    cols[tid] = k
    return k


def _name_for(st, tid, base, now):
    """这个任务的显示名:基础名没被别的在用任务占着就用它,占着就加最小编号(Claude、Claude2…);同一任务一直用同一个。
    存在 st["names"];不在用的任务(超过 RECENT_S 没动)的名字会被 _purge 清掉、可以再分。"""
    names = st.setdefault("names", {})
    cur = names.get(tid)
    taken = {v for t, v in names.items() if t != tid}
    if cur and cur not in taken and (cur == base or cur.startswith(base)):
        return cur
    if base not in taken:
        names[tid] = base
    else:
        n = 2
        while f"{base}{n}" in taken:
            n += 1
        names[tid] = f"{base}{n}"
    return names[tid]


def _publish(display, color_idx=None):
    """显示名、光标颜色号放进环境变量,本进程里的悬浮窗 / 光标调用拿得到;写了 SEEU_PROJECT 的照旧用项目名。"""
    os.environ["SEEU_TASK_DISPLAY"] = display
    if color_idx is not None:
        os.environ["SEEU_TASK_COLOR"] = str(color_idx)


def cursor_key():
    """这个任务的光标名(显示进程按它分光标):显示名;还没分到就用基础名。"""
    return os.environ.get("SEEU_TASK_DISPLAY") or me()[1]


def cursor_color(default=None):
    """这个任务的光标颜色 (r,g,b) 0~1。第 0 号用 default(设置里的「后台模式颜色」),其余按色板。"""
    try:
        k = int(os.environ.get("SEEU_TASK_COLOR", "0"))
    except ValueError:
        k = 0
    if k == 0 and default:
        return default
    h = PALETTE[k % len(PALETTE)].lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def island_wait(app, on, info=None):
    """排队中:告诉灵动岛(悬浮窗)把这个任务放进下段「排队中」;on=False 收回。悬浮窗关着 / 旧版都不管。"""
    if os.environ.get("SEEU_NO_WATCH"):
        return
    try:
        if WIN:
            from seeu.win import floatwin as ww
        else:
            from seeu_lib import watch_window as ww
        f = getattr(ww, "queue", None)
        if f:
            info = info or {}
            f(label_of(_key(app)), on, pos=max(1, int(info.get("ahead") or 1)), holder=info.get("holder") or "",
              color=cursor_hex())
    except Exception:
        pass


def cursor_hex(default=None):
    """光标颜色的 "#RRGGBB"(灵动岛圆点用,跟光标一致;0 号走设置里的后台模式颜色)。"""
    if default is None:
        try:
            default = _act()._cursor_style("bg")[1]
        except Exception:
            default = None
    r, g, b = cursor_color(default)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def cursor_wait(on):
    """排队中:让这个任务的光标打瞌睡(飘 z + 变淡);轮到了收掉。光标没开 / 显示进程是旧版都不管。"""
    if os.environ.get("SEEU_NO_CURSOR"):
        return
    try:
        if WIN:
            from seeu.win import cursor as co
        else:
            from seeu_lib import cursor_overlay as co
        f = getattr(co, "wait", None)
        if f:
            f(cursor_key(), on)
    except Exception:
        pass


WIN = sys.platform == "win32"


def _alive(pid):
    """进程还在不在。🔴 Windows 上不能用 os.kill(pid, 0):那是 TerminateProcess,会把对方直接杀掉(11-17 C-2.6)。"""
    try:
        pid = int(pid)
    except Exception:
        return True
    if pid <= 0:
        return False
    if WIN:
        try:
            import ctypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = ctypes.c_void_p
            k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            h = k.OpenProcess(0x1000, 0, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ctypes.get_last_error() == 5    # 拒绝访问 = 进程在(别人的 / 管理员的);别的错 = 没这个进程
            try:
                code = ctypes.c_uint32()
                if not k.GetExitCodeProcess(h, ctypes.byref(code)):
                    return True
                return code.value == 259               # STILL_ACTIVE
            finally:
                k.CloseHandle(h)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _lock_nb(fd):
    """非阻塞拿文件锁:拿到 True,被别人占着 False。Mac 用 flock;Windows 用 msvcrt 锁第一个字节(同 isee._Locked)。"""
    try:
        if WIN:
            import msvcrt
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd):
    if WIN:
        import msvcrt
        os.lseek(fd, 0, 0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


class Congested(RuntimeError):
    """状态锁一直拿不到(调度太挤)。"""


@contextlib.contextmanager
def _file_lock(name, wait_s, why):
    """拿一把文件锁(最多等 wait_s 秒,拿不到抛 RuntimeError(why));进程死了系统自己放。"""
    os.makedirs(_dir(), exist_ok=True)
    fd = os.open(os.path.join(_dir(), name), os.O_CREAT | os.O_RDWR, 0o600)
    got = False
    try:
        t0 = time.time()
        while True:
            if _lock_nb(fd):
                got = True
                break
            if time.time() - t0 > wait_s:
                raise Congested(why)
            time.sleep(0.05)
        yield time.time() - t0
    finally:
        try:
            if got:
                _unlock(fd)
        finally:
            os.close(fd)


@contextlib.contextmanager
def _flock():
    with _file_lock(".flock", FLOCK_WAIT_S, "调度状态文件被占着太久"):
        yield


def _load():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict):
            return _sane(st)
    except Exception:
        pass
    return {"apps": {}, "queue": {}, "recent": {}}


def _sane(st):
    """复查 11-17(C-2.7):文件能解析但字段类型不对(写坏一半、别的版本写的)→ 坏的那一项重置,别让 _purge 每次都抛错、调度一直失效。"""
    for k in ("apps", "recent", "focus", "names", "colors"):
        v = st.get(k)
        if not isinstance(v, dict):
            st[k] = {}
        else:
            st[k] = {kk: vv for kk, vv in v.items() if k in ("names", "colors") or (isinstance(vv, dict) and _nums(vv))}
    q = st.get("queue")
    st["queue"] = {k: [e for e in v if isinstance(e, dict) and _nums(e)] for k, v in q.items() if isinstance(v, list)} \
        if isinstance(q, dict) else {}
    return st


def _nums(d):
    """时间类字段(有的话)都是数字 —— 不然 _purge 做减法会抛错。"""
    return all(isinstance(d[f], (int, float)) and not isinstance(d[f], bool) for f in ("t", "seen", "since", "until") if f in d)


def _save(st):
    p = _state_path()
    tmp = p + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    for i in range(10):         # 复查 11-17 C-2.6:Windows 上别的进程正开着它读时 os.replace 报拒绝访问 → 有上限地重试
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if not WIN or i == 9:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.02)


def _purge(st, now):
    """清掉:进程没了还标着「正在做」的占用、过期的占用、进程没了或等太久的排队、很久没动的任务。"""
    for k, a in list(st["apps"].items()):
        dead = not _alive(a.get("pid", 0))
        if a.get("busy") and (dead or now - a.get("since", now) > BUSY_MAX_S):
            a["busy"], a["until"] = False, 0
        # 每个进程一个任务(没写项目名的命令行):进程没了就不会再来,余占直接清(写了项目名的几条命令算同一任务,余占照留)
        if dead and str(a.get("owner", "")).startswith("pid:"):
            a["busy"], a["until"] = False, 0
        if not a.get("busy") and a.get("until", 0) < now:
            del st["apps"][k]
    for k, q in list(st["queue"].items()):
        # 复查 11-17(C-2.7):排队的人每秒报一次到(seen),QUEUE_GONE_S 没报到当已经走了(退出排队没写成功时,别挡住后面的人)
        # 没有 seen 的(老版本的 SeeU 写的)不按报到清,只按进程 / 等太久清(用户常不重开客户端,新老混跑)
        q[:] = [e for e in q if _alive(e.get("pid", 0)) and now - e.get("t", now) < WAIT_APP_S + 30
                and ("seen" not in e or now - e["seen"] < QUEUE_GONE_S)]
        if not q:
            del st["queue"][k]
    st["recent"] = {t: v for t, v in st["recent"].items() if now - v.get("t", 0) < RECENT_S}
    busy = {a.get("owner") for a in st["apps"].values()} | {e.get("tid") for q in st["queue"].values() for e in q}
    st["names"] = {t: v for t, v in st.get("names", {}).items() if t in st["recent"] or t in busy}
    st["colors"] = {t: v for t, v in st.get("colors", {}).items() if t in st["recent"] or t in busy}
    # 焦点记录:过期的、记录主人的进程已经结束的都不算 —— 一次性命令行进程(pid: 任务);
    # 复查 11-17(C-2.7):AI 会话(mcp:<进程号>)关掉 / 客户端重开后,旧会话的记录也不算,不然新会话第一下打字就被「自己」拦住
    st["focus"] = {k: v for k, v in st.get("focus", {}).items() if now - v.get("t", 0) < FOCUS_KEEP_S
                   and not _tid_dead(v.get("tid", ""))}


def _tid_dead(tid):
    """任务号里带进程号的(pid:<n>、mcp:<n>):那个进程没了 → True。写了项目名的(proj:)不按进程算。"""
    t = str(tid or "")
    for p in ("pid:", "mcp:"):
        if t.startswith(p):
            return not _alive(t[len(p):])
    return False


_WKEY = {}          # Windows:App 写法 → (记下的时间, 占用键);同一步里占 / 让 / 显示要查好几次,别每次都列一遍窗口
WKEY_TTL = 2.0


WEB_KEY = "web:"        # Windows 专用浏览器的占用键前缀(win/web.py)


def _win_key(app):
    """Windows 按窗口分(11-17 C-2.6):Windows 打字、点击直投目标窗口,不同窗口互不干扰;同一个窗口才要排队。
    键 = 「程序名#窗口号」,同一个窗口不管写成 notepad / 记事本 / #窗口号 都对得上。找不到窗口就按写法本身。"""
    a = str(app or "").strip()
    if a.startswith(WEB_KEY):             # 11-18 C-2.8:SeeU 专用浏览器(调试端口,没有可找的窗口)按浏览器名排
        return a
    now = time.time()
    hit = _WKEY.get(a)
    if hit and now - hit[0] < WKEY_TTL:
        return hit[1]
    try:
        from seeu.win import window as W
        w = W.find(a)
        exe = os.path.splitext(os.path.basename(w.get("exe") or ""))[0] or W.split_target(a)[0]
        k = f"{exe}#{int(w['hwnd'])}"
    except Exception:
        k = a
    if len(_WKEY) > 64:
        _WKEY.clear()
    _WKEY[a] = (now, k)
    return k


def label_of(key):
    """占用键 → 给人看的 App 名(灵动岛「等 记事本」、排队提示用):Windows 的「notepad#1234」只留程序名。"""
    k = str(key or "")
    if k.startswith(WEB_KEY):
        k = k[len(WEB_KEY):]
        return k[:1].upper() + k[1:]
    if WIN and "#" in k and k.rsplit("#", 1)[1].isdigit():
        k = k.rsplit("#", 1)[0]
        if k.islower():
            k = k[:1].upper() + k[1:]
    return k


def _key(app):
    """按 App 分(不分窗口):「文本编辑「A」」和「文本编辑「B」」是同一个 App、同一个焦点。Windows 按窗口分,见 _win_key。"""
    if WIN:
        return _win_key(app)
    from seeu import bgclick as bg
    try:
        from seeu import web
        app = web.canon(app)
    except Exception:
        pass
    return bg.split_target(str(app))[0]


CONGESTED_WHY = ("SeeU 调度太挤:状态文件一直被别的任务占着(等了 {n:.0f} 秒),这次没做;稍后再试。"
                 "这不是哪个任务一直不放手,是同时在用 SeeU 的任务太多")


class Busy(Exception):
    def __init__(self, msg, info):
        super().__init__(msg)
        self.info = info


_local = threading.local()      # 同一进程里嵌套调用(mirror_open_app 里调 tap / type)只在最外层占 / 让


def _depthmap():
    d = getattr(_local, "d", None)
    if d is None:
        d = _local.d = {}
    return d


def acquire(app, on_wait=None, wait_max=None):
    """占用 App;要排队就等(最多 wait_max 秒),轮到返回 info:waited / ahead(刚排进去时前面几个)/ holder。
    等不到抛 Busy。on_wait():第一次发现要排队时调一下(调用方用来先截一张图,轮到时比画面)。"""
    key = _key(app)
    d = _depthmap()
    if d.get(key):
        d[key] += 1
        return {"waited": 0.0, "nested": True, "key": key}
    tid, name = me()
    pid = os.getpid()
    wait_max = WAIT_APP_S if wait_max is None else wait_max
    t0 = time.time()
    info = {"waited": 0.0, "ahead": 0, "holder": None, "key": key}   # 复查 11-17 C-2.6:release 用这个键,别重算(Windows 窗口顺序变了 / 被关掉会算出别的)
    queued = False
    holder = None
    while True:
        now = time.time()
        try:
            got = _turn(key, tid, name, pid, now, t0, info, queued, d)
        except Congested:
            # 外部评审 11-17(C-2.6):状态锁拿不到 = 调度太挤,放行正好违背调度的目的 → 一律按忙,说法跟「某任务占着」分开
            if queued:
                _leave(key, tid, tries=1)    # 已经挤了 5 秒,别再多等;没删掉的靠报到超时清
            info["waited"] = round(time.time() - t0, 1)
            info["congested"] = True
            raise Busy(CONGESTED_WHY.format(n=info["waited"]), info)
        except Exception:
            if not queued:
                raise                       # 状态文件读写坏了(不是挤):还没排进队就放行,别因为调度挡住所有动作
            _leave(key, tid)                # 复查 11-17:排过队再出错不能放行(别人可能正占着),按忙处理
            info["waited"] = round(time.time() - t0, 1)
            raise Busy(f"调度状态读写卡住,排队中断(等了 {info['waited']:.0f} 秒),这次没做;稍后再试", info)
        if got:
            return info
        holder = info.get("holder") or holder
        if not queued:
            queued = True
            if on_wait:
                try:
                    import inspect
                    if inspect.signature(on_wait).parameters:   # 复查 11-17:按签名判断,别拿 TypeError 猜(会把里面的错当老写法再调一次)
                        on_wait(dict(info))
                    else:
                        on_wait()
                except Exception:
                    pass
        if time.time() - t0 > wait_max:
            _leave(key, tid)
            info["waited"] = round(time.time() - t0, 1)
            raise Busy(f"别的任务(「{holder or '?'}」)正在用「{label_of(key)}」,排队等了 {info['waited']:.0f} 秒还没轮到,这次没做;"
                       f"稍后再试,或先做别的事", info)
        time.sleep(POLL_S)


def _leave(key, tid, tries=None):
    """把自己从排队名单里删掉(尽力而为:再试一次;还不行就靠报到超时 QUEUE_GONE_S、进程退出后 _purge 清)。"""
    for _ in range(tries or RELEASE_TRIES):
        try:
            with _flock():
                st = _load()
                q = st["queue"].get(key, [])
                q[:] = [e for e in q if e.get("tid") != tid]
                if not q:
                    st["queue"].pop(key, None)
                _save(st)
            return
        except Exception:
            continue


def _turn(key, tid, name, pid, now, t0, info, queued, d):
    """一次「读-判断-写」:轮到了返回 True(已占上);没轮到就排进队、更新 info,返回 False。"""
    with _flock():
        st = _load()
        s0 = json.dumps(st, sort_keys=True, ensure_ascii=False)
        _purge(st, now)
        base = name
        name = _name_for(st, tid, base, now)
        _publish(name, _color_for(st, tid, base))
        a = st["apps"].get(key)
        q = st["queue"].setdefault(key, [])
        mine = a is not None and a.get("owner") == tid
        if mine and not a.get("busy") and q and q[0].get("tid") != tid and now - q[0].get("t", now) > YIELD_AFTER_S:
            del st["apps"][key]           # 续占到点:后面有人等太久,让出来、自己去排队
            a, mine = None, False
        free = a is None
        first = not q or q[0].get("tid") == tid
        if mine or (free and first):
            st["apps"][key] = {"owner": tid, "name": name, "pid": pid, "busy": True, "until": 0, "since": now}
            q[:] = [e for e in q if e.get("tid") != tid]
            if not q:
                st["queue"].pop(key, None)
            st["recent"][tid] = {"t": now, "name": name}
            _save(st)
            d[key] = 1
            info["waited"] = round(now - t0, 2)
            fo = st.get("focus", {}).get(key)
            if fo and fo.get("tid") != tid:
                info["focus_by"] = fo.get("name") or "?"     # 外部评审 11-17:在你上一步之后,别的任务动过这个 App 的焦点
            return True
        if not any(e.get("tid") == tid for e in q):
            q.append({"tid": tid, "name": name, "pid": pid, "t": now, "seen": time.time()})
        pos = next(i for i, e in enumerate(q) if e.get("tid") == tid)
        if time.time() - q[pos].get("seen", 0) >= SEEN_EVERY_S:
            q[pos]["seen"] = time.time()    # 锁里取时间(now 是等锁之前取的,挤的时候会旧好几秒)           # 每秒报一次到(见 _purge);这一下会写文件,所以别每 0.15 秒都报
        holder = (a or {}).get("name") or (q[0].get("name") if q else None)
        if not queued:
            info["ahead"] = pos + (1 if a else 0)
            info["holder"] = holder
        old = st["recent"].get(tid) or {}
        if now - old.get("t", 0) > 2.0 or old.get("name") != name:
            st["recent"][tid] = {"t": now, "name": name}
        if json.dumps(st, sort_keys=True, ensure_ascii=False) != s0:     # 外部评审 11-17:排队中没变化就不写(每 0.15 秒写一次,任务多了锁更挤)
            _save(st)
        return False


def release(app, key=None, focus=False, keep=True):
    """动完一步:不马上放,接着占 LEASE_S 秒(同一任务的下一步直接用),到点自动让出。key = acquire 返回的 info["key"]。
    focus=True:这一步会动这个 App 的焦点(点、打字、按键、菜单、开 App…),记成「它最后动过焦点」。
    keep=False:这一步被拦下、什么都没做(focus_moved / stale)→ 马上让出,不接着占(11-18 C-2.8:原来白让排队的人多等约 6 秒)。"""
    key = key or _key(app)
    d = _depthmap()
    if d.get(key, 0) > 1:
        d[key] -= 1
        if focus:
            _local.focus = getattr(_local, "focus", set()) | {key}      # 嵌套里动过焦点,外层让出时一起记
        return
    d.pop(key, None)
    inner = getattr(_local, "focus", set())
    focus = focus or key in inner
    _local.focus = inner - {key}
    tid, _ = me()
    for _ in range(RELEASE_TRIES):    # 复查 11-17(C-2.7):挤的时候没写成功,App 会被白挡到 BUSY_MAX_S → 再试一次
        try:
            with _flock():
                st = _load()
                a = st["apps"].get(key)
                now = time.time()
                if a and a.get("owner") == tid:
                    a["busy"], a["until"] = False, now + (LEASE_S if keep else 0)
                if focus:
                    st.setdefault("focus", {})[key] = {"tid": tid, "name": (st.get("names") or {}).get(tid) or me()[1], "t": now}
                if (a and a.get("owner") == tid) or focus:
                    _save(st)
            return
        except Exception:
            continue


@contextlib.contextmanager
def _beat(key):
    """11-18 C-2.8:占着 App 做一个动作期间,每 BEAT_S 秒把「正在做」的开始时间刷成现在,别人不会因为做得久(超过 BUSY_MAX_S)
    把它当卡死清掉、插进来串字。最多报 BUSY_HARD_S 秒;不是自己占着了就停。出错不管(不影响动作)。"""
    stop = threading.Event()
    try:
        tid = me()[0]
    except Exception:
        tid = None
    t0 = time.time()

    def run():
        while not stop.wait(BEAT_S):
            if time.time() - t0 > BUSY_HARD_S:
                return
            try:
                with _flock():
                    st = _load()
                    a = st["apps"].get(key)
                    if not (a and a.get("owner") == tid and a.get("busy")):
                        return
                    a["since"] = time.time()
                    _save(st)
            except Exception:
                pass
    th = None
    if tid:
        try:
            th = threading.Thread(target=run, name="seeu-beat", daemon=True)
            th.start()
        except Exception:
            th = None
    try:
        yield
    finally:
        stop.set()


class Stale(Exception):
    """整段占用(hold)排完队发现画面变了,按位置点不安全。"""
    def __init__(self, msg, info):
        super().__init__(msg)
        self.info = info


@contextlib.contextmanager
def hold(app, pt=None):
    """外部评审 11-17 第 1 条:几步要连着做、中间不让别的任务插进来(点输入框 + 打字)时,整段占着。
    yield 占用信息;排不上抛 Busy(调用方报 busy);调度自己出错就不占(跟单步一样放行)。里面的动作按嵌套算,不再各自排队。
    pt = 要按位置点的屏幕点(按编号点传 None):排队超过 STALE_AFTER_S 才轮到、这期间画面变了 / 窗口挪了 → 抛 Stale(复查 11-17 C-2.7)。
    排队时光标打瞌睡、灵动岛显示排队(跟单步一样)。"""
    if os.environ.get("SEEU_NO_SCHED"):
        yield None
        return
    snap = {}

    def on_wait(qinfo=None):
        _wait_show(app, True, qinfo)
        snap["waiting"] = True
        if pt:
            _snap_before(app, snap)
    try:
        try:
            info = acquire(app, on_wait=on_wait)
        finally:
            if snap.get("waiting"):
                _wait_show(app, False)
    except Busy:
        raise
    except Exception:
        yield None
        return
    stale = False
    try:
        why = _stale_why(app, snap, pt, info)
        if why:
            stale = True
            raise Stale(why, info)
        if info.get("nested"):
            yield info
        else:
            with _beat(info.get("key")):
                yield info
    finally:
        release(app, key=info.get("key"), keep=not stale)    # 11-18:防过时拦下 = 什么都没做,马上让出。复查 11-17(C-2.7):焦点记录交给里面真动过手的那几步(嵌套时记下,这里一起写)


def mark_focus(app):
    """不经过调度的动作(后台开 App)也会动焦点:登记一下「这个任务最后动过它」。出错不管。"""
    if os.environ.get("SEEU_NO_SCHED"):
        return
    try:
        key = _key(app)
        tid, base = me()
        with _flock():
            st = _load()
            now = time.time()
            _purge(st, now)
            name = _name_for(st, tid, base, now)
            st.setdefault("focus", {})[key] = {"tid": tid, "name": name, "t": now}
            _save(st)
    except Exception:
        pass


DEVICE_APPS = ("iPhone Mirroring", "BlueStacks")      # 状态全局、会留下来的设备画面(外部评审 11-17 第 4 条)


def device_busy(app):
    """外部评审 11-17 第 4 条:镜像 / 模拟器正被别的项目(用户自己的自动化程序)按桌面锁占着 → 返回给 AI 的原因;没占着返回 None。
    只读查锁(seeu_lib.desktop_lock.status),不改协议;SeeU 自己借鼠标拿的锁不算。只在 Mac 上查(Windows 上没有这些项目)。"""
    if WIN:
        return None
    k = label_of(_key(app))
    if not any(k == d or k.startswith(d) for d in DEVICE_APPS):
        return None
    try:
        from seeu_lib import desktop_lock as dl
        cur = dl.status()
    except Exception:
        return None
    if not cur or cur.get("stale") or cur.get("alive") is False:
        return None
    if str(cur.get("label", "")).startswith("SeeU") or int(cur.get("pid") or 0) == os.getpid():
        return None
    # 复查 11-17(C-2.7):原来只查 AI 走工具(mcp:)的,走命令行(没写项目名)的 AI 能绕过 → 也查。放过的只有:
    # 写了项目名的程序调用(设了 SEEU_PROJECT;锁上写的项目名常跟它对不上,锁可能正是它自己拿的),
    # 或者拿锁的进程是自己的上级
    if _own_lock(cur):
        return None
    proj = cur.get("project") or "?"
    return (DEVICE_WHY.format(proj=proj, app=k, ts=cur.get("ts") or "?", label=cur.get("label") or ""))


def _own_lock(cur):
    tid = str(me()[0])
    if tid.startswith("proj:"):
        return True
    if tid.startswith("mcp:"):
        return False            # AI 会话一律查(它不会是用户自动化程序的下级)
    try:
        want = int(cur.get("pid") or 0)
    except Exception:
        want = 0
    return bool(want) and want in _ancestors()


def _ancestors(limit=12):
    """本进程的上级进程号(最多 limit 层)。读不到返回空。Mac 用 ps;Windows 不用(Windows 上不查设备锁)。"""
    out, pid = [], os.getppid()
    try:
        import subprocess
        for _ in range(limit):
            if pid <= 1:
                break
            out.append(pid)
            r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=2)
            pid = int((r.stdout or "0").strip() or 0)
    except Exception:
        pass
    return out


DEVICE_WHY = ("「{proj}」正在用 {app}(从 {ts} 起,{label}),这期间 SeeU 不去点它,免得两边的点击插在一起。"
              "这可能要好一阵(自动化程序跑一轮常要很久):先告诉用户,或先做别的事,别反复重试")
FOCUS_WHY = ("在你上一步之后,别的任务(「{who}」)动过这个 App 的焦点,不带输入框直接{what}可能打进它点开的地方,这次没做。"
             "带上输入框的编号(target)再做一次(SeeU 会先点框再{what},中间不让别人插进来)")
# 复查 11-17(C-2.7):seeu_press 没有 target 参数,不能叫 AI 带编号重试 → 先自己点一下(点完焦点就算你的)再按
FOCUS_WHY_PRESS = ("在你上一步之后,别的任务(「{who}」)动过这个 App 的焦点,不带输入框直接按键可能打进它点开的地方,这次没做。"
                   "先用 seeu_tap 点一下要按键的地方(输入框或窗口),再按一次")


def active_tasks():
    """最近 RECENT_S 秒内动过的任务数、排队中的动作数(记录用,以后给悬浮标 / 任务窗口用)。"""
    try:
        try:
            with _file_lock(".flock", 1.0, "busy"):     # 复查 11-17:在锁里读(Windows 上锁外开着文件会让别人的 os.replace 失败)
                st = _load()
        except RuntimeError:
            return 1, 0
        now = time.time()
        n = sum(1 for v in st["recent"].values() if now - v.get("t", 0) < RECENT_S)
        return max(n, 1), sum(len(q) for q in st["queue"].values())
    except Exception:
        return 1, 0


# ---------------------------------------------------------------- 只记录(任务窗口协议的数据)

_heavy = threading.local()


def add_heavy(kind, secs):
    """重活(截图、认字…)用时,act.shoot 等调用;算在当前动作头上。"""
    h = getattr(_heavy, "v", None)
    if h is not None:
        h[kind] = round(h.get(kind, 0.0) + secs, 3)


def _sys():
    out = {"cpus": os.cpu_count()}
    try:
        out["load1"] = round(os.getloadavg()[0], 2)     # Windows 没有
    except Exception:
        pass
    return out


def touch():
    """登记「这个任务刚动过」并分好显示名(看画面这类不占 App 的动作也算在用);出错不管。返回显示名。"""
    tid, base = me()
    try:
        with _flock():
            st = _load()
            now = time.time()
            _purge(st, now)
            name = _name_for(st, tid, base, now)
            col = _color_for(st, tid, base)
            st["recent"][tid] = {"t": now, "name": name}
            _save(st)
        _publish(name, col)
        return name
    except Exception:
        return base


def record(action, app, secs, outcome, info=None, heavy=None):
    try:
        os.makedirs(_dir(), exist_ok=True)
        p = os.path.join(_dir(), "samples.jsonl")
        if os.path.exists(p) and os.path.getsize(p) > SAMPLES_MAX:
            os.replace(p, p + ".1")
        tasks, queued = active_tasks()
        tid, _ = me()
        name = os.environ.get("SEEU_TASK_DISPLAY") or me()[1]
        row = dict(t=round(time.time(), 2), task=name, tid=tid, act=action, app=_key(app) if app else None,
                   secs=round(secs, 3), out=outcome, tasks=tasks, queued=queued, heavy=heavy or {}, **_sys())
        if info and info.get("waited"):
            row["waited"] = info["waited"]
            row["ahead"] = info.get("ahead", 0)
        row["work"] = round(max(0.0, secs - (row.get("waited") or 0)), 3)   # 动作本身用时(去掉排队)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- 包在对外动作外面

def queue_note(info):
    """排过队就告诉 AI(由它转告用户):等了几秒、刚排进去时前面几个、谁占着。"""
    if not info or info.get("waited", 0) < 0.5:
        return None
    return (f"排队等了 {info['waited']:.1f} 秒(排进去时前面有 {info.get('ahead', 0)} 个,"
            f"「{info.get('holder') or '?'}」在用同一个 App)")


def _no_focus(app):
    """浏览器 / SeeU 专用那份网页壳:点、滚动走网页里的脚本,不碰 App 焦点,不用占 App(打字照占)。
    Windows 没有这条路(用户的浏览器窗口也是发消息点),一律占。"""
    if WIN:
        return False
    try:
        from seeu import web
        a = web.canon(app)
        return web.is_browser(a) or web.is_cdp(a)
    except Exception:
        return False


def scheduled(action, positional=None, lease=True, focus=False, focus_check=None):
    """装在 act 的对外动作上(tap / type / scroll …):先占 App(要排队就等)、做、记录、让出(接着占 LEASE_S 秒)。
    positional(args, kwargs) → True 表示这次是按位置点:排队超过 STALE_AFTER_S 才轮到,先比画面,变了就不点。
    lease=False 只记录不占(看画面这类第 ③ 层动作);lease="focus" 浏览器里不占(点、滚动走网页脚本)。
    focus=True:这一步会动 App 的焦点,让出时记「它最后动过焦点」。focus_check(args, kwargs) → True 表示这次是往「当前焦点」里
    打字 / 按键(没指定输入框):在你上一步之后别的任务动过焦点,就不做(外部评审 11-17 第 1 条)。"""
    def deco(fn):
        import functools

        import inspect
        sig = inspect.signature(fn)
        first = next(iter(sig.parameters))

        @functools.wraps(fn)
        def wrap(*args, **kwargs):
            if os.environ.get("SEEU_NO_SCHED"):
                return fn(*args, **kwargs)
            try:            # 复查 11-17:app 有默认值的(mirror_home)不传也要能调
                ba = sig.bind(*args, **kwargs)
                ba.apply_defaults()
                app = ba.arguments[first]
                rest = tuple(ba.args[1:])
            except TypeError:
                return fn(*args, **kwargs)      # 参数不对:让原函数自己报原来的错
            t0 = time.time()
            own_heavy = getattr(_heavy, "v", None) is None      # 嵌套调用不清掉外层累计的重活用时、也不另记一行
            if own_heavy:
                _heavy.v = {}
            info, r, pos = None, None, None
            snap = {}
            use = bool(lease) and not (lease == "focus" and _no_focus(app))
            if own_heavy and not use:
                touch()                     # 不占 App 的动作也分好显示名(占 App 的在 _turn 里分)
            try:
                if use:
                    why = device_busy(app)      # 嵌套里也查(整段占用 hold 里点框那一步也要被拦)
                    if why:
                        r = dict(outcome="refused", route=None, tried=[], png=None, reason=why, code="device_busy")
                        return r
                if use:
                    pos = positional(rest, kwargs) if positional else None

                    def on_wait(qinfo=None):
                        _wait_show(app, True, qinfo)      # 11-17:排队中光标打瞌睡 + 变淡、灵动岛下段「排队中」
                        snap["waiting"] = True
                        if pos:
                            _snap_before(app, snap)
                    try:
                        try:
                            info = acquire(app, on_wait=on_wait)
                        finally:
                            if snap.get("waiting"):      # 复查 11-17(C-2.7):排上、排不上、调度出错都收(原来出错那条不收,挂 40 秒)
                                _wait_show(app, False)
                    except Busy as ex:      # 复查 11-17:不是被拦,是暂时排不上 → 单独的 busy,AI 稍后重试
                        r = dict(outcome="busy", route=None, tried=[], png=None, reason=str(ex), code="busy",
                                 queue=ex.info)
                        return r
                    except Exception:
                        info = None          # 调度自己出错:放行,不挡动作
                try:
                    # 复查 11-17(C-2.7):写了项目名的程序(用户自己的自动化程序调 SeeU 打字)不查 —— 跟设备锁一样,程序自己的调用不拦
                    # 浏览器里点击走网页脚本、不登记焦点(见 _no_focus),按键也不查,不然照提示点了也解不开
                    if (info and info.get("focus_by") and not info.get("nested") and focus_check
                            and not str(me()[0]).startswith("proj:") and not _no_focus(app) and focus_check(rest, kwargs)):
                        if action == "press" and not WIN:      # Windows 的 seeu_press 有 target,照旧叫带 target
                            why = FOCUS_WHY_PRESS.format(who=info["focus_by"])
                        else:
                            why = FOCUS_WHY.format(who=info["focus_by"], what="打字" if action == "type" else "按键")
                        r = dict(outcome="failed", route=None, tried=[], png=None, code="focus_moved",
                                 reason=why, queue=info)
                        return r
                    why = _stale_why(app, snap, pos, info)
                    if why:
                        r = dict(outcome="failed", route=None, tried=[], png=None, code="stale", reason=why, queue=info)
                        return r
                    if info and not info.get("nested"):
                        with _beat(info.get("key")):
                            r = fn(*args, **kwargs)
                    else:
                        r = fn(*args, **kwargs)
                    if isinstance(r, dict) and info:
                        note = queue_note(info)
                        if note:
                            r["queue"] = info
                            r["note"] = (str(r["note"]) + ";" if r.get("note") else "") + note
                    return r
                finally:
                    if use and info is not None:
                        # 复查 11-17(C-2.7):真动过手才记「最后动过焦点」(被拦下、防过时没点、出错没做的不算,
                        # 不然别的任务的插队保护会被它顶掉)
                        release(app, key=info.get("key"), focus=bool(focus) and isinstance(r, dict)
                                and (r.get("outcome") in ACTED or r.get("code") == "wrong_window")
                                and r.get("code") not in ("focus_moved", "stale"),
                                keep=not (isinstance(r, dict) and r.get("code") in ("focus_moved", "stale")))
            finally:
                if own_heavy:
                    out = (r.get("code") or r.get("outcome")) if isinstance(r, dict) else "error"
                    record(action, app, time.time() - t0, out, info or (r or {}).get("queue"), getattr(_heavy, "v", None))
                    _heavy.v = None
        return wrap
    return deco


ACTED = ("delivered", "unverified", "ineffective", "partial")    # 发出过事件的结果


def _wait_show(app, on, qinfo=None):
    cursor_wait(on)
    if on:
        island_wait(app, True, qinfo)
    else:
        island_wait(app, False)


def _snap_before(app, snap):
    """排队开始时记下目标窗口的样子和位置(轮到时比,见 _stale_why)。出错不管(不拦)。"""
    try:
        snap["geo"] = _win_rect(app)
    except Exception:
        snap["geo"] = None
    try:
        snap["before"] = _act().shoot(app)
    except Exception:
        snap["before"] = None


def _win_rect(app):
    """目标窗口在屏幕上的位置大小 (x, y, w, h);拿不到 None。"""
    if WIN:
        from seeu.win import window as W
        r = W.find(app).get("rect")
        return tuple(int(v) for v in r[:4]) if r else None
    g = _act()._geo(app)
    return tuple(round(float(g[k])) for k in ("x", "y", "w", "h")) if g else None


def _stale_why(app, snap, pt, info):
    """排队超过 STALE_AFTER_S 才轮到的按位置点:窗口挪过 / 改过大小,或点击处附近画面变了 → 返回原因(不点);否则 None。"""
    if not (snap.get("before") and info and info.get("waited", 0) >= STALE_AFTER_S):
        return None
    g0 = snap.get("geo")
    if g0:
        try:
            g1 = _win_rect(app)
        except Exception:
            g1 = None
        if g1 and any(abs(a - b) > 2 for a, b in zip(g0, g1)):    # 复查 11-17(C-2.7):窗口挪了内容没变,原来比不出来、照旧位置点偏
            return (f"排队等了 {info['waited']:.0f} 秒,这期间窗口挪动或改了大小,"
                    "按位置点可能点错;先看一眼(see)再点")
    changed = _changed(app, snap["before"], pt)
    if changed is not None and changed >= STALE_CHANGE:
        return (f"排队等了 {info['waited']:.0f} 秒,这期间画面变了({changed:.0%}),"
                "按位置点可能点错;先看一眼(see)再点")
    return None


def _safe_key(app):
    try:
        return _key(app)
    except Exception:
        return str(app)


def _act():
    """act 模块:用 `python3 -m seeu.act` 跑时它是 __main__,别再导入一份(复查 11-17)。"""
    name = "seeu.win.act" if WIN else "seeu.act"
    m = sys.modules.get(name)
    if m is None:
        main = sys.modules.get("__main__")
        if main is not None and hasattr(main, "shoot") and hasattr(main, "tap"):
            return main
        import importlib
        m = importlib.import_module(name)
    return m


def _changed(app, before_png, pt=None):
    """排队前后目标窗口变了多少(像素占比)。pt=点击的屏幕点 → 只比它附近 STALE_BOX_PT 点见方,别处一直在动不算。
    Windows 截图是内存里的画面(不是 png 文件),交给 win/act._stale_change 比。"""
    if WIN:
        try:
            return _act()._stale_change(app, before_png, pt)
        except Exception:
            return None
    try:
        from seeu_lib import wait
        after = _act().shoot(app)
        box = None
        if isinstance(pt, (tuple, list)) and len(pt) >= 2:
            try:                          # 换算不出点击处就比整张图(不跳过核对)
                import cv2
                g = _act()._geo(app)      # 复查 11-17:跟 shoot 截的是同一个窗口(多窗口时 main_window 可能挑别的)
                img = cv2.imread(after)
                if g and img is not None and g.get("w"):
                    k = img.shape[1] / g["w"]
                    cx, cy = (float(pt[0]) - g["x"]) * k, (float(pt[1]) - g["y"]) * k
                    r = STALE_BOX_PT / 2 * k
                    box = (max(0, cx - r), max(0, cy - r), min(img.shape[1], cx + r), min(img.shape[0], cy + r))
            except Exception:
                box = None
        return wait.frame_change(before_png, after, box=box)
    except Exception:
        return None


def real_wait(try_acquire, is_seeu_holder, wait_max=None):
    """第 ① 层:借真鼠标拿桌面锁。占着的是别的 SeeU 任务 → 排队等(最多 wait_max 秒);别的项目占着 → 马上返回(照协议拒)。
    try_acquire() → dict(ok, held);返回最后一次的结果,另加 waited。"""
    wait_max = WAIT_REAL_S if wait_max is None else wait_max
    t0 = time.time()
    while True:
        r = try_acquire()
        if r.get("ok") or not is_seeu_holder(r.get("held")) or time.time() - t0 > wait_max:
            r["waited"] = round(time.time() - t0, 1)
            return r
        time.sleep(0.3)


REAL_WHY = ("别的 SeeU 任务正在借用户的鼠标键盘,排队等了 {n:.0f} 秒还没轮到,这次没借;稍后再试")


@contextlib.contextmanager
def real_slot(wait_max=None):
    """Windows 借真鼠标的「SeeU 任务之间排队」(11-17 C-2.6;Mac 用桌面锁 + real_wait)。一次只让一个 SeeU 任务借,
    别的最多等 wait_max 秒(WAIT_REAL_S),等不到抛 Busy。进程死了锁自己放。yield 等了多少秒。"""
    wait_max = WAIT_REAL_S if wait_max is None else wait_max
    t0 = time.time()
    try:
        cm = _file_lock("real.lock", wait_max, "real")
        waited = cm.__enter__()
    except RuntimeError:
        n = time.time() - t0
        raise Busy(REAL_WHY.format(n=n), {"waited": round(n, 1)})
    try:
        yield round(waited, 1)
    finally:
        cm.__exit__(None, None, None)
