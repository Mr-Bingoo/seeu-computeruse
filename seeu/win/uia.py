# -*- coding: utf-8 -*-
"""SeeU Windows 版 · UI 自动化(UIA):读控件清单、读文字、认密码框、按按钮。

在本进程里直接调(comtypes);探路时另起 PowerShell 一次约 1 秒,太慢。
🔴 读(控件清单、文字、密码框)不抢前台;**按(Invoke / Toggle / 选中…)会把目标拉到前台**(11-11 真机,记事本、Chrome 都抢),
   所以「按」只能放在 inputs.borrow_front 里做(借前台再还),由动作层决定什么时候走这一档。
依赖:comtypes(pip install comtypes,纯 Python)。
"""
import threading

_LOCAL = threading.local()

# 属性 / 模式 / 控件类型编号(微软公开文档 UIAutomationClient.h)
P_RECT, P_TYPE, P_NAME, P_FOCUS, P_FOCUSABLE, P_ENABLED, P_AUTOID = 30001, 30003, 30005, 30008, 30009, 30010, 30011
P_PASSWORD, P_OFFSCREEN, P_HWND = 30019, 30022, 30020
P_HAS_INVOKE, P_HAS_TOGGLE, P_HAS_SELECT, P_HAS_EXPAND, P_HAS_VALUE = 30031, 30041, 30036, 30028, 30043
P_VALUE = 30045
PAT_INVOKE, PAT_VALUE, PAT_EXPAND, PAT_SELECT, PAT_TEXT, PAT_TOGGLE = 10000, 10002, 10005, 10010, 10014, 10015
PAT_SCROLL = 10004
P_ARIA_ROLE, P_WIN_MODAL = 30101, 30077
TREE_DESC = 4

TYPES = {50000: "按钮", 50002: "勾选框", 50003: "下拉框", 50004: "输入框", 50005: "链接", 50006: "图片", 50007: "列表项",
         50008: "列表", 50009: "菜单", 50010: "菜单栏", 50011: "菜单项", 50013: "单选", 50015: "滑块", 50018: "标签栏",
         50019: "标签页", 50020: "文字", 50021: "工具栏", 50023: "树", 50024: "树节点", 50025: "自定义", 50026: "组",
         50029: "数据项", 50030: "文档", 50031: "拆分按钮", 50032: "窗口", 50033: "面板", 50034: "表头", 50035: "表头项",
         50037: "标题栏", 50038: "分隔线"}
# 进清单的:能点能填的 + 有名字的文字。面板、组、窗口这类容器不进(太多,AI 用不上)。
KEEP = {50000, 50002, 50003, 50004, 50005, 50007, 50011, 50013, 50015, 50019, 50024, 50029, 50030, 50031, 50035}
KEEP_IF_NAMED = {50020, 50006, 50025}


def _auto():
    a = getattr(_LOCAL, "auto", None)
    if a is None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        a = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        _LOCAL.auto, _LOCAL.U = a, U
    return a


def _U():
    _auto()
    return _LOCAL.U


def element(hwnd):
    return _auto().ElementFromHandle(hwnd)


def _cache():
    a = _auto()
    c = a.CreateCacheRequest()
    for p in (P_RECT, P_TYPE, P_NAME, P_FOCUS, P_ENABLED, P_AUTOID, P_PASSWORD, P_OFFSCREEN,
              P_HAS_INVOKE, P_HAS_TOGGLE, P_HAS_SELECT, P_HAS_EXPAND, P_HAS_VALUE, P_VALUE):
        c.AddProperty(p)
    return c


def _val(e, pid):
    try:
        return e.GetCachedPropertyValue(pid)
    except Exception:
        return None


