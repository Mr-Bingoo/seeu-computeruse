# -*- coding: utf-8 -*-
"""SeeU 检查授权(C-0.9,10-24):一条命令看本机缺哪些授权/开关,缺的逐项写怎么开。

    python3 -m seeu 检查            # 只查不改;没开着的浏览器不会被打开
    python3 -m seeu 检查 --open     # 另外把缺的那几项的系统设置页打开(只打开,勾选要你亲手)

查什么:辅助功能、屏幕录制、后台点击私有接口、iPhone 镜像、每个装了的浏览器(开关 / 插件 / 自动化)、隐身 Chrome 专用配置的开关。
「怎么开」只从 isee.FIXES 固定清单里给(跟卡住时说的一样)。授权是给"运行这条命令的程序"的(Claude 或终端),不是 Python。
🔴 浏览器开着时会试一下开关,第一次可能弹「允许控制 Safari / Chrome」,点允许(跟 I See 开启体检一样)。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OK, BAD, NA = "✅", "❌", "—"


def _bundle_name(app_dir):
    """系统设置授权列表里显示的名字:实测是 .app 文件名(10-31:Claude 自带的 claude.app 包名叫「Claude Code」,设置里却显示「claude」)。"""
    return os.path.basename(app_dir)[:-4]


def _responsible():
    """问系统谁是本进程的负责进程(私有接口,只当加速层;拿不到返回 None,退回看父进程链)。"""
    try:
        import ctypes
        f = ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
        f.restype, f.argtypes = ctypes.c_int, [ctypes.c_int]
        r = f(os.getpid())
        if r <= 0:
            return None
        return subprocess.run(["ps", "-o", "comm=", "-p", str(r)], capture_output=True, text=True, timeout=3).stdout.strip() or None
    except Exception:
        return None


def host_app():
    """授权对象 = 系统认的"负责进程"。找不到返回 None。
    默认是父进程链里最外层的 .app(终端、Claude);但链里有 Claude 的 disclaimer 时,它下面那一个才是负责进程
    (10-31 实测:Code 页 = Claude 自带的 claude.app;聊天页直接拉起 Python → 授权要给 Python;接 SeeU 小程序后 = SeeU)。"""
    chain, pid = [], os.getpid()
    for _ in range(20):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception:
            break
        if not out:
            break
        ppid, comm = out.split(None, 1)
        chain.append(comm)
        if ppid in ("0", "1"):
            break
        pid = int(ppid)
    pick = _responsible()
    for i, comm in enumerate(chain if pick is None else []):
        if comm.endswith("/Helpers/disclaimer") and i > 0:
            pick = chain[i - 1]
            break
    if not pick:
        apps = [c for c in chain if ".app/" in c]
        pick = apps[-1] if apps else None
    if not pick:
        return None
    if "python" in os.path.basename(pick).lower():
        return "python3"            # 10-31:聊天页直接拉起 Python 后,设置里出现的是「python3」
    if ".app/" in pick:
        return _bundle_name(pick.rsplit(".app/", 1)[0] + ".app")
    return os.path.basename(pick)


def _w(s):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fix(key):
    from seeu import isee
    return isee.fix_plan(key)


def _row(rows, ok, name, note="", fix=None):
    rows.append(dict(ok=ok, name=name, note=note, fix=fix))


def check():
    """返回 [{ok: ✅/❌/—, name, note, fix(FIXES 键或 None)}]。"""
    rows = []
    try:
        from seeu import ax
        t = ax.trusted()
    except Exception as e:
        t = None
        _row(rows, NA, "辅助功能", f"查不到({e.__class__.__name__})")
    if t is not None:
        _row(rows, OK if t else BAD, "辅助功能", "按控件点、读控件、后台打字" if t else "没有:原生 App 和浏览器的控件操作做不了",
             None if t else "accessibility")

    try:
        import Quartz
        s = bool(Quartz.CGPreflightScreenCaptureAccess())
        _row(rows, OK if s else BAD, "屏幕录制", "看画面、认字、取证" if s else "没有:画面是黑的,认字、看画面全废",
             None if s else "screen")
    except Exception as e:
        _row(rows, NA, "屏幕录制", f"查不到({e.__class__.__name__})")

    try:                                 # 11-06 二次复查:截图、核实画面变没变都要这两个库,原来安装说明没写、这里也不查
        import cv2, numpy  # noqa: F401
        _row(rows, OK, "图像库(OpenCV、numpy)", "已装")
    except Exception:
        _row(rows, BAD, "图像库(OpenCV、numpy)",
             "没装:截图、核实画面都会报错。运行 /usr/bin/python3 -m pip install --user opencv-python-headless numpy")

    try:
        from seeu import bgclick
        a = bgclick.available()
        _row(rows, OK if a else BAD, "后台点击(SkyLight)", "可用" if a else "系统改了私有接口,只能退回真鼠标 + 让路")
    except Exception as e:
        _row(rows, BAD, "后台点击(SkyLight)", f"加载失败({e.__class__.__name__}),只能退回真鼠标")

    m = os.path.isdir("/System/Applications/iPhone Mirroring.app")
    _row(rows, OK if m else NA, "iPhone 镜像", "系统自带,已有" if m else "这台 Mac 没有(要 macOS 15+ 和配对的 iPhone)")

    rows += browsers()
    return rows


def _installed(app):
    return any(os.path.isdir(os.path.join(d, app + ".app")) for d in ("/Applications", os.path.expanduser("~/Applications")))


def _host_registered(app):
    from seeu.web import install
    d = install.found().get(app if app != "Brave Browser" else "Brave")
    if not d:
        return None
    try:
        return os.path.exists(os.path.join(d, "NativeMessagingHosts", install.HOST_NAME + ".json"))
    except OSError:
        return None


def browsers():
    from seeu.web import aejs, plugin_ready
    rows = []
    for app in ["Safari"] + sorted(aejs.CHROME_LIKE):
        if app != "Safari" and not _installed(app):
            continue
        chrome = app in aejs.CHROME_LIKE
        if not aejs.running(app):
            note = "没开着,开着时再查开关"
            if chrome:
                reg = _host_registered(app)
                note += ";插件中转" + ("已登记" if reg else "没登记(要插件路再装)" if reg is False else "查不到")
            _row(rows, NA, app, note)
            continue
        st = aejs.state(app)
        key = "aejs_safari" if app in aejs.SAFARI else "aejs_chrome"
        if st == "on":
            ok, note, fix = OK, "开关开着(读写网页)", None
        elif st == "switch_off":
            ok, note, fix = BAD, "开关没开:网页里只能靠辅助功能", key
        elif st == "denied":
            ok, note, fix = BAD, "系统没允许控制它", "automation"
        elif st == "timeout":
            ok, note, fix = BAD, "卡在系统授权弹窗上,去点「允许」", None
        elif st == "no_tab":
            ok, note, fix = NA, "没有窗口,判断不了开关", None
        else:
            ok, note, fix = NA, f"查不到({st})", None
        if chrome:
            if plugin_ready(app):
                note += ";插件在线 ✅"
                if ok == BAD and fix == key:      # 插件能顶开关
                    ok, fix = OK, None
                    note = note.replace("开关没开:网页里只能靠辅助功能", "开关没开(插件顶上)")
            else:
                note += ";插件不在线" + ("" if _host_registered(app) else "(中转没登记)")
        _row(rows, ok, app, note, fix)
    stealth_chrome(rows)
    cdp_apps(rows)
    return rows


def cdp_apps(rows):
    """C-1.0:本机哪些网页壳 App 能走调试端口(看 App 里带不带 Electron / CEF;不拉起,能不能真开端口要用时才知道)。"""
    try:
        from seeu import cdp, safety
        apps = [(n, k, b) for n, k, b in cdp.installed() if n != "Google Chrome"]
    except Exception as e:
        _row(rows, NA, "调试端口(网页技术做的 App)", f"查不到({e.__class__.__name__})")
        return
    ok = [n for n, k, b in apps if b not in safety.host_bundles()]
    if not ok:
        _row(rows, NA, "调试端口(网页技术做的 App)", "本机没有网页技术做的 App")
        return
    tested = [n for n in ok if n in cdp.TESTED]
    other = [n for n in ok if n not in cdp.TESTED]
    note = f"本机 {len(ok)} 个网页技术做的 App,测过能藏着用:" + "、".join(tested) + (";没试(有的会禁掉):" + "、".join(other) if other else "")
    if len(ok) < len(apps):
        note += ";Claude 不碰"
    _row(rows, OK, "调试端口(网页技术做的 App)", note + ";只用 SeeU 专用那份,你自己开着的不碰")


def stealth_chrome(rows):
    """隐身 Chrome 专用配置的「允许 Apple 事件中的 JavaScript」(用过隐身 Chrome 才查;读偏好文件,不开 Chrome)。"""
    from seeu import stealth
    p = os.path.join(stealth.CHROME_PROFILE, "Default", "Preferences")
    if not os.path.exists(p):
        return
    try:
        on = bool(json.load(open(p, encoding="utf-8")).get("browser", {}).get("allow_javascript_apple_events"))
    except Exception:
        on = None
    if on is None:
        _row(rows, NA, "隐身 Chrome 开关", "查不到")
    else:
        _row(rows, OK if on else NA, "隐身 Chrome 开关",
             "开着(后备)" if on else "没开:不要紧,C-1.0 起隐身 Chrome 读写页面走调试端口,这个开关只当后备")


def _register(rows):
    """经 SeeU 小程序跑、又缺授权时,向系统申请一次 → 「SeeU」出现在辅助功能 / 屏幕录制列表里(开关要用户亲手开)。"""
    miss = {r["fix"] for r in rows if r["fix"]}
    try:
        if "accessibility" in miss:
            import ApplicationServices as AS
            AS.AXIsProcessTrustedWithOptions({AS.kAXTrustedCheckOptionPrompt: True})
        if "screen" in miss:
            import Quartz
            Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    # 11-01:清单是给人看的,语言设成 English 时按 reason_en 的表转英文(中文时原样,不影响别的调用方)
    from seeu.i18n import lang
    if lang() == "en":
        from seeu.reason_en import to_en as _t
    else:
        _t = lambda x: x   # noqa: E731
    who = host_app()
    if who == "python3":
        print(_t("SeeU 检查授权 · 授权对象:python3(这家客户端直接拉起 Python;SeeU 小程序不在时才会这样,建议放回 seeu/launcher/SeeU.app,授权给「SeeU」)") + "\n")
    else:
        print(_t(f"SeeU 检查授权 · 授权对象:{who or '运行这条命令的程序'}(授权给它,不是给 Python)") + "\n")
    from seeu import version
    from seeu.i18n import T
    print("  " + T("ver.line", v=version.current()) + "\n")   # 11-01:报问题时一眼看出是哪版
    rows = check()
    for r in rows:
        r["name"], r["note"] = _t(r["name"]), _t(r["note"])
    if who == "SeeU":
        _register(rows)
    w = max(_w(r["name"]) for r in rows)
    for r in rows:
        print(f"  {r['ok']} {r['name']}{' ' * (w - _w(r['name']))}  {r['note']}")
    todo = [r for r in rows if r["fix"]]
    if not todo:
        print("\n" + _t("都齐了(— 是没装/没开着、查不了的,不算缺)。"))
        return 0
    print("\n" + _t("缺的,照这样开:"))
    seen = set()
    for r in todo:
        if r["fix"] in seen:
            continue
        seen.add(r["fix"])
        f = _fix(r["fix"])
        print(f"  · {_t(f['name'])}: {_t(f['how'])}" if lang() == "en" else f"  · {f['name']}:{f['how']}")
        if f["open"]:
            print("    " + _t("设置页:") + (" " if lang() == "en" else "") + f"open \"{f['open']}\"")
            if "--open" in argv:
                subprocess.Popen(["open", f["open"]])
    if "--open" not in argv and any(_fix(k)["open"] for k in seen):
        print("\n" + _t("加 --open 会把上面的设置页直接打开(只打开,勾选要你亲手)。"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
