# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 安全底线(硬拦,写死、不留开关;跟 Mac / Windows 版同一套口径)。

不管谁下的指令(包括网页上藏的字、AI 自己的判断),这几类一律不做,抛 Refused(动作层报 refused「这一步请你自己来」):
  0. 🔴 锁屏 / 屏保时什么都不做(Linux 新加:实测 Cua Driver 锁屏时照样能后台写字、点按钮)。
  1. 危险打字内容:下载后直接运行、sudo / pkexec、删整个硬盘 / 家目录、格式化、抹盘、fork 炸弹。
  2. 终端类程序(GNOME 终端 / Console / Ptyxis、Konsole、xterm、kitty…):不看、不点、不写字。
  3. 系统权限 / 密码弹窗:管理员授权框(polkit)、钥匙环密码框、GPG 密码框、系统的授权确认框(截图、远程操作…由
     xdg-desktop-portal 弹的,AI 不能替自己点「允许」)、GNOME Shell 自己(运行框 Alt+F2、锁屏、系统菜单都在里面)。
  4. 存密码的程序(密码和密钥、KeePassXC、1Password、Bitwarden…)。
  5. 「设置」:第一版读不准它开着哪一页(GNOME 设置的窗口标题不随页面变),整个不碰(Mac 版只拦隐私 / 安全页)。
  6. 正在运行 SeeU 的程序本身(往上找父进程):防 AI 自己批准自己。
  另:密码框里不写字、不按会改内容的键。
