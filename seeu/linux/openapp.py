# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 后台打开 App(照 Windows 版 win/openapp.py / Mac 版 seeu/openapp.py)。

规则跟 Mac / Windows 一样:只给自己打不开 App 的客户端用(工具清单里平时没有它;SEEU_OPEN_APP=1 强制给,测试用);
只开不关;终端 / 命令行、系统设置和管理工具、密码程序、浏览器(网页走 seeu_web_open)、AI 客户端和远程协助、虚拟机都不开;
已经开着的不动;App 打开时自己抢了前台,就把前台还给用户原来的窗口,结果里照实说。

找 App:系统的程序清单(.desktop 文件,Gio.AppInfo;名字有中英文,跟「活动」里搜到的一样),按清单启动(跟用户在「活动」里点开一样)。
"""
import os
import re
import time

NEED_OPEN = set()        # Linux 上现在没有自己打不开 App 的客户端(Claude Code / Codex / Cursor / VS Code 都能自己开)

_BLOCK = [
    (re.compile(r"(terminal|console|konsole|xterm|ptyxis|tilix|terminator|alacritty|kitty|wezterm|foot|guake|yakuake|tilda|"
                r"终端|終端|\bbash\b|\bzsh\b|\bfish\b|python|\bidle\b|node|ruby|\bperl\b|\bphp\b|\blua\b|irb|jupyter)", re.I),
     "是命令行程序,能直接运行任何命令"),
    (re.compile(r"(gnome-control-center|org\.gnome\.settings|^settings$|^设置$|^設定$|system ?settings|systemsettings|"
                r"gnome-system-monitor|system ?monitor|系统监视器|task ?manager|任务管理器|gnome-disks|^disks$|磁盘|gparted|"
                r"software|软件|synaptic|update-manager|software-properties|软件和更新|software ?&? ?updates|"
                r"firmware|固件|users?(-admin)?$|用户和组|gnome-logs|^logs$|日志|dconf|gsettings|seahorse|passwords and keys|"
                r"密码和密钥|polkit|pkexec|gufw|firewall|防火墙|extension|扩展|tweaks|优化)", re.I),
     "是系统设置或系统管理相关的界面"),
    (re.compile(r"(1password|bitwarden|keepass|enpass|lastpass|dashlane|nordpass|proton ?pass|keeper|secrets|gnome-secrets|"
                r"password ?safe|passwordsafe)", re.I),
     "是存密码的程序"),
    (re.compile(r"(anthropic|claude|openai|chatgpt|codex|cursor|windsurf|codeium|copilot|workbuddy|doubao|豆包|kimi|deepseek|"
                r"qianwen|千问|tongyi|通义|\bqwen\b|yuanbao|元宝|ollama|lm ?studio|\btrae\b|\bkiro\b|antigravity|"
                r"remmina|vinagre|gnome-connections|connections|remote ?desktop|远程|rustdesk|anydesk|teamviewer|todesk|"
                r"sunlogin|向日葵|parsec|nomachine|\bvnc|krdc|krfb)", re.I),
     "是 AI 客户端或远程协助程序"),
    (re.compile(r"(virt-manager|virtualbox|vmware|gnome-boxes|^boxes$|qemu|quickemu|distrobox|toolbox|docker|podman|"
                r"boxbuddy|wine|bottles|lutris)", re.I),
     "是虚拟机 / 容器 / 兼容层,能在里面运行任何程序"),
]
_BROWSER = re.compile(r"(firefox|chromium|chrome|brave|vivaldi|opera|epiphany|org\.gnome\.epiphany|^web$|microsoft-edge|msedge|"
                      r"librewolf|waterfox|floorp|zen-browser|tor ?browser)", re.I)


def enabled():
    """这次的 MCP 服务要不要给「打开 App」工具:SEEU_OPEN_APP=1/0 强制;否则看运行 SeeU 的客户端在不在 NEED_OPEN 里(现在是空的)。"""
    v = os.environ.get("SEEU_OPEN_APP", "").strip()
    if v in ("1", "0"):
        return v == "1"
    if not NEED_OPEN:
        return False
    try:
        from seeu.linux import safety
        return bool({n.lower() for n in safety.host_names()} & NEED_OPEN)
    except Exception:   # noqa: BLE001
        return False


def _apps():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    out = []
    for a in Gio.AppInfo.get_all():
        try:
            if not a.should_show():
                continue
            out.append(a)
        except Exception:   # noqa: BLE001
            continue
    return out


def _info(a):
    """(显示名, 程序 id, 执行文件, 分类, 是否终端里跑)"""
    did = (a.get_id() or "").removesuffix(".desktop")
    exe = os.path.basename(a.get_executable() or "")
    cats = (a.get_categories() or "") if hasattr(a, "get_categories") else ""
    term = bool(a.get_boolean("Terminal")) if hasattr(a, "get_boolean") else False
    return a.get_display_name() or a.get_name() or did, did, exe, cats, term


def find(name):
    """按名字找程序:显示名 / 程序 id / 执行文件,先全等再开头再包含(不分大小写)。返回 Gio.AppInfo 或 None。"""
    n = str(name or "").strip().lower()
    if not n:
        return None
    apps = [(a, [x.lower() for x in _info(a)[:3] if x]) for a in _apps()]
    for test in (lambda k: k == n, lambda k: k.startswith(n), lambda k: n in k):
        for a, keys in apps:
            if any(test(k) for k in keys) or any(test(k.split(".")[-1]) for k in keys):
                return a
    return None


def why_not(dn, did, exe, cats="", term=False):
    s = f"{dn} {did} {exe}"
    if term or "TerminalEmulator" in cats or "System" in cats.split(";") and "Monitor" in cats:
        return f"{dn} 是命令行程序或系统工具,SeeU 不替你打开"
    for rx, why in _BLOCK:
        if rx.search(dn) or rx.search(did) or rx.search(exe):
            return f"{dn} {why},SeeU 不替你打开"
    if "WebBrowser" in cats or _BROWSER.search(s):
        return f"{dn} 是浏览器,开网页请用 seeu_web_open(网址要过允许名单)"
    try:
        from seeu.linux import safety
        w = dict(comm=exe, exe=exe, wm_class=did, app_id=did, title=dn)
        why = safety.why_not(w)
        if why:
            return f"{dn}:{why}"
    except Exception:   # noqa: BLE001
        pass
    return None


def _keys(dn, did, exe):
    return {k.lower() for k in (dn, did, did.split(".")[-1], exe) if k}


def _matches(w, keys):
    names = {n.lower() for n in w.get("names") or []} | {(w.get("comm") or "").lower(), (w.get("app_id") or "").lower(),
                                                         (w.get("wm_class") or "").lower()}
    return bool(names & keys)


def _running(keys):
    from seeu.linux import window as W
    return next((w for w in W.list_windows() if _matches(w, keys)), None)


def open_app(app, wait_s=15):
    from seeu.linux import safety, shell, window as W
    safety.check_unlocked()
    name = str(app or "").split("「")[0].strip()
    if not name:
        return {"outcome": "failed", "reason": "没写要打开哪个 App"}
    a = find(name)
    if a is None:
        return {"outcome": "failed", "reason": f"找不到叫「{name}」的 App(「活动」里搜得到的才找得到),请用户确认 App 名"}
    dn, did, exe, cats, term = _info(a)
    w = why_not(dn, did, exe, cats, term)
    if w:
        return {"outcome": "refused", "reason": f"{w}(这一步请你自己来)", "name": dn}
    keys = _keys(dn, did, exe)
    old = _running(keys)
    if old:
        return {"outcome": "delivered", "name": dn, "note": f"{dn} 已经开着,没动它(没拉到前台)。用 seeu_see 看它的画面"}
    before = {x["id"] for x in W.list_windows()}
    try:
        f0 = shell.focus()
    except Exception:   # noqa: BLE001
        f0 = 0
    try:
        ok = a.launch([], None)
    except Exception as ex:   # noqa: BLE001
        return {"outcome": "failed", "name": dn, "reason": f"系统没打开 {dn}({ex})"}
    if not ok:
        return {"outcome": "failed", "name": dn, "reason": f"系统没打开 {dn}"}

    def give_back():
        """新开的窗口占了前台 → 还给原来的窗口(用户自己切到别处的不算)。返回这次有没有还。"""
        try:
            fg = shell.focus()
        except Exception:   # noqa: BLE001
            return False
        if not f0 or not fg or fg == f0:
            return False
        me = next((x for x in W.list_windows() if x["id"] == fg), None)
        if me is not None and (me["id"] not in before or _matches(me, keys)):
            shell.activate(f0)
            return True
        return False

    t0, win, stole = time.time(), None, False
    while time.time() - t0 < wait_s:                     # 硬上限
        time.sleep(0.25)
        stole = give_back() or stole
        win = win or next((x for x in W.list_windows() if x["id"] not in before and _matches(x, keys)), None)
        if win:
            break
    if win:
        for _ in range(4):                               # 有的程序窗口出来后一两秒才抢前台,再看几次
            time.sleep(0.4)
            stole = give_back() or stole
    note = ""
    if stole:
        try:
            back = shell.focus() == f0
        except Exception:   # noqa: BLE001
            back = False
        note = f"{dn} 打开时自己跳到了最前面," + ("已切回原来的窗口。" if back else "没能切回原来的窗口。")
    if not win:
        return {"outcome": "unverified", "name": dn, "note": note + f"{dn} 开起来了,但还没看到它的窗口。等一两秒再 seeu_see 看看"}
    return {"outcome": "delivered", "name": dn, "window": win["title"],
            "note": note + f"已在后台打开 {dn}(没拉到前台)。接下来用 seeu_see 看它的画面"}
