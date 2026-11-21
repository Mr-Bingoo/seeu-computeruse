# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 找窗口:App 名字 → 哪个窗口(位置来自 GNOME 小插件)。

App 可以写:程序名(gnome-text-editor、firefox)、窗口类(org.gnome.TextEditor)、程序在菜单里的名字(Text Editor / 文本编辑器)、
同一个程序好几个窗口时 「App「标题里的几个字」」,或 「#窗口号」(windows 命令列出来的)。
"""
import glob
import os
import re

from seeu.linux import shell

_DESKTOP_NAMES = {}             # 窗口类型(Meta.WindowType):0 普通、1 桌面(图标层,不列)、3 对话框、4 模态对话框
_DESKTOP_LABEL = {}             # {同上的键: 按当前语言挑的给人看的名字}(11-21 C-3.4)


def _comm(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _exe(pid):
    try:
        return os.path.basename(os.readlink(f"/proc/{pid}/exe"))
    except OSError:
        return ""


def _cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [x.decode("utf-8", "replace") for x in f.read().split(b"\0") if x]
    except OSError:
        return []


def _desktop_names():
    """.desktop 文件里的名字(含中文):{小写的 app_id / 文件名: [名字…]}。"""
    if _DESKTOP_NAMES:
        return _DESKTOP_NAMES
    dirs = [os.path.expanduser("~/.local/share/applications"), "/usr/share/applications",
            "/var/lib/snapd/desktop/applications", "/var/lib/flatpak/exports/share/applications"]
    for d in dirs:
        for p in glob.glob(os.path.join(d, "*.desktop")):
            key = os.path.basename(p)[:-8].lower()
            names, loc = [], {}
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    sec = None
                    for ln in f:
                        ln = ln.strip()
                        if ln.startswith("["):
                            sec = ln
                            continue
                        if sec != "[Desktop Entry]":
                            continue
                        m = re.match(r"^(Name(?:\[[^\]]+\])?|StartupWMClass|Exec)=(.*)$", ln)
                        if m:
                            v = m.group(2).strip()
                            if m.group(1) == "Exec":
                                v = os.path.basename(v.split()[0]) if v.split() else ""
                            if v:
                                names.append(v)
                                if m.group(1).startswith("Name"):
                                    loc.setdefault(m.group(1), v)
            except OSError:
                continue
            _DESKTOP_NAMES.setdefault(key, []).extend(names)
            pick = _pick_name(loc)
            if pick:
                _DESKTOP_LABEL.setdefault(key, pick)
    return _DESKTOP_NAMES


def _pick_name(loc):
    """按当前语言挑一个给人看的名字:Name[zh_CN] → Name[zh] → Name(11-21 C-3.4:Fedora 上按字母排第一的是
    卡拜尔语「Amaẓrag n Weḍris」,被当成文本编辑器的程序名显示了)。"""
    lang = (os.environ.get("LANGUAGE") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
            or os.environ.get("LANG") or "").split(":")[0].split(".")[0]
    for k in (f"Name[{lang}]", f"Name[{lang.split('_')[0]}]", "Name"):
        if lang or k == "Name":
            if loc.get(k):
                return loc[k]
    return None


def info(w):
    """给小插件报的窗口补上程序名、能匹配的名字。"""
    pid = w.get("pid") or 0
    w = dict(w)
    w["comm"], w["exe"] = _comm(pid), _exe(pid)
    names = {w["comm"], w["exe"], w.get("wm_class") or "", w.get("app_id") or ""}
    dn = _desktop_names()
    label = None
    for key in {(w.get("app_id") or "").lower(), (w.get("wm_class") or "").lower(), w["comm"].lower()}:
        if key and key in dn:
            names.update(dn[key])
            label = label or _DESKTOP_LABEL.get(key)
    # snap 的程序:firefox_firefox 这种
    for k in list(names):
        if "_" in k:
            names.add(k.split("_")[0])
    rest = sorted(n for n in names if n and n != label)
    w["names"] = ([label] if label else []) + rest      # 第一个是给人看的名字(按当前语言),其余照旧按字母排
    return w


def list_windows():
    """看得到的普通窗口(从上到下)。"""
    out = []
    for w in shell.rects():
        if w.get("type") == 1 or w.get("w", 0) <= 2 or w.get("h", 0) <= 2:     # 桌面图标层、1×1 的隐形窗口
            continue
        if w.get("skip") and not w.get("title"):
            continue
        out.append(info(w))
    out.sort(key=lambda w: -w["z"])
    return out


def find(app):
    """返回一个窗口(dict)。找不到抛 RuntimeError(带现在开着哪些窗口)。"""
    app = a0 = str(app).strip()
    title_part = None
    m = re.match(r"^(.*?)「(.*)」$", app)
    if m:
        app, title_part = m.group(1).strip(), m.group(2)
        if app.lower() in ("", "app"):            # 11-20:AI 照抄说明里的占位「App「标题」」→ 只按标题找
            app = ""
    wins = list_windows()
    if app.startswith("#") and app[1:].isdigit():
        for w in wins:
            if w["id"] == int(app[1:]):
                return w
        raise RuntimeError(f"没有窗口号 {app}")
    low = app.lower()

    def score(w):
        ns = [n.lower() for n in w["names"]]
        if low in ns:
            return 3
        if any(low in n for n in ns):
            return 2
        if low and low in (w.get("title") or "").lower():
            return 1
        return 0
    cands = [(score(w), w) for w in wins]
    best = max((s for s, _ in cands), default=0)
    hits = [w for s, w in cands if s == best and s > 0]
    if title_part:
        hits = [w for w in hits if title_part.lower() in (w.get("title") or "").lower()]
        progs = {os.path.basename(str(w.get("exe") or "")) or w.get("comm") for w in hits}
        if not app and len(progs) > 1:           # 第二轮复查(照 Windows):照抄「App「标题」」对上好几个程序的窗口,别乱挑
            cands = "、".join(f"{(w.get('names') or [w.get('comm')])[0]}「{(w.get('title') or '')[:40]}」" for w in hits[:6])
            raise RuntimeError(f"「{a0}」对得上好几个程序的窗口:{cands};请写成「程序名「标题里的几个字」」或「#窗口号」")
    if not hits:
        opened = "、".join(sorted({w["names"][0] if w["names"] else w["comm"] for w in wins}))
        raise RuntimeError(f"找不到「{app}」的窗口(现在开着:{opened or '无'});没开的话先打开它")
    # 同名的好几个:前台的优先,再按上下顺序
    hits.sort(key=lambda w: (not w.get("focus"), -w["z"]))
    return hits[0]


def covered(w, wins=None):
    """这个窗口被上面的窗口盖住了多少(0~1)。不在当前工作区 / 最小化算 1。"""
    if w.get("minimized") or not w.get("active_ws", True):
        return 1.0
    wins = wins if wins is not None else list_windows()
    x0, y0, x1, y1 = w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"]
    area = max(1, (x1 - x0) * (y1 - y0))
    # 用格子近似算被盖的面积(窗口不多,够用)
    step = 8
    hit = tot = 0
    above = [o for o in wins if o["z"] > w["z"] and not o.get("minimized") and o.get("active_ws", True)]
    for yy in range(y0, y1, step):
        for xx in range(x0, x1, step):
            tot += 1
            if any(o["x"] <= xx < o["x"] + o["w"] and o["y"] <= yy < o["y"] + o["h"] for o in above):
                hit += 1
    return hit / max(1, tot) if tot else (0.0 if area else 1.0)


def sensitive_above(w, wins=None):
    """11-20 复查:盖在这个窗口上面、又是 SeeU 不碰的程序(终端、密码程序、系统授权框…)的窗口位置,截图发给 AI 前涂黑。"""
    from seeu.linux import safety
    wins = wins if wins is not None else list_windows()
    out = []
    for o in wins:
        if o["z"] > w["z"] and not o.get("minimized") and o.get("active_ws", True) and o.get("pid") != w.get("pid"):
            try:
                if safety.why_not(o):
                    out.append((o["x"], o["y"], o["w"], o["h"]))
            except Exception:   # noqa: BLE001
                pass
    return out


def point_visible(w, x, y, wins=None):
    """屏幕点 (x, y) 在这个窗口里、而且没被别的窗口盖住。"""
    if w.get("minimized") or not w.get("active_ws", True):
        return False
    if not (w["x"] <= x < w["x"] + w["w"] and w["y"] <= y < w["y"] + w["h"]):
        return False
    wins = wins if wins is not None else list_windows()
    return not any(o["z"] > w["z"] and not o.get("minimized") and o.get("active_ws", True)
                   and o["x"] <= x < o["x"] + o["w"] and o["y"] <= y < o["y"] + o["h"] for o in wins)
