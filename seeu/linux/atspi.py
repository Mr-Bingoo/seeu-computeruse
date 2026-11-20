# -*- coding: utf-8 -*-
"""SeeU Linux 版 · AT-SPI(Linux 的辅助功能接口):读控件、按控件、往输入框里写字。全部不动鼠标键盘、不抢前台。

坐标:GNOME + Wayland 下控件报的「屏幕坐标」全是 0(拿不到),要用「窗口内坐标」+ 小插件报的窗口外框位置(GTK4 实测,11-18)。
"""
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

MAX_NODES = 4000
MAX_DEPTH = 60
WALK_BUDGET = 4.0        # 一次读控件最多花几秒(大网页、大文件管理器会很多)
PRESS_ACTIONS = ("click", "press", "activate", "jump", "toggle", "open", "select")
# 有名字就列出来的「只看」角色(按不了,但 AI 要靠它们读内容)
TEXT_ROLES = {"label", "static", "heading", "paragraph", "text", "link", "list item", "table cell", "menu item",
              "check box", "radio button", "page tab", "status bar", "notification", "alert", "tree item"}
EDIT_ROLES = {"text", "entry", "password text", "terminal", "document text", "editbar", "combo box", "spin button"}
SKIP_ROLES = {"filler", "panel", "scroll pane", "viewport", "redundant object", "section", "grouping", "invalid"}
ROLE_ZH = {"push button": "按钮", "button": "按钮", "toggle button": "开关按钮", "check box": "勾选框", "radio button": "单选",
           "text": "输入框", "entry": "输入框", "password text": "密码框", "label": "文字", "static": "文字",
           "link": "链接", "menu item": "菜单项", "menu": "菜单", "page tab": "标签页", "combo box": "下拉框",
           "list item": "列表项", "table cell": "格子", "heading": "标题", "paragraph": "段落", "tree item": "列表项",
           "spin button": "数字框", "slider": "滑块", "image": "图片", "document web": "网页", "frame": "窗口",
           "dialog": "对话框", "terminal": "终端", "document text": "文档"}


def _states(acc):
    try:
        return acc.get_state_set()
    except Exception:   # noqa: BLE001
        return None


def _has(st, s):
    return bool(st) and st.contains(s)


def apps():
    d = Atspi.get_desktop(0)
    out = []
    for i in range(d.get_child_count()):
        a = d.get_child_at_index(i)
        if a is None:
            continue
        try:
            out.append((a, a.get_name() or "", a.get_process_id()))
        except Exception:   # noqa: BLE001
            continue
    return out


def apps_of(pid):
    """同一个进程可能登记好几条(Qt 程序 11-18 实测:一条空的 featherpad + 一条带窗口的 FeatherPad)。"""
    return [a for a, name, p in apps() if p == pid]


def app_of(pid):
    xs = apps_of(pid)
    return xs[0] if xs else None


def top_windows(app):
    out = []
    try:
        n = app.get_child_count()
    except Exception:   # noqa: BLE001
        return out
    for i in range(n):
        try:
            c = app.get_child_at_index(i)
        except Exception:   # noqa: BLE001
            c = None
        if c is not None:
            out.append(c)
    return out


class Ambiguous(RuntimeError):
    """同一个程序开着几个同名窗口,分不清小插件说的是哪个 —— 宁可停手,不往别的窗口里写。"""


def _fits(t, win):
    """AT-SPI 顶层报的大小跟小插件的外框对不对得上(GTK4 一样大;Qt 少标题栏;Chrome 多一圈阴影)。"""
    try:
        e = t.get_extents(Atspi.CoordType.WINDOW)
    except Exception:   # noqa: BLE001
        return False
    dw, dh = e.width - win.get("w", 0), e.height - win.get("h", 0)
    return (abs(dw) <= 2 and abs(dh) <= 2) or (-40 < dw <= 0 and -120 < dh <= 0) or (0 < dw < 160 and 0 < dh < 160)


