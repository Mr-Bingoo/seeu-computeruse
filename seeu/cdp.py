"""SeeU · 调试端口(Chrome DevTools Protocol,公开协议)(C-1.0,10-25 用户拍板「那就做吧」)

网页壳 App(Electron / CEF:VS Code、GitHub Desktop、Chatbox…)和隐身 Chrome 走这条路:**全程藏着**也能读、写、按快捷键(10-25 实测)。
只给 **SeeU 专用那份**:单独配置(`~/.seeu/cdp/<短名>`)带参数拉起,随机端口、只绑 127.0.0.1,起来马上藏 + 前台还回去,干完 quit 关端口。
🔴 用户自己开着的那份不碰(接不上,也不提供「帮你关掉重开」):调用方走老办法(辅助功能 → 后台打字 → 需要时借前台,结果里如实说)。

用法:
    from seeu import cdp
    h = cdp.launch("Visual Studio Code", "/path/a.txt")     # 隐身拉起专用那份(已经在跑就接上);返回 Handle
    cdp.vscode_read(h)          # {path, text, dirty, lines}:整个文件(含没保存的改动)
    cdp.vscode_dirty(h)         # 有没有没保存的改动
    cdp.type(h, "abc")          # 往当前焦点处打字(模拟焦点 + Input.insertText)
    cdp.key(h, "s", "cmd")      # 发快捷键(⌘S 保存)
    cdp.quit(h)
    h = cdp.restart(h)          # 被叫出来后:关掉、隐身重开(同样的文件)
通用的读/点/填走 seeu.web(see/tap/type… 自动排第一条路「调试端口」,复用插件同款 pageSnapshot/pageAct/pageRead)。
命令行:python3 -m seeu.cdp list | status | restart <App> | quit <App>

约定(SeeU-相关要点 10-25 两节):
- Python 自己实现 WebSocket(标准库),不依赖 Node / 第三方包。
- 被叫出来就停手:launch 会开 stealth 的看门狗(同隐身浏览器);之后这里所有动作抛 CDPError(code=called_out)。
- 安全底线:打字查 safety.check_text、快捷键查 safety.check_keys;Claude、终端类不拉起;VS Code 焦点在内置终端时不打字不按键。
- 坑:Electron 拉起会抢前台(open -g 拦不住)→ 一出窗口就按 pid 藏、前台还回去;VS Code 配置路径要短(socket 路径超长一启动就退);
  🔴 别直接跑 App 里的可执行文件查版本(`Code --version` 会把 GUI 用用户自己的配置拉起来,10-25 踩过)。
"""
import base64
import hashlib
import json
import os
import plistlib
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.request import urlopen

from seeu.web import WebError
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)

DIR = home("cdp")
APP_DIRS = ("/Applications", os.path.expanduser("~/Applications"))
CALL_TIMEOUT = 15        # 一次调用最多等几秒(无人值守:必须有上限)
LAUNCH_WAIT_S = 40
QUIT_WAIT_S = 15
SHORT = {"Visual Studio Code": "code", "GitHub Desktop": "ghd", "Chatbox": "chatbox", "Google Chrome": "chrome"}
# 测过的(10-25):VS Code 读写保存、GitHub Desktop / Chatbox 端口能开读页面;其余没试,有的 App 会禁掉这个参数
TESTED = {"Visual Studio Code": "藏着读/写/保存 ✅", "GitHub Desktop": "藏着读页面 ✅", "Chatbox": "藏着读页面 ✅",
          "Google Chrome": "隐身 Chrome ✅"}
# 能同时开两份的(单独配置互不影响);别的 App 用户开着就不拉(单实例锁可能把参数转给用户那份、把它叫到前台)
MULTI = {"Visual Studio Code"}
VSCODE_SETTINGS = {
    "window.title": "${dirty}${activeEditorLong}",      # 标题 = 「● 」+ 完整路径:读当前文件路径、有没有改动
    "editor.accessibilitySupport": "on",                 # 读屏模式:隐藏输入框里放整页文字(配合下面两条 = 整个文件)
    "editor.accessibilityPageSize": 1000000,
    "editor.editContext": False,                         # 用老的 textarea(新的 EditContext 读不到整页文字)
    "workbench.startupEditor": "none", "security.workspace.trust.enabled": False,
    "update.mode": "none", "telemetry.telemetryLevel": "off", "extensions.autoCheckUpdates": False,
    "extensions.autoUpdate": False, "workbench.enableExperiments": False, "window.confirmBeforeClose": "never",
    "workbench.tips.enabled": False, "accessibility.signals.sounds.volume": 0,
}


