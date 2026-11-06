"""一键接入 / 移除 SeeU(MCP + Skill)。10-30 第一版,支持 Codex、Claude(Claude Code 和桌面版 Code 页共用一份设置);
11-01 加 Cursor、Trae、VS Code(Copilot):这三家没有命令,直接改它们的 mcp.json(只加/删 seeu 这一条,别的不动)。

    python3 -m seeu 接入                 # 看哪家已接
    python3 -m seeu 接入 自动            # 认出是哪家 AI 在运行这条命令就接哪家(给 AI 自己装用)
    python3 -m seeu 接入 codex
    python3 -m seeu 接入 claude [--本项目]   # 默认所有项目;--本项目 只给当前文件夹
    python3 -m seeu 接入 cursor|trae|vscode
    python3 -m seeu 移除 codex|claude|cursor|trae|vscode

做的事:找到那家的命令 → 备份设置 → 用那家自带的命令接 MCP → 装 Skill(没装过才装)→ 试连 → 查授权、说清授给谁。
记录放 ~/.seeu/seeu_接入.json,备份放 ~/.seeu/seeu_接入备份/。
🔴 `codex mcp add/remove` 会重写整份 config.toml(打乱顺序、丢空的 args = [],10-30 实测),所以移除时设置没被别人改过就整份拿备份恢复。
"""
import hashlib
import re
import json
import os
import shutil
import subprocess
import sys
import time
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "mcp_server.py")
SKILL = os.path.join(HERE, "skill")
STATE = home("seeu_接入.json")
BAK = home("seeu_接入备份")
NAME = "seeu"

CLIENTS = {
    "codex": dict(label="Codex", cmd="codex", app="ChatGPT", config="~/.codex/config.toml", skills="~/.codex/skills",
                  get="https://developers.openai.com/codex(装好后终端里能运行 codex)"),
    "claude": dict(label="Claude", cmd="claude", app="Claude", config="~/.claude.json", skills="~/.claude/skills",
                   get="https://claude.com/claude-code(装好后终端里能运行 claude)"),
}
# 11-01 实测的三家:没有命令行,接入 = 往 mcp.json 里加一条。root = 放服务的键(VS Code 叫 servers,别家 mcpServers)。
# apps = 认 App 用的 .app 名(按顺序找第一个装了的);config 跟着 App 走。授权对象 = 系统设置里显示的名字。
JSON_CLIENTS = {
    "cursor": dict(label="Cursor", apps={"Cursor": "~/.cursor/mcp.json"}, root="mcpServers",
                   get="https://cursor.com/download",
                   hint="打开 Cursor(开着的话 ⌘Q 退出再开,开着时它不重读设置)。"),
    "trae": dict(label="Trae", apps={"Trae CN": "~/Library/Application Support/Trae CN/User/mcp.json",
                                     "Trae": "~/Library/Application Support/Trae/User/mcp.json"}, root="mcpServers",
                 get="https://www.trae.cn(国内版)或 https://www.trae.ai(国际版)",
                 hint="Trae 开着也会自己读到,几秒内连上。(国际版 Trae 没实测过)"),
    "vscode": dict(label="VS Code", apps={"Visual Studio Code": "~/Library/Application Support/Code/User/mcp.json"},
                   root="servers", get="https://code.visualstudio.com(Copilot 已内置,登录 GitHub 就能用)",
                   hint="VS Code 里 ⌃⌘I 打开 Copilot 对话(Agent 模式)。第一次用会问「信任工作区」,"
                        "每个 SeeU 工具第一次用会问「Allow tool from seeu?」,都点允许。"),
}
ALL = list(CLIENTS) + list(JSON_CLIENTS)
# 父进程里出现这些 App 名 = 正在这家里跑
HOST_APPS = {"Claude": "claude", "ChatGPT": "codex", "Codex": "codex", "Cursor": "cursor", "Trae CN": "trae",
             "Trae": "trae", "Visual Studio Code": "vscode"}