"""
import os
import re


class Refused(Exception):
    """安全底线硬拦。调用方别换路硬做,交给用户。"""


# ---------------------------------------------------------------- 按键(跟 Mac 同一套归一)
KEY_ALIAS = {"esc": "escape", "del": "forwarddelete", "delete": "forwarddelete", "forward_delete": "forwarddelete",
             "page_up": "pageup", "page_down": "pagedown", "enter": "return", "backspace": "backspace"}
MOD_ALIAS = {"control": "ctrl", "ctl": "ctrl", "cmd": "ctrl", "command": "ctrl", "⌘": "ctrl", "⌃": "ctrl",
             "option": "alt", "opt": "alt", "⌥": "alt", "⇧": "shift", "win": "super", "meta": "super", "super": "super"}
_EDIT_KEYS = {"return", "backspace", "forwarddelete", "space"}
_NAV_KEYS = {"tab", "escape", "left", "right", "up", "down", "home", "end", "pageup", "pagedown"} | {f"f{i}" for i in range(1, 21)}


def norm_key(key):
    k = str(key).strip().lower()
    return KEY_ALIAS.get(k, k)


def norm_mods(mods=()):
    if isinstance(mods, str):
        mods = [mods]
    # 空串不算修饰键(AI 传 [""] 时别被下面「不认识的修饰键」误拦)
    return [MOD_ALIAS.get(str(m).strip().lower(), str(m).strip().lower()) for m in mods or () if str(m).strip()]


def key_enters(key, mods=()):
    """这个键会不会往输入框里放东西、改它或提交它(密码框里这些不按)。"""
    k, m = norm_key(key), set(norm_mods(mods))
    if k in _EDIT_KEYS:
        return True
    if "ctrl" in m:
        return k in ("v", "x", "z", "y") or (k == "insert" and "shift" in m)
    if k == "insert" and "shift" in m:
        return True
    if k in _NAV_KEYS:
        return False
    return True


KNOWN_MODS = {"ctrl", "alt", "shift", "super"}


def check_keys(key, mods=()):
    """原来按「修饰键集合正好等于」判,多写一个就绕过(ctrl+alt+shift+delete;ctrl+alt+fn+delete 里
    不认识的 fn 真按时被丢掉,按出去就是 Ctrl+Alt+Delete)。改成:不认识的修饰键直接拒;危险组合按「包含」判。"""
    k, m = norm_key(key), set(norm_mods(mods))
    unknown = sorted(m - KNOWN_MODS)
    if unknown:
        raise Refused(f"不认识的修饰键「{unknown[0]}」(只认 ctrl / shift / alt),SeeU 不按(这一步请你自己来)")
    if "super" in m:
        raise Refused("带 Super(Windows / ⌘)键的组合是系统快捷键,SeeU 不按(这一步请你自己来)")
    if {"ctrl", "alt"} <= m and k in ("delete", "forwarddelete", "backspace", "t", "l"):
        raise Refused("这是注销 / 锁屏 / 开终端一类的系统快捷键,SeeU 不按(这一步请你自己来)")
    if "alt" in m and k in ("f2",):
        raise Refused("Alt+F2 是「运行命令」框,SeeU 不按(这一步请你自己来)")


# ---------------------------------------------------------------- 打字内容
BLOCKED_TEXT = [
    ("下载后直接运行", r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da|k|fi)?sh\b"),
    ("下载后直接运行", r"\b(ba|z)?sh\s+(-c\s+)?[\"']?\$\(\s*(curl|wget)\b"),
    ("用管理员权限运行", r"(^|[\s;&|`(])(sudo|pkexec|doas)\s+[-a-zA-Z/.~$]"),
    ("删整个硬盘 / 家目录", r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(--no-preserve-root\s+)?(/|~/?|\$\{?HOME\}?/?|/\*|~/\*|\$\{?HOME\}?/\*|/home/?\S*)(\s|$)"),
    ("抹盘", r"\bdd\b[^\n]*\bof=/dev/"),
    ("格式化磁盘", r"\bmkfs(\.\w+)?\s+/dev/"),
    ("抹盘", r"\b(wipefs|shred)\b[^\n]*\s/dev/"),
    ("fork 炸弹", r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
]
_TEXT_RES = [(n, re.compile(p, re.I)) for n, p in BLOCKED_TEXT]


def check_text(text):
    t = str(text or "")
    for name, rx in _TEXT_RES:
        if rx.search(t):
            raise Refused(f"要打的字里有危险命令(「{name}」),SeeU 不打(这一步请你自己来)")


# ---------------------------------------------------------------- 目标程序(按 /proc/pid/comm、程序文件名、窗口类,小写比)
TERMINALS = {
    "gnome-terminal-server": "GNOME 终端", "gnome-terminal": "GNOME 终端", "kgx": "终端(Console)", "gnome-console": "终端(Console)",
    "ptyxis": "终端(Ptyxis)", "ptyxis-agent": "终端(Ptyxis)", "konsole": "Konsole", "xterm": "xterm", "uxterm": "xterm",
    "kitty": "kitty", "alacritty": "Alacritty", "wezterm-gui": "WezTerm", "wezterm": "WezTerm", "foot": "foot",
    "tilix": "Tilix", "terminator": "Terminator", "xfce4-terminal": "Xfce 终端", "lxterminal": "LXTerminal",
    "qterminal": "QTerminal", "mate-terminal": "MATE 终端", "guake": "Guake", "tilda": "Tilda", "blackbox": "Black Box",
    "cosmic-term": "COSMIC 终端", "warp": "Warp", "warp-terminal": "Warp", "ghostty": "Ghostty", "hyper": "Hyper",
    "tabby": "Tabby", "deepin-terminal": "深度终端", "terminology": "Terminology", "st": "st", "urxvt": "urxvt", "rxvt": "rxvt",
    # 复查补:名单外的终端
    "sakura": "Sakura", "roxterm": "ROXTerm", "cool-retro-term": "cool-retro-term", "contour": "Contour", "rio": "Rio",
    "yakuake": "Yakuake", "mlterm": "mlterm", "eterm": "Eterm", "aterm": "aterm", "zutty": "Zutty", "st-256color": "st",
    "extraterm": "Extraterm", "termite": "Termite", "kermit": "Kermit", "xiterm": "xiterm", "lilyterm": "LilyTerm",
}
# 名单外的终端兜底 —— 名字 / 窗口类里带 terminal、console,或以 term 结尾(xterm、roxterm、cool-retro-term…)
_TERM_RX = re.compile(r"terminal|(^|[-_. ])console($|[-_. ])|term$", re.I)
TERMINAL_CLASSES = {"org.gnome.terminal", "org.gnome.console", "org.gnome.ptyxis", "org.kde.konsole", "xterm", "kitty",
                    "alacritty", "org.wezfurlong.wezterm", "foot", "com.gexperts.tilix", "terminator", "xfce4-terminal",
                    "com.raggesilver.blackbox", "com.mitchellh.ghostty", "dev.warp.warp"}
SYSTEM_APPS = {
    "gnome-shell": "GNOME Shell 自己(运行框、锁屏、系统菜单、管理员授权框都在里面)",
    "polkit-gnome-authentication-agent-1": "管理员授权框", "polkit-kde-authentication-agent-1": "管理员授权框",
    "lxpolkit": "管理员授权框", "mate-polkit": "管理员授权框",
    "gcr-prompter": "钥匙环密码框", "gcr4-prompter": "钥匙环密码框", "pinentry-gnome3": "GPG 密码框", "pinentry-qt": "GPG 密码框",
    "pinentry-gtk-2": "GPG 密码框", "ksshaskpass": "SSH 密码框", "ssh-askpass": "SSH 密码框",
    "xdg-desktop-portal-gnome": "系统授权确认框(截图、远程操作、文件访问…)",
    "xdg-desktop-portal-gtk": "系统授权确认框", "xdg-desktop-portal-kde": "系统授权确认框",
    "gnome-control-center": "「设置」(第一版读不准它开着哪一页,整个不碰)",
    "systemsettings": "「系统设置」(第一版读不准它开着哪一页,整个不碰)",
    "gdm-session-worker": "登录界面", "gnome-initial-setup": "系统初始设置(可能要设密码、登账号)",
}
PASSWORD_APPS = {"seahorse": "密码和密钥", "keepassxc": "KeePassXC", "keepass2": "KeePass", "1password": "1Password",
                 "bitwarden": "Bitwarden", "enpass": "Enpass", "kwalletmanager5": "KDE 钱包", "kwalletmanager": "KDE 钱包",
                 "gnome-passwordsafe": "Secrets", "secrets": "Secrets", "keeper": "Keeper", "proton-pass": "Proton Pass"}
PASSWORD_CLASSES = {"org.gnome.seahorse.application", "org.keepassxc.keepassxc", "1password", "bitwarden",
                    "org.gnome.world.secrets"}
SEEU_TITLES = ("SeeU",)       # 将来 SeeU 自己的悬浮窗(第 3 段)


def _ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            s = f.read()
        return int(s[s.rfind(")") + 2:].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def _comm(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


_STOP = {"systemd", "init", "gnome-shell", "gnome-session-b", "gnome-session-binary", "gdm-wayland-ses", "gdm-session-wor",
         "sshd", "login", "bwrap"}
_HOST = []


def host_pids():
    """正在运行 SeeU 的那条父进程链(到会话管理器 / systemd 为止)。"""
    if _HOST:
        return _HOST[0]
    pids, p = set(), os.getppid()
    for _ in range(40):
        if p <= 1:
            break
        if _comm(p) in _STOP:
            break
        pids.add(p)
        p = _ppid(p)
    _HOST.append(pids)
    return pids


def why_not(win):
    """win = window.info() 的结果。不能碰返回原因,能碰返回 None。"""
    names = {n.lower() for n in [win.get("comm") or "", os.path.basename(win.get("exe") or "")] if n}
    cls = {(win.get("wm_class") or "").lower(), (win.get("app_id") or "").lower()} - {""}
    alias = {str(n).lower() for n in (win.get("names") or []) if n}      # 程序菜单里的名字、桌面文件名也比
    for n in names | cls | alias:
        if n in TERMINALS:
            return f"「{TERMINALS[n]}」是终端,往里打字等于能执行任何命令"
    if cls & TERMINAL_CLASSES:
        return "这是终端,往里打字等于能执行任何命令"
    if any(_TERM_RX.search(n.rsplit(".", 1)[-1] if "." in n and n.count(".") >= 2 else n) for n in names | cls | alias):
        return "这看起来是终端(名字里带 terminal / console / …term),往里打字等于能执行任何命令"
    for n in names:
        if n in SYSTEM_APPS:
            return f"这是{SYSTEM_APPS[n]}"
        if n in PASSWORD_APPS:
            return f"「{PASSWORD_APPS[n]}」里存的是密码"
    if cls & PASSWORD_CLASSES:
        return "这是存密码的程序"
    if any(c.startswith("org.gnome.settings") or c == "gnome-control-center" for c in cls):
        return "这是「设置」(第一版读不准它开着哪一页,整个不碰)"
    if win.get("pid") in host_pids():
        return "这是正在运行 SeeU 的程序自己(防止 AI 替自己批准)"
    return None


def check_control(e):
    """程序里嵌着的终端面板(GNOME Builder、Geany、Kate…)控件角色是 terminal,不往里打字、不按键、不点。"""
    if e is not None and (e.get("role") or "") == "terminal":
        raise Refused("这是程序里嵌着的终端,往里打字等于能执行任何命令,SeeU 不碰(这一步请你自己来)")


def check_window(win):
    why = why_not(win)
    if why:
        raise Refused(f"{why},SeeU 不碰(这一步请你自己来)")


def check_unlocked():
    """锁屏 / 屏保时一律不做。"""
    from seeu.linux import shell
    if shell.locked():
        # 刚装好小插件、还没重新登录时也走到这里(logind 明说没锁)→ 照旧不动手,但说真正的原因
        if shell.not_loaded():
            raise Refused(shell.why_missing())
        raise Refused("屏幕锁着(或屏保开着),SeeU 什么都不做;等你解锁后再说")


# ---------------------------------------------------------------- 菜单(照 Mac safety.check_menu)
# Mac 那份 + Linux 多两样:注销 / 挂起 / 关机这类会话菜单;「运行 / 执行」(FeatherPad 这类编辑器的「Run」直接把文件当程序跑)
BLOCKED_MENU = re.compile(r"清[空倒]废纸篓|[清倒]空?垃圾桶|清空回收站|立即[删刪]除|永久删除|退出登录|注销|登出|锁定屏幕|鎖定螢幕|锁屏|关机|關機|"
                          r"挂起|休眠|强制退出|強制結束|\b(Empty (the )?(Trash|Bin)|Delete (Immediately|Permanently)|"
                          r"Log ?Out|Lock Screen|Shut ?Down|Power Off|Suspend|Hibernate|Force Quit)\b", re.I)
# 「重启」类只认整个名字(系统菜单里的「重新启动…」「Restart」「Restart Now」「重启」),
# 「Restart Kernel」「Restart Language Server」「重启服务」这类程序自己的按钮不算;英文词加词边界(「Design Outline」里的 sign out 不算)
BLOCKED_RESTART = re.compile(r"^\s*(重新启动|重新開機|重启|Restart|Reboot)(\s*(Now|Computer|电脑|计算机|系统))?\s*(\(&?[A-Za-z]\))?\s*(\.{3}|…)?\s*$|"
                             r"\bUpdate and restart\b|更新并重启", re.I)
RUN_MENU = re.compile(r"^\s*(run|execute|运行|執行|执行)\b", re.I)


def check_menu(path, run=True):
    """run=False:只查危险词、不查「运行」(列表项里叫 run.sh 的文件会被误伤)。"""
    for p in path:
        t = str(p)
        if BLOCKED_MENU.search(t) or BLOCKED_RESTART.search(t):
            raise Refused(f"菜单「{p}」是危险操作,SeeU 不点(这一步请你自己来)")
        if run and RUN_MENU.search(t):
            raise Refused(f"菜单「{p}」会把文件当程序运行,SeeU 不点(这一步请你自己来)")

