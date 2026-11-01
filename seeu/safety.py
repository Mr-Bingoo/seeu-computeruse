# -*- coding: utf-8 -*-
"""SeeU 安全底线:硬拦(C-0.9,10-25 用户定;参照 Codex、Cua/Hermes 的公开说明)。

不管谁下的指令(包括网页上藏的字、AI 自己的判断),这几类一律不做,抛 Refused(= ax.AXRefused,SeeU 会报 refused「这一步请你自己来」):
  1. 危险快捷键:清空废纸篓、不进废纸篓直接删除、锁屏、注销、强制退出。
  2. 危险打字内容:下载后直接运行、sudo、删整个硬盘/家目录、抹盘、fork 炸弹。只拦明显危险的,普通 rm 不拦。
  3. 终端类 App(终端、iTerm2、Warp、Ghostty、kitty、Alacritty、WezTerm):不点、不打字、不按键。
  4. 系统权限 / 密码弹窗(「想要控制」授权框、管理员密码框、互联网 App 打开确认、辅助功能授权提示、指纹确认)
     和系统设置里的隐私与安全性 / 密码页面:不点、不打字。
  4b. 存密码的 App(钥匙串访问、密码 App、1Password 等,10-30 加):不点、不打字。
  5. 正在运行 SeeU 的程序本身(往上找父进程)和能调 SeeU 的 AI 桌面 App(Claude、ChatGPT/Codex App,10-30 加后者):
     不点、不打字(防 AI 自己批准自己)。Codex 命令行跑在终端里,第 3 条已拦。
  6. SeeU 自己的悬浮窗 / 悬浮标 / 多任务岛(10-30 加):借真鼠标点之前查那个位置最上层,是它们(而且没在让路)就不点。
     10-30 实测:不让路时真鼠标点得中按钮栏,能把 I See 点开 = AI 自己给自己放权。后台点击按名字找不到它们(只认普通窗口),不用拦。
  另:菜单里的「清空废纸篓 / 立即删除 / 退出登录 / 锁定屏幕 / 关机 / 重新启动」也拦(跟快捷键同一件事)。
🔴 写死、不留开关(用户定:开关一留,AI 就可能被网页上的字骗去打开)。
接在:bgclick._prepare / click、bgkey.press / type_unicode / type_physical、ax.press / type_text / set_text / menu、
act._ladder(借真鼠标那条路也在里面)、web.type。直接调底层的程序(镜像、模拟器自动化)碰不到这几条。
第 4 条的弹窗进程名只按公开资料写,除「想要控制」那个外都没实测(SeeU-相关要点 10-25 节)。
"""
import os
import re
import subprocess

from seeu.ax import AXRefused


class Refused(AXRefused):
    """安全底线硬拦。调用方别换路硬做,交给用户。"""


# ---------------------------------------------------------------- 1. 快捷键
_K = lambda key, *mods: (key, frozenset(mods))
BLOCKED_KEYS = {
    _K("delete", "cmd", "shift"): "清空废纸篓",
    _K("delete", "cmd", "shift", "alt"): "清空废纸篓(不确认)",
    _K("delete", "cmd", "alt"): "不进废纸篓直接删除",
    _K("q", "cmd", "ctrl"): "锁屏",
    _K("q", "cmd", "shift"): "注销",
    _K("q", "cmd", "shift", "alt"): "注销(不确认)",
    _K("escape", "cmd", "alt"): "强制退出",
}


def check_keys(key, mods=()):
    hit = BLOCKED_KEYS.get((str(key).lower(), frozenset(m.lower() for m in mods)))
    if hit:
        raise Refused(f"「{hit}」是危险快捷键,SeeU 不按(这一步请你自己来)")


