"""探一下某个 App 能不能用 SeeU 自动化:python3 -m seeu 探一下 <App>   (英文别名 probe;MCP 工具 seeu_probe)

只读,不点、不打字、不切前台(11-01 做,开源前补齐的第 4 项)。一次看完:
  装在哪、版本、是不是在跑;安全底线碰不碰;内核(原生 / 浏览器 / 网页壳 Electron·CEF / 截图认字类);
  有没有 AppleScript 字典、URL scheme;在跑的话再看:开着哪些窗口、辅助功能能读到几个控件 / 几个输入框、后台能不能截到图;
  最后给一句「SeeU 会走哪条路」。网页壳要看穿一层:有的把 Chromium 埋在 Contents/Helpers 里,顶层 Frameworks 是空的。
"""
import os
import plistlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

APP_DIRS = ("/Applications", os.path.expanduser("~/Applications"), "/System/Applications",
            "/System/Applications/Utilities", "/System/Library/CoreServices/Applications")
DEEP_FW = ("Electron Framework.framework", "Chromium Embedded Framework.framework")
DEEP_MAX = 9            # 往 Contents 里最多看几层(豆包的内核在第 8 层)
FEW_CONTROLS = 5        # 辅助功能读到的控件少于这个 = 基本读不到,只能按截图位置点

TXT = {
    "zh": dict(title="SeeU 探一下「{app}」", path="装在", ver="版本", run="在跑", yes="是", no="没开(开着再探能多看几项)",
               notfound="没找到这个 App(看看名字对不对,用程序名,如 TextEdit、Notes)",
               safety="⛔ 安全底线:{why},SeeU 不碰", kind="内核", native="原生 App", browser="浏览器(走网页工具)",
               canvas="画面认字类(截图 + 认字 + 后台点击)", shell="网页技术做的 App({k})", deep="(藏在 App 里层)",
               cdp_tested="SeeU 调试端口:{t}", cdp_untested="SeeU 调试端口:没试过,有的会禁掉,用前先试",
               osa="AppleScript 字典", url="URL scheme", none="没有",
               wins="窗口", ctrls="能读到的控件", edits="其中输入框", shot="后台截图", shot_ok="能截到({w}×{h})",
               shot_no="截不到:{err}", route="SeeU 会怎么做",
               r_block="不操作这个 App,这一步请用户自己来",
               r_browser="用 seeu_web_open / see / tap / type(带 tab),网站要在允许名单里",
               r_canvas="see 认字 → 按字或截图位置 tap;窗口要露着才截得到图",
               r_cdp="SeeU 会拉起它自己那份(调试端口),全程藏着读写;你自己开着的那份不碰",
               r_ax="按控件编号点、打字(最稳);看画面用 see",
               r_px="控件读不到几个:按 see 截图上的像素点(px、py),每步看截图核实",
               r_notrun="先开着再探:open -g -j -a \"{app}\"(藏着拉起,不抢前台)"),
    "en": dict(title="SeeU probe: \"{app}\"", path="Location", ver="Version", run="Running", yes="yes",
               no="no (probe again while it's open to see more)",
               notfound="App not found (check the name; use the process name, e.g. TextEdit, Notes)",
               safety="⛔ Safety rule: {why}; SeeU won't touch it", kind="Engine", native="native app",
               browser="browser (use the web tools)", canvas="screen-read (screenshot + OCR + background click)",
               shell="built with web technology ({k})", deep=" (nested deep inside the app)", cdp_tested="SeeU debug port: {t}",
               cdp_untested="SeeU debug port: not tried yet (some apps disable it), test first",
               osa="AppleScript dictionary", url="URL schemes", none="none",
               wins="Windows", ctrls="Readable controls", edits="text fields among them", shot="Background screenshot",
               shot_ok="works ({w}×{h})", shot_no="fails: {err}", route="How SeeU will do it",
               r_block="Don't operate this app; ask the user to do this step",
               r_browser="seeu_web_open / see / tap / type with tab; the site must be on the allow list",
               r_canvas="see reads text → tap by text or screenshot pixel; the window must be visible to be captured",
               r_cdp="SeeU launches its own instance (debug port) and reads/writes it hidden; the user's own instance is left alone",
               r_ax="tap and type by control number (most reliable); use see to look",
               r_px="few readable controls: tap by pixel on the see screenshot (px, py) and verify each step",
               r_notrun="open it first, then probe again: open -g -j -a \"{app}\" (launches hidden, no focus change)"),
}


def _find_path(app):
    from seeu import ax
    for n, pid, b in ax.running_apps():
        if n == app or b == app:
            from AppKit import NSRunningApplication
            ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if ra and ra.bundleURL():
                return ra.bundleURL().path(), pid
    for d in APP_DIRS:
        p = os.path.join(d, app + ".app")
        if os.path.isdir(p):
            return p, None
    return None, None


def _plist(path):
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def _shell_kind(path):
    """(内核, 是否藏得深);不是网页壳返回 (None, False)。
    先按框架名认(cdp.kind,只看顶层 Frameworks);认不出再往里找 Chromium 的通用特征「… Helper (Renderer).app」——
    11-01 豆包实测:Chromium 改名叫「Doubao Browser Framework」、埋在 Contents/Helpers/Doubao Browser.app 里,按名字认不出。"""
    from seeu import cdp
    k = cdp.kind(path)
    if k:
        return k, False
    contents = os.path.join(path, "Contents")
    base = contents.count(os.sep)
    for dp, dn, fn in os.walk(contents):
        if dp.count(os.sep) - base >= DEEP_MAX:
            dn[:] = []
        for d in dn:
            if d in DEEP_FW:
                return ("Electron" if d.startswith("Electron") else "CEF"), True
            if d.endswith("Helper (Renderer).app"):
                return "Chromium", True
        dn[:] = [d for d in dn if d not in ("Resources", "_CodeSignature", "MacOS")]   # 这几处不会有内核,省时间
    return None, False