def pick_same_title(cands, win):
    """几个同名顶层里挑出小插件说的那个:先比大小,再看是不是当前窗口。挑不出唯一一个 → Ambiguous。
    (11-20 x86 实测:两个都叫「新建文档 (草稿)」的文本编辑器窗口,原来按标题对上第一个 → 看的是新窗口、字写进了旧窗口)"""
    if len(cands) == 1:
        return cands[0]
    sized = [t for t in cands if _fits(t, win)]
    if len(sized) == 1:
        return sized[0]
    pool = sized or cands
    active = [t for t in pool if _has(_states(t), Atspi.StateType.ACTIVE)]
    pool2 = active if win.get("focus") else [t for t in pool if t not in active]
    if len(pool2) == 1:
        return pool2[0]
    raise Ambiguous(f"「{win.get('title') or ''}」这个程序开着 {len(cands)} 个同名窗口,SeeU 分不清是哪一个,先停手没动"
                    "(免得写进别的窗口)。请先把要用的那个点到前台,或者关掉 / 改名多余的(比如先存成不同文件名)再试")


def frame_for(win):
    """小插件报的窗口 → 对应的 AT-SPI 顶层(按进程 + 标题对;同名的几个再比大小 / 前台)。找不到返回 None。"""
    tops = [t for a in apps_of(win["pid"]) for t in top_windows(a)]
    if not tops:
        return None
    title = (win.get("title") or "").strip()
    same = []
    for t in tops:
        try:
            if (t.get_name() or "").strip() == title:
                same.append(t)
        except Exception:   # noqa: BLE001
            continue
    if same:
        return pick_same_title(same, win)
    if len(tops) == 1:
        return tops[0]
    # 11-20 复查:标题对不上(刚改名、未保存加了 *)又有好几个窗口时,原来随手挑「当前的 / 第一个看得见的」可能对到别的窗口上
    # → 跟同名那条一样比大小、再看是不是当前窗口;挑不出唯一一个就报 Ambiguous,不乱挑
    showing = [t for t in tops if _has(_states(t), Atspi.StateType.SHOWING)] or tops
    return pick_same_title(showing, win)


# 🔴 一律用「接口名.方法(控件, …)」显式调:控件对象上有同名方法会盖掉接口的(11-18 栽过:acc.get_text 是「取文字接口」,
#    带参数调直接报错,又落到 Value 接口读出一串乱数字)。先看控件支持哪些接口再调。
def ifaces(acc):
    try:
        return set(acc.get_interfaces() or ())
    except Exception:   # noqa: BLE001
        return set()


def actions(acc):
    if "Action" not in ifaces(acc):
        return []
    try:
        n = Atspi.Action.get_n_actions(acc)
        return [Atspi.Action.get_action_name(acc, i) for i in range(n)]
    except Exception:   # noqa: BLE001
        return []


def text_of(acc, limit=20000):
    """控件里的文字(输入框 / 文档 / 标签)。读不到返回 None。"""
    fs = ifaces(acc)
    if "Text" in fs:
        try:
            n = Atspi.Text.get_character_count(acc)
            if n is not None and n >= 0:
                return Atspi.Text.get_text(acc, 0, min(n, limit))
        except Exception:   # noqa: BLE001
            pass
    if "Value" in fs:
        try:
            v = Atspi.Value.get_current_value(acc)
            return None if v is None else f"{v:g}"
        except Exception:   # noqa: BLE001
            return None
    return None


def rect(acc, origin, thin=False):
    """屏幕上的 (x, y, w, h)。origin = 窗口外框左上角。读不到返回 None。
    thin=True:宽或高是 0 的也收下(按 2 像素算)—— VS Code 这类自己画编辑器的,收键盘的是一个宽 0 的隐形输入框(11-18 实测)。"""
    try:
        e = acc.get_extents(Atspi.CoordType.WINDOW)
    except Exception:   # noqa: BLE001
        return None
    if e is None:
        return None
    if thin and (e.width > 0 or e.height > 0) and e.width >= 0 and e.height >= 0:
        return (origin[0] + e.x, origin[1] + e.y, max(e.width, 2), max(e.height, 2))
    if e.width <= 0 or e.height <= 0:
        return None
    return (origin[0] + e.x, origin[1] + e.y, e.width, e.height)


