# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 一键接入 / 移除(第 2 段先做 Claude)。

    python -m seeu 接入            # 看接了没有
    python -m seeu 接入 claude     # Claude 桌面版(聊天页)+ Claude Code(装了 claude 命令才接)
    python -m seeu 移除 claude

做的事(跟 Mac 版同一个思路:只加 / 删 seeu 这一条,别的不动;改之前先备份):
  ① Claude 桌面版:%APPDATA%\\Claude\\claude_desktop_config.json 的 mcpServers 里加 seeu(Python + seeu\\win\\mcp_server.py)。
     Claude 开着的话要完全退出(托盘里也退)再开才读得到。
  ② Claude Code(有 claude 命令时):claude mcp add -s user seeu -- <Python> <mcp_server.py>;
     Skill 复制到 %USERPROFILE%\\.claude\\skills\\seeu(Windows 上建软链接要管理员权限,所以复制,里面放一个记号文件,移除时只删带记号的)。
  ③ 试连一次(起服务、问工具列表)。
记录放 <SEEU_HOME>\\seeu_接入_win.json,备份放 <SEEU_HOME>\\seeu_接入备份\\。

加 Codex(命令行和 Codex App 共用一份 %USERPROFILE%\\.codex\\config.toml,设了 CODEX_HOME 就用那个):
    python -m seeu 接入 codex      /  python -m seeu 移除 codex
  ① 直接往 config.toml 末尾追加一节 [mcp_servers.seeu](不用 `codex mcp add`:它会重写整份文件、打乱顺序,Mac 实测);
     移除时只删这一节,别的一个字不动。写完自己核对一遍,读不懂就拿备份还原。
  ② Skill 复制到 .codex\\skills\\seeu(带记号文件,移除只删带记号的)。
  ③ 试连一次。Codex 开着的话要退出再开才读得到。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from seeu_lib import home

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "mcp_server.py")
SKILL = os.path.join(HERE, "skill")
STATE = os.path.normpath(home("seeu_接入_win.json"))
BAK = os.path.normpath(home("seeu_接入备份"))
NAME = "seeu"
MARK = ".seeu_installed"


# 英文界面时在出口换(提示本身照旧写中文,见 win/lang.py)。片段按长的先换,所以整句和它的半句可以同时列
POINTER = os.path.normpath(home("seeu_server.json"))
# 照 Mac 版 install.QIANWEN_HOW:千问只认 npx 启动的工具,设置在它界面上加
QIANWEN_HOW_ZH = ("千问的设置不在文件里,要在它界面上加一次:\n"
                  "  左上切到「工作」→ 左栏「连接」→ 右上「+ 添加」→「手动填写配置」\n"
                  "  服务器名称:seeu    命令:npx -y seeu-computeruse\n"
                  "  (要先装 Node.js:https://nodejs.org;千问只认 npx 启动的工具,这个小启动包会找到本机的 SeeU)")
QIANWEN_HOW_EN = ("Qwen (千问) keeps this setting in its own window, not in a file. Add it once:\n"
                  "  switch to \"Work\" (top left) → \"Connections\" in the left bar → \"+ Add\" (top right) → \"Fill in manually\"\n"
                  "  Server name: seeu    Command: npx -y seeu-computeruse\n"
                  "  (needs Node.js: https://nodejs.org. Qwen only accepts tools started with npx; this small launcher finds the SeeU on this PC)")

QIANWEN_REMOVE_ZH = "千问的连接在它自己的界面里删:左上「工作」→ 左栏「连接」→ seeu 那张卡片的「…」→「删除」。"
QIANWEN_REMOVE_EN = ("Remove it inside Qwen (千问): \"Work\" (top left) → \"Connections\" in the left bar → "
                     "the \"…\" on the seeu card → \"Delete\".")


def write_pointer():
    """照 Mac 版 install.write_pointer:留「SeeU 装在这儿」的纸条给 npm 启动包 seeu-computeruse 找。
    接入 / 每次 MCP 服务启动都写一次;写不了就算了。"""
    try:
        from seeu.where import as_plugin
        if as_plugin():
            # 插件版不写。纸条是给千问的 npx 启动包找 git 版用的;插件版一写,千问就被改去跑插件缓存里那份
            # (换了设置文件),插件一更新旧缓存被删,千问直接启动失败
            return
    except Exception:   # noqa: BLE001
        pass
    try:
        d = {"python": _python(), "server": SERVER}
        try:
            with open(POINTER, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:   # noqa: BLE001
            old = None
        if old == d:
            return
        os.makedirs(os.path.dirname(POINTER), exist_ok=True)
        tmp = POINTER + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, POINTER)
    except Exception:   # noqa: BLE001
        pass


