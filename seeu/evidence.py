# -*- coding: utf-8 -*-
"""SeeU 出事时一键取证(C-0.5,10-22 用户要):觉得被抢键盘、打字跑错地方、窗口乱跳时,马上跑一下,当场记下现场。

    python3 -m seeu 取证              # 记文字现场(几秒)
    python3 -m seeu 取证 --shot       # 再截一张整屏(先查 iPhone 镜像在不在当前桌面,在就不截)

只读、不改任何东西:不点、不打字、不切前台、不动 Safari。每一步都有超时,查不到就写「查不到」接着往下。
记到 seeu/参考/取证/取证-MMDD-HHMMSS.md(文字,进备份);截图放 ~/.seeu/seeu_evidence/(整屏会拍到整个桌面,不进备份)。
记什么:谁在前台、前台的当前窗口;每个浏览器藏没藏、露几个窗口、各标签页网页焦点在哪(要浏览器开关);
输入法、密码输入状态;屏幕上最上面的窗口;在跑的 SeeU 相关程序;悬浮窗状态和最近日志。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "参考/取证")
SHOT_DIR = home("seeu_evidence")
BROWSERS = ["Safari", "Google Chrome", "Microsoft Edge", "Brave Browser", "Arc", "Chromium"]
# 网页焦点:焦点在哪个元素(穿过 shadow DOM),可不可编辑;页面在不在显示
PAGE_JS = ("(function(){var a=document.activeElement;while(a&&a.shadowRoot&&a.shadowRoot.activeElement)a=a.shadowRoot.activeElement;"
           "var d=a?(a.tagName+(a.id?'#'+a.id:'')+(a.className&&typeof a.className=='string'?'.'+a.className.split(' ')[0]:'')):'无';"
           "return JSON.stringify({hasFocus:document.hasFocus(),visible:document.visibilityState,active:d,"
           "editable:!!(a&&(a.isContentEditable||/^(INPUT|TEXTAREA)$/.test(a.tagName)))})})()")


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"查不到({e.__class__.__name__})"


def _osa(s, timeout=5):
    return _run(["osascript", "-e", s], timeout)


def _try(fn, default="查不到"):
    try:
        return fn()
    except Exception as e:
        return f"{default}({e})"


def front_app():
    name = _osa('tell application "System Events" to get name of first process whose frontmost is true')
    win = _osa('tell application "System Events" to tell (first process whose frontmost is true) to get name of front window')
    return name, win


def running(app):
    return subprocess.run(["pgrep", "-x", app], capture_output=True).returncode == 0


def windows():
    import Quartz
    return list(Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, 0) or [])   # 系统给的是 NSArray


def browser_state(app, wins):
    pids = _run(["pgrep", "-x", app]).split()
    pid = int(pids[0]) if pids and pids[0].isdigit() else None
    vis = _osa(f'tell application "System Events" to get visible of process "{app}"')
    mine = [w for w in wins if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0
            and (w.get("kCGWindowBounds") or {}).get("Width", 0) > 100]
    out = [f"- **{app}**(pid {pid}):可见={vis};正常窗口 {len(mine)} 个,露在当前桌面 "
           f"{sum(1 for w in mine if w.get('kCGWindowIsOnscreen'))} 个"]
    try:
        from seeu.web import aejs
        if not aejs.supported(app):
            return out
        st = aejs.state(app)
        if st != "on":
            out.append(f"  - 浏览器开关:{st}(网页焦点查不到)")
            return out
        for t in aejs.tabs(app):
            info = _try(lambda: json.loads(aejs.js(app, PAGE_JS, t["id"])), "读不到")
            mark = "★当前" if t["active"] else "  "
            out.append(f"  - {mark} 标签 {t['id']}:{t['title'][:30]} | {t['url'][:60]} | 网页 {info}")
    except Exception as e:
        out.append(f"  - 标签页查不到({e})")
    return out


def input_source():
    s = _run(["defaults", "read", os.path.expanduser("~/Library/Preferences/com.apple.HIToolbox"),
              "AppleSelectedInputSources"])
    import re
    names = re.findall(r'"Input Mode" = "([^"]+)"', s) + re.findall(r'"KeyboardLayout Name" = "?([^";]+)"?;', s)
    return ", ".join(dict.fromkeys(names)) or s[:120]


def top_windows(wins, n=8):
    out = []
    for w in wins:
        if not w.get("kCGWindowIsOnscreen"):
            continue
        b = w.get("kCGWindowBounds") or {}
        if b.get("Width", 0) < 40 or b.get("Height", 0) < 20:
            continue
        out.append(f"- 层 {w.get('kCGWindowLayer')} · {w.get('kCGWindowOwnerName')} · {(w.get('kCGWindowName') or '')[:30]} · "
                   f"{int(b.get('X', 0))},{int(b.get('Y', 0))} {int(b.get('Width', 0))}×{int(b.get('Height', 0))}")
        if len(out) >= n:
            break
    return out


def seeu_procs():
    s = _run(["ps", "-axo", "pid=,lstart=,command="])
    keys = ("watch_window", "cursor_overlay", "seeu", "mir.py", "quick.py", "tx_frost", "sendcn", "pastecn", "host.py")
    out = []
    for ln in s.splitlines():
        if not any(k in ln for k in keys) or "取证" in ln or "evidence" in ln or "grep" in ln:
            continue
        p = ln.split()
        cmd = " ".join(p[6:])
        # 只留程序名那段(去掉一长串 Python 路径)
        tail = next((cmd[cmd.find(k):] for k in keys if k in cmd), cmd)
        out.append(f"{p[0]} · {p[4][:5]} 起 · {tail[:100]}")
    return out


def watch_state():
    out = []
    live = home("seeu_live.json")
    if os.path.exists(live):
        out.append("- 悬浮窗开关状态:" + open(live, encoding="utf-8").read().strip()[:200])
    log = home("watch_window.log")
    if os.path.exists(log):
        lines = open(log, encoding="utf-8", errors="replace").read().splitlines()[-8:]
        out.append("- 悬浮窗日志最后几行:")
        out += [f"  - {ln}" for ln in lines]
    return out


def shot():
    """截整屏:iPhone 镜像在当前桌面就不截(会触发有的 App 的截屏提示)。"""
    try:
        from seeu_lib import mac_input as mi
        g = mi.win_geo("iPhone Mirroring")
    except Exception:
        g = "查不到"
    if g is not None:
        return "iPhone 镜像在当前桌面(或查不到),不截整屏"
    os.makedirs(SHOT_DIR, exist_ok=True)
    p = os.path.join(SHOT_DIR, time.strftime("取证-%m%d-%H%M%S.png"))
    _run(["screencapture", "-x", p], 10)
    return p if os.path.exists(p) else "截图失败"


def collect(with_shot=False):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# SeeU 取证 {t}", ""]
    name, win = front_app()
    lines += ["## 前台", f"- 前台程序:{name}", f"- 它的当前窗口:{win}", ""]
    wins = _try(windows, [])
    if not isinstance(wins, list):
        wins = []
    lines.append("## 浏览器")
    any_b = False
    for b in BROWSERS:
        if running(b):
            any_b = True
            lines += browser_state(b, wins)
    if not any_b:
        lines.append("- 没有开着的浏览器")
    lines += ["", "## 键盘", f"- 输入法:{input_source()}"]
    sec = _try(lambda: __import__("seeu_lib.input_guard", fromlist=["x"]).secure_input_pid())
    lines += [f"- 密码输入状态占用的进程:{sec or '没有'}", ""]
    lines += ["## 屏幕最上面的窗口(从上往下)"] + top_windows(wins) + [""]
    lines += ["## 在跑的 SeeU 相关程序"] + ([f"- {p}" for p in seeu_procs()] or ["- 没有"]) + [""]
    lines += ["## 悬浮窗"] + (watch_state() or ["- 没有记录"]) + [""]
    if with_shot:
        lines += ["## 截图", f"- {shot()}", ""]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, time.strftime("取证-%m%d-%H%M%S.md"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path, lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    t0 = time.time()
    path, lines = collect(with_shot="--shot" in argv)
    print("\n".join(lines))
    print(f"\n已记下(用时 {time.time() - t0:.1f} 秒):{path}")
    os.system(f'cd "{ROOT}" && python3 -m seeu_lib.cursor_overlay toast "SeeU 取证完成" "记在 seeu/参考/取证/,告诉 Claude 就行" 5 >/dev/null 2>&1')


if __name__ == "__main__":
    main()