# ---------------------------------------------------------------- 2. 打字内容
BLOCKED_TEXT = [
    ("下载后直接运行", r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da|k|fi)?sh\b"),
    ("下载后直接运行", r"\b(ba|z)?sh\s+(-c\s+)?[\"']?\$\(\s*(curl|wget)\b"),
    ("用管理员权限运行(sudo)", r"(^|[\s;&|`(])sudo\s+[-a-zA-Z/.~$]"),
    ("删整个硬盘 / 家目录", r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(--no-preserve-root\s+)?(/|~|\$HOME|/\*|~/\*|/Users/?\S*)(\s|$)"),
    ("抹盘", r"\bdiskutil\s+(erase|zero|secureErase|partitionDisk|reformat)"),
    ("抹盘", r"\bdd\b[^\n]*\bof=/dev/"),
    ("格式化磁盘", r"\bmkfs(\.\w+)?\s+/dev/"),
    ("fork 炸弹", r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
]
_TEXT_RES = [(n, re.compile(p, re.I)) for n, p in BLOCKED_TEXT]


def check_text(text):
    t = str(text or "")
    for name, rx in _TEXT_RES:
        if rx.search(t):
            raise Refused(f"要打的字里有危险命令(「{name}」),SeeU 不打(这一步请你自己来)")


# ---------------------------------------------------------------- 3~5. 目标程序
TERMINALS = {
    "Terminal": "com.apple.Terminal", "iTerm2": "com.googlecode.iterm2", "Warp": "dev.warp.Warp-Stable",
    "Ghostty": "com.mitchellh.ghostty", "kitty": "net.kovidgoyal.kitty", "Alacritty": "org.alacritty",
    "WezTerm": "com.github.wez.wezterm",
}
# 系统权限 / 密码弹窗(进程名;只有 UserNotificationCenter 那类「想要控制」10-25 真见过,其余按公开资料)
SYSTEM_PROMPTS = {
    "UserNotificationCenter": "系统授权弹窗",
    "SecurityAgent": "管理员密码框",
    "CoreServicesUIAgent": "「来自互联网的 App 要打开吗」确认框",
    "universalAccessAuthWarn": "辅助功能授权提示",
    "coreautha": "指纹 / 密码确认",
    "LocalAuthenticationRemoteService": "指纹 / 密码确认",
    "TCCAuthorizationPrompt": "系统授权弹窗",
}
# 10-30:存密码的 App(参考别家停手线时发现没拦)。钥匙串访问在 /System/Library/CoreServices/Applications/(macOS 26)
PASSWORD_APPS = {
    "com.apple.keychainaccess": "钥匙串访问", "com.apple.Passwords": "密码 App",
    "com.1password.1password": "1Password", "com.agilebits.onepassword7": "1Password",
    "com.bitwarden.desktop": "Bitwarden", "com.dashlane.dashlanephonefinal": "Dashlane",
    "com.callpod.keepermacapp": "Keeper", "com.lastpass.lastpassmacdesktop": "LastPass", "in.sinew.Enpass-Desktop": "Enpass",
}
SETTINGS_APPS = {"System Settings", "System Preferences", "系统设置", "系统偏好设置"}
# 隐私与安全性本身 + 它下面各子页面(窗口标题只写子页面名,10-25 实测「Automation」)+ 密码、用户与群组、登录项
SETTINGS_PRIVATE = re.compile(r"隐私|安全|密码|自动化|辅助功能|屏幕(与系统)?录|完全磁盘|文件与文件夹|输入监控|开发者工具|App 管理|"
                              r"定位服务|通讯录|相机|麦克风|登录项|用户与群组|"
                              r"Privacy|Security|Password|Automation|Accessibility|Screen (& System Audio )?Recording|Full Disk|"
                              r"Files (and|&) Folders|Input Monitoring|Developer Tools|App Management|Location Services|Contacts|"
                              r"Camera|Microphone|Login Items|Users (&|and) Groups|Device Control|Data Access|设备控制|数据访问", re.I)
# 能调 SeeU 的 AI 桌面 App(名字沿用老的,cdp/doctor 在用):Claude;ChatGPT(本机 /Applications/ChatGPT.app 包名就是
# com.openai.codex,10-30 查;老版 ChatGPT 是 com.openai.chat)
CLAUDE_BUNDLES = {"com.anthropic.claudefordesktop", "com.openai.codex", "com.openai.chat"}
# 🔴 10-31 用户定:「工具是人在控制,工具不操作自己,但是可以操作其他」→ 任何 AI App(含 Claude、Codex)都不一律拦,
# 只拦「正在运行 SeeU 的那个」(防它替自己批准),由 host_pids / host_bundles 认(含经 XPC 拉起的,见下)。
# CLAUDE_BUNDLES 只留作「已知 AI 桌面 App」名单(文案、检查授权里提示用),不再用来拦。

_proc = {}          # pid -> (名字, bundle)


def _info(pid):
    if pid in _proc:
        return _proc[pid]
    name = bundle = ""
    try:
        from AppKit import NSRunningApplication
        a = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if a:
            name = str(a.localizedName() or "")
            bundle = str(a.bundleIdentifier() or "")
    except Exception:
        pass
    if not name:
        try:
            name = os.path.basename(subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True,
                                                   text=True, timeout=3).stdout.strip())
        except Exception:
            pass
    _proc[pid] = (name, bundle)
    return _proc[pid]


_host = []


def host_pids():
    """运行 SeeU 的程序:往上找父进程里所有 .app 的 pid(Claude 里跑:Claude 自带的 claude.app 和 Claude.app 都算)。"""
    if _host:
        return _host[0]
    pids, pid = set(), os.getppid()
    for _ in range(16):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True,
                                 timeout=3).stdout.strip()
        except Exception:
            break
        if not out:
            break
        ppid, comm = out.split(None, 1)
        if ".app/" in comm:
            pids.add(pid)
        if ppid in ("0", "1"):
            break
        pid = int(ppid)
    # 10-31:豆包经 XPC 服务(Doubao.app/…/McpService.xpc)拉起 SeeU,父进程链到 launchd 就断了,认不到豆包主程序 →
    # 再按「最外层 .app」认:祖先程序装在哪个 App 包里,那个 App 正在跑的进程都算宿主
    try:
        outer = set()
        for p in list(pids):
            out = subprocess.run(["ps", "-o", "comm=", "-p", str(p)], capture_output=True, text=True, timeout=3).stdout
            i = out.find(".app/")
            if i > 0:
                outer.add(out[:i + 4].strip())
        if outer:
            from AppKit import NSWorkspace
            for a in NSWorkspace.sharedWorkspace().runningApplications():
                u = a.bundleURL()
                if u is not None and str(u.path()) in outer:
                    pids.add(int(a.processIdentifier()))
    except Exception:
        pass
    _host.append(pids)
    return pids