EN = [
    ("SeeU 接入 Claude(Windows)", "SeeU · connect Claude (Windows)"), ("SeeU 接入 Codex(Windows)", "SeeU · connect Codex (Windows)"),
    ("SeeU 移除 Codex(Windows)", "SeeU · remove from Codex (Windows)"),
    ("Claude 桌面版:", "Claude desktop: "), ("Claude Code:", "Claude Code: "), ("Codex:", "Codex: "),
    ("没有 claude 命令", "no claude command"), ("已接 ✅", "connected ✅"), ("没装", "not installed"), ("没接", "not connected"),
    ("已有一条叫 seeu 的,不是这份 SeeU 接的", "there is an entry named seeu that this copy of SeeU didn't add"),
    ("接入:python -m seeu 接入 claude|codex|cursor|trae|vscode    移除:python -m seeu 移除 claude|codex|cursor|trae|vscode",
     "Connect: python -m seeu install claude|codex|cursor|trae|vscode    Remove: python -m seeu uninstall claude|codex|cursor|trae|vscode"),
    ("① Claude 桌面版:已经接过了(", "① Claude desktop: already connected ("),
    ("① Claude 桌面版:已接上 ✅(改了 ", "① Claude desktop: connected ✅ (edited "), (",备份 ", ", backup "),
    ("   Claude 开着的话:托盘图标右键退出(要完全退出),再打开。",
     "   If Claude is open: right-click its tray icon and quit (quit completely), then open it again."),
    ("① 没找到 Claude 桌面版(%APPDATA%\\Claude 不在)。要用的话先装:", "① Claude desktop not found (no %APPDATA%\\Claude). To use it, install it first: "),
    ("② Claude Code:MCP 已接上 ✅", "② Claude Code: MCP connected ✅"), ("② Claude Code:接 MCP 失败:", "② Claude Code: connecting MCP failed: "),
    ("② 没有 claude 命令,Claude Code 这边跳过", "② No claude command, skipping Claude Code"),
    ("③ Skill 那个位置已经有别的东西,没动:", "③ Something else is already at the skill location, left alone: "),
    ("③ Skill 已装 → ", "③ Skill installed → "),
    ("④ 试连一次 ", "④ Test connection "), ("✅ 能连上,", "✅ works, "), (" 个工具", " tools"),
    ("❌ 连不上(运行 python -m seeu mcp 看报错;没装 comtypes 先 python -m pip install comtypes)",
     "❌ can't connect (run python -m seeu mcp to see the error; if comtypes is missing: python -m pip install comtypes)"),
    ("好了。新开一个对话,说一句「用 SeeU 看一下记事本」试试。不想用了:python -m seeu 移除 claude",
     "Done. Start a new chat and say \"use SeeU to look at Notepad\". To remove later: python -m seeu uninstall claude"),
    ("· Claude 桌面版:已移除 seeu(只删这一条)→ ", "· Claude desktop: seeu removed (only that entry) → "),
    ("· Claude 桌面版:设置里有一条叫 seeu 的,但不是这份 SeeU 接的,没动。真要删:打开 ",
     "· Claude desktop: there is an entry named seeu, but this copy of SeeU didn't add it; left untouched. To remove it anyway: open "),
    (",手动删掉「mcpServers」里的 seeu", " and delete seeu from \"mcpServers\" by hand"),
    ("② Claude Code:已经有一条叫 seeu 的,看不出是不是指着这份 SeeU,没动、也没记成这份接的。",
     "② Claude Code: there is already an entry named seeu and SeeU can't tell whether it points at this copy; left untouched and not recorded as ours."),
    ("   想换成这份:先运行 claude mcp remove -s user ", "   To switch to this copy: run claude mcp remove -s user "),
    (",再运行一次接入", ", then run the install again"),
    ("· Claude Code:已移除 seeu", "· Claude Code: seeu removed"), ("· Skill 已拿掉 → ", "· Skill removed → "),
    ("移除好了。Claude 开着的话退出再开。", "Removed. If Claude is open, quit and reopen it."),
    ("移除好了。Codex 开着的话退出再开。", "Removed. If Codex is open, quit and reopen it."),
    ("① 没找到 Codex(没有 codex 命令、没有 %USERPROFILE%\\.codex,也没装 ChatGPT / Codex App)。",
     "① Codex not found (no codex command, no %USERPROFILE%\\.codex, and the ChatGPT / Codex app isn't installed). "),
    ("先装:", "Install it first: "), (" ,装好再运行这条。", " , then run this again."),
    ("① 找到 Codex ✅(", "① Codex found ✅ ("), ("有 codex 命令", "codex command"), ("Codex App 装了,还没打开过", "the Codex app is installed but has never been opened"),
    ("② 已经接过了(", "② Already connected ("), (")。要重接先运行:python -m seeu 移除 codex", "). To reconnect, first run: python -m seeu uninstall codex"),
    (" 里已经有一条叫 seeu 的,不是这份 SeeU 接的,没动。", " already has an entry named seeu that this copy of SeeU didn't add; left alone."),
    ("② 写进去以后核对不对,已还原成原样,没接上。请把 ", "② The file didn't check out after writing, so it was restored and nothing was connected. Please send us "),
    (" 发给我们看看。", " so we can take a look."),
    ("② 已写进 ", "② Written to "), ("(备份 ", " (backup "), ("(文件是新建的)", " (new file)"),
    ("好了。Codex 开着的话先退出再开,说一句「用 SeeU 看一下记事本」试试。",
     "Done. If Codex is open, quit and reopen it, then say \"use SeeU to look at Notepad\"."),
    ("Codex 第一次调 SeeU 可能会问要不要允许,点允许就行。不想用了:python -m seeu 移除 codex",
     "The first time Codex calls SeeU it may ask for permission; click Allow. To remove later: python -m seeu uninstall codex"),
    ("· 设置里本来就没有 SeeU", "· SeeU wasn't in the config to begin with"),
    (" 里那条 seeu 不是这份 SeeU 接的(或者不是一整节),没动。真要删:打开这个文件,手动删掉 seeu 那几行。",
     " has a seeu entry that this copy of SeeU didn't add (or it isn't a whole section); left alone. To delete it anyway, open the file and remove the seeu lines by hand."),
    ("· MCP 已拿掉,设置文件是接入时新建的,已删掉 ✅", "· MCP removed; the config file was created when connecting, so it was deleted ✅"),
    ("· MCP 已拿掉,设置文件恢复成接入前的原样 ✅(", "· MCP removed; the config file is back exactly as it was before connecting ✅ ("),
    ("· MCP 已拿掉(只删了 seeu 那一节,别的没动)→ ", "· MCP removed (only the seeu section was deleted, nothing else touched) → "),
    ("认不出是在哪家 AI 里运行的,请写明:python -m seeu 接入 claude|codex|cursor|trae|vscode",
     "Can't tell which AI client is running this; name it: python -m seeu install claude|codex|cursor|trae|vscode"),
    ("Windows 预览版现在支持接 Claude、Codex、Cursor、Trae、VS Code:python -m seeu 接入 claude|codex|cursor|trae|vscode    移除:python -m seeu 移除 claude|codex|cursor|trae|vscode",
     "The Windows preview can connect Claude, Codex, Cursor, Trae and VS Code: python -m seeu install claude|codex|cursor|trae|vscode    Remove: python -m seeu uninstall claude|codex|cursor|trae|vscode"),
    (QIANWEN_HOW_ZH, QIANWEN_HOW_EN), (QIANWEN_REMOVE_ZH, QIANWEN_REMOVE_EN),
]


