# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 一键接入 / 移除(第 2 段,11-18)。

    python3 -m seeu 接入                  # 看接了没有
    python3 -m seeu 接入 claude|codex|cursor|vscode|自动
    python3 -m seeu 移除 claude|codex|cursor|vscode

做法:直接用 Windows 版 seeu/win/install.py 那一整套(只加 / 删 seeu 这一条、改前备份、写完核对、试连、带记号的 Skill),
只把跟系统有关的几处换成 Linux 的 —— 服务和 Skill 指向 seeu/linux/、Cursor / VS Code 的设置位置、找进程走 /proc、
提示里的 Windows 字样。Windows 那份改了逻辑,这边自动跟上;改了提示文字,看看下面 _FIX 要不要补。
- Claude 桌面版没有 Linux 版 → 只接 Claude Code(有 claude 命令时 `claude mcp add -s user`)+ Skill 到 ~/.claude/skills/seeu。
- Codex:~/.codex/config.toml 追加一节(设了 CODEX_HOME 用那个)+ Skill 到 ~/.codex/skills/seeu。
- Cursor:~/.cursor/mcp.json;VS Code:~/.config/Code/User/mcp.json(snap 版也是这里)。Trae 没有 Linux 版,不列。
记录放 <SEEU_HOME>/seeu_接入_linux.json,备份放 <SEEU_HOME>/seeu_接入备份/。
"""
import builtins
import os
import signal

from seeu_lib import home
from seeu.win import install as _w

HERE = os.path.dirname(os.path.abspath(__file__))
_w.SERVER = os.path.join(HERE, "mcp_server.py")
_w.SKILL = os.path.join(HERE, "skill")
_w.STATE = os.path.normpath(home("seeu_接入_linux.json"))
_w.JSON_KEYS = ("cursor", "vscode")
_w._desktop_cfg = lambda: None                 # Claude 桌面版没有 Linux 版
_w.write_pointer = lambda: None                # npm 启动包是给千问的(Windows / Mac),Linux 用不上


def _codex_app():
    """装了 ChatGPT 桌面版(内含 Codex,.deb 包名 chatgpt,装在 /usr/lib/chatgpt)就返回版本号。11-19 虚拟机实测:
    刚装完、没打开过时没有 ~/.codex,也没有 codex 命令,只能这样认。"""
    import subprocess
    try:
        v = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "chatgpt"], capture_output=True, text=True,
                           timeout=10).stdout.strip()
    except Exception:   # noqa: BLE001
        v = ""
    if not v:   # Fedora 一家(11-21 C-3.4):rpm 包
        try:
            v = subprocess.run(["rpm", "-q", "--qf", "%{VERSION}", "chatgpt"], capture_output=True, text=True,
                               timeout=10).stdout.strip()
            v = "" if "not installed" in v or " " in v else v
        except Exception:   # noqa: BLE001
            v = ""
    if v:
        return v
    return "?" if os.path.exists("/usr/lib/chatgpt/codex-launcher") else None


_w._codex_app = _codex_app
_codex_block0 = _w._codex_block
_w._codex_block = lambda: _codex_block0().replace("python -m seeu", "python3 -m seeu")   # 写进设置的说明行

# 提示里的 Windows 字样换成 Linux 的(长的先换;中英两套都换)
_FIX = [
    ("① 没找到 Claude 桌面版(%APPDATA%\\Claude 不在)。要用的话先装:https://claude.ai/download",
     "① Claude 桌面版没有 Linux 版,跳过(Linux 上用 Claude Code)"),
    ("① Claude desktop not found (no %APPDATA%\\Claude). To use it, install it first: https://claude.ai/download",
     "① Claude desktop has no Linux version, skipped (use Claude Code on Linux)"),
    ("Claude 桌面版:没装", "Claude 桌面版:没有 Linux 版"), ("Claude desktop: not installed", "Claude desktop: no Linux version"),
    ("① 没找到 Codex(没有 codex 命令、没有 %USERPROFILE%\\.codex,也没装 ChatGPT / Codex App)。",
     "① 没找到 Codex(没有 codex 命令、没有 ~/.codex,也没装 ChatGPT 桌面版)。"),
    ("① Codex not found (no codex command, no %USERPROFILE%\\.codex, and the ChatGPT / Codex app isn't installed). ",
     "① Codex not found (no codex command, no ~/.codex, and the ChatGPT desktop app isn't installed). "),
    ("https://learn.chatgpt.com/docs/windows/windows-app", "https://developers.openai.com/codex/cli"),
    (";没装 comtypes 先 python -m pip install comtypes", ""),
    ("; if comtypes is missing: python -m pip install comtypes", ""),
    ("Windows 预览版现在支持接 Claude、Codex、Cursor、Trae、VS Code", "Linux 预览版现在支持接 Claude Code、Codex、Cursor、VS Code"),
    ("The Windows preview can connect Claude, Codex, Cursor, Trae and VS Code", "The Linux preview can connect Claude Code, Codex, Cursor and VS Code"),
    ("claude|codex|cursor|trae|vscode", "claude|codex|cursor|vscode"),
    ("(Windows)", "(Linux)"), ("(Windows)", "(Linux)"),
    ("python -m seeu", "python3 -m seeu"),
    ("看一下记事本", "看一下文本编辑器"), ("look at Notepad", "look at Text Editor"),
]


def _fix(s):
    for a, b in sorted(_FIX, key=lambda p: -len(p[0])):
        s = s.replace(a, b)
    return s


def _print(*a, **k):
    builtins.print(*[_fix(x) if isinstance(x, str) else x for x in a], **k)


_w.print = _print            # win/install.py 里的 _p / _pl 都走模块里的 print:截在这里统一换字样


def _json_clients():
    h = os.path.expanduser("~")
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(h, ".config")
    return {
        "cursor": dict(label="Cursor", root="mcpServers", procs=("cursor",), cmd="cursor", get="https://cursor.com/download",
                       variants=[("Cursor", os.path.join(h, ".cursor", "mcp.json"),
                                  [os.path.join(h, ".cursor"), os.path.join(cfg, "Cursor")])],
                       hint=("打开 Cursor(开着的话完全退出再开,开着时它不重读设置)。",
                             "Open Cursor (if it is open, quit it fully and reopen; it doesn't re-read the config while running).")),
        "vscode": dict(label="VS Code", root="servers", procs=("code",), cmd="code", get="https://code.visualstudio.com",
                       variants=[("Visual Studio Code", os.path.join(cfg, "Code", "User", "mcp.json"),
                                  [os.path.join(cfg, "Code"), "/usr/share/code/code", "/snap/code/current"])],
                       hint=("VS Code 里打开 Copilot 对话(Agent 模式)。第一次用会问「信任工作区」,每个 SeeU 工具第一次用会问要不要允许,都点允许。",
                             "In VS Code open Copilot Chat (Agent mode). The first time it asks to trust the workspace, and each SeeU tool asks "
                             "for permission on first use: allow both.")),
    }


_w._json_clients = _json_clients


def _proc_table():
    """pid → (父 pid, 程序名)。读 /proc,读不到的跳过。"""
    t = {}
    try:
        ds = os.listdir("/proc")
    except OSError:                  # 不是 Linux(Mac 上跑离线测试)
        return t
    for d in ds:
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", encoding="utf-8", errors="replace") as f:
                s = f.read()
            name = s[s.index("(") + 1:s.rindex(")")]
            ppid = int(s[s.rindex(")") + 2:].split()[1])
            t[int(d)] = (ppid, name)
        except (OSError, ValueError):
            continue
    return t


def _cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _stop_running(procs):
    """停掉这家拉起的 SeeU 服务(设置删了它察觉不到,会一直挂着)。只停命令行里指着这份 mcp_server.py、上级链上有这家程序的。"""
    table = _proc_table()
    n = 0
    for pid in table:
        if pid == os.getpid() or _w.SERVER not in _cmdline(pid):
            continue
        cur, seen = table[pid][0], set()
        while cur and cur not in seen and cur in table:
            seen.add(cur)
            if table[cur][1].lower() in procs:
                try:
                    os.kill(pid, signal.SIGTERM)
                    n += 1
                except OSError:
                    pass
                break
            cur = table[cur][0]
    return n


def _auto():
    """父进程链上认出是哪家在跑这条命令。"""
    table = _proc_table()
    cur, seen = os.getpid(), set()
    while cur and cur not in seen and cur in table:
        seen.add(cur)
        parent, name = table[cur]
        n = name.lower()
        if "codex" in n:
            return "codex"
        if n.startswith("claude"):
            return "claude"
        if n == "cursor":
            return "cursor"
        if n == "code":
            return "vscode"
        cur = parent
    return None


_w._stop_running = _stop_running
_w._auto = _auto


def main(cmd, args):
    which = (args[0] if args else "").lower()
    if which in ("千问", "qianwen", "qwen", "trae"):
        _print("这一家没有 Linux 版。" if which != "trae" else "Trae 没有 Linux 版。")
        return 2
    if cmd in ("接入", "install"):           # 11-21 C-3.3:不满足要求的先说一声,接入照常做(不拦,用户可能先接好再换桌面)
        from seeu.linux.doctor import env_warnings
        from seeu.linux.lang import say
        w = env_warnings()
        if w:
            say("⚠️ 先说一声:这台电脑不完全满足 SeeU Linux 预览版的要求")
            for x in w:
                say("   - " + x)
            say("   接入照常做;运行 python3 -m seeu 检查 能看全哪些没齐。")
            builtins.print()
    removing = cmd in ("移除", "uninstall", "remove")
    before = _read_state() if removing else None
    rc = _w.main(cmd, args)
    # 11-21 C-3.5(两轮复查):这次之前记录读得出、里面有接过的,这次移除成功后记录空了,才删小插件。
    # 记录读坏(_w.main 会把它改写成 {})、没有记录(只手动接过)、打错名字 / 没带参数(rc=2)都不删。
    if removing and rc == 0 and before and _read_state() == {}:
        _drop_extension()
    return rc


def _read_state():
    """读接入记录:读得出且是 dict 才返回,没有文件 / 读坏 / 格式不对都返回 None。"""
    import json
    try:
        with open(_w.STATE, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    return st if isinstance(st, dict) else None


def _drop_extension():
    """11-21 C-3.4:哪家都不接了 → 把 GNOME 小插件也删掉(以前 shell.uninstall() 写了没人调,移除完小插件还留在系统里)。"""
    from seeu.linux import shell
    from seeu.linux.lang import say
    try:
        if shell.installed():
            shell.uninstall()
            say("一键接入的 AI 客户端都移除了,同时删掉了 SeeU 的 GNOME 小插件(注销重新登录一次后彻底停下)。"
                "要是你还手动接了别的 AI 客户端,运行 python3 -m seeu 检查 --fix 再注销重新登录一次就能装回。")
    except Exception as ex:   # noqa: BLE001
        say(f"SeeU 的 GNOME 小插件没删掉({ex}),可以到「扩展」App 里手动删")
