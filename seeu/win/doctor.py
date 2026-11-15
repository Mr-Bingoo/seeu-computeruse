# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 检查(11-14,照 Mac 版 seeu/doctor.py):一条命令看这台电脑上 SeeU 能不能用、缺什么,缺的写怎么补。

    python -m seeu 检查        (英文 check / doctor)

只查不改:不开窗口、不起浏览器、不动设置。Windows 上不用开系统授权,所以查的是:
Python 版本、控件接口(comtypes)、是不是管理员身份、认字语言包、专用浏览器用的 Chrome / Edge、git(更新用)、借用鼠标设置、接了哪几家 AI。
check() 不依赖 Windows 以外的东西;每一项查不到就写「查不到」接着往下。
"""
import os
import shutil
import sys

OK, BAD, NA = "✅", "❌", "—"
PY_MIN = (3, 10)


def _en():
    try:
        from seeu.i18n import lang
        return lang() == "en"
    except Exception:
        return False


def L(zh, en):
    return en if _en() else zh


def _w(s):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _row(rows, ok, name, note=""):
    rows.append(dict(ok=ok, name=name, note=note))


def check():
    """返回 [{ok: ✅/❌/—, name, note}]。❌ = 缺了、SeeU 有一块用不了;— = 没装 / 查不到,不算缺。"""
    import platform
    rows = []
    v = sys.version_info
    good = (v.major, v.minor) >= PY_MIN
    _row(rows, OK if good else BAD, "Python",
         f"{platform.python_version()}({platform.machine()})" if good else
         L(f"{platform.python_version()} 太旧,要 {PY_MIN[0]}.{PY_MIN[1]} 以上:到 python.org 装新版",
           f"{platform.python_version()} is too old, {PY_MIN[0]}.{PY_MIN[1]}+ is needed: install a newer one from python.org"))
    _row(rows, OK, "Windows", f"{platform.release()} · {platform.version()}")

    try:
        from seeu.win import uia
        uia._auto()
        _row(rows, OK, L("控件接口", "UI Automation"), L("按编号点、读控件、读回文字", "tap by number, read controls and text"))
    except Exception as e:
        _row(rows, BAD, L("控件接口", "UI Automation"),
             L(f"用不了({e.__class__.__name__}):运行 python -m pip install comtypes",
               f"not available ({e.__class__.__name__}): run python -m pip install comtypes"))

    try:
        from seeu.win import window as W
        adm = W.self_elevated()
        _row(rows, OK, L("管理员身份", "Administrator"),
             L("是(一般不需要;这样 SeeU 也能碰管理员窗口,请留意)", "yes (not normally needed; SeeU can then touch admin windows too, take care)")
             if adm else L("不是(正常;以管理员身份运行的窗口 SeeU 碰不了)", "no (normal; windows that run as administrator can't be touched)"))
    except Exception as e:
        _row(rows, NA, L("管理员身份", "Administrator"), L(f"查不到({e.__class__.__name__})", f"unknown ({e.__class__.__name__})"))

    try:
        from seeu.win import ocr
        ls = ocr.langs()
        _row(rows, OK if ls else NA, L("认字语言包", "Text recognition (OCR)"),
             ("、".join(ls) if not _en() else ", ".join(ls)) if ls else
             L("没装:模拟器、自绘界面的字认不了(别的不受影响)。装法:设置 → 时间和语言 → 语言和区域 → 你的语言 → 语言选项 → 光学字符识别",
               "none installed: text in emulators / custom-drawn windows can't be read (nothing else is affected). "
               "To add: Settings → Time & language → Language & region → your language → Language options → Optical character recognition"))
    except Exception as e:
        _row(rows, NA, L("认字语言包", "Text recognition (OCR)"), L(f"查不到({e.__class__.__name__})", f"unknown ({e.__class__.__name__})"))

    try:
        from seeu.win import web
        found = [n for n in ("chrome", "edge") if web._exe(n)]
        names = {"chrome": "Chrome", "edge": "Edge"}
        _row(rows, OK if found else BAD, L("专用浏览器", "SeeU's browser"),
             L("用 " + names[found[0]] + "(不出窗口、单独配置,不碰你自己的浏览器)",
               "uses " + names[found[0]] + " (no window, its own profile, never your own browser)") if found else
             L("没找到 Chrome 或 Edge:网页工具用不了,装一个就行", "Chrome or Edge not found: the web tools won't work, install either"))
    except Exception as e:
        _row(rows, NA, L("专用浏览器", "SeeU's browser"), L(f"查不到({e.__class__.__name__})", f"unknown ({e.__class__.__name__})"))

    git = shutil.which("git")
    _row(rows, OK if git else NA, "git", L("有(更新命令要用)", "found (used by the update command)") if git else
         L("没有:python -m seeu 更新 用不了(别的不受影响),到 git-scm.com 装", "not found: python -m seeu update won't work (nothing else is affected); get it from git-scm.com"))

    try:
        from seeu.win import act
        m = act.real_mode()
        _row(rows, OK, L("借用鼠标", "Borrow mouse"), {
            "on": L("开:后台没效果时借你的鼠标键盘几秒,用完还原", "on: borrows your mouse / keyboard for a few seconds when the background has no effect"),
            "ask": L("问我:借之前先由 AI 问你", "ask: the AI asks you before borrowing"),
            "off": L("关:从不借,做不到就停下报告", "off: never borrows, stops and reports instead")}[m])
    except Exception as e:
        _row(rows, NA, L("借用鼠标", "Borrow mouse"), L(f"查不到({e.__class__.__name__})", f"unknown ({e.__class__.__name__})"))
    return rows


def main(argv=None):
    from seeu import version
    print(L("SeeU 检查(Windows 预览版)· Windows 上不用开系统授权", "SeeU check (Windows preview) · no Windows permissions are needed") + "\n")
    print("  " + L(f"版本 v{version.current()}", f"Version v{version.current()}") + "\n")
    rows = check()
    w = max(_w(r["name"]) for r in rows)
    for r in rows:
        print(f"  {r['ok']} {r['name']}{' ' * (w - _w(r['name']))}  {r['note']}")
    print()
    try:
        from seeu.win import install
        install.status()
    except Exception as e:
        print(L(f"接入情况查不到({e.__class__.__name__})", f"Couldn't read which AI clients are connected ({e.__class__.__name__})"))
    bad = [r for r in rows if r["ok"] == BAD]
    print("\n" + (L("都齐了(— 是没装 / 查不到的,不算缺)。", "All set (— means not installed / unknown, not a problem).") if not bad else
                  L(f"有 {len(bad)} 项要补,照上面 ❌ 那几行写的做。", f"{len(bad)} item(s) need fixing: follow the ❌ lines above.")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