def probe(app):
    """返回 dict(给 format 排版);只读。"""
    from seeu import act, ax, safety, web, cdp
    r = dict(app=app)
    path, pid = _find_path(app)
    r["path"], r["pid"] = path, pid
    if not path:
        return r
    info = _plist(path)
    r["bundle"] = info.get("CFBundleIdentifier", "")
    r["version"] = info.get("CFBundleShortVersionString", "")
    r["osa"] = bool(info.get("NSAppleScriptEnabled")) or any(
        n.endswith(".sdef") for n in os.listdir(os.path.join(path, "Contents", "Resources"))
        if os.path.isdir(os.path.join(path, "Contents", "Resources")))
    r["schemes"] = sorted({s for t in info.get("CFBundleURLTypes", []) for s in t.get("CFBundleURLSchemes", [])})
    if pid:
        r["block"] = safety.why_not(pid)
    elif app in safety.TERMINALS or r["bundle"] in safety.TERMINALS.values():
        r["block"] = f"{app} 是终端,往里打字等于能执行任何命令"
    elif r["bundle"] in safety.PASSWORD_APPS:
        r["block"] = f"{safety.PASSWORD_APPS[r['bundle']]} 里存的是密码"
    if web.is_browser(app):
        r["kind"] = "browser"
    elif app in act.CANVAS_APPS:
        r["kind"] = "canvas"
    else:
        k, deep = _shell_kind(path)
        r["kind"], r["deep"] = (k or "native"), deep
        if k:
            r["cdp_tested"] = cdp.TESTED.get(app)
    if pid and not r.get("block"):
        try:
            el, _ = ax.app_element(app)
            r["windows"] = ax.window_titles(el)
            items = ax.elements(app, include_menu=False)
            r["controls"] = len(items)
            r["edits"] = sum(1 for e in items if e["role"] in ax.TEXT_ROLES)
        except Exception as e:
            r["controls_err"] = str(e)
        try:
            png = act.shoot(app)
            from AppKit import NSImage
            sz = NSImage.alloc().initWithContentsOfFile_(png).size()
            r["shot"] = (int(sz.width), int(sz.height))
        except Exception as e:
            r["shot_err"] = str(e)
    return r


def route(r):
    if r.get("block"):
        return "r_block"
    if not r.get("pid") and r.get("kind") not in ("browser",):
        return "r_notrun"
    if r["kind"] == "browser":
        return "r_browser"
    if r["kind"] == "canvas":
        return "r_canvas"
    if r["kind"] in ("Electron", "CEF") and not r.get("deep"):
        return "r_cdp"
    return "r_ax" if r.get("controls", 0) >= FEW_CONTROLS else "r_px"


def format(r, lang="zh"):
    t = TXT[lang]
    out = [t["title"].format(app=r["app"])]
    if not r.get("path"):
        return out[0] + "\n" + t["notfound"]
    out.append(f"  {t['path']}: {r['path']}" + (f"  ({r['bundle']})" if r.get("bundle") else ""))
    if r.get("version"):
        out.append(f"  {t['ver']}: {r['version']}")
    out.append(f"  {t['run']}: {t['yes'] if r.get('pid') else t['no']}")
    if r.get("block"):
        out.append("  " + t["safety"].format(why=r["block"]))
    k = r.get("kind")
    kind = {"browser": t["browser"], "canvas": t["canvas"], "native": t["native"]}.get(k) or \
        (t["shell"].format(k=k) + (t["deep"] if r.get("deep") else ""))
    out.append(f"  {t['kind']}: {kind}")
    if k in ("Electron", "CEF") and not r.get("deep"):
        out.append("  " + (t["cdp_tested"].format(t=r["cdp_tested"]) if r.get("cdp_tested") else t["cdp_untested"]))
    out.append(f"  {t['osa']}: {t['yes'] if r.get('osa') else t['none']}")
    out.append(f"  {t['url']}: {', '.join(r['schemes']) if r.get('schemes') else t['none']}")
    if "windows" in r:
        out.append(f"  {t['wins']}: {'、'.join(r['windows']) if lang == 'zh' else ', '.join(r['windows']) or t['none']}"
                   if r["windows"] else f"  {t['wins']}: {t['none']}")
    if "controls" in r:
        out.append(f"  {t['ctrls']}: {r['controls']}({t['edits']} {r['edits']})" if lang == "zh"
                   else f"  {t['ctrls']}: {r['controls']} ({r['edits']} {t['edits']})")
    if "shot" in r:
        out.append(f"  {t['shot']}: " + t["shot_ok"].format(w=r["shot"][0], h=r["shot"][1]))
    elif "shot_err" in r:
        out.append(f"  {t['shot']}: " + t["shot_no"].format(err=r["shot_err"]))
    out.append(f"→ {t['route']}: " + t[route(r)].format(app=r["app"]))
    return "\n".join(out)


def main(args):
    if not args:
        print("用法:python3 -m seeu 探一下 <App>")
        return 2
    from seeu.i18n import lang
    r = probe(" ".join(args))
    print(format(r, "en" if lang() == "en" else "zh"))
    return 0 if r.get("path") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