class CDPError(WebError):
    """code:no_app / busy / refused / called_out / timeout / no_page / script / error。"""


@dataclass
class Handle:
    app: str
    pid: int
    port: int
    key: str
    profile: str
    wid: int = 0                  # bgclick 用的窗口号(这条路用不上,stealth 看门狗不看它)
    files: list = field(default_factory=list)
    restart_cmd: str = ""


def _log(*a):
    print("[SeeU 调试端口]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- WebSocket(RFC 6455,客户端最小实现)

class WS:
    GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, url, timeout=CALL_TIMEOUT):
        u = urlsplit(url)
        if u.hostname not in ("127.0.0.1", "localhost"):
            raise CDPError("调试端口只连本机", "refused")
        self.s = socket.create_connection((u.hostname, u.port), timeout)
        key = base64.b64encode(os.urandom(16))
        path = u.path + ("?" + u.query if u.query else "")
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key.decode()}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            chunk = self.s.recv(4096)
            if not chunk:
                raise CDPError("调试端口握手断了", "error")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise CDPError("调试端口拒绝连接:" + lines[0], "error")
        want = base64.b64encode(hashlib.sha1(key + self.GUID).digest()).decode()
        if not any(l.lower().startswith("sec-websocket-accept:") and l.split(":", 1)[1].strip() == want for l in lines):
            raise CDPError("调试端口握手校验不对", "error")

    def _frame(self, op, data):
        n = len(data)
        head = bytes([0x80 | op])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send(self, text):
        self._frame(0x1, text.encode())

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise CDPError("调试端口连接断了(App 退出了?)", "no_app")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self, timeout):
        """收一条完整消息(文字)。超时抛 socket.timeout。"""
        self.s.settimeout(max(0.05, timeout))
        parts = []
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x9:                       # ping → pong
                self._frame(0xA, data)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise CDPError("调试端口关了连接(App 退出了?)", "no_app")
            parts.append(data)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")

    def close(self):
        try:
            self._frame(0x8, b"")
        except OSError:
            pass
        self.s.close()


class Session:
    """连一个页面(或整个浏览器)。call 只等自己那条回话,中间的事件丢掉。"""

    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self.n = 0

    def call(self, method, params=None, timeout=CALL_TIMEOUT):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}, ensure_ascii=False))
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise CDPError(f"{method} {timeout} 秒没回话", "timeout")
            try:
                m = json.loads(self.ws.recv(left))
            except socket.timeout:
                raise CDPError(f"{method} {timeout} 秒没回话", "timeout")
            if m.get("id") == mid:
                if "error" in m:
                    raise CDPError(f"{method}:{m['error'].get('message')}", "script")
                return m.get("result") or {}

    def eval(self, expr, timeout=CALL_TIMEOUT):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True},
                      timeout=timeout)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise CDPError("网页脚本出错:" + str((d.get("exception") or {}).get("description") or d.get("text"))[:200],
                           "script")
        return (r.get("result") or {}).get("value")

    def close(self):
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _http(port, path, timeout=3):
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- 找 App、登记

def app_path(app):
    for d in APP_DIRS:
        p = os.path.join(d, app + ".app")
        if os.path.isdir(p):
            return p
    raise CDPError(f"没装 {app}", "no_app")


def _plist(path):
    with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
        return plistlib.load(f)


def kind(path):
    """Electron / CEF / Chrome / None(不是 Chromium 内核)。"""
    fw = os.path.join(path, "Contents", "Frameworks")
    if os.path.isdir(os.path.join(fw, "Electron Framework.framework")):
        return "Electron"
    if os.path.isdir(os.path.join(fw, "Chromium Embedded Framework.framework")):
        return "CEF"
    if os.path.isdir(os.path.join(fw, "Google Chrome Framework.framework")):
        return "Chrome"
    return None


def installed():
    """本机能走调试端口的 App:[(名字, 内核, bundle)]。"""
    out = []
    for d in APP_DIRS:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if not n.endswith(".app"):
                continue
            p = os.path.join(d, n)
            k = kind(p)
            if k:
                try:
                    b = _plist(p).get("CFBundleIdentifier", "")
                except Exception:
                    b = ""
                out.append((n[:-4], k, b))
    return out


def _key(app):
    k = SHORT.get(app)
    if k:
        return k
    return "".join(c for c in app.lower() if c.isascii() and c.isalnum())[:12] or hashlib.md5(app.encode()).hexdigest()[:8]


