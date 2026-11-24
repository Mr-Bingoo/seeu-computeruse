# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 安全底线(硬拦,写死、不留开关;跟 Mac 版 seeu/safety.py 同一套口径)。

不管谁下的指令(包括网页上藏的字、AI 自己的判断),这几类一律不做,抛 Refused(动作层报 refused「这一步请你自己来」):
  1. 危险打字内容:下载后直接运行、提权运行、删整个硬盘 / 用户目录、格式化、抹盘、fork 炸弹(Mac 那几条 + Windows 的写法)。
  2. 命令行类程序(命令提示符、PowerShell、Windows 终端、WSL、PuTTY…)和能直接跑脚本的(PowerShell ISE、「运行」框):不看、不点、不打字。
  3. 系统权限 / 密码弹窗(UAC 授权框本来就在隔离桌面上,碰不到;另有「Windows 安全中心」、凭据输入框、凭据管理器)、
     注册表编辑器、管理控制台、任务管理器,和「设置」里的隐私 / 安全 / 账户 / 登录页:不看、不点、不打字。
  4. 存密码的程序(1Password、Bitwarden、KeePass…):不看、不点、不打字。
  5. 正在运行 SeeU 的程序本身(往上找父进程;跟 Mac 版一样只拦这一个):防 AI 自己批准自己。
  6. 资源管理器里 Shift+Delete(不进回收站直接删)。
  7. 名字是「清空回收站 / 关机 / 注销 / 重启 / 永久删除…」的按钮、菜单项:不点(check_menu,11-23)。
  8. 锁屏(或屏保 / 系统授权框占着屏幕)时什么都不做(check_unlocked,11-23)。
  另:密码框里不打字、不按会改内容的键(key_enters,跟 Mac 版同一条规则)。