def is_password(acc, role=None):
    role = role or (acc.get_role_name() or "")
    if role == "password text":
        return True
    try:
        attrs = acc.get_attributes() or {}
        if str(attrs.get("input-type", "")).lower() == "password" or str(attrs.get("type", "")).lower() == "password":
            return True
    except Exception:   # noqa: BLE001
        pass
    return False


def elements(frame, origin, budget=WALK_BUDGET):
    """顶层窗口下所有值得列出的控件。每项:role、name、value、actions、editable、password、focused、rect、acc、path。"""
    out = []
    t0 = time.time()
    stack = [(frame, 0, ())]
    seen = 0
    truncated = False
    while stack:
        acc, depth, path = stack.pop()
        seen += 1
        if seen > MAX_NODES or time.time() - t0 > budget:
            truncated = True
            break
        try:
            role = acc.get_role_name() or ""
            st = _states(acc)
        except Exception:   # noqa: BLE001
            continue
        if depth and not _has(st, Atspi.StateType.SHOWING):
            continue                       # 看不见的(收起的菜单、别的标签页)整枝跳过
        if depth:
            name = (acc.get_name() or "").strip()
            acts = actions(acc)
            editable = _has(st, Atspi.StateType.EDITABLE) or role in ("password text", "terminal")
            pressable = any(a.lower() in PRESS_ACTIONS for a in acts)
            val = None
            if editable or role in ("text", "entry", "spin button", "slider", "combo box", "document text"):
                val = text_of(acc, 2000)
            want = pressable or editable or (name and role in TEXT_ROLES) or role == "terminal"   # 第二轮复查:终端一律列出来,好拦
            if want and role not in SKIP_ROLES:
                r = rect(acc, origin, thin=editable)
                if r is not None:
                    out.append(dict(role=role, name=name, value=val, actions=acts, editable=editable,
                                    writable=editable and "EditableText" in ifaces(acc),
                                    password=is_password(acc, role), focused=_has(st, Atspi.StateType.FOCUSED),
                                    enabled=_has(st, Atspi.StateType.ENABLED) or _has(st, Atspi.StateType.SENSITIVE),
                                    rect=r, acc=acc, path=path))
            # 文字类控件下面通常只剩一堆字块,不往下走(网页段落里的链接例外)
            # 11-18:没名字的 label / static 其实是个容器(VS Code 的编辑区就夹在这么一层下面),照常往下走
            if role in ("text", "entry", "password text", "terminal") or (role in ("label", "static") and name):
                continue
        try:
            n = acc.get_child_count()
        except Exception:   # noqa: BLE001
            continue
        if depth >= MAX_DEPTH:
            continue
        kids = []
        for i in range(min(n, 2000)):
            try:
                c = acc.get_child_at_index(i)
            except Exception:   # noqa: BLE001
                c = None
            if c is not None:
                kids.append((c, depth + 1, path + (i,)))
        stack.extend(reversed(kids))     # 先序遍历,顺序跟界面从上到下大致一致
    return out, truncated


def press(acc):
    """按控件自己的动作(按钮的 click、链接的 jump…)。返回用的动作名;没有能按的动作抛 RuntimeError。"""
    acts = actions(acc)
    low = [a.lower() for a in acts]                  # Qt 的动作名大写开头(Press、ShowMenu),GTK / Chrome 小写
    for want in PRESS_ACTIONS:
        if want in low:
            if not Atspi.Action.do_action(acc, low.index(want)):
                raise RuntimeError(f"控件没接受「{want}」")
            return want
    raise RuntimeError("这个控件没有能按的动作" + (f"(它只有 {acts})" if acts else ""))