def _item(e):
    """一个 UIA 元素(带缓存)→ 清单里的一项;不进清单的返回 None。"""
    t = _val(e, P_TYPE) or 0
    name = (_val(e, P_NAME) or "").strip()
    if t not in KEEP and not (t in KEEP_IF_NAMED and name):
        return None
    if _val(e, P_OFFSCREEN):
        return None
    r = e.CachedBoundingRectangle
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    acts = [k for k, p in (("invoke", P_HAS_INVOKE), ("toggle", P_HAS_TOGGLE), ("select", P_HAS_SELECT),
                           ("expand", P_HAS_EXPAND), ("value", P_HAS_VALUE)) if _val(e, p)]
    val = _val(e, P_VALUE) if "value" in acts else None
    pw = bool(_val(e, P_PASSWORD))
    return dict(name=name, role=TYPES.get(t, str(t)), type=t, rect=(r.left, r.top, w, h),
                enabled=bool(_val(e, P_ENABLED)), password=pw, focused=bool(_val(e, P_FOCUS)),
                actions=acts, value=None if pw else (val or None), autoid=_val(e, P_AUTOID) or "", el=e)


def elements(hwnd, limit=500):
    """窗口里的控件清单(只读,不抢前台)。每项:name、role(中文类型)、type、rect(x,y,w,h 屏幕物理像素)、
    enabled、password、focused、actions(invoke/toggle/select/expand/value)、value、el(UIA 元素,按的时候用)。
    窗口在别的虚拟桌面上时,再从各个子窗口问一遍补上(见 _child_items)。"""
    a = _auto()
    root = element(hwnd)
    arr = root.FindAllBuildCache(TREE_DESC, a.ControlViewCondition, _cache())
    out = []
    n = arr.Length if arr else 0
    for i in range(n):
        it = _item(arr.GetElement(i))
        if it is None:
            continue
        out.append(it)
        if len(out) >= limit:
            return out
    try:
        out += _child_items(hwnd, out, limit - len(out))
    except Exception:   # noqa: BLE001  补不上就算了,不影响主清单
        pass
    return out


CHILD_MAX = 80          # 最多问这么多个子窗口(按个数截、不按时间截:动作前后两次读要截在同一处,不然清单前后对不上会误判「变了」,二轮复查 11-18)


def _desk_kids(hwnd):
    """窗口在别的虚拟桌面上时,要从哪些子窗口补问(同一进程、看得见的,按列举顺序 = 先上级后下级);不在别的桌面返回 []。
    复查 11-18:用 window.children(api 里设好了参数类型,64 位句柄不出错);别的进程嵌进来的子窗口不问(安全底线只按顶层程序查过)。"""
    from seeu.win import window as W
    if not W.other_desktop(hwnd):
        return []
    import ctypes
    from seeu.win import api

    def pid(h):
        p = ctypes.c_ulong(0)
        api.user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        return p.value
    me = pid(hwnd)
    return [c["hwnd"] for c in W.children(hwnd) if c["visible"] and pid(c["hwnd"]) == me][:CHILD_MAX]


def _child_items(hwnd, have, room):
    """11-18 C-2.8(Win10 / Win11 实测):窗口在别的虚拟桌面上时,从顶层窗口往下读,系统只给菜单、标题栏按钮那几项,正文输入框不见了;
    但从各个子窗口句柄往下问,控件和值都还在:Win10 老式记事本(Edit)读得到全文;Win11 新记事本顶层只剩 6 项,
    从子窗口(DesktopChildSiteBridge 等)补回全部 34 项,按编号打字也进得去(两边 other_desk_type.py 各 7/7)。
    只在别的桌面上补;某个子窗口读出了东西,它下面的子窗口就不再重复读;按(类型, 位置, 名字)去重。只读。"""
    if room <= 0:
        return []
    from seeu.win import api
    kids = _desk_kids(hwnd)
    if not kids:
        return []
    a = _auto()
    seen = {(i["type"], tuple(i["rect"]), i["name"]) for i in have}
    done = set()            # 读出过东西的子窗口:它的子树已经包含下面各层
    out = []
    for c in kids:
        p, skip = c, False
        for _ in range(30):
            p = int(api.user32.GetAncestor(p, 1) or 0)          # 1 = GA_PARENT(SetParent 挂上去的也找得到上级)
            if not p or p == int(hwnd):
                break
            if p in done:
                skip = True
                break
        if skip:
            continue
        try:
            arr = element(c).FindAllBuildCache(7, a.ControlViewCondition, _cache())    # 7 = TreeScope_Subtree(连它自己)
        except Exception:   # noqa: BLE001
            continue
        got = False
        for i in range(arr.Length if arr else 0):
            try:
                it = _item(arr.GetElement(i))
            except Exception:   # noqa: BLE001  个别元素读错只跳过这一项
                continue
            if it is None:
                continue
            got = True
            k = (it["type"], tuple(it["rect"]), it["name"])
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
            if len(out) >= room:
                return out
        if got:
            done.add(int(c))
    return out