系统限制附带的保护:以管理员身份运行的窗口,普通进程发不进去消息,SeeU 不提权,所以本来就碰不到。
"""
import ctypes
import ctypes.wintypes as wt
import os
import re


class Refused(Exception):
    """安全底线硬拦。调用方别换路硬做,交给用户。"""


# ---------------------------------------------------------------- 按键(跟 Mac 版同一套规则,修饰键 cmd 在 Windows 上 = ctrl)
# Windows 上 Delete 键就是「向后删」(Mac 的 delete 是退格),所以 delete 归成 forwarddelete,退格单叫 backspace
KEY_ALIAS = {"esc": "escape", "del": "forwarddelete", "delete": "forwarddelete", "forward_delete": "forwarddelete",
             "page_up": "pageup", "page_down": "pagedown", "enter": "return"}
MOD_ALIAS = {"control": "ctrl", "ctl": "ctrl", "cmd": "ctrl", "command": "ctrl", "⌘": "ctrl", "⌃": "ctrl",
             "option": "alt", "opt": "alt", "⌥": "alt", "⇧": "shift", "win": "win", "meta": "win", "super": "win"}


def norm_key(key):
    k = str(key).strip().lower()
    return KEY_ALIAS.get(k, k)


def norm_mods(mods=()):
    if isinstance(mods, str):
        mods = [mods]
    return [MOD_ALIAS.get(str(m).strip().lower(), str(m).strip().lower()) for m in mods or ()]


_EDIT_KEYS = {"return", "backspace", "forwarddelete", "space"}
_NAV_KEYS = {"tab", "escape", "left", "right", "up", "down", "home", "end", "pageup", "pagedown"} | {f"f{i}" for i in range(1, 21)}


def key_enters(key, mods=()):
    """这个键会不会往输入框里放东西、改它或提交它(密码框里这些不按)。Windows 上 Ctrl+V / X / Z / Y 改内容,别的 Ctrl 快捷键不算。"""
    k, m = norm_key(key), set(norm_mods(mods))
    if k in _EDIT_KEYS:
        return True
    if "ctrl" in m:
        return k in ("v", "x", "z", "y") or (k == "insert" and "shift" in m)
    if k == "insert" and "shift" in m:
        return True          # Shift+Insert = 粘贴
    if k in _NAV_KEYS:
        return False
    return True


_STAY_CTRL = {"a", "c", "v", "x", "z", "y", "insert"}      # 带 Ctrl 也还留在原来那个框里的(全选、复制、粘贴、剪切、撤销、重做)


def moves_focus(key, mods=()):
    """这个键按完,光标可能已经不在原来那个输入框里了(11-23 C-3.9 整体复查)。
    Tab / Shift+Tab、Esc、F1~F20(F6 跳到地址栏),和别的带 Ctrl / Alt 的快捷键(Ctrl+L、Alt+D、Ctrl+Tab、Ctrl+F…)算;
    方向键、Home / End、翻页、删除、空格、普通字符只在框里动,不算。回车不算(聊天框、多行框里回车后还在原来的框)。"""
    k, m = norm_key(key), set(norm_mods(mods))
    if k in ("tab", "escape") or re.fullmatch(r"f\d{1,2}", k):
        return True
    if m & {"ctrl", "alt"}:
        return k not in _STAY_CTRL
    return False


def check_keys(key, mods=(), exe=""):
    k, m = norm_key(key), set(norm_mods(mods))
    if "win" in m:
        raise Refused("带 Windows 键的组合 SeeU 不按(这一步请你自己来)")
    if k == "forwarddelete" and m == {"shift"} and exe.lower() == "explorer.exe":
        raise Refused("「不进回收站直接删除」SeeU 不按(这一步请你自己来)")


# ---------------------------------------------------------------- 打字内容
BLOCKED_TEXT = [
    ("下载后直接运行", r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da|k|fi)?sh\b"),
    ("下载后直接运行", r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget)\b[^\n|]*\|\s*(iex|invoke-expression)\b"),
    ("下载后直接运行", r"\b(iex|invoke-expression)\b[^\n]*(downloadstring|iwr|irm|invoke-webrequest|invoke-restmethod)"),
    ("下载后直接运行", r"\bmshta\s+(https?|vbscript|javascript):"),
    ("用管理员权限运行", r"(^|[\s;&|`(])sudo\s+[-a-zA-Z/.~$]"),
    ("用管理员权限运行", r"-verb\s+runas\b|\brunas\s+/"),
    ("删整个硬盘 / 家目录", r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(--no-preserve-root\s+)?(/|~/?|\$\{?HOME\}?/?|/\*|~/\*)(\s|$)"),
    ("删整个硬盘 / 用户目录", r"\b(rd|rmdir)\s+(/[sq]\s+)+[\"']?([a-z]:\\?|%userprofile%|%systemroot%|%homepath%)[\"']?(\s|$)"),
    ("删整个硬盘 / 用户目录", r"\bdel\s+(/[fsqa]\s+)+[\"']?([a-z]:\\?\*?|%userprofile%\\?\*?)[\"']?(\s|$)"),
    ("删整个硬盘 / 用户目录", r"\bremove-item\b[^\n]*-recurse[^\n]*[\"' ]([a-z]:\\?|\$env:userprofile|~)[\"']?(\s|$)"),
    ("格式化磁盘", r"\bformat(\.com)?\s+[a-z]:"),
    ("格式化磁盘", r"\b(format-volume|clear-disk|initialize-disk)\b"),
    ("抹盘", r"\bdiskpart\b|\bcipher\s+/w"),
    ("改系统启动", r"\bbcdedit\b[^\n]*/(delete|set)"),
    ("抹盘", r"\bdd\b[^\n]*\bof=/dev/"),
    ("格式化磁盘", r"\bmkfs(\.\w+)?\s+/dev/"),
    ("fork 炸弹", r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    ("fork 炸弹", r"%0\s*\|\s*%0"),
]
_TEXT_RES = [(n, re.compile(p, re.I)) for n, p in BLOCKED_TEXT]


def check_text(text):
    t = str(text or "")
    for name, rx in _TEXT_RES:
        if rx.search(t):
            raise Refused(f"要打的字里有危险命令(「{name}」),SeeU 不打(这一步请你自己来)")


# ---------------------------------------------------------------- 目标程序(按程序名,小写)
TERMINALS = {"cmd.exe": "命令提示符", "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell", "powershell_ise.exe": "PowerShell ISE",
             "windowsterminal.exe": "Windows 终端", "wt.exe": "Windows 终端", "openconsole.exe": "终端", "conhost.exe": "终端",
             "wsl.exe": "WSL", "wslhost.exe": "WSL", "bash.exe": "Bash", "mintty.exe": "Git Bash", "putty.exe": "PuTTY",
             "kitty.exe": "KiTTY", "mobaxterm.exe": "MobaXterm", "alacritty.exe": "Alacritty", "wezterm-gui.exe": "WezTerm",
             "tabby.exe": "Tabby", "hyper.exe": "Hyper", "warp.exe": "Warp", "cmder.exe": "Cmder", "conemu64.exe": "ConEmu",
             "wscript.exe": "脚本宿主", "cscript.exe": "脚本宿主"}
# 命令行窗口的窗口类(conhost 老窗口、Windows 终端、伪控制台、mintty、ConEmu、PuTTY)
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow", "mintty",
                   "VirtualConsoleClass", "PuTTY", "KiTTY"}
SYSTEM_APPS = {"consent.exe": "管理员授权框(UAC)", "credentialuibroker.exe": "凭据输入框", "logonui.exe": "登录界面",
               "regedit.exe": "注册表编辑器", "mmc.exe": "管理控制台", "taskmgr.exe": "任务管理器",
               "sechealthui.exe": "Windows 安全中心", "securityhealthhost.exe": "Windows 安全中心",
               "lockapp.exe": "锁屏", "useraccountcontrolsettings.exe": "UAC 设置"}
PASSWORD_APPS = {"1password.exe": "1Password", "bitwarden.exe": "Bitwarden", "keepass.exe": "KeePass", "keepassxc.exe": "KeePassXC",
                 "dashlane.exe": "Dashlane", "lastpass.exe": "LastPass", "enpass.exe": "Enpass", "keeperpasswordmanager.exe": "Keeper",
                 "roboform.exe": "RoboForm", "nordpass.exe": "NordPass", "protonpass.exe": "Proton Pass"}
SETTINGS_EXES = {"systemsettings.exe", "applicationframehost.exe"}
SETTINGS_PRIVATE = re.compile(r"隐私|安全|账户|帐户|登录选项|密码|家庭|开发者选项|恢复|激活|"
                              r"Privacy|Security|Accounts?|Sign-in|Password|Family|For developers|Recovery|Activation", re.I)
EXPLORER_PRIVATE = re.compile(r"凭据管理器|Credential Manager|用户帐户|用户账户|User Accounts|Windows Defender|防火墙|Firewall|"
                              r"^运行$|^Run$", re.I)


# ---------------------------------------------------------------- 正在运行 SeeU 的程序(父进程链)
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD), ("szExeFile", wt.WCHAR * 260)]


def _process_table():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    k.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.CloseHandle.argtypes = [wt.HANDLE]
    snap = k.CreateToolhelp32Snapshot(0x2, 0)
    table = {}
    if not snap or snap == wt.HANDLE(-1).value:
        return table
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            table[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return table


_HOST = []
# 父进程链往上走到这些就停(再往上是系统 / 资源管理器,拦了就什么都做不了)
_STOP = {"explorer.exe", "services.exe", "svchost.exe", "wininit.exe", "winlogon.exe", "system", "smss.exe", "csrss.exe"}


def host_pids():
    """本进程往上的父进程链(不含系统那几层)。Claude 桌面版 / 别的 AI 客户端跑 SeeU 时,它们就在这条链上。"""
    if not _HOST:
        table = _process_table()
        pids, cur, seen = set(), os.getpid(), set()
        while cur and cur not in seen and cur in table:
            seen.add(cur)
            parent, name = table[cur]
            if name.lower() in _STOP:
                break
            pids.add(cur)
            cur = parent
        _HOST.append(pids)
    return _HOST[0]


# 11-23 C-3.9 整体复查(用户定):开始菜单 / 任务栏搜索框打程序名回车就能直接启动程序(跟「运行」框一样)→ 整个不碰
SEARCH_APPS = {"searchhost.exe": "Windows 搜索", "searchapp.exe": "Windows 搜索", "searchui.exe": "Windows 搜索",
               "startmenuexperiencehost.exe": "开始菜单"}


def why_not(win):
    """win = window.info() 的结果。不能碰返回原因,能碰返回 None。"""
    e = (win.get("exe") or "").lower()
    title = win.get("title") or ""
    if win.get("class") in ("SeeUFloat", "SeeUGlow"):   # 11-13:SeeU 自己的浮标、光圈不碰(浮标上有只能用户亲手点的 I See 按钮)
        return "这是 SeeU 自己的浮标,上面的按钮只能用户亲手点"
    if e in TERMINALS:
        return f"「{TERMINALS[e]}」是命令行程序,能直接运行任何命令"
    if win.get("class") in CONSOLE_CLASSES:     # 11-15 复查:WSL 发行版、商店版 Python 这类,程序名不在名单里,窗口类是命令行窗口
        return "这是命令行窗口,能直接运行任何命令"
    if e in SYSTEM_APPS:
        return f"「{SYSTEM_APPS[e]}」是系统权限相关的界面"
    if e in SEARCH_APPS:
        return f"「{SEARCH_APPS[e]}」里打程序名回车就能直接启动程序"
    if e in PASSWORD_APPS:
        return f"「{PASSWORD_APPS[e]}」是存密码的程序"
    if e in SETTINGS_EXES and SETTINGS_PRIVATE.search(title):
        return f"「设置」里的这一页({title})管隐私 / 安全 / 账户"
    if e == "explorer.exe" and EXPLORER_PRIVATE.search(title.strip()):
        return f"「{title}」管密码 / 账户 / 安全,或能直接运行命令"
    if win.get("pid") in host_pids():
        return "这是正在运行 SeeU 的程序自己(防止 AI 替自己批准)"
    return None


def check_window(win):
    why = why_not(win)
    if why:
        raise Refused(f"{why},SeeU 不碰(这一步请你自己来)")


# ---------------------------------------------------------------- 危险名字的按钮 / 菜单项
# 11-23 C-3.9 整体复查:按编号 / 按名字点按钮、菜单项、列表项之前查名字(原来 Windows 完全没查;照 Mac safety.check_menu 的词表
# 和 Linux 11-20 的做法)。Windows 的叫法补上:清空回收站、注销 / Sign out / Log off、永久删除、休眠。
# 没照搬 Linux 的「运行 / Run」那条:Windows 上编辑器的「运行」菜单太常见,规则照 Mac(Mac 没有这条)。
BLOCKED_MENU = re.compile(r"清空回收站|清[空倒]废纸篓|[清倒]空?垃圾桶|立即[删刪]除|永久[删刪]除|退出登录|注销|登出|锁定屏幕|鎖定螢幕|锁屏|"
                          r"关机|關機|休眠|强制退出|強制結束|"
                          r"\b(Empty (the )?(Recycle Bin|Trash|Bin)|Delete (Immediately|Permanently)|Permanently delete|"
                          r"Log ?Out|Log ?Off|Sign ?out|Lock Screen|Shut ?Down|Power Off|Hibernate|Force Quit)\b", re.I)
# 11-23 C-4.0 Fable 复查:「重启」类只认整个名字(系统菜单里的「重新启动…」「Restart」「Restart Now」「重启」),
# 「Restart Kernel」「Restart Language Server」「重启服务」这类程序自己的按钮不算;英文词加词边界(「Design Outline」里的 sign out 不算)
BLOCKED_RESTART = re.compile(r"^\s*(重新启动|重新開機|重启|Restart|Reboot)(\s*(Now|Computer|电脑|计算机|系统))?\s*(\(&?[A-Za-z]\))?\s*(\.{3}|…)?\s*$|"
                             r"\bUpdate and restart\b|更新并重启", re.I)
# 只有整个名字正好是这些才算(「锁定任务栏」「睡眠模式设置」这类不算);后面带的快捷键字母「(L)」不影响
BLOCKED_MENU_EXACT = re.compile(r"^\s*(锁定|睡眠|切换用户|Lock|Sleep|Switch user)\s*(\(&?[A-Za-z]\))?\s*$", re.I)
# 资源管理器里磁盘右键的「格式化(A)...」/「Format...」:只在资源管理器里、只认整个名字(Word 的「格式」、VS Code 的「格式化文档」不算)
FORMAT_MENU = re.compile(r"^\s*(格式化\s*(\(&?[A-Za-z]\))?\s*(\.{3}|…)?|Format\s*(\.{3}|…))\s*$", re.I)


def check_menu(path, exe=""):
    """path = 要点的控件名字(一串)。名字是危险操作就抛 Refused。exe = 目标程序名(「格式化」只在资源管理器里查)。"""
    for p in path:
        t = str(p)
        if BLOCKED_MENU.search(t) or BLOCKED_RESTART.search(t) or BLOCKED_MENU_EXACT.search(t) or (
                str(exe).lower() == "explorer.exe" and FORMAT_MENU.search(t)):
            raise Refused(f"「{t[:30]}」是危险操作,SeeU 不点(这一步请你自己来)")


# ---------------------------------------------------------------- 锁屏
# 11-23 C-3.9 整体复查:原来没有锁屏检查(Mac / Linux 都有)。锁屏、屏保(要密码的)、管理员授权框(UAC)出来时,
# 接收键盘鼠标的「输入桌面」不是平时那个 Default:普通程序打不开它(拒绝访问),或打开了名字不是 Default。
# 🔴 判断出错一律当「没锁」(免得把正常使用卡死)。真机还没验过(见 11-23 复查清单 A8)。
ERROR_ACCESS_DENIED = 5


def _input_desktop():
    """现在接收输入的桌面:返回 (名字, 0);打不开返回 (None, 错误码)。只读、纯 ctypes。"""
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    u.OpenInputDesktop.restype = wt.HANDLE
    u.GetUserObjectInformationW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    u.GetUserObjectInformationW.restype = wt.BOOL
    u.CloseDesktop.argtypes = [wt.HANDLE]
    ctypes.set_last_error(0)
    h = u.OpenInputDesktop(0, False, 0x0001)        # DESKTOP_READOBJECTS
    if not h:
        return None, ctypes.get_last_error()
    try:
        buf = ctypes.create_unicode_buffer(256)
        need = wt.DWORD(0)
        if not u.GetUserObjectInformationW(h, 2, buf, ctypes.sizeof(buf), ctypes.byref(need)):     # 2 = UOI_NAME
            return None, 0                          # 打开了但问不出名字:不知道,按没锁算
        return buf.value, 0
    finally:
        u.CloseDesktop(h)


def locked():
    """屏幕是不是锁着(或屏保 / 系统授权框占着屏幕)。问不出来 = False。"""
    try:
        name, err = _input_desktop()
    except Exception:   # noqa: BLE001
        return False
    if name is None:
        return err == ERROR_ACCESS_DENIED
    return bool(name) and name.lower() != "default"


def check_unlocked():
    """锁屏时一律不做(提示照 Linux 版那句)。"""
    if locked():
        raise Refused("屏幕锁着(或屏保开着),SeeU 什么都不做;等你解锁后再说")


# ---------------------------------------------------------------- 资源管理器地址栏
# 11-23 C-3.9 整体复查(虚拟机实测 + 用户定):资源管理器地址栏跟「运行」框一样,打程序名 / 命令回车会直接运行。
# 先借鼠标点进地址栏、再借真键盘打字回车,SeeU 打得进去。规则:地址栏里只打「已经存在的文件夹路径」(%变量% 先展开),
# 回车前也看地址栏里现在是不是已有的文件夹;别的(程序名、命令、带参数的、网址)一律不打不按。认不出焦点在哪 = 按地址栏算。
# 11-23 C-4.0 Fable 复查:原来只要名字里带「地址」就算(文件「地址簿.txt」被误当地址栏);英文 Win10 面包屑叫「Address: C:\Users」没认出来
ADDRESS_NAME = re.compile(r"^(地址栏|地址|Address( bar| band)?)\s*$|^(地址|Address)\s*[:：]", re.I)
NOT_FOLDER = "资源管理器地址栏里只打已有文件夹的路径(打程序名、命令回车会直接运行),SeeU 不打(这一步请你自己来)"
NOT_FOLDER_ENTER = "资源管理器地址栏里现在不是已有文件夹的路径,回车会直接运行里面的东西,SeeU 不按(这一步请你自己来)"
NOT_ADDRESS_KEY = "资源管理器地址栏里 SeeU 不一个个按字符键(拼出来的命令会被运行);要跳到某个文件夹,用打字工具打完整的文件夹路径"


def is_address(name):
    return bool(ADDRESS_NAME.search(str(name or "").strip()))


def folder_ok(text):
    """text 是不是一个已经存在的文件夹路径(只有这一个,不带参数)。"""
    t = str(text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] == '"':
        t = t[1:-1].strip()
    if not t or any(c in t for c in "\r\n\t|&<>^"):
        return False
    t = os.path.expandvars(t)
    if "%" in t:
        return False
    return os.path.isabs(t) and os.path.isdir(t)


def check_address_text(text):
    if not folder_ok(text):
        raise Refused(NOT_FOLDER)
