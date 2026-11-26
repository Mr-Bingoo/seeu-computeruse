# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 后台打开 App(照 Mac 版 seeu/openapp.py)。

只给自己打不开 App 的客户端用(现在只有千问)。规则跟 Mac 一样:只开不关;终端 / 命令行、系统权限界面、
密码程序、「设置」、浏览器(网页走 seeu_web_open)、正在运行 SeeU 的程序都不开;已经开着的不动;
App 打开时自己抢了前台,就把前台还给用户原来的窗口,结果里照实说。

找 App:「开始」菜单里的全部 App(PowerShell Get-StartApps:名字 + AppID,传统程序和商店 App 都有,名字是系统语言),
按 AppID 用 shell:AppsFolder\\<AppID> 打开(ShellExecute,SW_SHOWNOACTIVATE = 窗口显示但不激活;商店 App 不认这个,靠事后还前台)。
"""
import ctypes
import json
import os
import re
import subprocess
import time

# 自己打不开 App 的客户端(程序名,小写)。千问 Windows 版的程序名没实测,先按常见写法列,装上后核对
NEED_OPEN = {"qianwen.exe", "千问.exe", "qwen.exe", "tongyi.exe"}

# 常用系统自带 App 的中文名 → 英文系统里的叫法(照 Mac 版 ax.canon_name:AI 写中文名,英文 Windows 上也认)
ZH_EN = {"记事本": "Notepad", "计算器": "Calculator", "画图": "Paint", "写字板": "WordPad", "截图工具": "Snipping Tool",
         "文件资源管理器": "File Explorer", "资源管理器": "File Explorer", "照片": "Photos", "相机": "Camera",
         "日历": "Calendar", "邮件": "Mail", "时钟": "Clock", "闹钟和时钟": "Clock", "地图": "Maps", "天气": "Weather",
         "便笺": "Sticky Notes", "便签": "Sticky Notes", "录音机": "Sound Recorder", "媒体播放器": "Media Player",
         "命令提示符": "Command Prompt", "任务管理器": "Task Manager", "设置": "Settings", "控制面板": "Control Panel",
         "注册表编辑器": "Registry Editor", "终端": "Terminal"}
EN_ZH = {}
for _z, _e in ZH_EN.items():
    EN_ZH.setdefault(_e, _z)

# 不替 AI 打开的(按名字 / AppID 片段,不分大小写;AppID 按子串认,不用 \b —— Terminal_8wekyb… 里 \b 不成立)
_BLOCK = [
    (re.compile(r"(cmd\.exe|^cmd$|command prompt|命令提示符|命令提示字元|powershell|pwsh|windowsterminal|windows ?terminal|"
                r"^terminal$|终端|終端|\bwsl\b|microsoft\.wsl|wsl\.exe|wslhost|linux|ubuntu|debian|kali|opensuse|suse|fedora|almalinux|oracle ?linux|pengwin|alpine|"
                r"python|\\py\.exe|^py$|\bidle\b|node(\.exe|\.js|js)|^node$|ruby|\bperl\b|\bphp\b|\blua\b|anaconda prompt|msys2|ucrt64|mingw|cygwin|git ?bash|git-bash|mintty|putty|kitty|"
                r"mobaxterm|alacritty|wezterm|tabby|hyper ?terminal|\\hyper\.exe|warp ?terminal|\\warp\.exe|cmder|conemu|"
                r"wscript|cscript|mshta|rundll32|regsvr32|msiexec|\\bash\.exe|\\sh\.exe|\.(bat|cmd|ps1|vbs|vbe|js|jse|wsf|hta|psm1)$)", re.I),
     "是命令行程序,能直接运行任何命令"),
    (re.compile(r"(regedit|registry editor|注册表|登錄編輯程式|\.msc$|\\mmc\.exe|computer management|计算机管理|task ?manager|taskmgr|"
                r"任务管理器|工作管理員|windows security|windows 安全|sechealth|credential|凭据|認證|user accounts|用户帐户|用户账户|"
                r"^uac$|useraccountcontrol|rundialog|^run$|^运行$|^執行$|windows tools|windows 工具|administrative tools|管理工具|"
                r"event viewer|事件查看器|gpedit|group policy|组策略|secpol|msconfig|system configuration|系统配置|"
                r"file explorer|文件资源管理器|资源管理器|檔案總管|\\explorer\.exe|^explorer$|windows\.explorer)", re.I),
     "是系统权限或系统管理相关的界面"),
    (re.compile(r"(1password|bitwarden|keepass|dashlane|lastpass|enpass|keeper ?password|keeper security|keeperpassword|"
                r"roboform|nordpass|proton ?pass)", re.I),
     "是存密码的程序"),
    (re.compile(r"(immersivecontrolpanel|^settings$|^设置$|^設定$|control ?panel|controlpanel|控制面板|^控制台$|コントロール)", re.I),
     "是系统设置,可能直接开在隐私 / 账户那页"),
    # 能被 AI 借来跑命令 / 交出电脑的 —— 别的 AI 客户端、远程协助
    (re.compile(r"(anthropic|claude|openai|chatgpt|codex|cursor|windsurf|codeium|copilot|officehub|workbuddy|doubao|豆包|"
                r"kimi|moonshot|deepseek|lingma|qoder|\btrae\b|marscode|qianwen|千问|tongyi|通义|\bqwen\b|yuanbao|元宝|"
                r"perplexity|ollama|lm ?studio|zhipu|智谱|chatglm|\bkiro\b|antigravity|\bvoid\b|"
                r"quick ?assist|快速助手|quickassist|mstsc|msrdc|remote ?desktop|远程|遠端|windows365|^windows app$|"
                r"teamviewer|anydesk|todesk|sunlogin|向日葵|parsec|rustdesk|splashtop|chrome ?remote|\bvnc|realvnc|tightvnc|"
                r"ultravnc|anyviewer|nomachine|radmin)", re.I),
     "是 AI 客户端或远程协助程序"),
    # 终端名单外的终端、带命令行的 IDE、能跑脚本的启动器、虚拟机、磁盘 / 系统管理
    (re.compile(r"(wave ?terminal|\brio\b|termius|electerm|securecrt|mremoteng|xshell|finalshell|"
                r"visual studio|vs ?code|vscodium|^code$|\\code\.exe|jetbrains|intellij|pycharm|webstorm|goland|clion|rider|"
                r"phpstorm|datagrip|android studio|\bzed\b|sublime text|notepad\+\+|"
                r"autohotkey|powertoys|flow ?launcher|wox\b|listary|keypirinha|"
                r"vmware|virtualbox|hyper-v|parallels|sandbox|windows 沙盒|"
                r"disk ?management|磁盘管理|diskmgmt|disk cleanup|磁盘清理|system information|系统信息|msinfo|recovery drive|"
                r"恢复驱动器|odbc|iscsi|print management|services$|^服务$|task scheduler|任务计划)", re.I),
     "打开后能直接运行命令或改系统"),
]
_BROWSER = re.compile(r"(chrome|msedge|microsoft edge|firefox|brave|\bopera\b|vivaldi|360se|360chrome|qqbrowser|sogouexplorer|"
                      r"iexplore|internet explorer|liebao|猎豹|2345(浏览器|explorer|browser)|maxthon|傲游|浏览器|瀏覽器|"
                      r"\b(web|uc|qq|tor|avast secure|avg secure|cent|yandex|quark|夸克|arc|zen|floorp|waterfox|librewolf) ?browser\b|"
                      r"yandex)", re.I)
_BROWSER_NAME = re.compile(r"^(arc|zen|dia|comet|opera|edge|chrome|firefox)$", re.I)   # 只对显示名整串比(拼进 AppID 后永远对不上)
_VM_SHARED = re.compile(r"(parallels|vmware|virtualbox).*shared|shared.*(parallels|vmware|virtualbox)", re.I)
_MAC_NAME = re.compile(r"[(（]\s*(mac|macos)\s*[)）]\s*$", re.I)


def _host_hint():
    """mcp_server._fix_env 读走的千问原值(存在 sys 上,没留在环境变量里,免得传给被打开的程序)。"""
    import sys
    return (getattr(sys, "seeu_host_home", "") or "") + "|" + (getattr(sys, "seeu_host_userprofile", "") or "")


def enabled():
    """这次的 MCP 服务要不要给「打开 App」工具:SEEU_OPEN_APP=1/0 强制;否则看父进程链里有没有 NEED_OPEN 里的程序。"""
    v = os.environ.get("SEEU_OPEN_APP", "").strip()
    if v in ("1", "0"):
        return v == "1"
    try:
        from seeu.win import safety
        table = safety._process_table()
        for p in safety.host_pids():
            if p in table and table[p][1].lower() in NEED_OPEN:
                return True
    except Exception:   # noqa: BLE001
        pass
    h = _host_hint().lower()
    return "qwen-agent" in h and "custom-mcp" in h


_apps = []
_last_read = 0.0
REFRESH_GAP_S = 120          # 找不到时重读列表的冷却(写错名字每次都白读一遍,千问沙箱里一次 30 秒)
import threading
_apps_lock = threading.Lock()


def preload():
    """Win10 千问实测:千问的沙箱里第一次读开始菜单要 30 秒(平时约 6 秒)→ 认出是千问时就在后台先读好。"""
    threading.Thread(target=lambda: _safe_start_apps(), daemon=True).start()


def _safe_start_apps():
    try:
        start_apps()
    except Exception:   # noqa: BLE001
        pass


def start_apps(refresh=False):
    """「开始」菜单里的 App:[(名字, AppID)]。PowerShell 跑一次约 6 秒(千问沙箱里 30 秒),记住;同时只读一份。"""
    with _apps_lock:
        return _start_apps(refresh)


def _powershell():
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.exists(p) else "powershell"      # 全路径,别被当前目录里同名程序顶替


def _start_apps(refresh=False):
    if _apps and not refresh:
        return _apps[0]
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
          "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
    global _last_read
    _last_read = time.time()
    try:
        out = subprocess.run([_powershell(), "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                             timeout=60, creationflags=0x08000000)  # CREATE_NO_WINDOW;千问沙箱里实测 30 秒,给到 60
    except (subprocess.TimeoutExpired, OSError):
        return _apps[0] if _apps else []
    try:
        d = json.loads(out.stdout.decode("utf-8-sig", "replace") or "[]")
    except ValueError:
        d = []
    if isinstance(d, dict):
        d = [d]
    apps = [(str(x.get("Name") or ""), str(x.get("AppID") or "")) for x in d if isinstance(x, dict) and x.get("AppID")]
    if apps:                                     # 读失败(空)不记住,下次再读
        _apps[:] = [apps]
    return apps


def canon(name):
    """中文名 ↔ 英文名换一下,给找窗口 / 找 App 多一个候选。"""
    n = str(name or "").strip()
    n = n[:-4] if n.lower().endswith(".exe") else n
    low = n.lower()
    for z, e in ZH_EN.items():
        if low == e.lower() or low == e.lower().replace(" ", ""):
            return EN_ZH.get(e)
    return ZH_EN.get(n)


def _find_in(apps, n):
    cands = [n] + ([canon(n)] if canon(n) else [])
    for c in cands:
        for dn, aid in apps:
            if dn.lower() == c.lower():
                return dn, aid
    for c in cands:                             # notepad → AppID 里的 notepad.exe(传统程序 AppID 常是路径)
        for dn, aid in apps:
            if os.path.basename(aid).lower() in (c.lower(), c.lower() + ".exe"):
                return dn, aid
    for c in cands:
        hits = [(dn, aid) for dn, aid in apps if dn.lower().startswith(c.lower())]
        if len(hits) == 1:
            return hits[0]
    return None


def find(name):
    """名字 → (显示名, AppID);找不到 None。先全名(不分大小写),再候选名,再「名字开头是它」;找不到时重读一次列表。"""
    n = str(name or "").strip()
    n = n[:-4] if n.lower().endswith(".exe") else n
    if not n or any(ch in n for ch in "\\/:*?\"<>|") or ".." in n:
        return None                              # 写成路径 / 带通配符的一律不认
    hit = _find_in(start_apps(), n)
    if hit or time.time() - _last_read < REFRESH_GAP_S:
        return hit
    return _find_in(start_apps(refresh=True), n)


def why_not(dn, aid):
    s = f"{dn} {aid}"
    # Win10 实测:Parallels 把 Mac 上的 App 也放进「开始」菜单(…\Parallels\Shared Applications\Terminal (Mac).exe),
    # 一打开就是在 Mac 上运行真程序,出了 Windows 的安全底线管得到的范围 → 一律不开(别的虚拟机软件同理按路径认)
    if _VM_SHARED.search(aid) or _MAC_NAME.search(dn) or _MAC_NAME.search(os.path.splitext(os.path.basename(aid))[0]):
        return f"{dn} 是虚拟机共享过来的 Mac 上的 App,打开它会在 Mac 上运行,SeeU 不从 Windows 里替你打开"
    if "://" in aid or aid.lower().endswith(".url"):
        return f"{dn} 是网址快捷方式,开网页请用 seeu_web_open(网址要过允许名单)"
    for rx, why in _BLOCK:
        if rx.search(dn) or rx.search(aid) or rx.search(os.path.basename(aid)):
            return f"{dn} {why},SeeU 不替你打开"
    if _BROWSER.search(s) or _BROWSER_NAME.search(dn.strip()) or "thebrowsercompany" in aid.lower():
        return f"{dn} 是浏览器,开网页请用 seeu_web_open(网址要过允许名单)"
    try:
        from seeu.win import safety
        table = safety._process_table()
        hosts = {table[p][1].lower() for p in safety.host_pids() if p in table}
        if os.path.basename(aid).lower() in hosts:
            return f"{dn} 是正在运行 SeeU 的程序"
    except Exception:   # noqa: BLE001
        pass
    return None


def _keys(dn):
    return {dn.lower()} | ({canon(dn).lower()} if canon(dn) else set())


def _matches(w, keys):
    """窗口是不是这个 App 的:程序名对得上,或标题等于名字 / 以「 - 名字」结尾(原来按子串,太宽)。"""
    t, e = (w.get("title") or "").strip().lower(), os.path.basename(w.get("exe") or "").lower()
    return any(t == k or t.endswith(" - " + k) or e in (k + ".exe", k.replace(" ", "") + ".exe") for k in keys)


def _window_of(dn, before):
    """新出现的、名字对得上的窗口(窗口号不在 before 里)。"""
    from seeu.win import window as W
    keys = _keys(dn)
    for w in W.list_windows():
        if w["hwnd"] not in before and _matches(w, keys):
            return w
    return None


def _exe_of(aid):
    b = os.path.basename(aid).lower()
    return b if b.endswith(".exe") else None


def _running(dn, aid=""):
    """已经开着的窗口:名字对得上,或(传统程序)窗口的程序就是 AppID 里那个 exe(Teams、网易云这类标题对不上)。"""
    from seeu.win import window as W
    keys, ex = _keys(dn), _exe_of(aid)
    for w in W.list_windows():
        if _matches(w, keys) or (ex and os.path.basename(w.get("exe") or "").lower() == ex):
            return w
    return None


class _SEI(ctypes.Structure):
    import ctypes.wintypes as _wt
    _fields_ = [("cbSize", _wt.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", _wt.HWND), ("lpVerb", _wt.LPCWSTR),
                ("lpFile", _wt.LPCWSTR), ("lpParameters", _wt.LPCWSTR), ("lpDirectory", _wt.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", _wt.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", _wt.LPCWSTR), ("hkeyClass", _wt.HKEY),
                ("dwHotKey", _wt.DWORD), ("hIconOrMonitor", _wt.HANDLE), ("hProcess", _wt.HANDLE)]


def _shell_open(target):
    """ShellExecuteExW + SEE_MASK_FLAG_NO_UI:出错不弹系统提示框(弹了框 MCP 服务会一直等)。返回 (成没成, 错误码)。"""
    e = _SEI()
    e.cbSize = ctypes.sizeof(_SEI)
    e.fMask = 0x00000400 | 0x00000100         # SEE_MASK_FLAG_NO_UI | SEE_MASK_NOASYNC
    e.lpVerb, e.lpFile, e.nShow = "open", target, 4   # 4 = SW_SHOWNOACTIVATE
    try:                                       # shell: 路径要 COM(开 App 前可能还没有任何 UIA 调用)
        ctypes.windll.ole32.CoInitializeEx(None, 2)
    except Exception:   # noqa: BLE001
        pass
    sh = ctypes.WinDLL("shell32", use_last_error=True)
    sh.ShellExecuteExW.argtypes = [ctypes.POINTER(_SEI)]
    ok = bool(sh.ShellExecuteExW(ctypes.byref(e)))
    return ok, (0 if ok else ctypes.get_last_error())


def open_app(app, wait_s=15):
    from seeu.win import window as W, inputs
    name = W.split_target(app)[0]
    if not name:
        return {"outcome": "failed", "reason": "没写要打开哪个 App"}
    hit = find(name)
    if not hit:
        return {"outcome": "failed", "reason": f"找不到叫「{name}」的 App(「开始」菜单里有的才找得到),请用户确认 App 名"}
    dn, aid = hit
    w = why_not(dn, aid)
    if w:
        return {"outcome": "refused", "reason": f"{w}(这一步请你自己来)", "name": dn}
    old = _running(dn, aid)
    if old:
        return {"outcome": "delivered", "name": dn, "note": f"{dn} 已经开着,没动它(没拉到前台)。用 seeu_see 看它的画面"}
    keys = _keys(dn)
    before = {x["hwnd"] for x in W.list_windows()}
    fg0 = W.foreground()
    ok, code = _shell_open("shell:AppsFolder\\" + aid)
    if not ok:
        return {"outcome": "failed", "name": dn, "reason": f"系统没打开 {dn}(错误码 {code})"}

    def _stolen():
        """前台被新开的这个 App 占了(用户自己点开始菜单、开别的窗口不算,不还)。"""
        fg = W.foreground()
        if not fg0 or not fg or fg == fg0:
            return False
        try:                                   # 单实例 App 再启动会把旧窗口拉到前面(旧窗口在 before 里),也算它抢的
            i = W.info(fg)
            return _matches(i, keys) or bool(_exe_of(aid) and os.path.basename(i.get("exe") or "").lower() == _exe_of(aid))
        except Exception:   # noqa: BLE001
            return False

    t0, win, stole = time.time(), None, False
    while time.time() - t0 < wait_s:                     # 硬上限
        time.sleep(0.25)
        if _stolen():
            stole = True
            inputs.give_back(fg0)
        win = win or _window_of(dn, before)
        if win:
            break
    note = ""
    if win:
        for _ in range(4):                               # 有的 App 窗口出来后一两秒才抢前台,再看几次
            time.sleep(0.4)
            if _stolen():
                stole = True
                inputs.give_back(fg0)
    if stole:
        back = W.foreground() == fg0
        note = f"{dn} 打开时自己跳到了最前面," + ("已切回原来的窗口。" if back else "没能切回原来的窗口。")
    if not win:
        return {"outcome": "unverified", "name": dn,
                "note": note + f"{dn} 开起来了,但还没看到它的窗口。等一两秒再 seeu_see 看看"}
    return {"outcome": "delivered", "name": dn, "window": win["title"],
            "note": note + f"已在后台打开 {dn}(没拉到前台)。接下来用 seeu_see 看它的画面"}
