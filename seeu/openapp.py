# -*- coding: utf-8 -*-
"""后台打开 App(只给自己打不开 App 的客户端用,比如千问;加 DeepSeek / Kimi Code / ZCode)。

千问跑命令关在沙箱里,`open -a 备忘录` 每次都要用户点「允许」。SeeU 的 MCP 服务不在那个沙箱里,
由它用系统接口打开(不激活 = 窗口开在后面,不抢前台)。

规则:
- 只开不关;终端 / 能跑脚本的 App / 密码 App / 系统设置 / 正在运行 SeeU 的程序 不开(跟点击、打字同一套安全底线);
  浏览器不走这里(用 seeu_web_open,网址要过允许名单)。
- 有的 App 一打开就自己跳到最前面,拦不住:跳了就切回用户原来在用的程序,并在结果里照实说。
- 已经开着的不动它(不拉前台)。

谁能看到这个工具:见 enabled()。别的客户端(Claude、Codex…)自己能在后台开 App,不给,工具清单也不多一项。
"""
import os
import re
import time

# 自己打不开 App 的客户端(包名)。千问 5.2:跑的命令在沙箱里,打开 App 要用户批准。
# DeepSeek Harness / Kimi Code / ZCode 照新用户路子实测时都没有正规工具,只好自己跑 `open -a`
# (Kimi 不带 -g,App 跳到前台;DeepSeek 违反「只用 seeu_」),也给。包名照本机 /Applications 里的 Info.plist。
NEED_OPEN = {"com.alibaba.tongyi": "千问", "com.deepseek.dsh": "DeepSeek", "com.kimi.code.desktop": "Kimi Code",
             "dev.zcode.app": "ZCode"}

# 同一家常有好几个马甲 / 极速版(Kimi Code / Kimi Work、豆包 / 豆包工作、WorkBuddy / CodeBuddy…),
# 按程序名一个个列会漏 → 名字或包名里带这些品牌字样的一律算「要 SeeU 帮着开 App」的客户端。
# Claude、Codex、Cursor、Trae、VS Code 这些自己能在后台开 App,不在里面。
NEED_OPEN_BRANDS = re.compile(r"(tongyi|qianwen|千问|通义|(?<![a-z])qwen(?![a-z])|deepseek|kimi|moonshot|zcode|zhipu|智谱|"
                              r"doubao|豆包|workbuddy|codebuddy)", re.I)

APP_DIRS = ("/System/Applications", "/System/Applications/Utilities", "/Applications", "/Applications/Utilities",
            os.path.expanduser("~/Applications"), "/System/Library/CoreServices/Applications",
            "/System/Cryptexes/App/System/Applications")      # 新版 macOS 的 Safari 真身在这(「应用程序」里那个是链接)


_HOST_HOME = os.environ.pop("SEEU_HOST_HOME", None)   # 读一次就从环境里拿掉,别传给被打开的程序(那边再起 SeeU 会误认成千问)


def enabled():
    """这次的 MCP 服务要不要给「打开 App」工具。
    SEEU_OPEN_APP=1 / 0 强制开关(测试用);否则看运行 SeeU 的程序是不是 NEED_OPEN 里的。"""
    v = os.environ.get("SEEU_OPEN_APP", "").strip()
    if v in ("1", "0"):
        return v == "1"
    try:
        from seeu import safety
        if safety.host_bundles() & set(NEED_OPEN):
            return True
        for p in safety.host_pids():
            if NEED_OPEN_BRANDS.search(" ".join(safety._info(p)[:2])):
                return True
    except Exception:
        pass
    # 千问拉起工具时把 HOME 换成它自己的文件夹,npm 启动包把原值放在 SEEU_HOST_HOME(父进程链断了时的兜底)
    h = (_HOST_HOME or "").lower()
    return "/qwen-agent/" in h and "/custom-mcp/" in h


def _running(bundle=None, name=None):
    from AppKit import NSWorkspace
    from Foundation import NSRunLoop, NSDate
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        if (bundle and a.bundleIdentifier() == bundle) or (name and a.localizedName() == name):
            return a
    return None


def _in_app_dirs(path):
    """真实路径在不在那几个「应用程序」文件夹里(直接放在里面那一层;../ 和链接先解开)。"""
    rp = os.path.realpath(path)
    return rp.endswith(".app") and any(os.path.dirname(rp) == os.path.realpath(d) for d in APP_DIRS)