def _python():
    """写进设置的 Python:系统那个是 /usr/bin/python3 转到 Xcode / 命令行工具里的真身,真身路径升级就变 → 写入口那个(10-30 实测)。"""
    exe = sys.executable
    if exe.startswith(("/Applications/Xcode", "/Library/Developer/CommandLineTools")) and os.path.exists("/usr/bin/python3"):
        return "/usr/bin/python3"
    return exe


def _p(s):
    print(s, flush=True)


def _toml_norm(path, drop=None):
    """粗略把 toml 拆成 {(节, 键): 值},不管顺序;空 args、120 / 120.0 这类写法差别抹平。drop = 不比较的节(如 SeeU 自己那节)。
    10-31 Codex App 实测:接入后 App 会把整份设置重排一遍,按逐字比就误判成「用户改过」,不敢整份还原。"""
    out, sec = {}, ""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return None
    for ln in lines:
        t = ln.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("[") and t.endswith("]"):
            sec = t.strip("[]").strip()
            continue
        if drop and (sec == drop or sec.startswith(drop + ".")):
            continue
        if "=" not in t:
            return None                      # 多行数组之类看不懂 → 放弃,按老办法
        k, v = (x.strip() for x in t.split("=", 1))
        if k == "args" and v == "[]":
            continue
        if re.fullmatch(r"-?\d+\.0", v):
            v = v[:-2]
        out[(sec, k)] = v
    return out


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _run(args, timeout=60, cwd=None):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr).strip()


def host_chain():
    """父进程链上所有 .app 的名字(由近到远)。"""
    names, pid = [], os.getppid()
    for _ in range(20):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True,
                                 timeout=3).stdout.strip()
        except Exception:
            break
        if not out:
            break
        ppid, comm = out.split(None, 1)
        if ".app/" in comm:
            n = os.path.basename(comm.split(".app/")[0])
            if n not in names:
                names.append(n)
        if ppid in ("0", "1"):
            break
        pid = int(ppid)
    return names


def current_client():
    for n in host_chain():
        if n in HOST_APPS:
            return HOST_APPS[n]
    return None


# ---------------------------------------------------------------- 查看

def _codex_has():
    code, out = _run(["codex", "mcp", "get", NAME], timeout=30)
    return code == 0


def _claude_has(cwd=None):
    code, out = _run(["claude", "mcp", "get", NAME], timeout=60, cwd=cwd)
    return code == 0


def status():
    st = _load()
    _p("SeeU 接入情况(MCP + Skill):")
    for key, c in CLIENTS.items():
        if not shutil.which(c["cmd"]):
            _p(f"  {c['label']:<8} —  没装 {c['cmd']} 命令")
            continue
        rec = st.get(key)
        has = _codex_has() if key == "codex" else _claude_has()
        if rec:
            where = "只给 " + rec["cwd"] if rec.get("scope") == "local" else "所有项目"
            _p(f"  {c['label']:<8} ✅ 已接({rec['time']},{where})" if key == "claude" else
               f"  {c['label']:<8} ✅ 已接({rec['time']})")
        elif has:
            _p(f"  {c['label']:<8} ✅ 已接(不是这条命令接的)")
        else:
            _p(f"  {c['label']:<8} —  没接")
    for key, c in JSON_CLIENTS.items():
        app, cfg = _json_app(key)
        if not app:
            _p(f"  {c['label']:<8} —  没装")
            continue
        has = NAME in (_json_read(cfg) or {}).get(c["root"], {})
        rec = st.get(key)
        _p(f"  {c['label']:<8} ✅ 已接({rec['time']})" if rec and has else
           f"  {c['label']:<8} ✅ 已接(不是这条命令接的)" if has else f"  {c['label']:<8} —  没接")
    cur = current_client()
    if cur:
        _p(f"\n现在是在 {_label(cur)} 里运行。接这家:python3 -m seeu 接入 {cur}")
    else:
        _p(f"\n接入:python3 -m seeu 接入 {'|'.join(ALL)}   移除:python3 -m seeu 移除 {'|'.join(ALL)}")
    return 0


# ---------------------------------------------------------------- 试连 + 授权

