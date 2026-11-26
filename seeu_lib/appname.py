"""App 名字跟系统语言走:英文名 ⇄ 系统现在显示的名字。

中文 macOS 上,正在运行的 App 和窗口进程名(NSRunningApplication.localizedName / kCGWindowOwnerName)会变成中文:
TextEdit → 文本编辑、Safari → Safari浏览器、iPhone Mirroring → iPhone镜像(繁体 iPhone鏡像輸出)、Dock → 程序坞。
seeu_lib 各处调用方传的都是英文名,直接 == 比对在中文系统上会对不上(SeeU 在朋友的中文 Intel Mac 上实测)。
做法照 SeeU 的 seeu/ax.py(local_name / same_app):按 App 包文件名、Info.plist 的 CFBundleName / CFBundleExecutable
这些不随语言变的名字,对回当前显示名;另外读包里各语言的显示名(InfoPlist.loctable / *.lproj/InfoPlist.strings)。

用法:
    from seeu_lib import appname
    appname.same_app(w["kCGWindowOwnerName"], "iPhone Mirroring")   # 显示名是不是这个 App
    appname.names("iPhone Mirroring")    # {'iPhone Mirroring', 'iPhone镜像', ...} 这个 App 可能叫的所有名字
    python3 -m seeu_lib.appname "iPhone Mirroring"     # 打印能认的名字

🔴 给热路径用的约定:调用方先拿原名 == 比,对不上再调这里(英文系统零额外开销)。结果记 2 秒。
"""
import os
import plistlib
import re
import sys
import time

CACHE_S = 2.0        # 对上了记 2 秒
MISS_CACHE_S = 0.3   # 没对上只记 0.3 秒(App 刚启动那会儿别一直认不出)
APPS_CACHE_S = 0.3   # 正在运行的 App 名单共用一份,几个名字一起查只转一次事件循环
_names_cache = {}   # 名字 -> (时间, 名字集合)
_base_cache = {}    # App 包路径 -> 不随语言变的名字
_loc_cache = {}     # App 包路径 -> 包里写的各语言显示名
_apps_cache = [0.0, []]
_ui_english = None  # 系统界面语言是不是英文(None = 还没查);测试可以直接设成 False 假装中文系统


def _is_english_ui():
    """系统第一语言是英文:App 显示名就是英文名,不用换名,直接跳过(英文系统零开销)。"""
    global _ui_english
    if _ui_english is None:
        try:
            from Foundation import NSLocale
            langs = list(NSLocale.preferredLanguages() or [])
            _ui_english = bool(langs) and str(langs[0]).lower().startswith("en")
        except Exception:
            _ui_english = False
    return _ui_english


def _running_apps():
    """正在运行的、有界面的 App(activationPolicy == 0,跟 seeu/ax.py 一样)。
    不过滤的话会认到后台进程上(Shortcuts → ShortcutsViewService、Electron 的 Helper 进程,实测)。
    没有事件循环的进程里名单会停在第一次,先转 20ms。"""
    from AppKit import NSWorkspace
    from Foundation import NSRunLoop, NSDate
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    return [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.activationPolicy() == 0]


def _apps():
    """(显示名, 包路径) 名单,记 0.3 秒。"""
    now = time.time()
    if now - _apps_cache[0] < APPS_CACHE_S and _apps_cache[1]:
        return _apps_cache[1]
    out = [(str(a.localizedName() or ""), _app_path(a)) for a in _running_apps()]
    _apps_cache[0], _apps_cache[1] = now, out
    return out


def _app_path(a):
    try:
        url = a.bundleURL()
        return str(url.path()) if url is not None else ""
    except Exception:
        return ""


def _bases(path):
    """不随语言变的名字:包文件名(去 .app)、CFBundleName、CFBundleExecutable。"""
    if path in _base_cache:
        return _base_cache[path]
    b = os.path.basename(path)
    out = {b[:-4] if b.endswith(".app") else b}
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        for k in ("CFBundleName", "CFBundleExecutable"):
            v = info.get(k)
            if isinstance(v, str) and v:
                out.add(v)
    except Exception:
        pass
    out.discard("")
    _base_cache[path] = out
    return out


def _local_names(path):
    """包里写的各语言显示名。苹果自带 App 放 InfoPlist.loctable;别家多是 <语言>.lproj/InfoPlist.strings。"""
    if path in _loc_cache:
        return _loc_cache[path]
    import glob
    out = set()
    keys = ("CFBundleDisplayName", "CFBundleName")
    res = os.path.join(path, "Contents", "Resources")
    try:
        with open(os.path.join(res, "InfoPlist.loctable"), "rb") as f:
            for d in plistlib.load(f).values():
                if isinstance(d, dict):
                    out.update(v for k, v in d.items() if k in keys and isinstance(v, str))
    except Exception:
        pass
    for fn in glob.glob(os.path.join(res, "*.lproj", "InfoPlist.strings")):
        try:
            raw = open(fn, "rb").read()
            try:
                d = plistlib.loads(raw)
            except Exception:   # 老的文本写法 "CFBundleName" = "备忘录";(UTF-16 或 UTF-8)
                txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "ignore")
                d = dict(re.findall(r'"?(CFBundle(?:Display)?Name)"?\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', txt))
            out.update(v for k, v in d.items() if k in keys and isinstance(v, str))
        except Exception:
            pass
    out.discard("")
    _loc_cache[path] = out
    return out


def names(name):
    """这个 App 可能叫的名字:{原名, 系统现在的显示名}。对不上任何正在运行的 App、或系统是英文界面时只返回 {原名}。
    找法:先整份名单找「显示名完全相等」,没有再按包名(包文件名、CFBundleName、可执行文件名)找,
    还没有才翻包里各语言的显示名;只并进命中那个 App 的显示名,不把它的包名全并进来。"""
    owner = str(name or "")
    if not owner:
        return set()
    if _is_english_ui():
        return {owner}
    now = time.time()
    hit = _names_cache.get(owner)
    if hit and now - hit[0] < (CACHE_S if len(hit[1]) > 1 else MISS_CACHE_S):
        return hit[1]
    out = {owner}
    try:
        apps = _apps()
        if not any(shown == owner for shown, _ in apps):
            low = owner.casefold()
            for test in (lambda p: any(b.casefold() == low for b in _bases(p)),
                         lambda p: owner in _local_names(p)):
                found = next((shown for shown, path in apps if shown and path and test(path)), None)
                if found:
                    out.add(found)
                    break
    except Exception:
        pass
    _names_cache[owner] = (now, out)
    return out


def local_name(name):
    """英文 / 包里的名字 → 系统现在显示的名字;对不上正在运行的 App 原样返回。"""
    owner = str(name or "")
    if not owner:
        return name
    alt = names(owner) - {owner}
    return next(iter(alt)) if alt else name


def same_app(shown, name):
    """系统给的名字(显示名 / 窗口进程名)是不是这个 App(name 可以是英文名)。先比原名,对不上才查。"""
    if not shown or not name:
        return False
    return shown == name or shown in names(name)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 0
    for n in argv:
        print(f"{n}: 现在叫「{local_name(n)}」;能认 {sorted(names(n))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
