"""动作:python3 -m seeu see|tap|type|scroll|press|menu|base|home|open <App> ...
    例:python3 -m seeu see TextEdit   ·   python3 -m seeu tap TextEdit 加粗   ·   python3 -m seeu type TextEdit "你好" --enter
管理:python3 -m seeu isee on|off|status|report   ·   python3 -m seeu allow|disallow 网址   ·   python3 -m seeu allowed
python3 -m seeu 取证 [--shot]   出事时(被抢键盘、打字跑错地方)一键记下现场
python3 -m seeu 检查 [--open]   看本机缺哪些授权/开关,缺的逐项写怎么开
python3 -m seeu mcp             以 MCP 服务方式运行(给 Codex 等 AI 客户端接,见 mcp_server.py)
python3 -m seeu 接入 [codex|claude|自动] [--本项目]   一键接入 MCP + Skill;python3 -m seeu 移除 codex|claude
python3 -m seeu 更新 [--check]  更新到 GitHub 上的新版(git clone 装的才行)
python3 -m seeu 探一下 <App>     看这个 App 能不能用 SeeU 自动化、会走哪条路(只读)
python3 -m seeu 设置 [借用鼠标 开|问我|关]   看 / 改设置
python3 -m seeu 版本            看装的是哪一版(英文 --version)"""
import sys

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