def probe():
    """自己当客户端连一次服务:初始化 + 列工具。返回工具个数,连不上返回 None。"""
    try:
        p = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, cwd="/")
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "seeu-install"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        out, _ = p.communicate("\n".join(json.dumps(m) for m in msgs) + "\n", timeout=20)
        for line in out.splitlines():
            r = json.loads(line)
            if r.get("id") == 2:
                return len(r["result"]["tools"])
    except Exception:
        return None
    return None


def _auth_hint(key):
    """查授权;说清在那家 App 里用要授给谁(授权跟着启动的程序走,不跟 Python)。"""
    from seeu import doctor
    who = doctor.host_app() or "运行这条命令的程序"
    rows = {r["name"]: r for r in doctor.check()}
    need = [n for n in ("辅助功能", "屏幕录制") if n in rows]
    miss = [n for n in need if rows[n]["ok"] != doctor.OK]
    app = CLIENTS[key]["app"]
    if miss:
        _p(f"   ❌ {who} 缺:{'、'.join(miss)}(运行 python3 -m seeu 检查 看怎么开)")
    else:
        _p(f"   ✅ {who} 的辅助功能、屏幕录制都开了")
    # 10-31 实测:授权跟着系统认的「负责进程」走,每种用法各不相同(见 接入说明-AI客户端.md)
    if key == "claude":
        _p("   ⚠️ 在别处用时授权给的不是同一个:Claude 客户端 Code 页 →「claude」(客户端自带的那个,小写);"
           "聊天页 →「SeeU」(SeeU 小程序,首次会自己出现在列表里);终端里用 claude 命令 → 那个终端")
    elif who != app:
        _p(f"   ⚠️ 在 {app} 里用时,要给「{app}」也开这两项:系统设置 → 隐私与安全性 → 辅助功能 / 屏幕录制 → 打开 {app}")
        _p("      (在终端里用 codex 命令的话,授权给的是那个终端)")


# ---------------------------------------------------------------- Skill

def _skill_install(key):
    """装 Skill:目标没有才建软链接;已有就不动(可能是用户自己的)。返回 True = 这次装的。"""
    d = os.path.expanduser(os.path.join(CLIENTS[key]["skills"], NAME))
    if os.path.lexists(d):
        same = os.path.islink(d) and os.path.realpath(d) == os.path.realpath(SKILL)
        _p(f"④ Skill 已经在了 → {d}{'' if same else '(不是 SeeU 这份,没动)'}")
        return False
    os.makedirs(os.path.dirname(d), exist_ok=True)
    os.symlink(SKILL, d)
    _p(f"④ Skill 已装 → {d}")
    return True


def _skill_remove(key, rec):
    d = os.path.expanduser(os.path.join(CLIENTS[key]["skills"], NAME))
    if rec.get("skill") and os.path.islink(d) and os.path.realpath(d) == os.path.realpath(SKILL):
        os.unlink(d)
        _p(f"· Skill 已拿掉 → {d}")
    elif os.path.lexists(d):
        _p(f"· Skill 不是这条命令装的,留着 → {d}")


# ---------------------------------------------------------------- 接入

