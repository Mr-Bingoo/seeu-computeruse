# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 出事时一键取证(11-14,照 Mac 版 seeu/evidence.py):觉得被抢键盘、打字跑错地方、窗口乱跳时马上跑一下,记下现场。

    python -m seeu 取证            # 记文字现场(几秒)
    python -m seeu 取证 --shot     # 再截一张前台窗口(安全底线不让碰的窗口不截)

只读、不改任何东西:不点、不打字、不切前台、不起浏览器。每一步查不到就写「查不到」接着往下;调外部命令都有超时。
记到 ~/.seeu/seeu_evidence/取证-MMDD-HHMMSS.md(开源包里是 ~/.seeu/…)。
记什么:版本和设置、谁在前台、屏幕最上面的窗口、键盘语言、在跑的 SeeU 相关程序、浮标状态、专用浏览器状态。
"""
import json
import os
import subprocess
import sys
import time

from seeu_lib import home

OUT_DIR = os.path.normpath(home("seeu_evidence"))
PS_TIMEOUT_S = 15
KEYS = ("seeu", "floatwin", "mcp_server")          # 命令行里带这些字的 Python 进程算 SeeU 相关


# 英文界面时在出口换(见 win/lang.py);窗口不让碰的原因用给 AI 的那张表
EN = [
    ("# SeeU 取证(Windows)", "# SeeU evidence (Windows) "), ("## 前台", "## Foreground"), ("## 键盘", "## Keyboard"),
    ("## 屏幕最上面的窗口(从上往下)", "## Topmost windows (top to bottom)"), ("## 在跑的 SeeU 相关程序", "## Running SeeU processes"),
    ("## 浮标", "## Floating marker"), ("## 专用浏览器", "## SeeU's browser"), ("## 截图", "## Screenshot"),
    ("- 版本:v", "- Version: v"), ("(Windows 预览版)", " (Windows preview)"), ("- 借用鼠标:", "- Borrow mouse: "), ("- I See:开", "- I See: on"),
    ("- I See:关", "- I See: off"), ("- I See:查不到(", "- I See: unknown ("), ("- 键盘语言:", "- Keyboard language: "), ("- 前台窗口:", "- Foreground window: "),
    ("- 前台:没有(锁屏、或正在切换)", "- Foreground: none (locked, or switching)"), (" · 最小化", " · minimized"), (" · 管理员窗口", " · admin window"),
    ("- 没有看得见的窗口", "- no visible windows"),
    ("中文(简体)", "Chinese (Simplified)"), ("中文(繁体)", "Chinese (Traditional)"), ("英文(美国)", "English (US)"), ("英文(英国)", "English (UK)"),
    ("日文", "Japanese"), ("韩文", "Korean"), ("其他", "other"), ("(上级 ", " (parent "), ("- 没有", "- none"),
    ("- 命令行问不到(", "- couldn't read command lines ("), ("),只按名字列 Python 进程:", "), listing Python processes by name only:"),
    ("- 浮标显示进程:在跑", "- Marker process: running"), ("- 浮标显示进程:没在跑", "- Marker process: not running"),
    ("- 浮标上的开关:", "- Marker switches: "), ("- 专用浏览器(", "- SeeU's browser ("), ("):没开", "): not running"),
    ("):开着,", "): running, "), ("露着(登录用)", "shown (for sign-in)"), ("无界面", "no window"), (",端口 ", ", port "),
    (",标签页 ", ", tabs: "), ("- 没装 Chrome / Edge", "- Chrome / Edge not installed"),
    ("没有前台窗口,没截", "no foreground window, nothing captured"), ("前台是 ", "foreground is "), ("),不截", "), not captured"),
    ("查不到(", "unknown ("),
    ("已记下(用时 ", "Saved (took "), (" 秒):", " s): "),
    ("把这个文件给 AI 看,或贴到问题反馈里(里面有窗口标题,发之前自己看一眼)。",
     "Show this file to the AI, or attach it to an issue (it contains window titles, so look it over before sending)."),
]


def _t(s):
    """只用在程序自己写的固定文字上。🔴 窗口标题、命令行、路径是数据,别过这张表(标题里的中文会被换掉)。"""
    try:
        from seeu.win import lang
        if not lang.is_en():
            return s
        from seeu.win import mcp_server
        return lang.tx(s, EN + mcp_server.WIN_PHRASES)       # 一次换完:先过 to_en 的话,不让碰的原因会被拆散、对不上表
    except Exception:   # noqa: BLE001
        return s


def _try(fn, default="查不到"):
    try:
        return fn()
    except Exception as e:
        return _t(f"{default}(") + f"{e.__class__.__name__}: {e})"


def _win_line(w, why=None):
    x, y, ww, hh = w.get("rect") or (0, 0, 0, 0)
    title = "" if why else (w["title"] or "")[:40]          # 不让碰的窗口(密码程序、终端…)只记程序名和原因,不记标题
    s = f"#{w['hwnd']} · {w['exe']} · {title} · {x},{y} {ww}×{hh}"
    if w.get("minimized"):
        s += _t(" · 最小化")
    if w.get("elevated"):
        s += _t(" · 管理员窗口")
    if why:
        s += " · ⛔ " + _t(str(why))
    return s


def front():
    from seeu.win import safety, window as W
    h = W.foreground()
    if not h:
        return [_t("- 前台:没有(锁屏、或正在切换)")]
    w = W.info(h)
    return [_t("- 前台窗口:") + _win_line(w, safety.why_not(w))]


def top_windows(n=10):
    from seeu.win import safety, window as W
    return ["- " + _win_line(w, safety.why_not(w)) for w in W.list_windows()[:n]] or [_t("- 没有看得见的窗口")]


def keyboard():
    """前台窗口那条线程现在用的键盘语言(低 16 位是语言号,0x0804 = 中文简体,0x0409 = 英文美国)。"""
    import ctypes
    from seeu.win import window as W
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.GetKeyboardLayout.restype = ctypes.c_void_p
    h = W.foreground()
    tid = W.pid_tid(h)[1] if h else 0
    lid = (u.GetKeyboardLayout(tid) or 0) & 0xFFFF
    names = {0x0804: "中文(简体)", 0x0404: "中文(繁体)", 0x0409: "英文(美国)", 0x0411: "日文", 0x0412: "韩文", 0x0809: "英文(英国)"}
    return _t("- 键盘语言:") + _t(names.get(lid, "其他")) + f" (0x{lid:04X})"


def _short_cmd(cmd):
    """命令行只留「哪个模块 / 文件 + 子命令」(seeu type "打的字" 这种,后面的参数不记)。
    按词找:-m 后面那个带关键字的词,或文件名带关键字的 .py;安装文件夹名里带 seeu 不算(11-14 复查)。"""
    ws = cmd.split()
    base = lambda w: w.strip('"').replace("/", "\\").rsplit("\\", 1)[-1]      # noqa: E731
    for j, w in enumerate(ws):
        b = base(w).lower()
        if any(k in b for k in KEYS) and ((j and ws[j - 1] == "-m") or b.endswith(".py")):
            return " ".join((["-m"] if ws[j - 1] == "-m" else []) + [base(w)] + [x.strip('"') for x in ws[j + 1:j + 2]])[:70]
    i = min((cmd.lower().find(k) for k in KEYS if k in cmd.lower()), default=0)
    return cmd[max(0, i - 12):i] + " ".join(cmd[i:].split()[:2])[:60]


def seeu_procs():
    """在跑的 Python 进程里跟 SeeU 有关的(问系统要命令行;问不到就只按进程名列 Python)。"""
    me = os.getpid()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.CommandLine)\" }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + ps],
                           capture_output=True, timeout=PS_TIMEOUT_S, creationflags=0x08000000)
        out = []
        for ln in r.stdout.decode("utf-8", "replace").splitlines():
            p = ln.split("\t", 2)
            if len(p) < 3 or not p[0].isdigit() or int(p[0]) == me:
                continue
            cmd = p[2]
            if not any(k in cmd.lower() for k in KEYS) or "evidence" in cmd or "取证" in cmd:
                continue
            out.append(f"- {p[0]}" + _t("(上级 ") + f"{p[1]}) · …{_short_cmd(cmd)}")
        return out or [_t("- 没有")]
    except Exception as e:
        from seeu.win import safety
        py = [f"- {pid} · {name}" for pid, (_, name) in sorted(safety._process_table().items())
              if name.lower().startswith("python") and pid != me]
        return [_t("- 命令行问不到(") + e.__class__.__name__ + _t("),只按名字列 Python 进程:")] + (py or [_t("- 没有")])


def float_state():
    from seeu.win import floatwin as fw
    out = [_t("- 浮标显示进程:在跑" if fw._running() else "- 浮标显示进程:没在跑")]
    d = fw.live()
    if d:
        out.append(_t("- 浮标上的开关:") + json.dumps(d, ensure_ascii=False)[:200])
    return out


def web_state():
    from seeu.win import web
    out = []
    for b in ("chrome", "edge"):
        if not web._exe(b):
            continue
        d = web._load(b)
        if not d:
            out.append(_t("- 专用浏览器(") + b + _t("):没开"))
            continue
        shown = _t("露着(登录用)" if d.get("visible") else "无界面")
        try:
            n = len(web.tabs(b))
        except Exception:
            n = "?"
        out.append(_t("- 专用浏览器(") + b + _t("):开着,") + shown + _t(",端口 ") + str(d.get("port")) + _t(",标签页 ") + str(n))
    return out or [_t("- 没装 Chrome / Edge")]


def settings():
    from seeu import version
    from seeu.win import act
    out = [_t("- 版本:v") + version.current() + _t("(Windows 预览版)"), _t("- 借用鼠标:") + act.real_mode()]
    try:
        from seeu import isee
        out.append(_t("- I See:开" if _isee_on(isee) else "- I See:关"))
    except Exception as e:
        out.append(_t("- I See:查不到(") + e.__class__.__name__ + ")")
    return out


def _isee_on(isee):
    """I See 现在算不算开着。🔴 自己读文件判断、不落盘:isee.active() 发现过期会顺手改设置文件、弹提示(11-14 复查),取证不能改东西。"""
    env = os.environ.get("SEEU_ISEE", "").strip().lower()
    if env in ("1", "on", "开", "true"):
        return True
    if env in ("0", "off", "关", "false"):
        return False
    d = isee._load()
    if str(d.get(isee.KEY, "关")) not in ("开", "on", "1", "true"):
        return False
    until = d.get(isee.KEY_UNTIL)
    try:
        return not (until and time.time() > time.mktime(time.strptime(until, isee.FMT)))
    except ValueError:
        return True


def shot():
    """截前台窗口(PrintWindow,不抢前台)。安全底线不让碰的窗口不截。"""
    from seeu.win import safety, window as W
    h = W.foreground()
    if not h:
        return _t("没有前台窗口,没截")
    w = W.info(h)
    why = safety.why_not(w)
    if why:
        return _t("前台是 ") + f"{w['exe']} (" + _t(str(why)) + _t("),不截")
    ww, hh, data = W.capture(h)
    p = os.path.join(OUT_DIR, "取证-" + time.strftime("%m%d-%H%M%S") + ".png")
    with open(p, "wb") as f:
        f.write(W.png_bytes(ww, hh, data))
    return p


def collect(with_shot=False):
    lines = [_t("# SeeU 取证(Windows)") + time.strftime("%Y-%m-%d %H:%M:%S"), ""]      # 格式串里别放中文(非中文系统上 strftime 会出错)

    def part(title, fn):
        r = _try(fn)
        lines.append(_t(f"## {title}"))
        lines.extend(r if isinstance(r, list) else [f"- {r}"])
        lines.append("")
    part("SeeU", settings)
    part("前台", front)
    part("键盘", lambda: [keyboard()])
    part("屏幕最上面的窗口(从上往下)", top_windows)
    part("在跑的 SeeU 相关程序", seeu_procs)
    part("浮标", float_state)
    part("专用浏览器", web_state)
    os.makedirs(OUT_DIR, exist_ok=True)
    if with_shot:
        part("截图", lambda: [f"- {shot()}"])
    path = os.path.join(OUT_DIR, "取证-" + time.strftime("%m%d-%H%M%S") + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path, lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    t0 = time.time()
    path, lines = collect(with_shot="--shot" in argv)
    print("\n".join(lines))
    print(_t("已记下(用时 ") + f"{time.time() - t0:.1f}" + _t(" 秒):") + path + "\n" + _t("把这个文件给 AI 看,或贴到问题反馈里(里面有窗口标题,发之前自己看一眼)。"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
