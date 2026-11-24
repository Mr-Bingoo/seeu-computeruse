"""动作:python3 -m seeu see|tap|type|scroll|press|menu|base|home|open <App> ...
    例:python3 -m seeu see TextEdit   ·   python3 -m seeu tap TextEdit 加粗   ·   python3 -m seeu type TextEdit "你好" --enter
管理:python3 -m seeu isee on|off|status|report   ·   python3 -m seeu allow|disallow 网址   ·   python3 -m seeu allowed
python3 -m seeu 取证 [--shot]   出事时(被抢键盘、打字跑错地方)一键记下现场
python3 -m seeu 检查 [--open]   看本机缺哪些授权/开关,缺的逐项写怎么开
python3 -m seeu mcp             以 MCP 服务方式运行(给 Codex 等 AI 客户端接,见 mcp_server.py)
python3 -m seeu 接入 [claude|codex|cursor|trae|vscode|自动] [--本项目]   一键接入 MCP + Skill;python3 -m seeu 移除 <同上>
python3 -m seeu 更新 [--check]  更新到 GitHub 上的新版(git clone 装的才行)
python3 -m seeu 探一下 <App>     看这个 App 能不能用 SeeU 自动化、会走哪条路(只读)
python3 -m seeu 设置 [借用鼠标 开|问我|关]   看 / 改设置
python3 -m seeu 版本            看装的是哪一版(英文 --version)"""
import sys


def _ai_gate(args, what):
    """11-06 体检:加名单、改借用鼠标这两条命令,AI 客户端自己就能跑(只有 isee on 拦了),等于绕开 MCP 那边的「先问用户」。
    现在跟 MCP 一样:AI 在跑就要带 --user-said "用户原话",并弹提示条留痕。人自己在终端敲的不受影响。
    what:拿去掉 --user-said 之后的参数拼出「要做的事」的函数。返回 (去掉 --user-said 的参数, 能不能继续)。"""
    args = list(args)
    said = ""
    if "--user-said" in args:
        i = args.index("--user-said")
        said = (args[i + 1] if i + 1 < len(args) else "").strip()
        del args[i:i + 2]
    from seeu import isee
    if not isee.from_ai():
        return args, True
    try:
        from seeu.i18n import lang
        en = lang() == "en"
    except Exception:
        en = False
    what = what(args)
    if not said:
        if en:
            print(f"Not done: this command is being run by an AI client. \"{what}\" needs the user's OK first: ask in the chat, "
                  "then re-run with --user-said \"their reply\" (use the seeu_allow_site / seeu_manage tools if you have them).")
        else:
            print(f"没做:这条命令是 AI 客户端在跑。「{what}」要先在对话里问用户,答应了再带上 --user-said \"用户的原话\" 重跑"
                  "(有 seeu_allow_site / seeu_manage 工具的直接用工具)。")
        return args, False
    try:
        from seeu_lib import cursor_overlay as co
        co.toast("SeeU", (f"The AI did this for you: {what}" if en else f"AI 帮你做了:{what}"), 8)
    except Exception:
        pass
    return args, True


def _win_stdio():
    """11-14 复查:输出被接走(AI 客户端、管道、重定向)时 Windows 按系统代码页编码,✅ ⛔ 和中文在英文系统(cp1252)上
    一打印就崩。接走时统一用 UTF-8;在真终端里只保证打不出的字不崩。"""
    for s in (sys.stdout, sys.stderr):
        try:
            if s.isatty():
                s.reconfigure(errors="replace")
            else:
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _win_by_person():
    """这条命令是不是人自己在终端里敲的。没有终端 = 程序 / AI 调的;有终端但带着 AI 客户端的环境变量
    (在客户端自带的终端里跑)也算 AI 调的。"""
    import os
    if os.environ.get("CLAUDECODE") or os.environ.get("CODEX_SANDBOX") or os.environ.get("CURSOR_TRACE_ID"):
        return False
    # 🔴 不能用 sys.stdin.isatty():输入接到空设备(< NUL)时它也说是终端(11-14 实测,不带原话就改了设置)。
    #    问系统「这是不是真的控制台」,而且输入、输出都得是(输出被接走的多半是程序在跑)。
    try:
        import ctypes
        import msvcrt
        k = ctypes.windll.kernel32
        k.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]

        def con(fd):
            m = ctypes.c_uint32()
            return bool(k.GetConsoleMode(msvcrt.get_osfhandle(fd), ctypes.byref(m)))
        return con(0) and con(1)
    except Exception:
        return False