def install(key, local=False):
    c = CLIENTS[key]
    _p(f"SeeU 接入 {c['label']}\n")
    exe = shutil.which(c["cmd"])
    if not exe:
        _p(f"① 没找到 {c['cmd']} 命令。先装 {c['label']}:{c['get']},装好再运行这条。")
        return 1
    _p(f"① 找到 {c['cmd']} 命令 ✅")
    st = _load()
    if st.get(key) or (_codex_has() if key == "codex" else _claude_has(os.getcwd() if local else None)):
        _p(f"已经接过了。要重接先运行:python3 -m seeu 移除 {key}")
        return 0
    cfg = os.path.expanduser(c["config"])
    os.makedirs(BAK, exist_ok=True)
    bak = os.path.join(BAK, f"{key}-{time.strftime('%m%d-%H%M%S')}{os.path.splitext(cfg)[1]}")
    if os.path.exists(cfg):
        shutil.copy2(cfg, bak)
        _p(f"② 已备份设置 → {bak}")
    else:
        bak = None
        _p("② 还没有设置文件,不用备份")
    rec = dict(time=time.strftime("%m-%d %H:%M"), backup=bak)
    if key == "codex":
        code, out = _run(["codex", "mcp", "add", NAME, "--", _python(), SERVER])
        rec["after_sha"] = _sha(cfg)
    else:
        scope = "local" if local else "user"
        rec.update(scope=scope, cwd=os.getcwd() if local else None)
        code, out = _run(["claude", "mcp", "add", "-s", scope, NAME, "--", _python(), SERVER])
    if code != 0:
        _p(f"③ 接 MCP 失败:{out[-300:]}")
        return 1
    _p("③ MCP 已接上 ✅" + ("(只给 " + os.getcwd() + ")" if local else ""))
    rec["skill"] = _skill_install(key)
    st[key] = rec
    _save(st)
    n = probe()
    _p(f"⑤ 试连一次 {'✅ 能连上,' + str(n) + ' 个工具' if n else '❌ 连不上(运行 python3 -m seeu mcp 看报错)'}")
    _p("⑥ 检查授权:")
    _auth_hint(key)
    _p(f"\n好了。{'新开一个会话,' if key == 'claude' else '打开 Codex '}说一句「用 SeeU 看一下访达」试试。")
    if key == "codex":
        _p("注意:Codex 每次调 SeeU 会弹框让你批准,点允许就行。")
    _p(f"不想用了:python3 -m seeu 移除 {key}")
    return 0 if n else 1


# ---------------------------------------------------------------- 改 mcp.json 的三家(Cursor / Trae / VS Code)

def _label(key):
    return (CLIENTS.get(key) or JSON_CLIENTS[key])["label"]


def _json_app(key):
    """(装了的 .app 名, 设置文件路径);没装 (None, None)。"""
    for name, cfg in JSON_CLIENTS[key]["apps"].items():
        for d in ("/Applications", os.path.expanduser("~/Applications")):
            if os.path.isdir(os.path.join(d, name + ".app")):
                return name, os.path.expanduser(cfg)
    return None, None