def current(item):
    """清单里这一项**现在**的样子(不用 see 时的缓存,真去问一次):返回 (类型, (x, y, w, h));
    控件已经不在了 / 滚出去看不见了 / 没有大小,返回 None。按编号操作前核对用(11-14)。"""
    try:
        e = item["el"]
        t = e.CurrentControlType
        if e.CurrentIsOffscreen:
            return None
        r = e.CurrentBoundingRectangle
        w, h = r.right - r.left, r.bottom - r.top
        return (t, (r.left, r.top, w, h)) if w > 0 and h > 0 else None
    except Exception:   # noqa: BLE001  控件没了时 UIA 报「元素不可用」
        return None


def at_point(x, y):
    """屏幕这一点上现在的控件:返回 (类型, 名字, 元素);问不到返回 None。只读。"""
    try:
        e = _auto().ElementFromPoint(_U().tagPOINT(int(round(x)), int(round(y))))
        return (e.CurrentControlType, (e.CurrentName or "").strip(), e) if e else None
    except Exception:   # noqa: BLE001
        return None


def find(hwnd, name):
    """按名字找控件:先全等,再包含。找不到抛 RuntimeError。"""
    items = elements(hwnd)
    hits = [i for i in items if i["name"] == name] or [i for i in items if name and name in i["name"]]
    if not hits:
        raise RuntimeError(f"窗口里没找到「{name}」")
    return hits[0]


def press(item):
    """按下控件(会抢前台!只在 borrow_front 里调)。返回用的模式名。"""
    U = _U()
    e = item["el"]
    for pat, iface, call in ((PAT_INVOKE, U.IUIAutomationInvokePattern, "Invoke"),
                             (PAT_TOGGLE, U.IUIAutomationTogglePattern, "Toggle"),
                             (PAT_SELECT, U.IUIAutomationSelectionItemPattern, "Select"),
                             (PAT_EXPAND, U.IUIAutomationExpandCollapsePattern, "Expand")):
        try:
            p = e.GetCurrentPattern(pat)
        except Exception:
            p = None
        if p:
            getattr(p.QueryInterface(iface), call)()
            return call
    raise RuntimeError(f"「{item['name']}」不能按")


def focused_in(hwnd):
    """这个窗口里有键盘焦点的控件(窗口在后台时,UIA 记的是它自己的焦点;读不到返回 None)。"""
    a = _auto()
    try:
        cond = a.CreatePropertyCondition(P_FOCUS, True)
        e = element(hwnd).FindFirstBuildCache(TREE_DESC, cond, _cache())
    except Exception:
        return None
    if not e:
        try:        # 复查 11-18:别的虚拟桌面上顶层树被截断,焦点(可能是密码框)要从子窗口补查
            kids = _desk_kids(hwnd)
        except Exception:   # noqa: BLE001
            kids = []
        for c in kids:      # 二轮复查:一个子窗口出错只跳过它,别连累后面的(密码框会漏认)
            try:
                e = element(c).FindFirstBuildCache(7, cond, _cache())
            except Exception:   # noqa: BLE001
                e = None
            if e:
                break
    if not e:
        return None
    return dict(name=_val(e, P_NAME) or "", type=_val(e, P_TYPE), password=bool(_val(e, P_PASSWORD)), el=e)