def caret(acc):
    try:
        c = Atspi.Text.get_caret_offset(acc)
        return c if c is not None and c >= 0 else None
    except Exception:   # noqa: BLE001
        return None


def _count(acc):
    try:
        return Atspi.Text.get_character_count(acc)
    except Exception:   # noqa: BLE001
        return None


def _toolkit(acc):
    try:
        app = acc.get_application()
        return (app.get_toolkit_name() or "").lower() if app is not None else ""
    except Exception:   # noqa: BLE001
        return ""


def _insert_raw(acc, pos, text):
    """插入并核对字数。「长度」各家理解不一样(11-18 实测):GTK4 按 UTF-8 字节、Qt 按字符;
    给错了 GTK 会整段不写(中文一个字 3 字节)。先按界面库猜,字数没变就换另一种再试一次。"""
    nbytes, nchars = len(text.encode("utf-8")), len(text)
    order = [nbytes, nchars] if "gtk" in _toolkit(acc) else [nchars, nbytes]
    before = _count(acc)
    for n in dict.fromkeys(order):          # 去重(纯英文两种一样)
        Atspi.EditableText.insert_text(acc, pos, text, n)
        after = _count(acc)
        if before is None or after is None or after != before:
            return True
    return False


def selected(acc):
    """框里选中的那一段 (start, end);没选中 / 读不到 → None。"""
    try:
        if Atspi.Text.get_n_selections(acc) > 0:
            r = Atspi.Text.get_selection(acc, 0)
            a, b = sorted((r.start_offset, r.end_offset))
            if b > a:
                return a, b
    except Exception:   # noqa: BLE001
        pass
    return None


def insert(acc, text):
    """在光标处插入文字(光标读不到就加在末尾)。不经过键盘,不抢前台。返回插入的位置。
    框里有选中的字 → 先删掉再插,跟真键盘打字一样「替换选中的」(11-20:Codex 先 Ctrl+A 再写,原来是插在前面、旧字还在)。"""
    pos = caret(acc)
    sel = selected(acc)
    if sel:
        if not Atspi.EditableText.delete_text(acc, sel[0], sel[1]):
            raise RuntimeError("输入框没接受删除选中的字")
        try:
            Atspi.Text.remove_selection(acc, 0)
        except Exception:   # noqa: BLE001
            pass
        pos = sel[0]
    if pos is None:
        pos = _count(acc) or 0
    if not _insert_raw(acc, pos, text):
        raise RuntimeError("输入框没接受插入")
    try:
        Atspi.Text.set_caret_offset(acc, pos + len(text))
    except Exception:   # noqa: BLE001
        pass
    return pos


def replace_all(acc, text):
    """整段改写。有的程序(Chrome)不认「整段改写」→ 先删光再插。"""
    try:
        if Atspi.EditableText.set_text_contents(acc, text) and (text_of(acc) or "") == text:
            return
    except Exception:   # noqa: BLE001
        pass
    n = _count(acc) or 0
    if n and not Atspi.EditableText.delete_text(acc, 0, n):
        raise RuntimeError("输入框没接受删除")
    if text and not _insert_raw(acc, 0, text):
        raise RuntimeError("输入框没接受改写")


def still_there(acc):
    """控件还在、看得见。"""
    try:
        st = _states(acc)
        return st is not None and not _has(st, Atspi.StateType.DEFUNCT) and _has(st, Atspi.StateType.SHOWING)
    except Exception:   # noqa: BLE001
        return False


def signature(items):
    """一组控件的「样子」(名字、值、勾选),比较前后有没有变化用。"""
    sig = []
    for e in items:
        st = _states(e["acc"])
        sig.append((e["role"], e["name"], (text_of(e["acc"], 500) if e["editable"] else e.get("value")),
                    _has(st, Atspi.StateType.CHECKED), _has(st, Atspi.StateType.EXPANDED), _has(st, Atspi.StateType.SELECTED)))
    return sig