def host_bundles():
    """正在运行 SeeU 的那几个 App 的包名(调试端口那条路按包名判,不按进程号)。"""
    out = set()
    for p in host_pids():
        b = _info(p)[1]
        if b:
            out.add(b)
    return out


def _window_titles(pid):
    try:
        import Quartz
        return [str(w.get("kCGWindowName") or "") for w in
                Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, 0) or []
                if w.get("kCGWindowOwnerPID") == pid]
    except Exception:
        return []


def why_not(pid):
    """这个进程能不能碰:能 → None;不能 → 原因文字。"""
    if not pid:
        return None
    name, bundle = _info(pid)
    if name in TERMINALS or bundle in TERMINALS.values():
        return f"{name} 是终端,往里打字等于能执行任何命令"
    if name in SYSTEM_PROMPTS:
        return f"这是{SYSTEM_PROMPTS[name]}({name})"
    if bundle in PASSWORD_APPS:
        return f"{PASSWORD_APPS[bundle]} 里存的是密码"
    if pid in host_pids():
        return f"{name or pid} 是正在运行 SeeU 的程序(防 AI 自己批准自己)"
    if name in SETTINGS_APPS or bundle in ("com.apple.systempreferences", "com.apple.Settings"):
        if any(SETTINGS_PRIVATE.search(t) for t in _window_titles(pid)):
            return "系统设置正开着隐私与安全性 / 密码页面"
    return None