def read_element(e):
    """读一个控件的文字(值 / 文本),读不到 None。打字时读「刚点过的那个输入框」用,比猜焦点准(11-11:读成了地址栏)。"""
    U = _U()
    try:
        if _val(e, P_PASSWORD) or e.CurrentIsPassword:
            return None
    except Exception:
        pass
    for pat, iface, get in ((PAT_VALUE, U.IUIAutomationValuePattern, lambda p: p.CurrentValue),
                            (PAT_TEXT, U.IUIAutomationTextPattern, lambda p: p.DocumentRange.GetText(200000))):
        try:
            p = e.GetCurrentPattern(pat)
            if p:
                v = get(p.QueryInterface(iface))
                if v is not None:
                    return v
        except Exception:
            continue
    return None


CARET_MAX = 50000


def caret(hwnd):
    """输入区里光标在第几个字(选中了一段就是 (起点, 选中长度));读不到返回 None(11-15:核实 End / 方向键这类只挪光标的键)。
    只认有焦点的控件,再找第一个输入框;不退到「文档」(Electron 里那是整张网页,会动的内容会被当成光标挪了,11-15 复查)。只读。"""
    U = _U()

    def cands():                     # 焦点控件读不出来才去遍历找输入框(遍历整棵树费时间,11-15 第五轮复查)
        f = focused_in(hwnd)
        if f:
            yield f["el"]
        try:
            for it in elements(hwnd, limit=300):
                if it["type"] == 50004 and not it["password"]:
                    yield it["el"]
                    break
        except Exception:
            return
    for e in cands():
        try:
            if _val(e, P_PASSWORD):
                continue
            p = e.GetCurrentPattern(PAT_TEXT)
            if not p:
                continue
            tp = p.QueryInterface(U.IUIAutomationTextPattern)
            sel = tp.GetSelection()
            if not sel or sel.Length < 1:
                continue
            r = sel.GetElement(0)
            head = tp.DocumentRange.Clone()
            head.MoveEndpointByRange(1, r, 0)           # 文档开头 → 选区开头(1 = 终点,0 = 起点)
            pre = head.GetText(CARET_MAX)
            if len(pre) >= CARET_MAX:                   # 太长(大文档)就不核实了,免得读一大段
                return None
            return len(pre), len(r.GetText(CARET_MAX))
        except Exception:
            continue
    return None


def read_text(hwnd):
    """读窗口里输入区的文字(只读):优先有焦点的控件,再找第一个输入框 / 文档。读不到返回 None。
    VS Code(Monaco)没开屏幕阅读模式时只给一句提示,当成读不到(11-11 真机)。"""
    U = _U()
    cands = []
    f = focused_in(hwnd)
    if f:
        cands.append(f["el"])
    try:
        for it in elements(hwnd, limit=300):
            if it["type"] in (50004, 50030) and not it["password"]:
                cands.append(it["el"])
                break
    except Exception:
        pass
    for e in cands:
        if _val(e, P_PASSWORD):
            continue
        txt = None
        try:
            p = e.GetCurrentPattern(PAT_TEXT)
            if p:
                txt = p.QueryInterface(U.IUIAutomationTextPattern).DocumentRange.GetText(200000)
        except Exception:
            txt = None
        if not txt:
            try:
                p = e.GetCurrentPattern(PAT_VALUE)
                if p:
                    txt = p.QueryInterface(U.IUIAutomationValuePattern).CurrentValue
            except Exception:
                txt = None
        if txt and "editor is not accessible" not in txt:
            return txt
    return None