def find(name):
    """App 名 / 包名 → (路径, 包名, 显示名);找不到返回 None。
    只认那几个「应用程序」文件夹里的 App;名字里带 / 或 .. 的一律不认(原来写成路径就能开任意位置的 .app)。"""
    from AppKit import NSWorkspace
    from Foundation import NSBundle, NSFileManager
    name = str(name or "").strip()
    if name.lower().endswith(".app"):
        name = name[:-4]
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("~") or "\0" in name:
        return None
    ws, fm = NSWorkspace.sharedWorkspace(), NSFileManager.defaultManager()
    path = None
    if "." in name and " " not in name and not name.endswith(".app"):      # 包名 com.apple.Notes
        u = ws.URLForApplicationWithBundleIdentifier_(name)
        p = str(u.path()) if u else None
        path = p if p and _in_app_dirs(p) else None
    if not path:
        for d in APP_DIRS:
            p = os.path.join(d, f"{name}.app")
            if os.path.isdir(p) and _in_app_dirs(p):
                path = p
                break
    if not path:                        # 显示名跟文件名不一样的(文件名英文、显示名中文这类)
        for d in APP_DIRS:
            try:
                for fn in os.listdir(d):
                    if fn.endswith(".app"):
                        p = os.path.join(d, fn)
                        dn = str(fm.displayNameAtPath_(p) or "")
                        if name in (dn, dn[:-4] if dn.endswith(".app") else dn) and _in_app_dirs(p):
                            path = p
                            break
            except OSError:
                pass
            if path:
                break
    if not path:
        return None
    path = os.path.realpath(path)
    b = NSBundle.bundleWithPath_(path)
    bundle = str(b.bundleIdentifier() or "") if b else ""
    dn = str(fm.displayNameAtPath_(path) or os.path.basename(path))
    return path, bundle, (dn[:-4] if dn.endswith(".app") else dn)


# 能被 AI 借来跑命令 / 交出电脑的 —— 别的 AI 客户端(往对话框里打字让它跑命令)、远程协助 / 屏幕共享
AI_OR_REMOTE = re.compile(r"(anthropic|claude|openai|chatgpt|codex|cursor|\btrae\b|windsurf|codeium|github copilot|"
                          r"microsoft copilot|^copilot$|com\.microsoft\.copilot|workbuddy|doubao|kimi|moonshot|deepseek|lingma|"
                          r"qoder|qianwen|千问|tongyi|通义|\bqwen\b|yuanbao|元宝|perplexity|ollama|lm ?studio|lmstudio|zhipu|智谱|zcode|"
                          r"chatglm|\bkiro\b|antigravity|\bvoid\b|"
                          r"screensharing|screen sharing|屏幕共享|teamviewer|anydesk|todesk|sunlogin|向日葵|parsec|rustdesk|"
                          r"splashtop|chrome ?remote|remote ?desktop|远程|遠端|windows app|com\.microsoft\.rdc|\bvnc|realvnc|"
                          r"jump desktop|jumpdesktop|edovia|\bscreens\b|anyviewer|nomachine)", re.I)
# 开了就能跑命令 / 改系统的 —— 终端名单外的终端、带命令行的 IDE、能跑脚本的启动器、虚拟机、磁盘工具这类
CAN_RUN = re.compile(r"(wave ?terminal|\brio\b|termius|electerm|securecrt|royal ?tsx|tabby|\bhyper\b|co\.zeit\.hyper|\bwarp\b|"
                     r"visual studio code|^code$|vscodium|com\.microsoft\.vscode|com\.visualstudio|xcode|jetbrains|intellij|"
                     r"pycharm|webstorm|goland|clion|rider|phpstorm|rubymine|datagrip|android studio|\bzed\b|sublime text|"
                     r"^nova$|com\.panic\.nova|bbedit|raycast|alfred|keyboard ?maestro|hammerspoon|bettertouchtool|"
                     r"parallels desktop|com\.parallels\.desktop|\butm\b|vmware|virtualbox|crossover|"
                     r"disk utility|磁盘工具|migration assistant|迁移助理|activity monitor|活动监视器|boot camp|"
                     r"installer|安装器|system information|系统信息|console$|控制台$)", re.I)