def _p(s):
    try:
        from seeu.win import lang
        s = lang.tx(s, EN)
    except Exception:   # noqa: BLE001
        pass
    print(s, flush=True)


def _python():
    """写进设置的 Python:用 python.exe(pythonw 没有标准输入输出,MCP 用不了)。"""
    exe = sys.executable
    d, b = os.path.split(exe)
    if b.lower() == "pythonw.exe" and os.path.exists(os.path.join(d, "python.exe")):
        exe = os.path.join(d, "python.exe")
    return exe


def _desktop_cfg():
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    d = os.path.join(appdata, "Claude")
    return os.path.join(d, "claude_desktop_config.json") if os.path.isdir(d) else None


def _skills_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "skills", NAME)


def _load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _backup(path, tag):
    if not os.path.exists(path):
        return None
    os.makedirs(BAK, exist_ok=True)
    b = os.path.join(BAK, f"{tag}-{time.strftime('%m%d-%H%M%S')}.json")
    shutil.copy2(path, b)
    return b


def _json_read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        txt = f.read().strip()
    return json.loads(txt) if txt else {}


def _json_write(path, d):
    """先写临时文件再替换。写不进(只读、被占用、被安全软件拦)→ 删掉临时文件、打印一句人话、返回 False;原文件不动。"""
    tmp = path + ".seeu_tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as ex:
        try:
            os.remove(tmp)
        except OSError:
            pass
        _pl(f"· 设置文件写不进去(只读、或正被别的程序占着),没动:{path}\n  {ex}",
            f"· Can't write the config (read-only, or in use by another program), left untouched: {path}\n  {ex}")
        return False


def _entry():
    return {"command": _python(), "args": [SERVER]}


def probe():
    """起一次服务,问工具列表。返回工具个数,连不上 0。"""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    try:
        r = subprocess.run([_python(), SERVER], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, timeout=60, encoding="utf-8")
        for line in r.stdout.splitlines():
            d = json.loads(line)
            if d.get("id") == 2:
                return len(d["result"]["tools"])
    except Exception:
        pass
    return 0


def status():
    st = _load()
    cfg = _desktop_cfg()
    has_desk = bool(cfg and NAME in (_json_read(cfg).get("mcpServers") or {}))
    _p(f"Claude 桌面版:{'没装' if not cfg else ('已接 ✅' if has_desk else '没接')}" + (f"  ({cfg})" if cfg else ""))
    _p(f"Claude Code:{'没有 claude 命令' if not shutil.which('claude') else ('已接 ✅' if st.get('claude_code') else '没接')}")
    if not _codex_found():
        _p("Codex:没装")
    else:
        sec = _codex_section(_read_text(_codex_cfg()))
        _p(f"Codex:{'没接' if not sec else ('已接 ✅' if sec[0] >= 0 and _mine_codex(sec[2]) else '已有一条叫 seeu 的,不是这份 SeeU 接的')}  ({_codex_cfg()})")
    for key in JSON_KEYS:
        c = _json_clients()[key]
        app, cfg = _json_app(key)
        if not app:
            _pl(f"{c['label']}:没装", f"{c['label']}: not installed")
            continue
        d = _json_read_safe(cfg)
        ent = ((d or {}).get(c["root"]) or {}).get(NAME) if isinstance((d or {}).get(c["root"]), dict) else None
        if d is None:
            _pl(f"{c['label']}:设置文件读不懂  ({cfg})", f"{c['label']}: can't parse the config  ({cfg})")
        elif not ent:
            _pl(f"{c['label']}:没接  ({cfg})", f"{c['label']}: not connected  ({cfg})")
        elif _json_mine(st.get(key), ent):
            _pl(f"{c['label']}:已接 ✅  ({cfg})", f"{c['label']}: connected ✅  ({cfg})")
        else:
            _pl(f"{c['label']}:已有一条叫 seeu 的,不是这份 SeeU 接的  ({cfg})", f"{c['label']}: has an entry named seeu that this copy didn't add  ({cfg})")
    _p("接入:python -m seeu 接入 claude|codex|cursor|trae|vscode    移除:python -m seeu 移除 claude|codex|cursor|trae|vscode")
    return 0


