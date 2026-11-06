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


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
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
