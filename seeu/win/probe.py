# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 探一下某个程序能不能用 SeeU 自动化(照 Mac 版 seeu/probe.py 的思路):
    python -m seeu 探一下 Notepad      (英文 probe;MCP 工具 seeu_probe)

只读:不点、不打字、不切前台。程序要开着(Windows 上按名字找没装的程序不可靠,没开就说先打开)。一次看完:
  程序路径、版本;安全底线碰不碰;内核(原生 / 浏览器 / 网页壳 Electron·CEF / 画面认字类模拟器);
  开着哪些窗口、UIA 能读到几个控件 / 几个输入框、后台能不能截到图;最后给一句「SeeU 会走哪条路」。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

FEW_CONTROLS = 5        # 读到的控件少于这个 = 基本读不到,只能按截图位置点 / 认字

TXT = {
    "zh": dict(title="SeeU 探一下「{app}」", path="程序", ver="版本", notfound="没找到开着的窗口:{err}\n(Windows 版只探开着的程序:先把它打开再探)",
               safety="⛔ 安全底线:{why},SeeU 不碰", admin="⛔ 是以管理员身份运行的,SeeU 没有管理员权限、碰不了",
               kind="内核", native="原生程序", browser="浏览器(走网页工具)", canvas="画面认字类(截图 + 认字 + 后台点击)",
               shell="网页技术做的程序({k})", wins="窗口", ctrls="能读到的控件", edits="其中输入框", shot="后台截图",
               shot_ok="能截到({w}×{h})", shot_no="截不到:{err}", route="SeeU 会怎么做",
               r_block="不操作这个程序,这一步请用户自己来",
               r_browser="网页用 seeu_web_open(SeeU 专用的无界面浏览器)再按编号操作;用户自己那份浏览器后台打字 / 滚动常常不认",
               r_canvas="see 认字 → 按字或截图位置 tap;要装 Windows 的识别语言包",
               r_shell="按控件编号点;打字、按键带上 target(先点进输入框),Electron 程序后台常丢焦点",
               r_ax="按控件编号点、打字(最稳);看画面用 see",
               r_px="控件读不到几个:按 see 截图上的像素点(px、py),每步看截图核实;要认字的话装识别语言包"),
    "en": dict(title="SeeU probe: \"{app}\"", path="Program", ver="Version", notfound="No open window found: {err}\n"
               "(The Windows version only probes running programs: open it first)",
               safety="⛔ Safety rule: {why} — SeeU won't touch it", admin="⛔ Runs as administrator; SeeU has no admin rights and can't touch it",
               kind="Engine", native="native program", browser="browser (use the web tools)",
               canvas="screen-read (screenshot + text recognition + background clicks)", shell="built with web technology ({k})",
               wins="Windows", ctrls="Readable controls", edits="text fields", shot="Background screenshot",
               shot_ok="works ({w}×{h})", shot_no="doesn't work: {err}", route="What SeeU will do",
               r_block="don't operate this program; ask the user to do this step",
               r_browser="for web pages use seeu_web_open (SeeU's own invisible browser) and act by number; the user's own browser "
                         "often ignores background typing / scrolling",
               r_canvas="seeu_see recognizes text → tap by text or by pixel; needs a Windows OCR language pack",
               r_shell="tap by control number; pass target when typing / pressing keys (Electron apps often lose focus in the background)",
               r_ax="tap and type by control number (most reliable); use seeu_see to look",
               r_px="few readable controls: tap by pixel on the seeu_see screenshot (px, py) and check every step"),
}


def _exe_path(pid):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        k.CloseHandle(h)


def _version(path):
    """文件版本号(资源里的 FileVersion 数字);读不到 None。"""
    try:
        v = ctypes.WinDLL("version")
        size = v.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not v.GetFileVersionInfoW(path, 0, size, buf):
            return None
        p, n = ctypes.c_void_p(), wt.UINT()
        if not v.VerQueryValueW(buf, "\\", ctypes.byref(p), ctypes.byref(n)) or n.value < 52:
            return None
        ms, ls = ctypes.cast(p.value + 8, ctypes.POINTER(wt.DWORD * 2)).contents
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return None


