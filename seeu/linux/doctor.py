# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 检查(python3 -m seeu 检查 [--fix])。只查不改;--fix 只做不要管理员密码的事(装 SeeU 自己的 GNOME 小插件)。"""
import os
import sys


from seeu.linux.lang import say as print, tx  # noqa: E402, A001   打印给人看的走中英文(11-18 C-3.0)


def _line(ok, name, msg):
    mark = {True: "✅", False: "❌", None: "—"}[ok]
    print(f"  {mark} {tx(name):<16} {tx(msg)}")
    return ok is not False


def env_warnings():
    """不满足 Linux 预览版要求的地方(11-21 C-3.3 用户要:接入时先说一声,别等跑检查才知道)。返回给人看的句子(中文,打印时自动转英文)。
    只看环境变量和 Python 版本,不碰屏幕、不连系统服务,接入 / 检查前都能放心调。"""
    from seeu.linux import shell
    out = []
    if sys.version_info < (3, 10):
        out.append(f"Python 是 {sys.version.split()[0]},SeeU 要 3.10 以上,先升级 Python 再用")
    desk = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "?"
    if not shell.is_gnome():
        out.append(f"现在的桌面是 {desk},不是 GNOME;SeeU Linux 预览版只支持 GNOME(Ubuntu 默认桌面),"
                   "在这个桌面上接好了也看不了窗口、点不了按钮")
    elif os.environ.get("XDG_SESSION_TYPE", "?") != "wayland":
        out.append(f"现在的显示方式是 {os.environ.get('XDG_SESSION_TYPE', '?')},SeeU Linux 预览版只在 GNOME + Wayland 上测过,"
                   "可能有用不了的地方(Ubuntu 登录界面右下角的齿轮里能选 Wayland)")
    return out


def _a11y_on():
    import subprocess
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "toolkit-accessibility"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return {"true": True, "false": False}.get(out)
    except Exception:   # noqa: BLE001
        return None


def _a11y_set(on):
    import subprocess
    subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "toolkit-accessibility", "true" if on else "false"],
                   capture_output=True, timeout=10)


def main(argv=()):
    fix = "--fix" in argv
    from seeu.linux import shell, ocr
    print("SeeU 检查(Linux 版预览)")
    good = True
    good &= _line(sys.version_info >= (3, 10), "Python", sys.version.split()[0]
                  + ("" if sys.version_info >= (3, 10) else ";要 3.10 以上,先升级 Python"))
    st = os.environ.get("XDG_SESSION_TYPE", "?")
    good &= _line(True if st == "wayland" else None, "会话", f"{st}({os.environ.get('XDG_CURRENT_DESKTOP', '?')})"
                  + ("" if st == "wayland" else ";第一版只在 GNOME + Wayland 上测过"))
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
        n = Atspi.get_desktop(0).get_child_count()
        good &= _line(n > 0, "辅助功能接口", f"AT-SPI 正常,读到 {n} 个程序" if n else "AT-SPI 读不到任何程序")
    except Exception as ex:   # noqa: BLE001
        good &= _line(False, "辅助功能接口", f"用不了({ex});装:sudo apt install python3-gi gir1.2-atspi-2.0")
    # Qt(KDE 一系)、Electron(VS Code 这类)、Chrome 只在系统「辅助功能总开关」开着时才把控件交出来(GTK 一直交);
    # 开屏幕阅读器时系统打开的也是它(11-18 实测:没开时 FeatherPad、VS Code 一个控件都读不到)。改完那些程序要重开才生效
    on = _a11y_on()
    if fix and on is False:
        _a11y_set(True)
        on = _a11y_on()
        if on:
            print("     已打开系统的辅助功能总开关;已经开着的 Qt / Electron / Chrome 程序要重开一次才读得到控件")
    good &= _line(on if on is not None else None, "辅助功能总开关",
                  "开着(Qt、Electron、Chrome 的控件也读得到)" if on else
                  ("关着:Qt、Electron(VS Code 这类)、Chrome 的控件读不到;运行 python3 -m seeu 检查 --fix 打开" if on is False else "读不到"))
    if not shell.is_gnome():
        good &= _line(False, "GNOME 小插件", "现在不是 GNOME 桌面,第一版只支持 GNOME")
    else:
        if fix and (not shell.installed() or not shell.enabled()):
            r = shell.install()
            print("     已装好 SeeU 的 GNOME 小插件" + (";🔴 要注销重新登录一次才生效" if r["relogin"] else ""))
        if shell.available():
            p = shell.ping()
            old = int(p.get("api") or 1) < shell.NEED_API
            good &= _line(None if old else True, "GNOME 小插件", f"在跑(GNOME {p.get('shell')},小插件第 {p.get('version')} 版)"
                          + (";是旧版,借鼠标和代理光标要新版:运行 python3 -m seeu 检查 --fix,再注销重新登录一次" if old else ""))
        else:
            good &= _line(False, "GNOME 小插件", shell.why_missing() + ("" if fix else "(运行 python3 -m seeu 检查 --fix)"))
    try:
        from seeu.linux import shot
        p = shot.full(timeout=6)
        os.remove(p)
        good &= _line(True, "截图授权", "允许了")
    except Exception as ex:   # noqa: BLE001
        good &= _line(False, "截图授权", str(ex))
    _line(True if ocr.available() else None, "认字(可选)",
          ("Tesseract,语言:" + ",".join(ocr.langs())) if ocr.available() else "没装(读不到控件的窗口才用;sudo apt install tesseract-ocr tesseract-ocr-chi-sim)")
    from seeu.linux import real
    m = real.mode()
    if m == "off":
        _line(None, "借真鼠标键盘", "设置是「关」:后台做不到时不借(python3 -m seeu 设置 借用鼠标 开)")
    else:
        if fix and not real.has_grant():
            print("     现在会弹出系统的「远程桌面」框:请打开「允许远程操作」,再点「共享」(SeeU 只在后台做不到时借一下,借的时候右上角会亮提示)")
            try:
                real.grant()
                print("     已允许,以后借鼠标不再弹框")
            except Exception as ex:   # noqa: BLE001
                print(f"     没拿到授权:{ex}")
        _line(True if real.has_grant() else None, "借真鼠标键盘",
              ("已允许远程操作" if real.has_grant() else "还没允许远程操作(要用时 SeeU 会说;运行 python3 -m seeu 检查 --fix 先允许)")
              + f";设置「借用鼠标」= {dict(on='开', ask='问我')[m]}")
    print("都齐了" if good else "有没齐的,按上面说的补")
    return 0 if good else 1