def _is_applet(path, bundle):
    """脚本编辑器 / 自动操作存出来的小程序:一打开就执行里面的脚本,跟开终端一样。"""
    if bundle.startswith("com.apple.ScriptEditor.id") or bundle.startswith("com.apple.automator."):
        return True
    c = os.path.join(path, "Contents")
    if os.path.exists(os.path.join(c, "document.wflow")) or os.path.exists(os.path.join(c, "Resources", "Scripts", "main.scpt")):
        return True
    try:
        import plistlib
        with open(os.path.join(c, "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        exe = str(info.get("CFBundleExecutable", ""))
        if exe in ("applet", "Application Stub", "droplet"):
            return True
        with open(os.path.join(c, "MacOS", exe), "rb") as f:     # Platypus 这类:可执行文件就是一段 #! 脚本
            return f.read(2) == b"#!"
    except Exception:
        return False


def why_not(path, bundle, name):
    """能不能替 AI 打开:能 → None;不能 → 原因。"""
    from seeu import safety, web
    path = os.path.realpath(path)
    if web.is_browser(name) or web._by_bundle(bundle) or re.search(
            r"(browser|浏览器|\bopera\b|vivaldi|夸克|quark|yandex|firefox|safari)", f"{name} {bundle}", re.I) \
            or re.search(r"^(arc|dia|comet|zen|zen browser)$", name.strip(), re.I):
        return f"{name} 是浏览器,开网页请用 seeu_web_open(网址要过允许名单)"
    if name in safety.TERMINALS or bundle in safety.TERMINALS.values():
        return f"{name} 是终端,SeeU 不替你打开"
    if bundle in safety.SCRIPT_APPS or name in safety.SCRIPT_APP_NAMES or _is_applet(path, bundle):
        return f"{name} 能直接运行脚本,SeeU 不替你打开"
    if bundle in safety.PASSWORD_APPS or bundle == "com.apple.keychainaccess":
        return f"{name} 里存的是密码,SeeU 不替你打开"
    if name in safety.SETTINGS_APPS or bundle in ("com.apple.systempreferences", "com.apple.Settings"):
        return "系统设置可能直接开在隐私与安全性那页,SeeU 不替你打开"
    if AI_OR_REMOTE.search(name) or AI_OR_REMOTE.search(bundle):
        return f"{name} 是 AI 客户端或远程协助程序,SeeU 不替你打开"
    if CAN_RUN.search(name) or CAN_RUN.search(bundle):
        return f"{name} 打开后能直接运行命令或改系统,SeeU 不替你打开"
    try:
        if bundle and bundle in safety.host_bundles():
            return f"{name} 是正在运行 SeeU 的程序"
    except Exception:
        pass
    if not _in_app_dirs(path):
        return f"{name} 不在「应用程序」文件夹里,SeeU 不替你打开"
    if "/CoreServices/" in path and not path.startswith("/System/Library/CoreServices/Applications/"):
        return f"{name} 是系统自己的组件,SeeU 不替你打开"
    return None


def open_app(app, wait_s=15):
    """后台打开 App。返回 dict(outcome, reason, note, name)。"""
    from seeu import ax, bgclick as bg
    from seeu_lib import input_guard as ig
    name = str(ax.split_window(app)[0] or "").strip()
    if not name:
        return {"outcome": "failed", "reason": "没写要打开哪个 App"}
    hit = find(name)
    if not hit:
        return {"outcome": "failed", "reason": f"找不到叫「{name}」的 App(装在「应用程序」文件夹里的才找得到),请用户确认 App 名"}
    path, bundle, dname = hit
    w = why_not(path, bundle, dname)
    if w:
        return {"outcome": "refused", "reason": f"{w}(这一步请你自己来)", "name": dname}
    ra = _running(bundle or None, None if bundle else dname)
    if ra is not None:
        n = str(ra.localizedName())
        return {"outcome": "delivered", "name": n, "note": f"{n} 已经开着,没动它(没拉到前台)。用 seeu_see 看它的画面"}

    front = ig.frontmost_app()
    from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration
    from Foundation import NSURL, NSRunLoop, NSDate
    cfg = NSWorkspaceOpenConfiguration.configuration()
    cfg.setActivates_(False)            # 不激活:窗口开在后面,不抢前台
    cfg.setAddsToRecentItems_(False)
    err = []
    done = []

    def _cb(running_app, error):
        if error is not None:
            err.append(str(error.localizedDescription()))
        done.append(True)

    NSWorkspace.sharedWorkspace().openApplicationAtURL_configuration_completionHandler_(
        NSURL.fileURLWithPath_(path), cfg, _cb)
    t0, ra, win = time.time(), None, None
    while time.time() - t0 < wait_s:                     # 硬上限:最多等 wait_s 秒
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
        if err:
            return {"outcome": "failed", "name": dname, "reason": f"系统没打开 {dname}:{err[0]}"}
        ra = ra or _running(bundle or None, None if bundle else dname)
        if ra is not None:
            win = bg.main_window(str(ra.localizedName()))
            if win:
                break
    n = str(ra.localizedName()) if ra is not None else dname
    if ra is None:
        return {"outcome": "failed", "name": dname, "reason": f"等了 {wait_s}s {dname} 还没开起来"}

    # 有的 App 一打开就自己跳到最前面(有的晚一两秒才跳):1.5 秒内看几次,是它占了前台才切回用户原来的程序
    # (用户这期间自己换了程序,前台就不是它,不动)。切回用 NSRunningApplication,不走 osascript(会卡、会弹授权框)
    note, stole, back = "", False, True
    pid = int(ra.processIdentifier())
    for _ in range(5):
        time.sleep(0.3)
        fa = ig.frontmost_app()
        if fa and front and fa["pid"] == pid and front["pid"] != pid:
            stole = True
            from AppKit import NSRunningApplication
            r0 = NSRunningApplication.runningApplicationWithProcessIdentifier_(front["pid"])
            if r0:
                r0.activateWithOptions_(0)
            time.sleep(0.2)
            fb = ig.frontmost_app()                 # 新系统里「返回成功但没切过去」:按实际前台说
            back = bool(fb and fb["pid"] == front["pid"])
    if stole:
        note = (f"{n} 打开时自己跳到了最前面,已切回 {front['name']}。" if back
                else f"{n} 打开时自己跳到了最前面,没能切回 {front['name']}。")
    if not win:
        return {"outcome": "unverified", "name": n,
                "note": note + f"{n} 开起来了,但还没看到它的窗口。等一两秒再 seeu_see 看看"}
    return {"outcome": "delivered", "name": n,
            "note": note + f"已在后台打开 {n}(没拉到前台)。接下来用 seeu_see 看它的画面"}