def install_claude():
    st = _load()
    done = False
    _p("SeeU 接入 Claude(Windows)\n")
    cfg = _desktop_cfg()
    if cfg:
        d = _json_read_safe(cfg)
        servers = d.get("mcpServers") if d is not None else None
        if d is None:
            _p(f"① Claude 桌面版:设置文件读不懂,没动:{cfg}\n   请手动在「mcpServers」里加一条 seeu")
        elif servers is not None and not isinstance(servers, dict):
            _p(f"① Claude 桌面版:设置里「mcpServers」不是一组键值,没动:{cfg}")
        elif NAME in (servers or {}) and not _json_mine(st.get("claude_desktop"), servers[NAME]):
            # 叫 seeu 但不指着这份(跟 install_json 一样,别说「接过了」)
            _p(f"① Claude 桌面版:{cfg} 里已经有一条叫 seeu 的,但不指着这份 SeeU,没动。\n"
               f"   打开这个文件,手动删掉「mcpServers」里的 seeu,再运行一次接入")
        elif NAME in (servers or {}):
            _p(f"① Claude 桌面版:已经接过了({cfg})")
            done = True
        else:
            b = _backup(cfg, "claude_desktop")
            if not isinstance(servers, dict):          # 没有这一项,或写着 null
                d["mcpServers"] = {}
            d["mcpServers"][NAME] = _entry()
            if _json_write(cfg, d):
                st["claude_desktop"] = dict(time=time.strftime("%m-%d %H:%M"), backup=b, config=cfg)
                _p(f"① Claude 桌面版:已接上 ✅(改了 {cfg}" + (f",备份 {b})" if b else ")"))
                _p("   Claude 开着的话:托盘图标右键退出(要完全退出),再打开。")
                done = True
    else:
        _p("① 没找到 Claude 桌面版(%APPDATA%\\Claude 不在)。要用的话先装:https://claude.ai/download")
    claude = shutil.which("claude")
    if claude:
        # ① 用 which 找到的完整路径当命令(npm 装的是 claude.cmd,直接写 "claude" 系统找不到、整个接入崩掉);
        # ② 这一步出错 / 卡住也接着往下走(原来崩在这,第 ① 步已经改了桌面版设置却没存记录);
        # ③「already exists」= 已经有一条叫 seeu 的:查得出指着这份才记成自己接的(以前接过的照旧算),不然不记、移除时不会去删它
        try:
            r = subprocess.run([claude, "mcp", "add", "-s", "user", NAME, "--", _python(), SERVER],
                               capture_output=True, text=True, timeout=60)
            out, rc = (r.stdout or "") + (r.stderr or ""), r.returncode
        except (subprocess.TimeoutExpired, OSError) as ex:
            out, rc = f"{type(ex).__name__}: {ex}", -1
        if rc == 0 or ("already exists" in out and (st.get("claude_code") or _claude_code_mine(claude))):
            st["claude_code"] = dict(time=time.strftime("%m-%d %H:%M"))
            _p("② Claude Code:MCP 已接上 ✅")
            done = True
        elif "already exists" in out:
            _p("② Claude Code:已经有一条叫 seeu 的,看不出是不是指着这份 SeeU,没动、也没记成这份接的。\n"
               f"   想换成这份:先运行 claude mcp remove -s user {NAME},再运行一次接入")
        else:
            _p(f"② Claude Code:接 MCP 失败:{out[-300:]}")
    else:
        _p("② 没有 claude 命令,Claude Code 这边跳过")
    sk = _skills_dir()
    if os.path.exists(sk) and not os.path.exists(os.path.join(sk, MARK)):
        _p(f"③ Skill 那个位置已经有别的东西,没动:{sk}")
    else:
        if os.path.exists(sk):
            shutil.rmtree(sk)
        shutil.copytree(SKILL, sk)
        open(os.path.join(sk, MARK), "w").close()
        st["skill"] = sk
        _p(f"③ Skill 已装 → {sk}")
    _save(st)
    n = probe()
    _p(f"④ 试连一次 {'✅ 能连上,' + str(n) + ' 个工具' if n else '❌ 连不上(运行 python -m seeu mcp 看报错;没装 comtypes 先 python -m pip install comtypes)'}")
    if done:
        _p("\n好了。新开一个对话,说一句「用 SeeU 看一下记事本」试试。不想用了:python -m seeu 移除 claude")
    return 0 if (done and n) else 1


def _claude_code_mine(claude):
    """Claude Code 里那条叫 seeu 的是不是指着这份 SeeU(问 claude mcp get,看输出里有没有这份的 mcp_server.py)。问不出来 = 不是。"""
    try:
        r = subprocess.run([claude, "mcp", "get", NAME], capture_output=True, text=True, timeout=30)
        out = ((r.stdout or "") + (r.stderr or "")).replace("\\\\", "\\").replace("/", "\\").lower()
        return os.path.normpath(SERVER).replace("/", "\\").lower() in out
    except Exception:   # noqa: BLE001
        return False


def uninstall_claude():
    st = _load()
    bad = False                       # 桌面版这步失败也把 Claude Code、Skill 照常拆完,最后返回 1
    cfg = (st.get("claude_desktop") or {}).get("config") or _desktop_cfg()
    if cfg and os.path.exists(cfg):
        d = _json_read_safe(cfg)
        servers = (d or {}).get("mcpServers")
        if d is None:
            _p(f"· Claude 桌面版:设置文件读不懂,没动:{cfg}。请手动删掉「mcpServers」里的 seeu")
            bad = True
        elif isinstance(servers, dict) and NAME in servers and not _json_mine(st.get("claude_desktop"), servers[NAME]):
            # 照 uninstall_json:叫 seeu 但不是这份接的(没有接入记录、也没指着这份),不删
            _p(f"· Claude 桌面版:设置里有一条叫 seeu 的,但不是这份 SeeU 接的,没动。真要删:打开 {cfg},手动删掉「mcpServers」里的 seeu")
        elif isinstance(servers, dict) and NAME in servers:
            _backup(cfg, "claude_desktop_before_remove")
            del servers[NAME]
            if _json_write(cfg, d):
                _p(f"· Claude 桌面版:已移除 seeu(只删这一条)→ {cfg}")
            else:
                bad = True            # 写不进:接入记录留着
    if not bad:
        st.pop("claude_desktop", None)
    claude = shutil.which("claude")   # 用找到的完整路径当命令(npm 装的是 claude.cmd)
    if st.get("claude_code") and claude:
        try:                          # 看结果、接住超时;失败照实说、记录留着
            r = subprocess.run([claude, "mcp", "remove", "-s", "user", NAME], capture_output=True, text=True, timeout=60)
            gone = r.returncode == 0 or "not found" in (r.stdout + r.stderr).lower()
        except (subprocess.TimeoutExpired, OSError):
            gone = False
        if gone:
            st.pop("claude_code", None)
            _p("· Claude Code:已移除 seeu")
        else:
            bad = True
            _p(f"· Claude Code:移除没成功,请手动运行:claude mcp remove -s user {NAME}")
    else:
        st.pop("claude_code", None)
    sk = st.pop("skill", None) or _skills_dir()
    if os.path.exists(os.path.join(sk, MARK)):
        shutil.rmtree(sk)
        _p(f"· Skill 已拿掉 → {sk}")
    _save(st)
    if bad:
        _p("其余都拆了,上面说没成功的那一条请照提示手动处理。")
        return 1
    _p("移除好了。Claude 开着的话退出再开。")
    return 0