def shell_kind(path):
    """网页壳:Electron(resources\\app.asar 或 app 文件夹 + 同目录 Chromium 那几个 dll)、CEF(libcef.dll)。不是返回 None。"""
    if not path:
        return None
    d = os.path.dirname(path)
    has = lambda *p: os.path.exists(os.path.join(d, *p))          # noqa: E731
    if has("libcef.dll"):
        return "CEF"
    if (has("resources", "app.asar") or has("resources", "app")) and (has("ffmpeg.dll") or has("chrome_100_percent.pak")):
        return "Electron"
    return None


def probe(app):
    """返回 dict(给 format 排版);只读。"""
    from seeu.win import act, safety, uia, window as W
    r = dict(app=app)
    try:
        win = W.find(app)
    except RuntimeError as ex:
        r["err"] = str(ex)
        return r
    r["window"] = win
    r["path"] = _exe_path(win["pid"]) or win["exe"]
    r["version"] = _version(r["path"]) if os.path.isabs(r["path"]) else None
    r["block"] = safety.why_not(win)
    r["admin"] = bool(win.get("elevated")) and not W.self_elevated()
    e = win["exe"].lower()
    if e in act.BROWSER_EXES:
        r["kind"] = "browser"
    elif e in act.CANVAS_EXES:
        r["kind"] = "canvas"
    else:
        r["kind"] = shell_kind(r["path"]) or "native"
    r["windows"] = [w["title"] for w in W.list_windows() if w["exe"].lower() == e]
    if r["block"] or r["admin"]:
        return r
    try:
        items = [x for x in uia.elements(win["hwnd"]) if x["type"] in uia.KEEP]
        r["controls"] = len(items)
        r["edits"] = sum(1 for x in items if x["type"] == 50004)
    except Exception as ex:
        r["controls_err"] = str(ex)
    try:
        cap = W.capture(win["hwnd"])
        r["shot"] = (cap[0], cap[1])
    except Exception as ex:
        r["shot_err"] = str(ex)
    return r


def route(r):
    if r.get("block") or r.get("admin"):
        return "r_block"
    k = r.get("kind")
    if k == "browser":
        return "r_browser"
    if k == "canvas":
        return "r_canvas"
    if r.get("controls", 0) < FEW_CONTROLS:
        return "r_px"
    return "r_shell" if k in ("Electron", "CEF") else "r_ax"


def format(r, lang="zh"):
    t = TXT[lang]
    out = [t["title"].format(app=r["app"])]
    if "err" in r:
        return out[0] + "\n" + t["notfound"].format(err=r["err"])
    out.append(f"  {t['path']}: {r['path']}")
    if r.get("version"):
        out.append(f"  {t['ver']}: {r['version']}")
    if r.get("block"):
        out.append("  " + t["safety"].format(why=r["block"]))
    if r.get("admin"):
        out.append("  " + t["admin"])
    k = r["kind"]
    out.append(f"  {t['kind']}: " + ({"browser": t["browser"], "canvas": t["canvas"], "native": t["native"]}.get(k)
                                       or t["shell"].format(k=k)))
    sep = "、" if lang == "zh" else ", "
    out.append(f"  {t['wins']}: {sep.join(w[:40] for w in r['windows'][:8])}")
    if "controls" in r:
        out.append(f"  {t['ctrls']}: {r['controls']}({t['edits']} {r['edits']})" if lang == "zh"
                   else f"  {t['ctrls']}: {r['controls']} ({r['edits']} {t['edits']})")
    if "shot" in r:
        out.append(f"  {t['shot']}: " + t["shot_ok"].format(w=r["shot"][0], h=r["shot"][1]))
    elif "shot_err" in r:
        out.append(f"  {t['shot']}: " + t["shot_no"].format(err=r["shot_err"]))
    out.append(f"→ {t['route']}: " + t[route(r)])
    return "\n".join(out)


def main(args):
    if not args:
        print("用法:python -m seeu 探一下 <程序名或窗口标题>")
        return 2
    r = probe(" ".join(args))
    print(format(r))
    return 0 if "err" not in r else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