def _win_isee_ai():
    """isee on 专用、比 _win_by_person 再严一层(11-16 复查):编辑器 / AI 客户端的内置终端在 Windows 上是伪控制台,
    _win_by_person 会当成人。这里再看①编辑器、AI 命令行留下的环境变量 ②父进程链里有没有 AI 客户端 / 编辑器。
    查不了进程表就当是 AI(宁可拦错,用户可以点浮标上的 I See 按钮)。"""
    import os
    env = os.environ
    if env.get("TERM_PROGRAM", "").lower() == "vscode" or any(
            env.get(k) for k in ("VSCODE_PID", "VSCODE_IPC_HOOK_CLI", "VSCODE_INJECTION", "GEMINI_CLI")):
        return True
    try:
        from seeu import isee
        from seeu.win import safety
        names = tuple(isee.AI_PROCS) + ("code.exe", "code - insiders.exe", "qianwen", "chatgpt", "windsurf")
        table = safety._process_table()
        cur, seen = os.getpid(), set()
        while cur and cur not in seen and cur in table:
            seen.add(cur)
            parent, name = table[cur]
            n = name.lower()
            if n in safety._STOP:
                break
            if any(k in n for k in names):
                return True
            cur = parent
        return False
    except Exception:   # noqa: BLE001
        return True


def _win_key_confirm(lg, secs=60):
    """isee on 的现场确认(11-16 复查):随机一个字母,要人在这个控制台的键盘上按。读的是控制台键盘(msvcrt),不是 stdin,
    AI 在新开的窗口里跑这条命令也答不上来。最多等 secs 秒,超时算取消(别让藏着的窗口一直挂着)。"""
    import msvcrt
    import random
    import time
    ch = random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
    while msvcrt.kbhit():          # 先清掉之前积在键盘缓冲里的键
        msvcrt.getwch()
    print(lg.L(f"要打开 I See(我知风险),请在键盘上按字母 {ch} 确认,按别的键取消({secs} 秒内):",
               f"To turn on I See (I know the risks), press the letter {ch} to confirm, any other key cancels (within {secs} s):"),
          end=" ", flush=True)
    t0 = time.time()
    while time.time() - t0 < secs:
        if msvcrt.kbhit():
            k = msvcrt.getwch()
            print(k)
            return k.upper() == ch
        time.sleep(0.05)
    print()
    return False


