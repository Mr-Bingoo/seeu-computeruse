"""插件版第一次用时自己装 Python 库(11-22 C-3.7)。只用标准库。

为什么:插件市场只把 SeeU 的文件拷进客户端的插件文件夹,不会替用户装依赖。
做法:MCP 服务收到第一个工具调用时查一下缺不缺(只看找不找得到,不真 import);缺就在后台起一个
`python -m pip install --user …`(跟 README「自己动手」那条一样,装到同一个地方),工具先回一句「正在准备」,
AI 过半分钟再调就好。装完把用户库目录加回 sys.path,不用重开客户端。
- 只管插件版(seeu/where.py 认);git 版照旧由「检查」提示、用户或 AI 自己装。
- Linux 缺的都是系统软件(要管理员密码),这里不装,交给「检查」照旧给命令。
- 🔴 硬上限:pip 最多跑 15 分钟;状态文件里记的那一轮超过 20 分钟没结果就算失败,不无限等。
- 几个客户端(Claude Code、Codex)同时第一次启动:靠锁文件只装一次,别的只报「正在准备」。

命令行:python3 -m seeu.deps          看缺什么
        python3 -m seeu.deps run      在前台装(后台那一轮就是这样起的)
"""
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time

from seeu_lib import home

STATE = home("seeu_deps.json")
LOCK = home("seeu_deps.lock")
LOG = home("seeu_deps.log")
PIP_TIMEOUT_S = 15 * 60
STALE_S = 20 * 60

# (要找的模块名, pip 包名)。Mac 跟 README「自己动手 · 装依赖」那一行对齐;Windows 只要 comtypes。
NEED = {
    "darwin": [("AppKit", "pyobjc-framework-Cocoa"), ("Quartz", "pyobjc-framework-Quartz"),
               ("ScreenCaptureKit", "pyobjc-framework-ScreenCaptureKit"), ("CoreMedia", "pyobjc-framework-CoreMedia"),
               ("cv2", "opencv-python-headless"), ("numpy", "numpy")],
    "win32": [("comtypes", "comtypes")],
}


def _need():
    return NEED.get("darwin" if sys.platform == "darwin" else "win32" if sys.platform == "win32" else "", [])


def missing():
    """缺的 pip 包名(按 NEED 的顺序)。"""
    out = []
    for mod, pkg in _need():
        try:
            found = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(pkg)
    return out


def _pins(pkgs):
    """11-22 实测:Mac 系统自带 Python 3.9 + 自带的老 pip 会挑中 pyobjc 12.0(已撤回:它谎称支持 3.9)的源码包,编译失败。
    3.9 上把 pyobjc 钉在 12 以下(11.1 有现成的 3.9 安装包),pyobjc-core 也显式写上。"""
    if sys.platform != "darwin" or sys.version_info >= (3, 10):
        return list(pkgs)
    out = [p + "<12" if p.startswith("pyobjc-") else p for p in pkgs]
    if any(p.startswith("pyobjc-") for p in pkgs):
        out.insert(0, "pyobjc-core<12")
    return out


def pip_cmd(pkgs):
    # 11-22 Intel Mac(macOS 14)实测:opencv-python-headless 最新版 5.1 只有 macOS 15 的现成安装包,老系统上 pip 会下 83MB 源码包
    # 现场编译,十几分钟都装不完。--only-binary=:all: 只用现成安装包:pip 自己退回到这台系统能用的那一版(14 上是 5.0),
    # 真没有能用的就当场报错,不会闷头编译。顺带也躲开了 3.9 上那个撤回的 pyobjc 12.0 源码包(_pins 照旧留着兜底)。
    return [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check", "--only-binary=:all:", *_pins(pkgs)]


def _read():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:   # noqa: BLE001
        return {}


def _write(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = f"{STATE}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def _alive(pid):
    if not pid:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True, timeout=10).stdout
            return str(int(pid)) in out
        except Exception:   # noqa: BLE001
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _take_lock():
    """拿到锁返回 True。锁里写进程号;那个进程没了或锁太旧(超过 STALE_S)就当没人拿。"""
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                with open(LOCK, encoding="utf-8") as f:
                    pid = int(f.read().strip() or 0)
                old = time.time() - os.path.getmtime(LOCK) > STALE_S
            except (OSError, ValueError):
                pid, old = 0, True
            if _alive(pid) and not old:
                return False
            try:
                os.remove(LOCK)
            except OSError:
                return False
    return False


def _refresh_path():
    """装完把用户库目录加回来:启动时那个目录还不存在的话,Python 不会把它放进 sys.path。"""
    try:
        import site
        us = site.getusersitepackages()
        if os.path.isdir(us) and us not in sys.path:
            site.addsitedir(us)
    except Exception:   # noqa: BLE001
        pass
    importlib.invalidate_caches()
    if sys.platform == "darwin":                    # 同 seeu/__init__.py:启动时 pyobjc 还没装、那句没生效 → 补上(不冒 Dock 图标)
        try:
            from Foundation import NSBundle
            NSBundle.mainBundle().infoDictionary()["LSBackgroundOnly"] = "1"
        except Exception:   # noqa: BLE001
            pass


_TRIES = [0]


def _tries():
    return _TRIES[0]


def run(pkgs=None):
    """在当前进程里装(带超时),结果写进 STATE。返回退出码。"""
    pkgs = pkgs or missing()
    old = _read()
    _TRIES[0] = int(old.get("tries") or 0) if old.get("status") in ("failed", "installing") else 0
    if not pkgs:
        _write({"status": "ok", "t": time.time()})
        return 0
    _write({"status": "installing", "pid": os.getpid(), "t": time.time(), "pkgs": pkgs, "tries": _TRIES[0]})
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(pip_cmd(pkgs))}\n")
            log.flush()
            kw = {}
            if sys.platform == "win32":     # 11-23 C-3.9 整体复查:本进程是 DETACHED 起的、没有控制台,pip 不带这个会自己弹一个黑窗口(用户一关就装失败)
                kw["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
            rc = subprocess.run(pip_cmd(pkgs), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                timeout=PIP_TIMEOUT_S, **kw).returncode
    except subprocess.TimeoutExpired:
        rc = -1
    except Exception as ex:   # noqa: BLE001
        _write({"status": "failed", "t": time.time(), "pkgs": pkgs, "why": str(ex)[:300], "tries": _tries() + 1})
        return 1
    _refresh_path()
    left = [p for p in missing() if p in pkgs]
    if rc == 0 and not left:
        _write({"status": "ok", "t": time.time(), "pkgs": pkgs})
        return 0
    why = "pip ran for more than 15 minutes and was stopped" if rc == -1 else _last_log_line() or f"pip exit code {rc}"
    _write({"status": "failed", "t": time.time(), "pkgs": left or pkgs, "why": why, "tries": _tries() + 1})
    return 1


def _last_log_line():
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines()[-40:] if l.strip()]
        errs = [l for l in lines if "error" in l.lower()]
        return (errs or lines)[-1][:300] if lines else ""
    except OSError:
        return ""