def scroll(hwnd, sx, sy, dy=0, dx=0):
    """用辅助功能的「滚动」接口后台滚 (sx, sy) 处能滚的区域(找不到就滚整个网页文档)。dy 负 = 往下翻,单位约像素。
    不碰鼠标、不抢前台(11-12 旧 Intel Mac 的 Win10 + Chrome 真机:小步一次约 40 像素,前台不变)。
    Chrome 的滚动条消息要真鼠标在窗口里才认,这条是它的补位。
    注意:Win10 虚拟机窗口没显示在 Mac 屏幕上时,Chrome 不给网页文档(找到 0 个),这时也滚不了。
    返回实际滚了几步;找不到能滚的区域返回 0。"""
    a, U = _auto(), _U()
    want_v, want_h = bool(dy), bool(dx)
    sp = None
    try:
        import ctypes.wintypes as wt
        e = a.ElementFromPoint(wt.POINT(int(sx), int(sy)))
        walker = a.ControlViewWalker
        found = None
        for _ in range(40):
            if e is None:
                break
            if found is None:
                try:
                    p = e.GetCurrentPattern(PAT_SCROLL)
                    if p:
                        s = p.QueryInterface(U.IUIAutomationScrollPattern)
                        if (want_v and s.CurrentVerticallyScrollable) or (want_h and s.CurrentHorizontallyScrollable):
                            found = s
                except Exception:
                    pass
            if e.CurrentNativeWindowHandle == hwnd:
                sp = found      # 那个点确实落在目标窗口里(没被别的窗口盖住)才用,否则退回滚整个网页文档
                break
            e = walker.GetParentElement(e)
    except Exception:
        sp = None
    if sp is None:
        d = element(hwnd).FindFirst(TREE_DESC, a.CreatePropertyCondition(P_TYPE, 50030))
        if d is None:
            return 0
        p = d.GetCurrentPattern(PAT_SCROLL)
        if not p:
            return 0
        sp = p.QueryInterface(U.IUIAutomationScrollPattern)
    steps = 0
    # 小步(SmallIncrement=4 / SmallDecrement=1)一次约 40 像素;不滚的方向填 NoAmount=2
    for amount, horiz in ((dy, False), (dx, True)):
        if not amount:
            continue
        n = min(100, max(1, round(abs(amount) / 40)))
        code = 4 if amount < 0 else 1
        for _ in range(n):
            if horiz:
                sp.Scroll(code, 2)
            else:
                sp.Scroll(2, code)
            steps += 1
    return steps


def blocking_dialog(hwnd):
    """窗口里挡着的弹窗(网页 / Electron 里的模态对话框,如 VS Code 第一次打开的「欢迎 / 登录」窗)。没有返回 None。
    认法:窗口里面(不含窗口本身)类型是「窗口」、且标了模态或网页角色是 dialog / alertdialog、在屏幕上有大小。
    11-12 Win10 真机:VS Code 欢迎窗 = 类型 50032「对话框」、role=dialog、模态 True;被它挡着时后台打字画面会变,却打不进编辑区。
    注意:Chrome / VS Code 的辅助功能是用到才建,刚打开时可能只给十几个元素、认不出,读不到就当没有。"""
    a = _auto()
    cond = a.CreatePropertyCondition(P_TYPE, 50032)
    try:
        arrs = [element(hwnd).FindAll(TREE_DESC, cond)]
    except Exception:
        return None
    try:            # 复查 11-18:别的虚拟桌面上顶层树被截断,弹窗也从子窗口补查
        for c in _desk_kids(hwnd):
            try:
                arrs.append(element(c).FindAll(TREE_DESC, cond))
            except Exception:   # noqa: BLE001
                pass
    except Exception:   # noqa: BLE001
        pass
    els = [arr.GetElement(i) for arr in arrs for i in range(arr.Length if arr else 0)]
    for e in els:
        try:
            if e.CurrentNativeWindowHandle == hwnd or e.CurrentIsOffscreen:
                continue
            role = e.GetCurrentPropertyValue(P_ARIA_ROLE) or ""
            modal = e.GetCurrentPropertyValue(P_WIN_MODAL)
            if not (modal is True or role in ("dialog", "alertdialog")):
                continue
            r = e.CurrentBoundingRectangle
            if r.right - r.left <= 0 or r.bottom - r.top <= 0:
                continue
            return dict(name=(e.CurrentName or "").strip(), rect=(r.left, r.top, r.right - r.left, r.bottom - r.top), el=e)
        except Exception:
            continue
    return None


def inside(e, ancestor, depth=60):
    """e 是不是 ancestor 里面的元素(含它自己)。读不出返回 False。"""
    a = _auto()
    try:
        walker = a.ControlViewWalker
        for _ in range(depth):
            if e is None:
                return False
            if a.CompareElements(e, ancestor):
                return True
            e = walker.GetParentElement(e)
    except Exception:
        return False
    return False