def _json_read(path):
    """读 mcp.json。没有文件返回 {};读不懂(比如带注释)返回 None。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        return json.loads(txt) if txt.strip() else {}
    except (OSError, ValueError):
        return None


def _json_write(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _entry(key):
    e = {"command": _python(), "args": [SERVER]}
    return {"type": "stdio", **e} if key == "vscode" else e


def _stop_running(app):
    """停掉这家 App 拉起的 SeeU。11-01 实测:三家都察觉不到设置被删,拉起的 SeeU 一直挂着,要停掉才算移除干净。
    认法:命令行里有 mcp_server.py 的进程,系统记的「负责进程」在这个 .app 里(跟授权同一套)。"""
    try:
        import ctypes
        f = ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
        f.restype, f.argtypes = ctypes.c_int, [ctypes.c_int]
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return 0
    n = 0
    for ln in out.splitlines():
        pid, _, cmd = ln.strip().partition(" ")
        if SERVER not in cmd or "disclaimer" in cmd or int(pid) == os.getpid():
            continue
        r = f(int(pid))
        path = subprocess.run(["ps", "-o", "comm=", "-p", str(r)], capture_output=True, text=True, timeout=3).stdout
        if f"/{app}.app/" in path:
            try:
                os.kill(int(pid), 15)
                n += 1
            except OSError:
                pass
    return n


def install_json(key):
    c = JSON_CLIENTS[key]
    _p(f"SeeU 接入 {c['label']}\n")
    app, cfg = _json_app(key)
    if not app:
        _p(f"① 没找到 {c['label']}。先装:{c['get']},装好再运行这条。")
        return 1
    _p(f"① 找到 {app} ✅")
    d = _json_read(cfg)
    if d is None:
        _p(f"② 设置文件读不懂(可能带注释):{cfg}\n   请手动在「{c['root']}」里加一条 seeu,写法 : 把 python3 -m seeu mcp 当成本机 MCP 服务")
        return 1
    st = _load()
    if NAME in d.get(c["root"], {}):
        _p(f"已经接过了。要重接先运行:python3 -m seeu 移除 {key}")
        return 0
    rec = dict(time=time.strftime("%m-%d %H:%M"), config=cfg, created=not os.path.exists(cfg), backup=None)
    if rec["created"]:
        _p("② 还没有设置文件,新建一个")
    else:
        os.makedirs(BAK, exist_ok=True)
        rec["backup"] = os.path.join(BAK, f"{key}-{time.strftime('%m%d-%H%M%S')}.json")
        shutil.copy2(cfg, rec["backup"])
        _p(f"② 已备份设置 → {rec['backup']}")
    d.setdefault(c["root"], {})[NAME] = _entry(key)
    _json_write(cfg, d)
    _p(f"③ MCP 已接上 ✅ → {cfg}")
    st[key] = rec
    _save(st)
    n = probe()
    _p(f"④ 试连一次 {'✅ 能连上,' + str(n) + ' 个工具' if n else '❌ 连不上(运行 python3 -m seeu mcp 看报错)'}")
    _p(f"⑤ 授权:在 {c['label']} 里用时,系统把授权算在「{app}」头上(11-01 实测)。"
       f"\n   系统设置 → 隐私与安全性 → 辅助功能、屏幕与系统录音 → 都打开「{app}」,开完 ⌘Q 重开 {c['label']}。"
       f"\n   也可以先不开:在 {c['label']} 里让它调一次 seeu_check,缺什么它会照原话告诉你。")
    _p(f"\n好了。{c['hint']}\n然后说一句「用 SeeU 看一下访达」试试。")
    _p(f"不想用了:python3 -m seeu 移除 {key}")
    return 0 if n else 1


def _mine(rec, text):
    """设置里这条叫 seeu 的是不是这份 SeeU 接的:有接入记录,或内容里指着这份的 mcp_server.py。
    11-06 体检 C4:原来没有接入记录也照删,可能删掉用户手配的、或另一份 SeeU 接的那条。"""
    return bool(rec) or SERVER in str(text)


def uninstall_json(key):
    c = JSON_CLIENTS[key]
    st = _load()
    rec = st.get(key) or {}
    _p(f"SeeU 移除 {c['label']}\n")
    app, cfg = _json_app(key)
    cfg = rec.get("config") or cfg
    if not cfg:
        _p(f"没装 {c['label']},不用移除")
        return 0
    d = _json_read(cfg)
    if d is None:
        _p(f"· 设置文件读不懂,没动:{cfg}。请手动删掉「{c['root']}」里的 seeu")
        return 1
    servers = d.get(c["root"], {})
    if NAME not in servers:
        _p("· 设置里本来就没有 SeeU")
    elif not _mine(rec, json.dumps(servers[NAME], ensure_ascii=False)):
        _p(f"· 设置里有一条叫 seeu 的,但不是这份 SeeU 接的(没有接入记录,也没指着 {SERVER}),没动。"
           f"\n  真要删:打开 {cfg},手动删掉「{c['root']}」里的 seeu")
        _p("\n没有要移除的。")
        return 0
    else:
        servers.pop(NAME)
        if not servers:
            d.pop(c["root"], None)
        if rec.get("created") and not d:
            os.remove(cfg)
            _p("· MCP 已拿掉,设置文件是接入时新建的,已删掉 ✅")
        elif rec.get("backup") and _json_read(rec["backup"]) == d:
            shutil.copy2(rec["backup"], cfg)
            _p("· MCP 已拿掉,设置文件恢复成接入前的原样 ✅")
        else:
            _json_write(cfg, d)
            _p("· MCP 已拿掉(接入后设置里还加了别的,只删了 seeu 这一条)")
    k = _stop_running(app or c["label"])
    _p(f"· 停掉了 {c['label']} 拉起的 SeeU({k} 个)。{c['label']} 察觉不到设置被删,不停它会一直挂着" if k else
       f"· {c['label']} 没在跑 SeeU")
    st.pop(key, None)
    _save(st)
    _p("\n移除完了。")
    return 0


# ---------------------------------------------------------------- 移除

def uninstall(key):
    c = CLIENTS[key]
    st = _load()
    rec = st.get(key) or {}
    _p(f"SeeU 移除 {c['label']}\n")
    if not shutil.which(c["cmd"]):
        _p(f"没找到 {c['cmd']} 命令,不用移除")
        return 0
    cfg = os.path.expanduser(c["config"])
    if not rec:                             # 11-06 体检 C4:没有接入记录 → 先看那条是不是指着这份 SeeU,不是就不删
        try:
            code, out = _run([c["cmd"], "mcp", "get", NAME], timeout=60)
        except Exception as ex:             # 查不出来(超时等):没有记录又看不清是谁的,就不删
            _p(f"· 查不出设置里那条 seeu 是谁接的({type(ex).__name__}),没动。稍后再试,或手动:{c['cmd']} mcp remove {NAME}")
            return 1
        # 只认「没有这条服务」的说法;「命令 / 文件找不到」这类不算(那是命令本身出错,照样不删)
        gone = code != 0 and re.search(r"no mcp server|no (such )?server|seeu[^\n]*not found|not found[^\n]*seeu", out, re.I)
        if code != 0 and not gone:          # 命令本身出错(老版本没有 get、报别的错):同样看不清是谁的,不删
            _p(f"· 查不出设置里有没有 seeu、是谁接的({out[-200:] or '命令出错'}),没动。手动:{c['cmd']} mcp remove {NAME}")
            return 1
        if code == 0 and not _mine(rec, out):
            _p(f"· 设置里有一条叫 seeu 的,但不是这份 SeeU 接的(没有接入记录,也没指着 {SERVER}),没动。"
               f"\n  真要删:{c['cmd']} mcp remove {NAME}")
            _skill_remove(key, rec)
            _p("\n没有要移除的。")
            return 0
    if key == "codex":
        same = rec.get("backup") and rec.get("after_sha") and _sha(cfg) == rec["after_sha"]
        if not same and rec.get("backup"):
            a, b = _toml_norm(cfg, "mcp_servers." + NAME), _toml_norm(rec["backup"])
            same = a is not None and a == b      # 只是被重排过,内容跟接入前一样
        if same:
            shutil.copy2(rec["backup"], cfg)
            ok = _sha(cfg) == _sha(rec["backup"])
            _p("· MCP 已拿掉,设置文件恢复成接入前的原样" + (" ✅(跟备份逐字一致)" if ok else " ❌ 跟备份对不上"))
        else:
            code, out = _run(["codex", "mcp", "remove", NAME])
            if code != 0 and "not found" not in out.lower():
                _p(f"· 拿掉 MCP 失败:{out[-300:]}")
                return 1
            _p("· MCP 已拿掉" + ("。接入后你改过别的设置,所以没整份恢复;顺序可能被打乱,内容没变" if rec else ""))
    else:
        scopes = [rec["scope"]] if rec.get("scope") else ["user", "local"]
        done = False
        for sc in scopes:
            code, out = _run(["claude", "mcp", "remove", "-s", sc, NAME], cwd=rec.get("cwd") or None)
            done = done or code == 0
        _p("· MCP 已拿掉" if done else "· 设置里本来就没有 SeeU")
    _skill_remove(key, rec)
    st.pop(key, None)
    _save(st)
    _p("\n移除完了。")
    return 0


def main(cmd, args):
    names = [a for a in args if not a.startswith("-")]
    local = any(a in ("--本项目", "--local", "--project") for a in args)
    if cmd in ("移除", "uninstall", "remove"):
        if not names or names[0] not in ALL:
            _p(f"要说移除哪家:python3 -m seeu 移除 {'|'.join(ALL)}")
            return 2
        return uninstall_json(names[0]) if names[0] in JSON_CLIENTS else uninstall(names[0])
    if not names:
        return status()
    if names[0] in ("自动", "auto"):      # 给 AI 自己装用:认出是哪家在运行这条命令,就接哪家
        cur = current_client()
        if not cur:
            _p(f"认不出是在哪家 AI 里运行的,请写明:python3 -m seeu 接入 {'|'.join(ALL)}")
            return 2
        return install_json(cur) if cur in JSON_CLIENTS else install(cur, local)
    if names[0] not in ALL:
        _p(f"不认识「{names[0]}」,现在支持:{'、'.join(ALL)}")
        return 2
    return install_json(names[0]) if names[0] in JSON_CLIENTS else install(names[0], local)