def _start_background(pkgs):
    """起一个脱离本进程的 `python -m seeu.deps run`,本服务不等它。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    kw = dict(cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    tries = int(_read().get("tries") or 0)
    p = subprocess.Popen([sys.executable, "-m", "seeu.deps", "run", *pkgs], **kw)   # 装哪些由这边定,别让那边再算一遍
    _write({"status": "installing", "pid": p.pid, "t": time.time(), "pkgs": pkgs, "tries": tries})


def _manual(pkgs):
    cmd = " ".join(pip_cmd(pkgs)[:5] + ["--only-binary=:all:"] + [f'"{p}"' if "<" in p else p for p in _pins(pkgs)])   # 给人看的那条去掉 --disable-pip-version-check
    exe = sys.executable
    if sys.platform == "darwin":
        # SeeU 在 Mac 上一律用系统自带的 /usr/bin/python3(插件启动器、README 都是);用 Homebrew 的 python3 跑「检查」时
        # 照它给命令会被 pip 拒绝(externally-managed-environment),所以给人看的命令固定写系统那个(11-23 复查)
        cmd = cmd.replace(exe, "/usr/bin/python3", 1)
    elif " " in exe:
        cmd = cmd.replace(exe, f'"{exe}"', 1)      # Windows:装在 C:\Program Files 下,不加引号 cmd 只认到 C:\Program
    return cmd


MAX_TRIES = 3


def gate():
    """插件版:缺 Python 库就在后台装,返回给 AI 的一句话(英文,同别的工具结果);齐了 / 不是插件版 / Linux 返回 None。"""
    from seeu.where import as_plugin
    if not as_plugin() or not _need():
        return None
    pkgs = missing()
    if pkgs:
        _refresh_path()                             # 后台那一轮可能刚装完:把用户库目录加回来再看一次
        pkgs = missing()
    if not pkgs:
        return None
    st = _read()
    busy = st.get("status") == "installing" and _alive(st.get("pid")) and time.time() - float(st.get("t") or 0) < STALE_S
    if not busy and st.get("status") == "ok" and set(pkgs) & set(st.get("pkgs") or []):
        # 上一轮说装好了,这个进程还是找不到(装到了这个 Python 看不见的地方)→ 别再一轮轮重装,请用户手动装
        return ("SeeU installed its Python libraries, but this Python still can't find " + ", ".join(pkgs) + ". "
                "Ask the user to run this in Terminal, then restart the AI app: " + _manual(pkgs))
    if not busy and st.get("status") == "installing":
        # 11-23 复查:后台那一轮没跑完就没了(重启、注销、客户端关掉时连子进程一起杀)也算失败一次,
        # 不然每次工具调用都重起一轮,永远走不到「请用户手动装」
        st = {"status": "failed", "t": 0, "pkgs": pkgs, "tries": int(st.get("tries") or 0) + 1,
              "why": "the background installer stopped before it finished"}
        _write(st)
    if not busy:
        tries = int(st.get("tries") or 0) if st.get("status") == "failed" else 0
        if st.get("status") == "failed" and (tries >= MAX_TRIES or time.time() - float(st.get("t") or 0) < 120):
            return ("SeeU could not install the Python libraries it needs (" + str(st.get("why") or "unknown error") + "). "
                    "Ask the user to run this in Terminal, then try again: " + _manual(pkgs)
                    + "  (log: " + LOG + ")")
        if _take_lock():
            try:
                st2 = _read()                       # 11-23 复查:拿到锁再看一眼,别的进程可能刚起了一轮
                if not (st2.get("status") == "installing" and _alive(st2.get("pid"))):
                    _start_background(pkgs)
            finally:
                try:
                    os.remove(LOCK)
                except OSError:
                    pass
    return ("SeeU is getting ready: this is its first use after the plugin was installed, so it is installing the Python "
            "libraries it needs in the background (" + ", ".join(pkgs) + "; usually 1–3 minutes). Tell the user in a short "
            "line, wait about 30 seconds, then call seeu_check. Nothing is needed from the user yet.")


def main(args=()):
    if args[:1] == ["run"]:
        return run(list(args[1:]) or None)
    pkgs = missing()
    print("都装好了" if not pkgs else "缺:" + " ".join(pkgs) + "\n装:" + _manual(pkgs))
    return 0 if not pkgs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
