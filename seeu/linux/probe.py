# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 探一下某个程序能不能用 SeeU 自动化(11-18 C-3.0,照 Windows 版 win/probe.py):
    python3 -m seeu 探一下 featherpad      (英文 probe;MCP 工具 seeu_probe)

只读:不点、不打字、不切前台。程序要开着。一次看完:程序路径、版本(系统软件包 / snap / flatpak);安全底线碰不碰;
界面库(GTK / Qt / 浏览器 / Electron 这类网页壳);开着哪些窗口、辅助功能接口能读到几个控件 / 几个输入框、有没有菜单栏;
截图能不能截到它(被挡住多少);最后一句「SeeU 会走哪条路」。
"""
import os
import re
import subprocess
import sys

FEW_CONTROLS = 5

TXT = {
    "zh": dict(title="SeeU 探一下「{app}」", path="程序", ver="版本", notfound="没找到开着的窗口:{err}\n(只探开着的程序:先把它打开再探)",
               safety="⛔ 安全底线:{why},SeeU 不碰", kind="界面", native="原生程序({k})", browser="浏览器(走网页工具)",
               shell="网页技术做的程序({k})", wins="窗口", ctrls="能读到的控件", edits="其中输入框", writable="能后台写字的",
               menubar="菜单栏", yes="有(seeu_menu 能点)", no="没有", shot="截图", shot_ok="能截到({w}×{h})",
               shot_cov="能截到,但有 {p}% 被别的窗口挡着(那部分截到的是上面的窗口)", shot_no="截不到:{err}",
               route="SeeU 会怎么做", r_block="不操作这个程序,这一步请用户自己来",
               r_browser="网页用 seeu_web_open(SeeU 专用的无界面浏览器)再按编号操作;用户自己那份浏览器的输入框后台写不进",
               r_shell="按编号点(后台);它的输入框后台写不进,打字 / 按键要借真键盘(归「借用鼠标」设置管)",
               r_ax="按编号点、往 [可写] 的框里写字(后台、最稳);看画面用 seeu_see",
               r_px="控件读不到几个:按 seeu_see 截图上的像素点(px、py,要借真鼠标),每步看截图核实"),
    "en": dict(title="SeeU probe: \"{app}\"", path="Program", ver="Version", notfound="No open window found: {err}\n"
               "(Only running programs can be probed: open it first)",
               safety="⛔ Safety rule: {why} — SeeU won't touch it", kind="UI", native="native program ({k})",
               browser="browser (use the web tools)", shell="built with web technology ({k})", wins="Windows",
               ctrls="Readable controls", edits="text fields", writable="writable in the background", menubar="Menu bar",
               yes="yes (seeu_menu can click it)", no="no", shot="Screenshot", shot_ok="works ({w}×{h})",
               shot_cov="works, but {p}% is covered by other windows (that part shows the window on top)",
               shot_no="doesn't work: {err}", route="What SeeU will do",
               r_block="don't operate this program; ask the user to do this step",
               r_browser="for web pages use seeu_web_open (SeeU's own invisible browser) and act by number; the user's own "
                         "browser's fields can't be written in the background",
               r_shell="tap by number (background); its text fields can't be written in the background, so typing / keys "
                       "borrow the real keyboard (per the borrow-mouse setting)",
               r_ax="tap by number and type into [writable] fields (background, most reliable); use seeu_see to look",
               r_px="few readable controls: tap by pixel on the seeu_see screenshot (px, py; borrows the real mouse) and check "
                    "every step"),
}


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:   # noqa: BLE001
        return ""


def version_of(path, pid=0):
    """系统软件包 / snap / flatpak 的版本;读不到 None。"""
    if not path:
        return None
    m = re.match(r"^/snap/([^/]+)/", path)
    if m:
        try:
            with open(f"/snap/{m.group(1)}/current/meta/snap.yaml", encoding="utf-8") as f:
                v = re.search(r"^version:\s*['\"]?([^'\"\n]+)", f.read(), re.M)
            return f"{v.group(1)} (snap)" if v else None
        except OSError:
            return None
    if path.startswith("/app/") or "/flatpak/" in path:
        try:
            with open(f"/proc/{pid}/root/.flatpak-info", encoding="utf-8") as f:
                n = re.search(r"^name=(.+)$", f.read(), re.M)
            return f"flatpak {n.group(1)}" if n else "flatpak"
        except OSError:
            return "flatpak"
    pkg = _run(["dpkg-query", "-S", path]).split(":")[0].strip()
    if pkg and " " not in pkg:
        v = _run(["dpkg-query", "-W", "-f=${Version}", pkg])
        return f"{v} ({pkg})" if v else None
    out = _run(["rpm", "-qf", "--qf", "%{NAME} %{VERSION}-%{RELEASE}", path])   # Fedora 一家(11-21 C-3.4)
    if out and "not owned" not in out and len(out.split()) == 2:
        n, v = out.split()
        return f"{v} ({n})"
    return None


def shell_kind(path, toolkit=""):
    """网页壳:Electron(同目录有 resources/app.asar 或 resources/app)、CEF(libcef.so)。不是返回 None。"""
    if path:
        d = os.path.dirname(path)
        has = lambda *p: os.path.exists(os.path.join(d, *p))          # noqa: E731
        if has("libcef.so"):
            return "CEF"
        if has("resources", "app.asar") or has("resources", "app"):
            return "Electron"
    if toolkit == "chromium":
        return "Chromium"
    return None


def probe(app):
    """返回 dict(给 format 排版);只读。"""
    from seeu.linux import act, atspi, safety, window as W
    r = dict(app=app)
    try:
        w = W.find(app)
    except RuntimeError as ex:
        r["err"] = str(ex)
        return r
    r["window"] = w
    try:
        r["path"] = os.readlink(f"/proc/{w['pid']}/exe")
    except OSError:
        r["path"] = w.get("exe") or w.get("comm") or ""
    r["version"] = version_of(r["path"], w["pid"])
    r["block"] = safety.why_not(w)
    fr = atspi.frame_for(w)
    tk = atspi._toolkit(fr) if fr is not None else ""
    r["toolkit"] = tk
    if act._is_browser(w):
        r["kind"] = "browser"
    else:
        r["kind"] = shell_kind(r["path"], tk) or "native"
    keys = {w["comm"]}
    r["windows"] = [x["title"] or x["comm"] for x in W.list_windows() if x["comm"] in keys]
    if r["block"]:
        return r
    if fr is not None:
        try:
            items, _ = atspi.elements(fr, act._origin(w, fr), budget=2.0)
            r["controls"] = len(items)
            r["edits"] = sum(1 for x in items if x.get("editable") or x.get("password"))
            r["writable"] = sum(1 for x in items if x.get("writable"))
        except Exception as ex:   # noqa: BLE001
            r["controls_err"] = str(ex)
        r["menubar"] = act._menubar(fr) is not None
    else:
        r["controls"] = 0
    png, cov, note = act._shot(w)
    if png:
        try:
            from PIL import Image
            with Image.open(png) as im:
                r["shot"] = im.size
        except Exception:   # noqa: BLE001
            r["shot"] = (w["w"], w["h"])
        r["covered"] = cov
    else:
        r["shot_err"] = note or "?"
    return r


def route(r):
    if r.get("block"):
        return "r_block"
    k = r.get("kind")
    if k == "browser":
        return "r_browser"
    if r.get("controls", 0) < FEW_CONTROLS:
        return "r_px"
    return "r_shell" if k in ("Electron", "CEF", "Chromium") else "r_ax"


def format(r, lang="zh"):   # noqa: A001   跟 Windows 版同名
    t = TXT[lang]
    out = [t["title"].format(app=r["app"])]
    if "err" in r:
        return out[0] + "\n" + t["notfound"].format(err=r["err"])
    out.append(f"  {t['path']}: {r['path']}")
    if r.get("version"):
        out.append(f"  {t['ver']}: {r['version']}")
    if r.get("block"):
        out.append("  " + t["safety"].format(why=r["block"]))
    k = r["kind"]
    tk = {"gtk": "GTK", "qt": "Qt", "chromium": "Chromium", "gecko": "Gecko"}.get(r.get("toolkit") or "", r.get("toolkit") or "?")
    out.append(f"  {t['kind']}: " + ({"browser": t["browser"], "native": t["native"].format(k=tk)}.get(k) or t["shell"].format(k=k)))
    sep = "、" if lang == "zh" else ", "
    out.append(f"  {t['wins']}: {sep.join(x[:40] for x in r['windows'][:8])}")
    if "controls" in r and not r.get("block"):
        if lang == "zh":
            out.append(f"  {t['ctrls']}: {r['controls']}({t['edits']} {r.get('edits', 0)},{t['writable']} {r.get('writable', 0)})")
        else:
            out.append(f"  {t['ctrls']}: {r['controls']} ({r.get('edits', 0)} {t['edits']}, {r.get('writable', 0)} {t['writable']})")
        out.append(f"  {t['menubar']}: " + (t["yes"] if r.get("menubar") else t["no"]))
    if "shot" in r:
        cov = r.get("covered") or 0
        out.append(f"  {t['shot']}: " + (t["shot_cov"].format(p=round(cov * 100)) if cov > 0.02
                                           else t["shot_ok"].format(w=r["shot"][0], h=r["shot"][1])))
    elif "shot_err" in r:
        out.append(f"  {t['shot']}: " + t["shot_no"].format(err=r["shot_err"]))
    out.append(f"→ {t['route']}: " + t[route(r)])
    return "\n".join(out)


def main(args):
    if not args:
        print("用法:python3 -m seeu 探一下 <程序名或窗口标题>")
        return 2
    from seeu.linux import lang
    r = probe(" ".join(args))
    print(format(r, "en" if lang.is_en() else "zh"))
    return 0 if "err" not in r else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