# ---------------------------------------------------------------- Codex

def _codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def _codex_cfg():
    return os.path.join(_codex_home(), "config.toml")


def _codex_skill_dir():
    return os.path.join(_codex_home(), "skills", NAME)


def _codex_app():
    """装了 Codex App(微软商店里叫 ChatGPT,包名 OpenAI.Codex)就返回版本号。虚拟机实测:刚装完、没打开过时
    还没有 .codex 文件夹,也没有 codex 命令,只能这样认。"""
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-AppxPackage OpenAI.Codex).Version"],
                           capture_output=True, text=True, timeout=30, creationflags=0x08000000)   # 不弹黑窗
        return r.stdout.strip() or None
    except Exception:
        return None


def _codex_found():
    """有 codex 命令,或者有 .codex 文件夹,或者装了 Codex App(没打开过也算:先把设置写好,App 第一次打开就读到)。"""
    return bool(shutil.which("codex") or os.path.isdir(_codex_home()) or _codex_app())


def _read_text(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:     # newline="":原样读,Windows 换行不被改掉
            return f.read()
    except OSError:
        return ""


def _toml_str(s):
    """TOML 基本字符串:JSON 的转义写法 TOML 也认(\\\\、\\"、\\uXXXX)。"""
    return json.dumps(s, ensure_ascii=False)


_HDR = re.compile(r'^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$')
_SEEU_SEC = re.compile(r'^mcp_servers\s*\.\s*(seeu|"seeu"|\'seeu\')(\s*\..*)?$')


def _codex_section(text):
    """找 [mcp_servers.seeu](连同它的子表,如 [mcp_servers.seeu.env])。
    返回 (起始行, 结束行(不含), 这几行的原文);没有返回 None。
    另外几种写法(inline 表、[mcp_servers] 下面 seeu = {...}、顶层 mcp_servers.seeu.command = …)返回 (-1, -1, "")
    = 有,但不是一节,不敢动。"""
    lines = text.splitlines(keepends=True)
    start = end = None
    cur = ""
    for i, ln in enumerate(lines):
        m = _HDR.match(ln)
        if m:
            cur = m.group(1).replace(" ", "")
            hit = bool(_SEEU_SEC.match(cur))
            if hit and start is None:
                start = i
            elif not hit and start is not None and end is None:
                end = i
            continue
        t = ln.strip()
        if start is None and not t.startswith("#"):
            if cur == "mcp_servers" and re.match(r'^("seeu"|\'seeu\'|seeu)\s*[=.]', t):
                return (-1, -1, "")
            if cur == "" and re.match(r'^mcp_servers\s*\.\s*("seeu"|\'seeu\'|seeu)\s*[=.]', t):
                return (-1, -1, "")
            if cur == "" and re.match(r'^mcp_servers\s*=.*\bseeu\b', t):
                return (-1, -1, "")
    if start is None:
        return None
    end = len(lines) if end is None else end
    # 往回带上紧挨着的、我们自己写的那行说明
    if start > 0 and lines[start - 1].startswith(_MARK_LINE):
        start -= 1
    # 尾巴上的空行不算这一节的(留给后面那节)
    while end > start and not lines[end - 1].strip():
        end -= 1
    return (start, end, "".join(lines[start:end]))


_MARK_LINE = "# SeeU:"


def _mine_codex(sec_text):
    """这一节是不是指着这份 SeeU(设置里路径是转义过的写法)。"""
    return _toml_str(SERVER)[1:-1] in sec_text


def _codex_block():
    return (f"{_MARK_LINE}python -m seeu 移除 codex 会删掉这一节\n"
            f"[mcp_servers.{NAME}]\n"
            f"command = {_toml_str(_python())}\n"
            f"args = [{_toml_str(SERVER)}]\n"
            f"startup_timeout_sec = 60\n")


def _toml_ok(text):
    """写完核对:能用 tomllib 就真解析一遍,看 seeu 那条指着这份;没有 tomllib(3.10)就退回只看那一节在不在。"""
    try:
        import tomllib
    except ImportError:
        sec = _codex_section(text)
        return bool(sec and sec[0] >= 0 and _mine_codex(sec[2]))
    try:
        d = tomllib.loads(text)
    except Exception:
        return False
    e = (d.get("mcp_servers") or {}).get(NAME) or {}
    return e.get("command") == _python() and e.get("args") == [SERVER]


def _write_text(path, text):
    tmp = path + ".seeu_tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def install_codex():
    _p("SeeU 接入 Codex(Windows)\n")
    if not _codex_found():
        _p("① 没找到 Codex(没有 codex 命令、没有 %USERPROFILE%\\.codex,也没装 ChatGPT / Codex App)。"
           "先装:https://learn.chatgpt.com/docs/windows/windows-app ,装好再运行这条。")
        return 1
    _p(f"① 找到 Codex ✅({'有 codex 命令' if shutil.which('codex') else _codex_home() if os.path.isdir(_codex_home()) else 'Codex App 装了,还没打开过'})")
    cfg = _codex_cfg()
    st = _load()
    text = _read_text(cfg)
    sec = _codex_section(text)
    if sec:
        if sec[0] >= 0 and _mine_codex(sec[2]):
            _p(f"② 已经接过了({cfg})。要重接先运行:python -m seeu 移除 codex")
        else:
            _p(f"② {cfg} 里已经有一条叫 seeu 的,不是这份 SeeU 接的,没动。")
            return 1
    else:
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        existed = os.path.exists(cfg)
        b = _backup(cfg, "codex") if existed else None
        nl = "\r\n" if "\r\n" in text else "\n"                  # 跟着文件原来的换行写法
        sep = "" if (not text or text.endswith(nl * 2)) else (nl if text.endswith(nl) else nl * 2)
        new = text + sep + _codex_block().replace("\n", nl)
        _write_text(cfg, new)
        if not _toml_ok(_read_text(cfg)):
            if b:
                shutil.copy2(b, cfg)
            else:
                os.remove(cfg)
            _p(f"② 写进去以后核对不对,已还原成原样,没接上。请把 {cfg} 发给我们看看。")
            return 1
        st["codex"] = dict(time=time.strftime("%m-%d %H:%M"), backup=b, config=cfg, created=not existed)
        _p(f"② 已写进 {cfg} ✅" + (f"(备份 {b})" if b else "(文件是新建的)"))
    sk = _codex_skill_dir()
    if os.path.exists(sk) and not os.path.exists(os.path.join(sk, MARK)):
        _p(f"③ Skill 那个位置已经有别的东西,没动:{sk}")
    else:
        if os.path.exists(sk):
            shutil.rmtree(sk)
        shutil.copytree(SKILL, sk)
        open(os.path.join(sk, MARK), "w").close()
        st.setdefault("codex", {})["skill"] = sk
        _p(f"③ Skill 已装 → {sk}")
    _save(st)
    n = probe()
    _p(f"④ 试连一次 {'✅ 能连上,' + str(n) + ' 个工具' if n else '❌ 连不上(运行 python -m seeu mcp 看报错;没装 comtypes 先 python -m pip install comtypes)'}")
    _p("\n好了。Codex 开着的话先退出再开,说一句「用 SeeU 看一下记事本」试试。"
       "\nCodex 第一次调 SeeU 可能会问要不要允许,点允许就行。不想用了:python -m seeu 移除 codex")
    return 0 if n else 1


def uninstall_codex():
    st = _load()
    rec = st.get("codex") or {}
    cfg = rec.get("config") or _codex_cfg()
    _p("SeeU 移除 Codex(Windows)\n")
    text = _read_text(cfg)
    sec = _codex_section(text) if text else None
    if not sec:
        _p("· 设置里本来就没有 SeeU")
    elif sec[0] < 0 or not _mine_codex(sec[2]):
        _p(f"· {cfg} 里那条 seeu 不是这份 SeeU 接的(或者不是一整节),没动。真要删:打开这个文件,手动删掉 seeu 那几行。")
    else:
        lines = text.splitlines(keepends=True)
        rest = lines[:sec[0]] + lines[sec[1]:]
        while rest and not rest[-1].strip():         # 删掉我们追加时多出来的空行
            rest.pop()
        new = "".join(rest)
        if new and not new.endswith("\n"):
            new += "\r\n" if "\r\n" in text else "\n"
        b = rec.get("backup")
        if rec.get("created") and not new.strip():
            _backup(cfg, "codex_before_remove")
            os.remove(cfg)
            _p("· MCP 已拿掉,设置文件是接入时新建的,已删掉 ✅")
        else:
            _backup(cfg, "codex_before_remove")
            if b and os.path.exists(b) and _read_text(b).rstrip() == new.rstrip():
                shutil.copy2(b, cfg)                     # 跟接入前一样 → 拿备份逐字还原(连结尾换行都一样)
                _p(f"· MCP 已拿掉,设置文件恢复成接入前的原样 ✅({cfg})")
            else:
                _write_text(cfg, new)
                _p(f"· MCP 已拿掉(只删了 seeu 那一节,别的没动)→ {cfg}")
    sk = rec.get("skill") or _codex_skill_dir()
    if os.path.exists(os.path.join(sk, MARK)):
        shutil.rmtree(sk)
        _p(f"· Skill 已拿掉 → {sk}")
    st.pop("codex", None)
    _save(st)
    _p("移除好了。Codex 开着的话退出再开。")
    return 0


# ---------------------------------------------------------------- 改 mcp.json 的三家(Cursor / Trae / VS Code;照 Mac 版 install_json)
# 这三家没有命令行,接入 = 往它的 mcp.json 里加一条 seeu(别的不动)。root = 放服务的键(VS Code 叫 servers,别家 mcpServers)。
# 🔴 路径是照各家公开说明 + Mac 版对应位置写的,Windows 上还没拿真客户端验收过(见 win/README.md)。

def _env(name, default):
    return os.environ.get(name) or os.path.expanduser(default)


def _json_clients():
    home_, roaming, local = os.path.expanduser("~"), _env("APPDATA", r"~\AppData\Roaming"), _env("LOCALAPPDATA", r"~\AppData\Local")
    pf = [os.environ.get("ProgramFiles") or r"C:\Program Files", os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"]
    return {
        # variants:[(显示名, 设置文件, [认「装了」的文件夹 / 程序])];按顺序找第一个装了的
        "cursor": dict(label="Cursor", root="mcpServers", procs=("cursor.exe",), cmd="cursor", get="https://cursor.com/download",
                       variants=[("Cursor", os.path.join(home_, ".cursor", "mcp.json"),
                                  [os.path.join(home_, ".cursor"), os.path.join(roaming, "Cursor"),
                                   os.path.join(local, "Programs", "cursor", "Cursor.exe")])],
                       hint=("打开 Cursor(开着的话完全退出再开,开着时它不重读设置)。",
                             "Open Cursor (if it is open, quit it fully and reopen; it doesn't re-read the config while running).")),
        "trae": dict(label="Trae", root="mcpServers", procs=("trae cn.exe", "trae.exe"), cmd="trae",
                     get="https://www.trae.cn / https://www.trae.ai",
                     variants=[("Trae CN", os.path.join(roaming, "Trae CN", "User", "mcp.json"),
                                [os.path.join(roaming, "Trae CN"), os.path.join(local, "Programs", "Trae CN", "Trae CN.exe")]),
                               ("Trae", os.path.join(roaming, "Trae", "User", "mcp.json"),
                                [os.path.join(roaming, "Trae"), os.path.join(local, "Programs", "Trae", "Trae.exe")])],
                     hint=("Trae 开着的话退出再开。", "If Trae is open, quit and reopen it.")),
        "vscode": dict(label="VS Code", root="servers", procs=("code.exe",), cmd="code", get="https://code.visualstudio.com",
                       variants=[("Visual Studio Code", os.path.join(roaming, "Code", "User", "mcp.json"),
                                  [os.path.join(roaming, "Code"), os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe")]
                                  + [os.path.join(d, "Microsoft VS Code", "Code.exe") for d in pf])],
                       hint=("VS Code 里打开 Copilot 对话(Agent 模式)。第一次用会问「信任工作区」,每个 SeeU 工具第一次用会问要不要允许,都点允许。",
                             "In VS Code open Copilot Chat (Agent mode). The first time it asks to trust the workspace, and each SeeU tool asks "
                             "for permission on first use: allow both.")),
    }


JSON_KEYS = ("cursor", "trae", "vscode")


def _json_app(key):
    """(装了的那个的显示名, 设置文件);没装 (None, None)。"""
    c = _json_clients()[key]
    for name, cfg, marks in c["variants"]:
        if any(os.path.exists(m) for m in marks):
            return name, cfg
    if shutil.which(c["cmd"]):                       # 装在别处但命令在:用第一种的位置
        return c["variants"][0][0], c["variants"][0][1]
    return None, None


def _json_read_safe(path):
    """读 mcp.json。没有 / 空文件返回 {};读不懂(带注释、不是一组键值)返回 None。"""
    try:
        d = _json_read(path)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _json_entry(key):
    return {"type": "stdio", **_entry()} if key == "vscode" else _entry()


def _json_mine(rec, entry):
    """设置里这条叫 seeu 的是不是这份 SeeU 接的:有接入记录,或内容里指着这份的 mcp_server.py。"""
    if rec:
        return True
    try:
        return any(os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(SERVER)) for a in (entry.get("args") or []))
    except Exception:   # noqa: BLE001
        return False


def _pl(zh, en):
    """直接按语言打印(不过对照表:里面带路径,路径是数据)。"""
    from seeu.win import lang
    print(lang.L(zh, en), flush=True)


def _stop_running(procs):
    """停掉这家拉起的 SeeU 服务(设置删了它察觉不到,会一直挂着;同 Mac 版)。
    只停:命令行里指着这份 mcp_server.py 的 Python 进程,而且上级进程链上有这家的程序。问不到命令行就不停(返回 0)。"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        from seeu.win import safety as S
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + ps],
                           capture_output=True, timeout=15, creationflags=0x08000000)
        table = S._process_table()
    except Exception:   # noqa: BLE001
        return 0
    want = os.path.normcase(SERVER)
    n = 0
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        pid, _, cmd = ln.partition("\t")
        if not pid.strip().isdigit() or int(pid) == os.getpid() or want not in os.path.normcase(cmd):
            continue
        cur, seen, hit = int(pid), set(), False
        while cur and cur not in seen and cur in table:
            seen.add(cur)
            cur, name = table[cur][0], table[cur][1].lower()
            if name in procs:
                hit = True
                break
        if hit:
            try:
                subprocess.run(["taskkill", "/PID", pid.strip(), "/F"], capture_output=True, timeout=10, creationflags=0x08000000)
                n += 1
            except Exception:   # noqa: BLE001
                pass
    return n


def install_json(key):
    c = _json_clients()[key]
    lb = c["label"]
    _pl(f"SeeU 接入 {lb}(Windows)\n", f"Connecting SeeU to {lb} (Windows)\n")
    app, cfg = _json_app(key)
    if not app:
        _pl(f"① 没找到 {lb}。先装:{c['get']},装好打开一次,再运行这条。",
            f"① {lb} not found. Install it first: {c['get']}, open it once, then run this again.")
        return 1
    _pl(f"① 找到 {app} ✅", f"① Found {app} ✅")
    d = _json_read_safe(cfg)
    if d is None:
        _pl(f"② 设置文件读不懂(可能带注释),没动:{cfg}\n   请手动在「{c['root']}」里加一条 seeu:把 python -m seeu mcp 当成本机 MCP 服务",
            f"② Can't parse the config (it may contain comments), left untouched: {cfg}\n"
            f"   Add an entry named seeu under \"{c['root']}\" by hand: python -m seeu mcp as a local MCP server")
        return 1
    servers = d.get(c["root"])
    if servers is not None and not isinstance(servers, dict):
        _pl(f"② 设置文件里「{c['root']}」不是一组键值,没动:{cfg}", f"② \"{c['root']}\" in the config is not an object, left untouched: {cfg}")
        return 1
    if NAME in (servers or {}):
        if not _json_mine(None, servers[NAME]):     # 叫 seeu 但不指着这份(文件夹挪过、别人手写的)→ 别说「接过了」
            _pl(f"② {cfg} 里已经有一条叫 seeu 的,但不指着这份 SeeU,没动。\n   打开这个文件,手动删掉「{c['root']}」里的 seeu,再运行一次接入",
                f"② {cfg} already has an entry named seeu, but it doesn't point at this copy of SeeU; left untouched.\n"
                f"   Open that file, delete seeu from \"{c['root']}\" by hand, then run the install again")
            return 1
        _pl(f"已经接过了。要重接先运行:python -m seeu 移除 {key}", f"Already connected. To reconnect, first run: python -m seeu uninstall {key}")
        return 0
    rec = dict(time=time.strftime("%m-%d %H:%M"), config=cfg, created=not os.path.exists(cfg), backup=None)
    if rec["created"]:
        _pl("② 还没有设置文件,新建一个", "② No config file yet, creating one")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
    else:
        rec["backup"] = _backup(cfg, key)
        _pl(f"② 已备份设置 → {rec['backup']}", f"② Config backed up → {rec['backup']}")
    if not isinstance(d.get(c["root"]), dict):      # 没有这一项,或写着 null
        d[c["root"]] = {}
    d[c["root"]][NAME] = _json_entry(key)
    if not _json_write(cfg, d):
        return 1
    _pl(f"③ MCP 已接上 ✅ → {cfg}", f"③ MCP connected ✅ → {cfg}")
    st = _load()
    st[key] = rec
    _save(st)
    n = probe()
    _pl(f"④ 试连一次 {'✅ 能连上,' + str(n) + ' 个工具' if n else '❌ 连不上(运行 python -m seeu mcp 看报错)'}",
        f"④ Test connection {'✅ OK, ' + str(n) + ' tools' if n else '❌ failed (run python -m seeu mcp to see the error)'}")
    _pl(f"\n好了。{c['hint'][0]}\n然后说一句「用 SeeU 看一下记事本」试试。\n不想用了:python -m seeu 移除 {key}",
        f"\nDone. {c['hint'][1]}\nThen try saying \"use SeeU to look at Notepad\".\nTo remove: python -m seeu uninstall {key}")
    return 0 if n else 1


def uninstall_json(key):
    c = _json_clients()[key]
    lb = c["label"]
    st = _load()
    rec = st.get(key) or {}
    _pl(f"SeeU 移除 {lb}\n", f"Removing SeeU from {lb}\n")
    app, cfg = _json_app(key)
    cfg = rec.get("config") or cfg
    if not cfg:
        _pl(f"没装 {lb},不用移除", f"{lb} isn't installed, nothing to remove")
        return 0
    d = _json_read_safe(cfg)
    if d is None:
        _pl(f"· 设置文件读不懂,没动:{cfg}。请手动删掉「{c['root']}」里的 seeu",
            f"· Can't parse the config, left untouched: {cfg}. Remove seeu from \"{c['root']}\" by hand")
        return 1
    servers = d.get(c["root"])
    servers = servers if isinstance(servers, dict) else {}
    if NAME not in servers:
        _pl("· 设置里本来就没有 SeeU", "· SeeU wasn't in the config to begin with")
    elif not _json_mine(rec, servers[NAME]):
        _pl(f"· 设置里有一条叫 seeu 的,但不是这份 SeeU 接的(没有接入记录,也没指着 {SERVER}),没动。\n  真要删:打开 {cfg},手动删掉「{c['root']}」里的 seeu\n\n没有要移除的。",
            f"· There is an entry named seeu, but this copy of SeeU didn't add it (no install record, and it doesn't point at {SERVER}); left untouched.\n"
            f"  To remove it anyway: open {cfg} and delete seeu from \"{c['root']}\"\n\nNothing to remove.")
        return 0
    else:
        bak = _backup(cfg, key + "-before-remove")      # 移除也先备份(会整份重写)
        if bak:
            _pl(f"· 已备份设置 → {bak}", f"· Config backed up → {bak}")
        servers.pop(NAME)
        if not servers:
            d.pop(c["root"], None)
        if rec.get("created") and not d:
            os.remove(cfg)
            _pl("· MCP 已拿掉,设置文件是接入时新建的,已删掉 ✅", "· MCP removed; the config file was created by the install, so it was deleted ✅")
        else:
            if not _json_write(cfg, d):
                return 1
            _pl("· MCP 已拿掉(只删了 seeu 这一条,别的没动)✅", "· MCP removed (only the seeu entry, nothing else was touched) ✅")
    k = _stop_running(c["procs"])
    if k:
        _pl(f"· 停掉了 {lb} 拉起的 SeeU({k} 个)", f"· Stopped the SeeU server(s) started by {lb} ({k})")
    st.pop(key, None)
    _save(st)
    _pl(f"\n移除好了。{lb} 开着的话退出再开。", f"\nRemoved. If {lb} is open, quit and reopen it.")
    return 0


def _auto():
    """父进程链上认出是哪家在跑这条命令。"""
    try:
        from seeu.win import safety as S
        table = S._process_table()
    except Exception:
        return None
    cur, seen = os.getpid(), set()
    while cur and cur not in seen and cur in table:
        seen.add(cur)
        parent, name = table[cur]
        n = name.lower()
        if "codex" in n:
            return "codex"
        if n.startswith("claude"):
            return "claude"
        if n == "cursor.exe":
            return "cursor"
        if n in ("trae.exe", "trae cn.exe"):
            return "trae"
        if n == "code.exe":
            return "vscode"
        cur = parent
    return None


def main(cmd, args):
    which = (args[0] if args else "").lower()
    if which in ("千问", "qianwen", "qwen"):
        if cmd in ("接入", "install"):
            write_pointer()
            _p(QIANWEN_HOW_ZH)
        else:
            _p(QIANWEN_REMOVE_ZH)
        return 0
    if cmd in ("接入", "install"):
        write_pointer()
    if which in ("自动", "auto"):
        which = _auto() or ""
        if not which:
            _p("认不出是在哪家 AI 里运行的,请写明:python -m seeu 接入 claude|codex|cursor|trae|vscode")
            return 2
    if cmd in ("接入", "install"):
        if not args:
            return status()
        if which == "claude":
            return install_claude()
        if which == "codex":
            return install_codex()
        if which in JSON_KEYS:
            return install_json(which)
    else:
        if which == "claude":
            return uninstall_claude()
        if which == "codex":
            return uninstall_codex()
        if which in JSON_KEYS:
            return uninstall_json(which)
    _p("Windows 预览版现在支持接 Claude、Codex、Cursor、Trae、VS Code:python -m seeu 接入 claude|codex|cursor|trae|vscode    移除:python -m seeu 移除 claude|codex|cursor|trae|vscode")
    return 2