def _state_file(key):
    return os.path.join(DIR, key + ".json")


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _port_ok(port):
    try:
        _http(port, "/json/version", timeout=1.5)
        return True
    except Exception:
        return False


def register(app, pid, port, profile, files=()):
    """登记一份专用实例(隐身 Chrome 拉起时也调这个)。"""
    os.makedirs(DIR, exist_ok=True)
    key = _key(app)
    d = dict(app=app, pid=int(pid), port=int(port), profile=profile, files=list(files), started=time.time())
    with open(_state_file(key), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    _cache.pop(app, None)
    return _handle(d)


def _handle(d):
    short = "Chrome" if d["app"] == "Google Chrome" else d["app"]
    cmd = (f"python3 -m seeu.stealth restart Chrome" if d["app"] == "Google Chrome"
           else f'python3 -m seeu.cdp restart "{short}"')
    return Handle(d["app"], d["pid"], d["port"], _key(d["app"]), d["profile"], files=d.get("files") or [], restart_cmd=cmd)


_cache = {}       # app -> (检查时间, Handle 或 None)


def running(app, fresh=False):
    """SeeU 专用那份在跑且端口通 → Handle,否则 None(并清掉过期登记)。结果缓存 2 秒(web 每个动作都会问)。"""
    hit = _cache.get(app)
    if hit and not fresh and time.time() - hit[0] < 2:
        return hit[1]
    h = None
    try:
        with open(_state_file(_key(app)), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("app") == app and _alive(d["pid"]) and _port_ok(d["port"]):
            h = _handle(d)
        elif not _alive(d.get("pid")):
            os.remove(_state_file(_key(app)))
    except (OSError, ValueError, KeyError):
        pass
    _cache[app] = (time.time(), h)
    return h


def unregister(app):
    try:
        os.remove(_state_file(_key(app)))
    except OSError:
        pass
    _cache.pop(app, None)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _pids_of(path):
    """这个 App 的主进程(可执行文件就是 Contents/MacOS/xxx 的)。"""
    exe = os.path.join(path, "Contents", "MacOS", _plist(path).get("CFBundleExecutable", ""))
    r = subprocess.run(["pgrep", "-f", "^" + exe.replace("+", r"\+").replace(".", r"\.")], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def _pid_with_port(path, port):
    exe = os.path.join(path, "Contents", "MacOS", _plist(path).get("CFBundleExecutable", ""))
    r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    for line in r.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if cmd.startswith(exe) and f"--remote-debugging-port={port}" in cmd:
            return int(pid)
    return None


# ---------------------------------------------------------------- 藏、前台

def _osa(s, timeout=10):
    try:
        return subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def hide(pid):
    """按进程号藏(同名多份时不会藏错)。"""
    _osa(f'tell application "System Events" to set visible of (first process whose unix id is {int(pid)}) to false')


def is_hidden(pid):
    return _osa(f'tell application "System Events" to get visible of (first process whose unix id is {int(pid)})') != "true"


def _has_window(pid):
    import Quartz
    return any(w["kCGWindowOwnerPID"] == pid and w.get("kCGWindowLayer") == 0
               for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or [])


def _front():
    try:
        import AppKit
        # 11-06:先让事件循环跑 20ms 再问。没有事件循环的程序里 NSWorkspace 会一直返回第一次查到的旧值,
        # 「前台被抢了就还回去」就永远以为没被抢(seeu_lib.input_guard.frontmost_app 同款做法)。
        AppKit.NSRunLoop.currentRunLoop().runUntilDate_(AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.02))
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def _give_front_back(front, pid):
    """前台被它抢了就还回去(先藏,系统会把前台交还;还不对再点名激活原来那个)。"""
    now = _front()
    if front is None or now is None or now.processIdentifier() == front.processIdentifier():
        return
    if now.processIdentifier() == pid:
        hide(pid)
        time.sleep(0.3)
        now = _front()
    if now is not None and now.processIdentifier() != front.processIdentifier():
        try:
            front.activateWithOptions_(0)
        except Exception:
            pass


# ---------------------------------------------------------------- 拉起 / 退出

def _check_allowed(app, path):
    from seeu import safety
    b = ""
    try:
        b = _plist(path).get("CFBundleIdentifier", "")
    except Exception:
        pass
    if b and b in safety.host_bundles():       # 10-31:只拦正在运行 SeeU 的那个,别的 AI App 可以操作
        raise CDPError(f"{app} 是正在运行 SeeU 的程序,安全底线不碰(防 AI 自己批准自己)", "refused")
    if app in safety.TERMINALS or b in safety.TERMINALS.values():
        raise CDPError(f"{app} 是终端,安全底线不碰", "refused")


def _prep_profile(app, profile):
    os.makedirs(profile, exist_ok=True)
    if app != "Visual Studio Code":
        return []
    user = os.path.join(profile, "User")
    os.makedirs(user, exist_ok=True)
    p = os.path.join(user, "settings.json")
    cur = {}
    try:
        with open(p, encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        pass
    cur.update(VSCODE_SETTINGS)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=1)
    ext = os.path.join(DIR, "code-ext")
    os.makedirs(ext, exist_ok=True)
    return [f"--extensions-dir={ext}", "--disable-workspace-trust", "--skip-welcome", "--skip-release-notes",
            "--disable-telemetry", "--new-window"]


def launch(app, *files, wait_s=LAUNCH_WAIT_S, watch=True):
    """隐身拉起 SeeU 专用那份(已经在跑就直接接上,有新文件就让它打开)。返回 Handle。
    用户自己那份开着:VS Code 可以同时开(单独配置互不影响);别的 App 抛 CDPError(busy),调用方走老办法。"""
    if app in ("Chrome", "Google Chrome"):
        raise CDPError("隐身 Chrome 用 stealth.launch('Chrome', url)(它会自己开调试端口)", "error")
    files = [os.path.abspath(os.path.expanduser(f)) for f in files]
    h = running(app, fresh=True)
    if h:
        if files and app == "Visual Studio Code":
            for f in files:
                vscode_open(h, f)
        if watch:
            _guard(h)
        return h
    path = app_path(app)
    _check_allowed(app, path)
    if kind(path) is None:
        raise CDPError(f"{app} 不是 Chromium 内核(网页技术做的)App,这条路用不了", "error")
    if app not in MULTI and _pids_of(path):
        raise CDPError(f"{app} 你自己开着,SeeU 不碰你那份,也不帮你关掉重开;这次改走辅助功能(可能要借前台)", "busy")
    key = _key(app)
    profile = os.path.join(DIR, key)
    extra = _prep_profile(app, profile)
    port = _free_port()
    front = _front()
    args = ["open", "-n", "-g", "-j", "-a", path, "--args", f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"] + extra + files
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0, pid, hidden_once = time.time(), None, False
    while time.time() - t0 < wait_s:
        pid = pid or _pid_with_port(path, port)
        if pid and _has_window(pid) and not hidden_once:       # 一出窗口就藏(Electron 拉起会抢前台)
            hide(pid)
            _give_front_back(front, pid)
            hidden_once = True
        if pid and _port_ok(port) and (hidden_once or time.time() - t0 > 8):
            break
        time.sleep(0.05 if not hidden_once else 0.3)
    if not pid:
        raise CDPError(f"{app} {wait_s} 秒没拉起来", "timeout")
    if not _port_ok(port):
        _kill(pid)
        raise CDPError(f"{app} 拉起了但调试端口没开(这个 App 可能禁了这个参数),已关掉;这次走辅助功能", "error")
    # 有的 App 窗口晚出:再看几秒,露了就藏
    t1 = time.time()
    while time.time() - t1 < 4:
        if _has_window(pid):
            hide(pid)
            _give_front_back(front, pid)
        time.sleep(0.3)
    hide(pid)
    _give_front_back(front, pid)
    h = register(app, pid, port, profile, files)
    if app == "Visual Studio Code":
        _wait_vscode(h)
    if watch:
        _guard(h)
    _log(f"{app} 已隐身拉起:pid={pid} 端口={port}(只绑 127.0.0.1),藏着={is_hidden(pid)}")
    return h


def _guard(h):
    """接 stealth 的看门狗:窗口一露面(用户点程序坞图标等)就停手。"""
    try:
        from seeu import stealth
        stealth.guard(h)
    except Exception as e:
        _log("看门狗没开起来:", e)


def _kill(pid, wait_s=QUIT_WAIT_S):
    try:
        os.kill(pid, 15)
    except OSError:
        return True
    t0 = time.time()
    while _alive(pid) and time.time() - t0 < wait_s:
        time.sleep(0.3)
    if _alive(pid):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        time.sleep(0.5)
    return not _alive(pid)


def quit(h, discard_unsaved=False):
    """关掉 SeeU 专用那份(端口跟着关)。先礼后兵:Browser.close → 等 → SIGTERM → SIGKILL。
    VS Code 没保存的改动默认留着(下次拉起会恢复,restart 靠这个);discard_unsaved=True 关完把它的备份删掉 = 丢掉改动。"""
    if isinstance(h, str):
        h = running(h, fresh=True)
        if not h:
            return True
    try:
        url = _http(h.port, "/json/version").get("webSocketDebuggerUrl")
        with Session(url) as s:
            s.call("Browser.close", timeout=3)
    except Exception:
        pass
    t0 = time.time()
    while _alive(h.pid) and time.time() - t0 < 5:
        time.sleep(0.3)
    ok = _kill(h.pid)
    unregister(h.app)
    if discard_unsaved and ok and h.app == "Visual Studio Code":
        import shutil
        shutil.rmtree(os.path.join(h.profile, "Backups"), ignore_errors=True)
    return ok


def restart(target):
    """被叫出来后一键重开:关掉 → 清掉停手标记 → 隐身重开(同样的文件)→ 看门狗。返回新 Handle。"""
    from seeu import bgclick as bg
    h = target if isinstance(target, Handle) else running(target, fresh=True)
    app = h.app if h else target
    files = (h.files if h else [])
    if h:
        try:
            files = list(dict.fromkeys(files + ([vscode_read(h, _quiet=True)["path"]] if app == "Visual Studio Code" else [])))
        except Exception:
            pass
        quit(h)
    for pid in [p for p, v in bg.CALLED_OUT.items() if v[0] == app]:
        bg.CALLED_OUT.pop(pid, None)
    from seeu import stealth
    stealth.mark_called(app, False)
    return launch(app, *[f for f in files if f and os.path.exists(f)])


# ---------------------------------------------------------------- 页面

def pages(h):
    """这份 App 里的页面(type=page,去掉开发者工具自己的)。"""
    try:
        ts = _http(h.port, "/json/list")
    except Exception as e:
        raise CDPError(f"调试端口没回话({e.__class__.__name__})", "no_app")
    return [t for t in ts if t.get("type") == "page" and not str(t.get("url", "")).startswith("devtools://")]


def find_page(h, tab=None, match=None):
    """tab = 页面 id;match = 网址/标题里的字;都不给:VS Code 取主窗口,别的取第一个。"""
    ps = pages(h)
    if tab:
        p = next((t for t in ps if t["id"] == tab), None)
        if not p:
            raise CDPError("这个标签页/页面已经没了,重新 tabs() 拿编号", "stale")
        return p
    if match:
        ps = [t for t in ps if match in t.get("url", "") or match in t.get("title", "")]
    if h.app == "Visual Studio Code":
        ps = [t for t in ps if "workbench" in t.get("url", "")] or ps
    if not ps:
        raise CDPError(f"{h.app} 里没有页面", "no_page")
    return ps[0]


def session(h, tab=None, match=None):
    _check(h)
    return Session(find_page(h, tab, match)["webSocketDebuggerUrl"])


def _check(h):
    from seeu import bgclick as bg, safety
    hit = bg.CALLED_OUT.get(h.pid)
    if hit:
        raise CDPError(f"卡在:操作 {h.app} 原因:{h.app} 被叫到桌面上了(你可能正在看它),SeeU 已停手 "
                       f"怎么办:看完运行 {h.restart_cmd} 重开", "called_out")
    if not _alive(h.pid):
        unregister(h.app)
        raise CDPError(f"{h.app} 已经退出了", "no_app")
    try:
        safety.check_pid(h.pid)
    except safety.Refused as ex:
        raise CDPError(str(ex), "refused")


def page_fn(h, fn, args, tab=None):
    """跑插件同款的网页函数(pageSnapshot / pageAct / pageRead),返回解析好的结果。"""
    from seeu.web import aejs
    code = ("(function(){try{return (" + aejs._page_fn(fn) + ").apply(null," + json.dumps(args, ensure_ascii=False) +
            ")}catch(e){return {__err:String(e),code:'page'}}})()")
    with session(h, tab) as s:
        r = s.eval(code)
    if r is None:
        raise CDPError("网页脚本没回话(页面可能正在跳转)", "script")
    if isinstance(r, dict) and r.get("__err"):
        raise CDPError(r["__err"], r.get("code") or "page")
    return r


def wait_loaded(h, tab, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with session(h, tab) as s:
                if s.eval("document.readyState") == "complete":
                    return True
        except CDPError:
            pass
        time.sleep(0.3)
    return False


def open_tab(h, url):
    """后台开新标签页,返回页面 id。🔴 Chrome 开新标签一定会露一下窗口(10-25 试了 createTarget background / hidden、
    window.open 带不带手势四种,只有 hidden 不露但连接一断标签就没了)→ 看门狗暂停、开完马上藏、前台还回去。
    不想露:用 navigate(h, tab, url) 在已有标签里跳转(实测不露)。"""
    _check(h)
    front = _front()
    from seeu import stealth
    with stealth.pause(h):
        with Session(_http(h.port, "/json/version")["webSocketDebuggerUrl"]) as s:
            tid = s.call("Target.createTarget", {"url": url, "background": True})["targetId"]
        t0 = time.time()
        while time.time() - t0 < 1.5 and not _has_window(h.pid):
            time.sleep(0.05)
        hide(h.pid)
    _give_front_back(front, h.pid)
    return tid


def navigate(h, tab, url):
    """在已有的标签/页面里跳转(不开新标签,窗口不露)。"""
    with session(h, tab) as s:
        s.call("Page.navigate", {"url": url})


def eval(h, expr, tab=None):
    with session(h, tab) as s:
        return s.eval(expr)


# ---------------------------------------------------------------- 打字 / 按键

MOD = {"alt": 1, "option": 1, "opt": 1, "ctrl": 2, "control": 2, "cmd": 4, "command": 4, "meta": 4, "shift": 8}
KEYS = {"enter": ("Enter", "Enter", 13, "\r"), "return": ("Enter", "Enter", 13, "\r"), "tab": ("Tab", "Tab", 9, "\t"),
        "escape": ("Escape", "Escape", 27, ""), "esc": ("Escape", "Escape", 27, ""),
        "delete": ("Backspace", "Backspace", 8, ""), "backspace": ("Backspace", "Backspace", 8, ""),
        "forward_delete": ("Delete", "Delete", 46, ""), "space": (" ", "Space", 32, " "),
        "left": ("ArrowLeft", "ArrowLeft", 37, ""), "up": ("ArrowUp", "ArrowUp", 38, ""),
        "right": ("ArrowRight", "ArrowRight", 39, ""), "down": ("ArrowDown", "ArrowDown", 40, ""),
        "home": ("Home", "Home", 36, ""), "end": ("End", "End", 35, ""),
        "page_up": ("PageUp", "PageUp", 33, ""), "page_down": ("PageDown", "PageDown", 34, "")}
KEYS.update({f"f{i}": (f"F{i}", f"F{i}", 111 + i, "") for i in range(1, 13)})


def _key_spec(key):
    k = str(key).lower()
    if k in KEYS:
        return KEYS[k]
    if len(k) == 1 and k.isalpha():
        return (k, "Key" + k.upper(), ord(k.upper()), k)
    if len(k) == 1 and k.isdigit():
        return (k, "Digit" + k, ord(k), k)
    punct = {"`": ("Backquote", 192), "-": ("Minus", 189), "=": ("Equal", 187), "[": ("BracketLeft", 219),
             "]": ("BracketRight", 221), "\\": ("Backslash", 220), ";": ("Semicolon", 186), "'": ("Quote", 222),
             ",": ("Comma", 188), ".": ("Period", 190), "/": ("Slash", 191)}
    if k in punct:
        return (k, punct[k][0], punct[k][1], k)
    raise CDPError(f"不认识的键 {key}", "error")


_VSC_TERMINAL_JS = "!!(document.activeElement && document.activeElement.closest('.terminal, .xterm, .terminal-wrapper'))"


def _not_terminal(h, s):
    if h.app == "Visual Studio Code" and s.eval(_VSC_TERMINAL_JS):
        raise CDPError("VS Code 的焦点在内置终端里,往里打字等于能执行任何命令,SeeU 不碰(这一步请你自己来)", "refused")


_SECRET_JS = ("(function(){var e=document.activeElement;"
              "while(e&&e.shadowRoot&&e.shadowRoot.activeElement)e=e.shadowRoot.activeElement;"
              "if(!e)return '';var t=(e.type||'').toLowerCase(),"
              "a=(e.getAttribute&&e.getAttribute('autocomplete')||'').toLowerCase();"
              "if(t==='password')return '密码框';if(a.indexOf('one-time-code')>=0)return '验证码框';"
              "if(a.indexOf('cc-')===0)return '银行卡框';return ''})()")


def _chrome_guard(h, s):
    """隐身 Chrome 上按键 / 打字之前(11-06 体检:原来这两个动作不查名单、不查密码框,
    名单外网站的表单有焦点时按回车就提交了):当前页不在允许名单(I See 没开)→ 拒;焦点在密码 / 验证码 / 银行卡框 → 拒。"""
    if h.app != "Google Chrome":
        return
    from seeu import isee
    from seeu.web import aejs
    url = s.eval("location.href") or ""
    if not isee.active() and not aejs.is_allowed(url):
        o = aejs.origin(url) or url
        raise CDPError(f"这个网站({o})不在 SeeU 允许名单里,不往里按键 / 打字"
                       f"(AI 问你时答应就行;也可以终端 python3 -m seeu allow {o})", "refused")
    kind = s.eval(_SECRET_JS)
    if kind:
        raise CDPError(f"光标在{kind}里,SeeU 不碰(这一步请你自己来)", "refused")


def _focus(s):
    """让藏着的页面以为自己有焦点(不然输入框不收字)。"""
    s.call("Emulation.setFocusEmulationEnabled", {"enabled": True})


def _step(h, step):
    from seeu import web
    web._watch(h.app, step)


def type(h, text, tab=None):
    """往页面当前焦点处打字(中英文都行;换行也照打)。返回 dict(outcome, route, …)。"""
    from seeu import safety
    try:
        safety.check_text(text)
    except safety.Refused as ex:
        return dict(outcome="refused", route="调试端口", reason=str(ex))
    _step(h, "打字")
    try:
        with session(h, tab) as s:
            _focus(s)
            _not_terminal(h, s)
            _chrome_guard(h, s)
            s.call("Input.insertText", {"text": str(text)})
    except CDPError as ex:
        return dict(outcome="refused" if ex.code in ("refused", "called_out") else "failed", route="调试端口",
                    reason=str(ex), code=ex.code)
    return dict(outcome="unverified", route="调试端口", reason="已发给页面(要核实就读一次)")


def key(h, k, *mods, tab=None):
    """发一个键(可带修饰键):key(h, "s", "cmd") = ⌘S。"""
    from seeu import safety
    try:
        safety.check_keys(k, mods)
    except safety.Refused as ex:
        return dict(outcome="refused", route="调试端口", reason=str(ex))
    name, code, vk, text = _key_spec(k)
    m = 0
    for x in safety.norm_mods(mods):
        if x not in MOD:            # 11-06:原来不认识的修饰键静默忽略,跟安全检查看到的不是同一套
            return dict(outcome="failed", route="调试端口", reason=f"不认识的修饰键:{x}(只认 cmd / shift / alt / ctrl)")
        m |= MOD[x]
    _step(h, "按键")
    try:
        with session(h, tab) as s:
            _focus(s)
            _not_terminal(h, s)
            _chrome_guard(h, s)
            base = dict(key=name if not (m & 8 and len(name) == 1) else name.upper(), code=code,
                        windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk, modifiers=m)
            down = dict(base, type="keyDown", text=text, unmodifiedText=text) if text and not (m & 7) else dict(base, type="rawKeyDown")
            s.call("Input.dispatchKeyEvent", down)
            s.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
    except CDPError as ex:
        return dict(outcome="refused" if ex.code in ("refused", "called_out") else "failed", route="调试端口",
                    reason=str(ex), code=ex.code)
    return dict(outcome="unverified", route="调试端口", reason="已发给页面")


# ---------------------------------------------------------------- VS Code 专用

def _wait_vscode(h, timeout=20):
    """等编辑器出来(有打开文件时等到标签出现)。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with session(h) as s:
                if s.eval("!!document.querySelector('.monaco-workbench')") and (
                        not h.files or s.eval("!!document.querySelector('.tab .label-name')")):
                    return True
        except CDPError:
            pass
        time.sleep(0.5)
    return False


_VSC_READ_JS = r"""(function(){
  const ed = document.querySelector('.editor-group-container.active .monaco-editor') || document.querySelector('.monaco-editor');
  const ta = ed && ed.querySelector('textarea.inputarea, textarea');
  const tab = document.querySelector('.editor-group-container.active .tab.active') || document.querySelector('.tab.active');
  return {title: document.title, hasEditor: !!ed, text: ta ? ta.value : null,
          tab: tab ? (tab.querySelector('.label-name')||{}).innerText : null,
          tabTitle: tab ? tab.getAttribute('title') : null,
          dirty: !!(tab && tab.classList.contains('dirty')), anyDirty: !!document.querySelector('.tab.dirty')};
})()"""


def vscode_read(h, _quiet=False):
    """读当前打开的整个文件(含没保存的改动):{path, text, dirty, any_dirty, lines}。
    靠专用配置里开的读屏模式:编辑器的隐藏输入框里放整页文字,页大小设成 100 万行 = 整个文件。"""
    if not _quiet:
        _step(h, "读文件")
    with session(h) as s:
        _focus(s)
        # 读屏模式下输入框里只放光标附近那一页;焦点得在编辑器上它才会填
        s.eval("(document.querySelector('.editor-group-container.active .monaco-editor textarea')||{focus(){}}).focus(), 1")
        time.sleep(0.2)
        r = s.eval(_VSC_READ_JS)
    path = _title_path(r)
    return dict(path=path, text=r.get("text"), dirty=r.get("dirty"), any_dirty=r.get("anyDirty"),
                lines=None if r.get("text") is None else r["text"].count("\n") + 1, tab=r.get("tab"))


def vscode_dirty(h):
    """当前文件 / 任何一个标签有没有没保存的改动:{dirty, any_dirty, path}。"""
    with session(h) as s:
        r = s.eval(_VSC_READ_JS)
    return dict(dirty=r.get("dirty"), any_dirty=r.get("anyDirty"), path=_title_path(r))


def _title_path(r):
    """窗口标题(专用配置设成「● 」+ 完整路径,家目录写成 ~)→ 绝对路径;对不上就用标签的提示文字。"""
    p = os.path.expanduser((r.get("title") or "").lstrip("●").strip())
    return p if p.startswith("/") else (r.get("tabTitle") or "")


def vscode_open(h, path):
    """在 SeeU 专用那份里打开一个文件(快速打开 ⌘P → 粘路径 → 回车,全程藏着)。"""
    path = os.path.abspath(os.path.expanduser(path))
    r = key(h, "p", "cmd")
    if r.get("outcome") in ("refused", "failed"):   # 11-06 体检:焦点在内置终端时 ⌘P 被拒,原来没看结果,接着把路径打进终端
        raise CDPError(r.get("reason") or "快速打开没按出来", r.get("code") or "refused")
    time.sleep(0.5)
    with session(h) as s:
        _focus(s)
        s.eval("(document.querySelector('.quick-input-widget input')||{focus(){}}).focus(), 1")
        s.call("Input.insertText", {"text": path})
    time.sleep(0.8)
    key(h, "enter")
    if path not in h.files:
        h.files.append(path)
    t0 = time.time()
    while time.time() - t0 < 8:
        if vscode_dirty(h)["path"] == path:
            return True
        time.sleep(0.3)
    return False


# ---------------------------------------------------------------- 命令行

def main(argv=None):
    """python3 -m seeu.cdp list              本机哪些 App 能走调试端口
    python3 -m seeu.cdp status            SeeU 专用那几份现在开着没有
    python3 -m seeu.cdp restart <App>     被叫出来后一键重开(VS Code 同样的文件)
    python3 -m seeu.cdp quit <App>        关掉 SeeU 专用那份"""
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd == "list":
        from seeu import safety
        for n, k, b in installed():
            note = "安全底线不碰(正在运行 SeeU)" if b in safety.host_bundles() else TESTED.get(n, "没试过(有的 App 会禁掉这个参数)")
            print(f"  {n}({k}):{note}")
    elif cmd == "status":
        os.makedirs(DIR, exist_ok=True)
        any_ = False
        for f in sorted(os.listdir(DIR)):
            if f.endswith(".json"):
                try:
                    app = json.load(open(os.path.join(DIR, f), encoding="utf-8"))["app"]
                except Exception:
                    continue
                h = running(app, fresh=True)
                if h:
                    any_ = True
                    print(f"  {app}:开着 pid={h.pid} 端口={h.port},藏着={is_hidden(h.pid)}")
        if not any_:
            print("  SeeU 专用那几份都没开着")
    elif cmd in ("restart", "重开") and len(argv) > 1:
        app = argv[1]
        if app.lower() == "chrome":
            print("隐身 Chrome 用:python3 -m seeu.stealth restart Chrome"); return
        h = restart(app)
        print(f"已隐身重开 {h.app}:pid={h.pid},藏着={is_hidden(h.pid)}。注意:看门狗跟着这个命令结束,干活的程序要自己 cdp.launch 接上")
    elif cmd == "quit" and len(argv) > 1:
        print("已关掉" if quit(argv[1]) else "没关掉,请手动退出")
    else:
        print(main.__doc__)


if __name__ == "__main__":
    main()