def _win_gate_log(what, said):
    """带着 --user-said 放行的,记一行(跟 MCP 那边记在同一个文件),事后查得到。记不上不影响命令。"""
    try:
        import os
        import time
        from seeu_lib import home
        p = home("seeu_mcp.log")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  cli  {what}  user_said={said[:200]!r}\n")
    except Exception:
        pass
    try:                     # 屏幕上留痕(同 Mac 的 _ai_gate):AI 代你做了什么
        from seeu.win import cursor, lang
        cursor.toast("SeeU", lang.L(f"AI 帮你做了:{what}", f"The AI did this for you: {what}"), 8)
    except Exception:
        pass


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    # 11-22 C-3.7:插件版已经由 Claude Code / Codex 接好了,再「接入」会多出一份同样的工具 → 说清楚、不做(「看接了没有」照常)
    if cmd in ("接入", "install") and len(args) > 1:
        try:
            from seeu.where import as_plugin as _asp
            _plugin = _asp()
        except Exception:   # noqa: BLE001
            _plugin = False
        if _plugin:
            from seeu.i18n import T as _T
            print(_T("inst.plugin"))
            sys.exit(1)
    if sys.platform.startswith("linux"):   # 11-18:Linux 预览版(第 1 段),命令都在 seeu/linux/
        import seeu as _seeu                 # 包里没有 linux/ 时,这一行会给「只支持 macOS」的话
        if cmd == "mcp":                     # 11-18 第 2 段
            from seeu.linux import mcp_server as _lmcp
            _lmcp.main()
            sys.exit(0)
        if cmd in ("设置", "settings", "set"):
            args, ok = _ai_gate(args, lambda a: "改设置:" + " ".join(a[1:])) if len(args) > 1 else (args, True)
            if not ok:
                sys.exit(3)
            from seeu.linux import real as _lreal
            sys.exit(_lreal.settings_cmd(args[1:]))
        if cmd in ("接入", "install", "移除", "uninstall", "remove"):
            from seeu.linux import install as _linst
            sys.exit(_linst.main(cmd, args[1:]))
        if cmd in ("allow", "disallow", "allowed"):
            from seeu.web import aejs as _aejs
            if cmd == "allowed":
                print("\n".join(_aejs.allowed_list()) or "(允许名单是空的)")
                sys.exit(0)
            args, ok = _ai_gate(args, lambda a: ("把 " if cmd == "allow" else "从允许名单拿掉 ") + " ".join(a[1:])
                                + (" 加进允许名单" if cmd == "allow" else ""))
            if not ok:
                sys.exit(3)
            for u in args[1:]:
                _aejs.allow(u, on=(cmd == "allow"))
                print(("已加进允许名单:" if cmd == "allow" else "已从允许名单拿掉:") + u)
            sys.exit(0)
        if cmd in ("更新", "update"):            # 11-18 C-3.0
            from seeu import update as _upd
            sys.exit(_upd.main(args[1:]))
        if cmd in ("检查", "check", "doctor"):
            from seeu.linux import doctor as _ldoc
            sys.exit(_ldoc.main(args[1:]))
        if cmd in ("版本", "version", "--version", "-v"):
            from seeu import version
            print("SeeU v" + version.current() + " (Linux preview)")
            sys.exit(0)
        from seeu.linux import act as _lact
        sys.exit(_lact.main(args))
    if sys.platform == "win32":          # 11-11:Windows 预览版,命令都在 seeu/win/
        if cmd == "mcp":
            from seeu.win import mcp_server as _wmcp
            _wmcp.main()
            sys.exit(0)
        _win_stdio()
        if cmd in ("接入", "install", "移除", "uninstall", "remove"):
            from seeu.win import install as _winst
            sys.exit(_winst.main(cmd, args[1:]))
        if cmd in ("版本", "version", "--version", "-v"):
            from seeu import version
            print("SeeU v" + version.current() + " (Windows preview)")
            sys.exit(0)
        if cmd in ("allow", "disallow", "allowed"):
            from seeu.web import aejs
            from seeu.win import lang as _lg
            if cmd == "allowed":
                print(_lg.L("允许名单:", "Allow list:"), aejs.allowed_list())
                sys.exit(0)
            rest = list(args[1:])
            said = ""
            if "--user-said" in rest:
                i = rest.index("--user-said")
                said = (rest[i + 1] if i + 1 < len(rest) else "").strip()
                del rest[i:i + 2]
            # 人在终端里敲的(有终端)直接做;程序 / AI 调的(没有终端)要带用户原话(跟 Mac 版 _ai_gate 一个意思)
            # 11-16 复查:编辑器 / AI 客户端的内置终端是伪控制台,_win_by_person 会当成人 → 跟 isee on 一样再查父进程链
            if cmd == "allow" and not said and (not _win_by_person() or _win_isee_ai()):
                print(_lg.L("没做:这条命令不是人在终端里敲的。要先问用户,答应了带上 --user-said \"用户的原话\" 重跑"
                            "(有 seeu_allow_site 工具就用工具)。就是你本人的话:在 cmd / PowerShell 窗口里直接运行,别把输出接走。",
                            "Not done: this command wasn't typed by a person in a terminal. Ask the user first, then re-run with "
                            "--user-said \"their reply\" (use the seeu_allow_site tool if you have it). If this is you: run it directly "
                            "in a cmd / PowerShell window, without redirecting the output."), file=sys.stderr)
                sys.exit(3)
            if not rest:
                print(_lg.L("用法:python -m seeu allow|disallow 网址", "Usage: python -m seeu allow|disallow <site>"))
                sys.exit(2)
            if cmd == "allow" and said:
                _win_gate_log("allow " + rest[0], said)
            print(_lg.L("允许名单:", "Allow list:"), aejs.allow(rest[0], on=cmd == "allow"))
            sys.exit(0)
        if cmd == "isee":                    # 11-16:照 Mac 版 isee on|off|status|report
            from seeu import isee
            from seeu.win import lang as _lg
            sub = args[1] if len(args) > 1 else "status"
            if sub == "on":
                # 🔴 只让人自己开:Mac 的 isee.from_ai 靠 ps 查父进程,Windows 上没有 ps 会一律当「不是 AI」放行,
                #    所以这里用 _win_by_person(真控制台 + 没有 AI 客户端的环境变量)+ _win_isee_ai(编辑器终端、父进程链)
                #    + 现场按键确认(防 AI 新开一个控制台窗口来跑)。不收 --user-said(AI 永远不能替人开)。
                if not _win_by_person() or _win_isee_ai():
                    print(_lg.L("I See 只能你自己开:点 SeeU 悬浮窗上的「I See」按钮(网页任务时才有),"
                                "或者在系统的 cmd / PowerShell 窗口里直接运行这条命令(编辑器、AI 客户端自带的终端不算,别把输出接走)。AI 不能替你开。",
                                "Only you can turn on I See: click the I See button on the SeeU floating window (it shows during web tasks), "
                                "or run this command directly in a Windows cmd / PowerShell window (not a terminal inside an editor or AI app, "
                                "and without redirecting the output). The AI can't turn it on for you."), file=sys.stderr)
                    sys.exit(3)
                try:
                    hours = float(args[2]) if len(args) > 2 else isee.DEFAULT_HOURS
                    if not (hours == 0 or 1 / 60 <= hours <= 24 * 365):
                        raise ValueError
                except ValueError:
                    print(_lg.L("用法:python -m seeu isee on [小时](0 = 不自动关;最短 1 分钟,最长一年)",
                                "Usage: python -m seeu isee on [hours] (0 = never turns off by itself; 1 minute to 1 year)"), file=sys.stderr)
                    sys.exit(2)
                try:
                    isee.on(hours, by="console")      # 11-16 复查:三道门(含现场按键)在 isee.on 里自己再查,不信这里
                    st = isee.status()
                except PermissionError:
                    print(_lg.L("没开:没有按对确认键(或不是在 cmd / PowerShell 窗口里直接运行)。",
                                "Not turned on: the confirmation key wasn't pressed (or this isn't a cmd / PowerShell window)."), file=sys.stderr)
                    sys.exit(3)
                except Exception as ex:   # noqa: BLE001   设置文件坏了 / 写不进
                    print(_lg.L(f"没开成:{ex}", f"Couldn't turn it on: {ex}"), file=sys.stderr)
                    sys.exit(1)
                if not st.get("on"):
                    print(_lg.L("没开成:写进去了但读回来是关着(看一下设置文件)。", "Didn't take: it reads back as off (check the settings file)."),
                          file=sys.stderr)
                    sys.exit(1)
                print(_lg.L("I See 开了", "I See is on") + (_lg.L(f",到 {st['until']} 自动关", f", turns off at {st['until']}")
                                                           if st.get("until") else _lg.L("(不自动关)", " (won't turn off by itself)")))
            elif sub == "off":
                try:
                    isee.off()
                except Exception as ex:   # noqa: BLE001
                    print(_lg.L(f"没关成:{ex}", f"Couldn't turn it off: {ex}"), file=sys.stderr)
                    sys.exit(1)
                st = isee.status()
                print(_lg.L("I See 关了", "I See is off"))
            elif sub == "report":
                print(isee.report())
            elif sub == "status":
                st = isee.status()
                src = _lg.L("环境变量 SEEU_ISEE", "the SEEU_ISEE environment variable") if st.get("source") == "环境变量" else _lg.L("设置文件", "settings file")
                print(_lg.L("开着" if st["on"] else "关着", "on" if st["on"] else "off")
                      + (_lg.L(f",到 {st['until']}", f", until {st['until']}") if st.get("on") and st.get("until") else "")
                      + _lg.L(f"(来源:{src})", f" (from {src})")
                      + (_lg.L(";设置里写着开,但不是你用按钮 / 命令开的(或是升级前开的),按关算;要用请重新开一次",
                               "; the settings file says on, but it wasn't turned on with the button / command (or was turned on before "
                               "an update), so it counts as off; turn it on again if you need it") if st.get("forged") else ""))
            else:
                print(_lg.L("用法:python -m seeu isee on [小时] | off | status | report",
                            "Usage: python -m seeu isee on [hours] | off | status | report"), file=sys.stderr)
                sys.exit(2)
            sys.exit(0)
        if cmd in ("探一下", "probe"):        # 11-12
            from seeu.win import probe as _wprobe
            sys.exit(_wprobe.main(args[1:]))
        # 11-14:检查 / 设置 / 更新 / 取证(照 Mac 版)
        if cmd in ("检查", "check", "doctor"):
            from seeu.win import doctor as _wdoc
            sys.exit(_wdoc.main(args[1:]))
        if cmd in ("设置", "set", "settings"):
            rest = list(args[1:])
            said = ""
            if "--user-said" in rest:
                i = rest.index("--user-said")
                said = (rest[i + 1] if i + 1 < len(rest) else "").strip()
                del rest[i:i + 2]
            # 改设置跟加名单一个规矩:人在终端里敲的直接做;程序 / AI 调的要带用户原话。只看不改不用
            if rest and not said and (not _win_by_person() or _win_isee_ai()):     # 11-16:同 allow
                from seeu.win import lang as _lg
                print(_lg.L("没做:这条命令不是人在终端里敲的。改设置要先问用户,答应了带上 --user-said \"用户的原话\" 重跑。"
                            "就是你本人的话:在 cmd / PowerShell 窗口里直接运行,别把输出接走。",
                            "Not done: this command wasn't typed by a person in a terminal. Changing a setting needs the user's OK first: "
                            "ask them, then re-run with --user-said \"their reply\". If this is you: run it directly in a cmd / PowerShell window, "
                            "without redirecting the output."), file=sys.stderr)
                sys.exit(3)
            if rest and said:
                _win_gate_log("set " + " ".join(rest[:2]), said)
            from seeu.win import act as _wact
            sys.exit(_wact.settings_cmd(rest))
        if cmd in ("更新", "update"):
            from seeu import update as _upd
            sys.exit(_upd.main(args[1:]))
        if cmd in ("取证", "evidence"):
            from seeu.win import evidence as _wev
            sys.exit(_wev.main(args[1:]))
        from seeu.win import act as _wact
        sys.exit(_wact.main(args))
    if cmd in ("see", "tap", "type", "scroll", "press", "menu", "base", "home", "open"):
        from seeu import act
        sys.exit(act.main(args))
    elif cmd == "isee":
        from seeu import isee
        isee.main(args[1:])
    elif cmd in ("allow", "disallow") and len(args) > 1:
        if cmd == "allow":
            args, ok = _ai_gate(args, lambda a: "allow " + (a[1] if len(a) > 1 else ""))
            if not ok:
                sys.exit(3)
        if len(args) < 2:               # 只给了 --user-said、没给网址
            print(__doc__)
            sys.exit(2)
        from seeu.web import aejs
        print("允许名单(Safari 开关、Chrome 插件共用一份):", aejs.allow(args[1], on=cmd == "allow"))
        if cmd == "allow":
            print("用 Chrome 插件的话,还要在这个网页上点浏览器右上角的 SeeU 图标、选「允许这个网站」一次(Chrome 规定要你亲手点)")
    elif cmd in ("取证", "evidence"):
        from seeu import evidence
        evidence.main(args[1:])
    elif cmd in ("检查", "check", "doctor"):
        from seeu import doctor
        sys.exit(doctor.main(args[1:]))
    elif cmd in ("接入", "install", "移除", "uninstall", "remove"):
        from seeu import install
        sys.exit(install.main(cmd, args[1:]))
    elif cmd in ("设置", "set", "settings"):
        if len(args) > 2:
            args, ok = _ai_gate(args, lambda a: "set " + " ".join(a[1:3]))
            if not ok:
                sys.exit(3)
        from seeu import act
        sys.exit(act.settings_cmd(args[1:]))
    elif cmd in ("探一下", "probe"):
        from seeu import probe
        sys.exit(probe.main(args[1:]))
    elif cmd in ("更新", "update"):
        from seeu import update
        sys.exit(update.main(args[1:]))
    elif cmd in ("版本", "version", "--version", "-v"):
        from seeu import version
        print("SeeU v" + version.current())
    elif cmd == "mcp":
        from seeu import mcp_server
        mcp_server.main()
    elif cmd == "allowed":
        from seeu.web import aejs
        print("允许名单(Safari 开关、Chrome 插件共用一份):", aejs.allowed_list())
    else:
        print(__doc__)