def check_pid(pid):
    w = why_not(pid)
    if w:
        raise Refused(f"{w},SeeU 不碰(这一步请你自己来)")


def check_app(app):
    """按 App 名(可带「窗口标题」)查;找不到进程就放过(交给后面的步骤报找不到)。"""
    try:
        from seeu import bgclick as bg
        g = bg.main_window(app)
        pid = g["pid"] if g else None
        if pid is None:
            from seeu import ax
            pid = ax.app_element(bg.split_target(app)[0])[1]
    except Exception:
        return
    check_pid(pid)


# ---------------------------------------------------------------- 菜单
BLOCKED_MENU = re.compile(r"清空废纸篓|立即删除|退出登录|注销|锁定屏幕|关机|重新启动|"
                          r"Empty Trash|Delete Immediately|Log Out|Lock Screen|Shut Down|Restart", re.I)


def check_menu(path):
    for p in path:
        if BLOCKED_MENU.search(str(p)):
            raise Refused(f"菜单「{p}」是危险操作,SeeU 不点(这一步请你自己来)")


# ---------------------------------------------------------------- 6. SeeU 自己的浮标
SELF_UI = ("watch_window", "watch_island")      # 进程命令行里带这些 = SeeU 自己的悬浮窗/悬浮标/多任务岛
SELF_SKIP = ("cursor_overlay",)                 # 代理光标、光圈、提示条:永远不接鼠标,查最上层时跳过
_cmds = {}


def _cmdline(pid):
    if pid not in _cmds:
        try:
            _cmds[pid] = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                                        text=True, timeout=3).stdout
        except Exception:
            _cmds[pid] = ""
    return _cmds[pid]


def check_point(x, y):
    """借真鼠标点屏幕点 (x, y) 之前调:那里最上层是 SeeU 自己的浮标(又没在让路)→ Refused。查不了就放过。"""
    try:
        import Quartz
        from seeu_lib import watch_window as ww
        passing = ww.passthrough_wids()
        wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly
                                                 | Quartz.kCGWindowListExcludeDesktopElements, 0) or []
    except Exception:
        return
    for w in wins:                                   # 从最上层往下
        b = w.get("kCGWindowBounds") or {}
        if not (b.get("X", 0) <= x < b.get("X", 0) + b.get("Width", 0)
                and b.get("Y", 0) <= y < b.get("Y", 0) + b.get("Height", 0)):
            continue
        # Dock 的窗口号称占满全屏,实际不挡点击(跟 seeu_lib.input_guard.window_at 一样跳过)
        if w.get("kCGWindowOwnerName") == "Dock" or float(w.get("kCGWindowAlpha", 1)) <= 0.01 \
                or int(w["kCGWindowNumber"]) in passing:
            continue
        cmd = _cmdline(int(w["kCGWindowOwnerPID"]))
        if any(k in cmd for k in SELF_SKIP):
            continue
        if any(k in cmd for k in SELF_UI):
            raise Refused("这个位置盖着 SeeU 自己的浮标,SeeU 不点自己(防 AI 自己批准自己;这一步请你自己来)")
        return


def main():
    """自检:python3 -m seeu.safety —— 打印这台机器上会被拦的程序和规则条数。"""
    print("运行 SeeU 的程序 pid:", sorted(host_pids()), [(_info(p)[0]) for p in host_pids()])
    print(f"快捷键 {len(BLOCKED_KEYS)} 条,打字内容 {len(BLOCKED_TEXT)} 条,终端 {len(TERMINALS)} 个,系统弹窗 {len(SYSTEM_PROMPTS)} 个")


if __name__ == "__main__":
    main()
