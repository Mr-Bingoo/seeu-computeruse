# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 动作层(跟 Mac 版 seeu/act.py、Windows 版 seeu/win/act.py 同样的用法和返回格式)。

    import seeu
    v = seeu.see("gnome-text-editor")            # 截图 + 编号清单(AT-SPI 控件)
    seeu.tap("gnome-text-editor", "New Tab")     # 按名字 / 编号(上一次 see 的)
    seeu.type("gnome-text-editor", "你好", at=5)  # 写进第 5 项那个输入框

每个动作返回 dict:outcome = delivered(核实生效)| unverified(做了,没法核实)| ineffective(做了但没变化)
| refused(安全底线 / 做不到,原因在 reason)| failed(出错);route = 最后走的那条路;tried = 依次试过的路和结果;png = 最后一张截图。

Linux(GNOME + Wayland)跟 Mac / Windows 最大的不同:系统不让普通程序给别的窗口发键盘鼠标。所以
  能后台做的只有「按控件」:按按钮、往输入框里写字(都走 AT-SPI,不动鼠标键盘、不抢前台,窗口被挡着也行);
  按屏幕位置点、按别的键、滚没有滚动条的窗口、往 Chrome / Electron 的框里打字 → 借真鼠标 / 键盘(第 3 段,linux/real.py:
  系统「远程操作」授权,让路、拉前台、做完还原),归「借用鼠标」设置管(开 / 问我 / 关,跟 Mac / Windows 一样)。
坐标一律是屏幕逻辑像素(跟小插件、截图一致)。
"""
import os
import re
import sys
import time

from seeu.linux import atspi, real, safety, shell, shot, window as W

_last = {}            # 窗口号 → 上一次 see 的清单
_FIELD = {}           # 窗口号 → 上一次写过字的输入框(下次不指定 at 就写这里)
VERIFY_WAIT = 1.2     # 动作后最多等几秒看变化
NEAR = 60             # 点击处附近多大一块算「附近」(像素)
MIN_CHANGE = 0.05     # 整个窗口变了百分之几算有变化
NEAR_CHANGE = 1.0     # 附近变了百分之几算有变化
NEED_REAL = ("Linux(Wayland)上按屏幕位置点 / 按键 / 滚动要借你的真鼠标键盘(系统「远程操作」授权),"
             "这次调用不让借;按控件操作:先 see,按清单里的编号点、往输入框里写字")


def _refused(reason, route=None, **kw):
    return dict(outcome="refused", route=route, tried=[(route, "refused")] if route else [], reason=str(reason), **kw)


def _win(app, sticky=True):
    """找要操作的窗口。see 现找(前台的优先);别的动作先回到上次 see 这个写法时看的那个窗口 —— 同一个程序开着几个窗口时,
    看完用户把另一个点到前台,编号也不会对到别的窗口上去(x86 两个文本编辑器窗口实测;同 Mac / Windows 的 wrong_window 思路)。
    上次看的那个已经关了 → 现找,并把它的旧清单作废(编号要重新 see)。"""
    safety.check_unlocked()
    wid = _last.get(str(app)) if sticky else None
    w = None
    if wid is not None:
        try:
            w = W.find(f"#{wid}")
        except RuntimeError:
            _last.pop(str(app), None)
            _last.pop(wid, None)
    if w is None:
        w = W.find(app)
    safety.check_window(w)
    return w


def _origin(w, fr=None):
    """控件「窗口内坐标」的原点在屏幕上哪。GTK4 / Chrome / Electron = 窗口外框左上角;
    Qt 从它自己画的标题栏下面算起(FeatherPad 实测竖着差 39 像素)→ 比一下控件报的窗口大小和外框大小,差出来的补上
    (标题栏只在上面;左右的边框两边平分)。"""
    if fr is None:
        try:
            fr = atspi.frame_for(w)
        except Exception:   # noqa: BLE001
            fr = None
    dx = dy = 0
    if fr is not None:
        try:
            e = fr.get_extents(atspi.Atspi.CoordType.WINDOW)
            if 0 < e.height < w["h"] and w["h"] - e.height < 120:
                dy = w["h"] - e.height
            if 0 < e.width < w["w"] and w["w"] - e.width < 40:
                dx = (w["w"] - e.width) // 2
            # Chrome / Chromium 没最大化时,自己画的窗口阴影也算进「窗口内坐标」:报的比外框大一圈
            # (x86 实测 1265×1420 对外框 1221×1376,上 19 下 25 不对称)→ 原点用小插件给的含阴影画布左上角
            # (buf_x / buf_y);老版小插件没给就按四周平分估。不改的话点偏到右下(地址栏点成了网页)
            if w["w"] < e.width and e.width - w["w"] < 160 and w["h"] < e.height and e.height - w["h"] < 160:
                if w.get("buf_x") is not None and w.get("buf_y") is not None:
                    return (w["buf_x"], w["buf_y"])
                dx = -((e.width - w["w"]) // 2)
                dy = -((e.height - w["h"]) // 2)
        except Exception:   # noqa: BLE001
            pass
    return (w["x"] + dx, w["y"] + dy)


def _frame(w):
    fr = atspi.frame_for(w)
    if fr is None:
        raise RuntimeError(f"读不到「{w.get('title') or w['comm']}」的控件(这个程序没开辅助功能接口,或还没准备好;等一两秒再试)")
    return fr


def _shot(w, wins=None):
    """截这个窗口(整屏截了再裁)。返回 (png, 盖住的比例, 说明)。截不了返回 (None, 比例, 原因)。"""
    return _shot_rect(w, wins)[:3]


def _shot_rect(w, wins=None):
    """同 _shot,多返回第 4 项:截图实际对应屏幕上哪一块 (x, y, w, h)(截不了是 None)。
    窗口有一部分在屏幕外时,裁出来的图比窗口小、左上角也不是窗口左上角;原来把这个范围丢了,
    按截图位置点 / 认字清单都按整窗换算 → 点偏。"""
    cov = W.covered(w, wins)
    try:
        full = shot.full()
    except shot.NeedGrant as ex:
        return None, cov, str(ex), None
    except Exception as ex:   # noqa: BLE001
        return None, cov, f"截图出错:{ex}", None
    try:
        png, box = shot.crop(full, w["x"], w["y"], w["w"], w["h"], mask=W.sensitive_above(w, wins) if cov > 0 else ())
    except Exception as ex:   # noqa: BLE001
        return None, cov, str(ex), None
    finally:
        try:
            os.remove(full)          # 整屏原图裁完就删(原来最多攒 200 张)
        except OSError:
            pass
    note = None
    if w.get("minimized"):
        note = "窗口最小化了,截图里不是它"
    elif not w.get("active_ws", True):
        note = "窗口在另一个工作区,截图里不是它"
    elif cov > 0.02:
        note = f"窗口有 {cov * 100:.0f}% 被别的窗口挡着,截图里那部分是盖在上面的窗口"
    return png, cov, note, tuple(box)


def _item_text(e):
    name = " ".join((e["name"] or "").split())
    val = e.get("value")
    if val is not None:
        val = " ".join(str(val).split())
        if len(val) > 80:
            val = val[:80] + f"…(共 {len(str(e['value']))} 字)"
    if val and val != name:
        return f"{name} = {val}" if name else val
    return name


# ─────────────────────────────── 看 ───────────────────────────────

WIN_BUTTONS = {"minimize", "maximize", "restore", "restore down", "close", "unmaximize", "最小化", "最大化", "还原", "向下还原", "关闭", "取消最大化"}
EARLY_NOTE = "一个控件都没读到:程序刚打开的头几秒常常还没把控件交出来(Firefox 实测),等一两秒再 see 一次"


def see(app):
    """返回 {png, items, window, windows, note, stale, shot}。items 每项:id、kind(ax / ocr)、text、role、x/y(屏幕中心)、actions…
    shot = 截图实际对应屏幕上哪一块 (x, y, w, h)(窗口有一部分在屏幕外时比窗口小;没截图是 None)。"""
    w = _win(app, sticky=False)
    wins = W.list_windows()
    png, cov, note, box = _shot_rect(w, wins)
    fr = _frame(w)
    elems, truncated = atspi.elements(fr, _origin(w, fr))
    items = []
    for e in elems:
        x, y, ww, hh = e["rect"]
        items.append(dict(kind="ax", text=_item_text(e), role=atspi.ROLE_ZH.get(e["role"], e["role"]), x=x + ww / 2, y=y + hh / 2,
                          actions=e["actions"], password=e["password"], editable=e["editable"], focused=e["focused"],
                          el=e))
    # 标题栏上那三个按钮(GNOME 程序都有)不算「读得到控件」:不然游戏、模拟器这类窗口永远凑够 3 个、不认字(认字实测发现)
    real = [i for i in items if (i["actions"] or i["editable"]) and not (i["role"] == "按钮" and i["text"].strip().lower() in WIN_BUTTONS)]
    if png and cov < 0.02 and len(real) < 3:       # 读不到控件(游戏、模拟器、自绘界面):截图认字补清单
        try:
            from seeu.linux import ocr
            # 认出来的字的位置是截图里的 → 加截图实际的左上角(不是窗口左上角,窗口部分在屏幕外时两者不同);
            # win_xy 记下当时窗口在哪,之后按编号点时窗口挪了就跟着挪(见 _resolve)
            ox, oy = (box[0], box[1]) if box else (w["x"], w["y"])
            kx = ky = 1.0
            if box:                       # 显示缩放时截图是实际像素(比逻辑大),认字坐标按「范围 ↔ 图尺寸」换回逻辑
                from PIL import Image
                with Image.open(png) as _im:
                    kx, ky = box[2] / float(_im.width), box[3] / float(_im.height)
            for ln in ocr.recognize(png):
                items.append(dict(kind="ocr", text=ln["text"], role="认字", x=ox + (ln["x"] + ln["w"] / 2) * kx,
                                  y=oy + (ln["y"] + ln["h"] / 2) * ky, actions=[], password=False, editable=False,
                                  focused=False, el=None, win_xy=(w["x"], w["y"])))
        except Exception as ex:   # noqa: BLE001
            note = (note + ";" if note else "") + f"控件很少,本想认字补上,但{ex}"
    if not real and fr is not None:
        note = (note + ";" if note else "") + EARLY_NOTE
    for i, it in enumerate(items, 1):
        it["id"] = i
    _last[w["id"]] = items
    _last[str(app)] = w["id"]
    same = [x for x in wins if x["pid"] == w["pid"] or (x.get("wm_class") and x.get("wm_class") == w.get("wm_class"))]
    if truncated:
        note = (note + ";" if note else "") + "控件太多,只列了前面一部分"
    return {"png": png, "items": items, "windows": [x["title"] for x in same] if len(same) > 1 else [],
            "window": {k: w.get(k) for k in ("id", "title", "comm", "wm_class", "x", "y", "w", "h")},
            "note": note, "stale": note if (cov >= 0.02 or w.get("minimized") or not w.get("active_ws", True)) else None,
            "covered": cov, "shot": box if png else None}


def describe(items, en=None):
    """编号清单给人看的样子。en:英文时类别和标记换英文(控件上的字原样,不翻)。"""
    from seeu.linux import lang
    en = lang.is_en() if en is None else en
    out = []
    for it in items:
        el = it.get("el") or {}
        flag = "  [密码框]" if it.get("password") else (
            ("  [可写]" if el.get("writable", True) else "  [输入框,后台写不进]") if it.get("editable") else "")
        role = it.get("role", "")
        if en:
            role, flag = lang.ROLE_EN.get(role, role), lang.FLAG_EN.get(flag, flag)
        out.append(f"{it['id']:>3}. {role}  {it['text']}  ({it['x']:.0f},{it['y']:.0f}){flag}")
    return "\n".join(out)


# ─────────────────────────────── 找目标 ───────────────────────────────

class Stale(RuntimeError):
    pass


def _resolve(app, target, w):
    """target:编号(上一次 see 的)/ 名字 / 屏幕点 (x, y)。返回 (x, y, 控件 dict 或 None)。"""
    if isinstance(target, (tuple, list)) and len(target) == 2:
        return float(target[0]), float(target[1]), None
    s = str(target).strip()
    if s.isdigit():
        items = _last.get(w["id"])
        if not items:
            raise RuntimeError(f"先 see 一下「{app}」再按编号操作")
        n = int(s)
        if not 1 <= n <= len(items):
            raise RuntimeError(f"编号 {n} 不在上一次 see 的清单里(1~{len(items)})")
        it = items[n - 1]
        if it["kind"] == "ax" and not atspi.still_there(it["el"]["acc"]):
            raise Stale(f"第 {n} 项「{it['text']}」已经不在了(界面变了),请重新 see")
        return _relocate(it, w)
    # 按名字:现读一遍,完全相同优先,再找包含的;能按 / 能写的优先
    elems, _ = atspi.elements(_frame(w), _origin(w))
    low = s.lower()

    def rank(e):
        n = (e["name"] or "").strip().lower()
        exact = n == low
        part = low in n or (e.get("value") and low in str(e["value"]).lower())
        useful = bool(e["actions"]) or e["editable"]
        return (exact, bool(part), useful)
    cands = [e for e in elems if rank(e)[0] or rank(e)[1]]
    if not cands:
        raise RuntimeError(f"「{app}」里找不到「{s}」;先 see 看看清单")
    cands.sort(key=rank, reverse=True)
    e = cands[0]
    x, y, ww, hh = e["rect"]
    return x + ww / 2, y + hh / 2, e


def _relocate(it, w):
    """按编号操作时重读控件现在的位置。原来用 see 时记下的坐标,窗口挪过 / 界面滚过以后
    借真鼠标(点没有动作的控件、长按、在某一项上滚、先点进框再打字 / 按键)会点偏。读不到就用旧的(still_there 已经查过它还在)。
    返回 (x, y, 控件 dict 或 None);控件 dict 是带新位置的副本,不改上次 see 的清单。"""
    el = it.get("el")
    if it.get("kind") == "ax" and el is not None:
        try:
            rc = atspi.rect(el["acc"], _origin(w), thin=bool(el.get("editable")))
        except Exception:   # noqa: BLE001
            rc = None
        if rc is not None:
            return rc[0] + rc[2] / 2, rc[1] + rc[3] / 2, dict(el, rect=rc)
        return it["x"], it["y"], el
    # 认字出来的项没有控件可重读:窗口整个挪了就跟着挪
    wx, wy = it.get("win_xy") or (w["x"], w["y"])
    return it["x"] + (w["x"] - wx), it["y"] + (w["y"] - wy), el


# ─────────────────────────────── 核实 ───────────────────────────────

def _state(w, fr):
    """动作前后的「样子」:控件、窗口标题、窗口清单、前台。"""
    elems, _ = atspi.elements(fr, _origin(w, fr), budget=2.0)
    try:
        wins = W.list_windows()
    except Exception:   # noqa: BLE001
        wins = []
    me = next((x for x in wins if x["id"] == w["id"]), None)
    return dict(sig=atspi.signature(elems), title=me and me.get("title"), ids=sorted(x["id"] for x in wins),
                focus=next((x["id"] for x in wins if x.get("focus")), None), alive=me is not None)


def _verify(w, fr, before, read=None, timeout=VERIFY_WAIT):
    """动作后等一会儿,看变没变。read:读回函数,返回 True 就算核实。"""
    t0 = time.time()
    while True:
        if read is not None:
            try:
                if read():
                    return "delivered", "读回核对上了"
            except Exception:   # noqa: BLE001
                pass
        try:
            after = _state(w, fr)
        except Exception:   # noqa: BLE001
            after = None
        if after is not None:
            if not after["alive"]:
                return "delivered", "窗口关了"
            if after["title"] != before["title"]:
                return "delivered", "窗口标题变了"
            if after["ids"] != before["ids"]:
                return "delivered", "开 / 关了窗口"
            if after["sig"] != before["sig"]:
                return "delivered", "控件变了"
        if time.time() - t0 > timeout:
            return "unverified", "没看到控件、标题、窗口有变化(有的动作本来就看不出来,比如按了一个已经选中的按钮)"
        time.sleep(0.2)


# ─────────────────────────────── 借真鼠标键盘(第 3 段):能不能借、借了怎么报 ───────────────────────────────

ASK_REASON = ("后台做不到,要借用户的{what}(设置「借用鼠标」= 问我)。请问用户三选一:仅此一次 / 自动使用(这一轮不再问)/ 拒绝;"
              "选前两个就带上 allow_real=once 或 auto 再做一次这一步,拒绝就停手告诉用户卡在哪")
OFF_REASON = "后台做不到;按设置(借用鼠标 = 关)没借用户的鼠标键盘。停手告诉用户卡在哪(要借可以改设置:python3 -m seeu 设置 借用鼠标 开)"


def _gate(r, allow, what, w=None):
    """后台不行时能不能借。能借返回 None;不能借返回填好原因的结果(ask_user / refused)。
    先查借不借得成(锁屏、系统弹框、窗口最小化 / 在别的工作区、不碰的程序),再看「借用鼠标」设置 ——
    原来「问我」时先问用户,用户答应了才发现锁着屏借不了。"""
    if w is not None:
        try:
            real.check_window(w)
        except (safety.Refused, shell.NoHelper) as ex:
            r.update(outcome="refused", reason=str(ex), code="not_borrowable")
            return r
    if real.allowed(allow):
        return None
    if real.mode() == "ask":
        r.update(outcome="ask_user", reason=ASK_REASON.format(what=what))
        shell.toast(f"SeeU 想借你的{what.removesuffix('一下')}一下,AI 会问你", 8000)       # shell.toast 里按语言转
    else:
        r.update(outcome="refused", reason=OFF_REASON)
    return r


def _borrowed(r, route, fn, verify):
    """真借一次。fn() 做事(返回借用记录);verify() 返回 (outcome, how)。各种借不了的情况翻成结果。"""
    tried = list(r.get("tried") or [])
    try:
        b = fn()
    except real.SeeUBusy as ex:
        r.update(outcome="busy", code="busy", route=route, reason=str(ex), tried=tried + [(route, "busy")])
        return r
    except real.UserBusy as ex:
        r.update(outcome="refused", code="user_busy", route=route, reason=str(ex), tried=tried + [(route, "user_busy")])
        return r
    except real.NeedGrant as ex:
        r.update(outcome="refused", code="need_grant", route=route, reason=str(ex), tried=tried + [(route, "need_grant")])
        return r
    except (safety.Refused, shell.NoHelper) as ex:
        r.update(outcome="refused", route=route, reason=str(ex), tried=tried + [(route, "refused")])
        return r
    except Exception as ex:   # noqa: BLE001
        r.update(outcome="failed", route=route, reason=str(ex), tried=tried + [(route, f"error:{ex}")])
        return r
    outcome, how = verify()
    r.update(outcome=outcome, route=route, how=how, borrow=b, tried=tried + [(route, outcome)])
    r.pop("reason", None)
    r.pop("code", None)
    return r


def _mark(w, x, y):
    """悬浮标「看画面」时在小画面上标出点的位置(同 Windows floatwin.mark)。只是显示,出错不管。"""
    try:
        from seeu.linux import floatwin
        if w.get("w") and w.get("h"):
            floatwin.mark((x - w["x"]) / float(w["w"]), (y - w["y"]) / float(w["h"]), w["id"])
    except Exception:   # noqa: BLE001
        pass


def _bg_cursor(x, y, click=False):
    """后台动作也亮紫色代理光标(跟 Mac 一样:滑过去、点的话到点缩一下 + 波纹;停下 60 秒淡出)。只是显示。"""
    label, col, key = real.task_cursor("bg")
    t = shell.cursor(x, y, label, col, 60000, "click" if click else "move", key=key, auto=True)
    if t > 0:
        time.sleep(min(t, 0.65))          # 等光标滑到位再动手,波纹跟动作对上(同 Mac)


# ─────────────────────────────── 点 ───────────────────────────────

def tap(app, target, allow=None, real_ok=True, **kw):
    """点:先按控件自己的动作(后台、不抢前台);按屏幕位置、或控件没有能按的动作 → 借真鼠标(归「借用鼠标」设置管)。"""
    real_ok = kw.get("real", real_ok)          # 跟 Mac 版同名参数 real=False(不借)
    try:
        w = _win(app)
        _no_user_browser(w)                 # 用户自己开着的浏览器不碰(绕开网页允许名单)
        x, y, e = _resolve(app, target, w)
    except safety.Refused as ex:
        return _refused(ex)
    except Stale as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    except RuntimeError as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    try:
        safety.check_control(e)                  # 内嵌终端
        _check_name(e)
    except safety.Refused as ex:
        return _refused(ex)
    fr = _frame(w)
    _mark(w, x, y)
    r = dict(outcome="failed", route=None, tried=[], xy=(round(x), round(y)), png=None)
    if e is not None and any(a.lower() in atspi.PRESS_ACTIONS for a in e["actions"]):
        if not e.get("enabled", True):
            return dict(outcome="ineffective", route="按控件", tried=[("按控件", "灰着的")], reason="这个控件是灰的(现在按不了)")
        before = _state(w, fr)
        _bg_cursor(x, y, click=True)
        try:
            used = atspi.press(e["acc"])
        except Exception as ex:   # noqa: BLE001
            r["tried"].append(("按控件", f"error:{ex}"))
            used = None
        if used is not None:
            outcome, how = _verify(w, fr, before)
            _FIELD.pop(w["id"], None)
            return dict(outcome=outcome, route="按控件", tried=[("按控件", outcome)], how=f"{used};{how}",
                        xy=(round(x), round(y)), png=None)
    if e is None:
        # 按屏幕位置:AI 是从截图上挑的点 → 那一点被别的窗口挡着时,截图里看到的就不是它,不点(同 Mac「看不见就不按位置点」)
        if not W.point_visible(w, x, y):
            return _refused("那个位置被别的窗口挡着(截图里那块是盖在上面的窗口),SeeU 不按位置点;"
                            "按清单里的编号点,或请用户把窗口露出来", route="借真鼠标")
        r["tried"].append(("按控件", "屏幕位置"))
    elif not r["tried"]:
        r["tried"].append(("按控件", "没有能按的动作"))
    if not real_ok:
        return _refused(f"后台做不到。{NEED_REAL}", route="按控件", xy=(round(x), round(y)))
    g = _gate(r, allow, "鼠标", w)
    if g:
        return g
    before = _state(w, fr)
    out = _borrowed(r, "借真鼠标", lambda: real.click(w, x, y), lambda: _verify(w, fr, before))
    _FIELD.pop(w["id"], None)
    return out


# ─────────────────────────────── 菜单栏(照 Mac act.menu) ───────────────────────────────

MENU_ITEM_ROLES = ("menu item", "menu", "check menu item", "radio menu item", "tearoff menu item")
# 按编号点这些控件前也查危险菜单名(注销、清空回收站、「运行」…);GNOME 程序的菜单在 ≡ 里,只能按编号点
TAP_CHECK_ROLES = set(MENU_ITEM_ROLES) | {"push button", "button", "toggle button", "list item"}
PASTE_MENU = re.compile(r"粘贴|貼上|剪切|剪下|^\s*(paste|cut)\b", re.I)
NO_MENUBAR = ("这个程序没有菜单栏(GNOME 自带程序把菜单放在标题栏右边的「≡」按钮里):用 seeu_see 找到那个按钮按编号点,"
              "菜单弹出来后再按编号点里面的项")
MENU_FRONT_WATCH_S = 1.2


def _clean(t):
    return re.sub(r"[_&]|\s*(\.\.\.|…)\s*$", "", str(t or "")).strip().lower()


def _menu_kids(acc, depth=0):
    """acc 下面一层的菜单项(中间夹着的 menu / popup 容器跳过去,最多往下看 3 层)。"""
    out = []
    try:
        n = acc.get_child_count()
    except Exception:   # noqa: BLE001
        return out
    for i in range(min(n, 200)):
        try:
            c = acc.get_child_at_index(i)
            role = c.get_role_name()
        except Exception:   # noqa: BLE001
            continue
        if role in MENU_ITEM_ROLES and (c.get_name() or "").strip():
            out.append(c)
        elif depth < 3 and role not in MENU_ITEM_ROLES:
            out.extend(_menu_kids(c, depth + 1))
        elif depth < 3 and role in MENU_ITEM_ROLES and not (c.get_name() or "").strip():
            out.extend(_menu_kids(c, depth + 1))
    return out


def _menubar(fr, depth=0):
    try:
        if fr.get_role_name() == "menu bar":
            return fr
        n = fr.get_child_count()
    except Exception:   # noqa: BLE001
        return None
    if depth >= 6:
        return None
    for i in range(min(n, 60)):
        try:
            m = _menubar(fr.get_child_at_index(i), depth + 1)
        except Exception:   # noqa: BLE001
            m = None
        if m is not None:
            return m
    return None


def _pick(items, want):
    w = _clean(want)
    names = [(c, _clean(c.get_name())) for c in items]
    for test in (lambda n: n == w, lambda n: n.startswith(w), lambda n: w in n):
        hit = [c for c, n in names if test(n)]
        if hit:
            return hit[0]
    return None


def menu(app, *path):
    """点菜单栏里的项,path 例 ("File", "New")(按程序界面的语言写)。按控件后台点,不打开菜单、不动鼠标;
    点完盯一会儿前台,程序自己跳到前面就把前台还给用户原来的窗口(同 Mac _keep_front)。"""
    path = [str(p) for p in path if str(p).strip()]
    if not path:
        return dict(outcome="failed", route=None, tried=[], reason="没写点哪个菜单(例:File、New)")
    try:
        safety.check_menu(path)
        w = _win(app)
        _no_user_browser(w)                 # 用户自己开着的浏览器不碰(绕开网页允许名单)
    except safety.Refused as ex:
        return _refused(ex)
    except RuntimeError as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    if any(PASTE_MENU.search(p) for p in path) and _focused_password(w):
        return _refused("光标在密码框里,SeeU 不往里粘贴 / 剪切(这一步请你自己来)")
    try:
        fr = _frame(w)
    except RuntimeError as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    bar = _menubar(fr)
    if bar is None:
        return dict(outcome="failed", route="菜单", tried=[("菜单", "没有菜单栏")], reason=NO_MENUBAR)
    cur, got = bar, []
    for i, want in enumerate(path):
        kids = _menu_kids(cur)
        hit = _pick(kids, want)
        if hit is None:
            have = "、".join(dict.fromkeys((c.get_name() or "").strip() for c in kids if (c.get_name() or "").strip()))[:300]
            where = "菜单栏" if i == 0 else "「" + " › ".join(got) + "」下面"
            return dict(outcome="failed", route="菜单", tried=[("菜单", "找不到")],
                        reason=f"{where}没有「{want}」(有:{have or '空的'})")
        got.append((hit.get_name() or "").strip())
        cur = hit
    # _pick 按「全等 → 开头 → 包含」挑,AI 写「Ru」会挑中「Run」→ 对挑中的真名字再过一遍拦截
    try:
        safety.check_menu(got)
    except safety.Refused as ex:
        return _refused(ex)
    if any(PASTE_MENU.search(g) for g in got) and _focused_password(w):
        return _refused("光标在密码框里,SeeU 不往里粘贴 / 剪切(这一步请你自己来)")
    if not any(a.lower() in atspi.PRESS_ACTIONS for a in atspi.actions(cur)):
        return dict(outcome="failed", route="菜单", tried=[("菜单", "下面还有一层")],
                    reason=f"「{' › '.join(got)}」是一组菜单,下面还要再选一项(有:" +
                           "、".join((c.get_name() or "").strip() for c in _menu_kids(cur))[:300] + ")")
    try:
        if not cur.get_state_set().contains(atspi.Atspi.StateType.ENABLED):
            return dict(outcome="ineffective", route="菜单", tried=[("菜单", "灰着的")], reason="这个菜单项是灰的(现在点不了)")
    except Exception:   # noqa: BLE001
        pass
    before = _state(w, fr)
    try:
        f0 = shell.focus()
    except Exception:   # noqa: BLE001
        f0 = 0
    try:
        used = atspi.press(cur)
    except Exception as ex:   # noqa: BLE001
        return dict(outcome="failed", route="菜单", tried=[("菜单", f"error:{ex}")], reason=str(ex))
    note = _keep_front(f0, w, before.get("ids"))
    outcome, how = _verify(w, fr, before)
    r = dict(outcome=outcome, route="菜单", tried=[("菜单", outcome)], how=f"{used};{how}", path=got, png=None)
    if note:
        r["note"] = note
    return r


def _keep_front(f0, w=None, before_ids=None):
    """菜单点完盯一会儿:前台被换走(程序自己跳到了前面)就还给原来的窗口。返回一句说明或 None。
    原来这 1.2 秒里前台换成谁都拽回去,用户自己切窗口也被拽。照 openapp.give_back 的判断:
    新前台是目标程序的窗口、或点之前还没有的新窗口,才算「程序自己跳出来」;用户切到别的早就开着的窗口不管。
    w = 目标窗口,before_ids = 点之前的窗口号清单(老调用不带 w = 照旧一律拽回)。"""
    if not f0:
        return None
    t0, moved = time.time(), False
    while time.time() - t0 < MENU_FRONT_WATCH_S:
        time.sleep(0.15)
        try:
            fg = shell.focus()
            if fg not in (f0, 0) and _jumped(fg, w, before_ids):
                moved = True
                shell.activate(f0)
        except Exception:   # noqa: BLE001
            return None
    if not moved:
        return None
    try:
        back = shell.focus() == f0
    except Exception:   # noqa: BLE001
        back = False
    return "程序自己跳到了最前面," + ("已切回原来的窗口" if back else "没能切回原来的窗口")


def _jumped(fg, w, before_ids, wins=None):
    """新前台 fg 是不是「目标程序自己跳出来的」(不是用户自己切过去的)。"""
    if w is None:
        return True
    me = next((x for x in (W.list_windows() if wins is None else wins) if x["id"] == fg), None)
    if me is None:
        return False
    if me["id"] == w["id"] or (me.get("pid") and me.get("pid") == w.get("pid")):
        return True
    return before_ids is not None and me["id"] not in before_ids


# ─────────────────────────────── 长按、拖动 ───────────────────────────────

BROWSERS = ("chromium", "chrome", "google-chrome", "firefox", "brave", "vivaldi", "opera", "epiphany", "msedge", "microsoft-edge")
NO_BROWSER = ("浏览器里不长按 / 不拖动(这两样按屏幕位置操作,会绕开网页的允许名单);"
              "网页请用 SeeU 专用浏览器(seeu_web_open)按编号点")


NO_USER_BROWSER = ("这是你自己开着的浏览器:SeeU 不在里面点、打字、按键、滚动(会绕开网页的允许名单,还带着你的登录);"
                   "网页请用 SeeU 专用的后台浏览器(seeu_web_open),要登录时再叫出来让用户自己登")


def _no_user_browser(w):
    """用户自己的 Firefox / Chrome 这类窗口,点 / 写 / 按 / 滚 / 菜单一律不做;看(see)照常。"""
    if _is_browser(w):
        raise safety.Refused(NO_USER_BROWSER)


def _is_browser(w):
    ns = " ".join([w.get("comm") or "", w.get("wm_class") or "", w.get("app_id") or ""] + list(w.get("names") or [])).lower()
    return any(b in ns for b in BROWSERS)


def _check_name(e):
    """危险名字的按钮 / 菜单项不点(tap 查;长按、带 target 的按键 / 打字会先点它,一样查)。"""
    if e is not None and e.get("role") in TAP_CHECK_ROLES and (e.get("name") or "").strip():
        safety.check_menu([e["name"]], run=e.get("role") != "list item")


def long_press(app, target, ms=1000, allow=None):
    """长按:Linux 的辅助功能接口没有「按住」,直接借真鼠标(归「借用鼠标」设置管;同 Mac / Windows 后台不行再借)。浏览器里不做。"""
    try:
        w = _win(app)
        if _is_browser(w):
            return _refused(NO_BROWSER)
        x, y, e = _resolve(app, target, w)
        safety.check_control(e)
        _check_name(e)
    except safety.Refused as ex:
        return _refused(ex)
    except (Stale, RuntimeError) as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    if e is None and not W.point_visible(w, x, y):
        return _refused("那个位置被别的窗口挡着(截图里那块是盖在上面的窗口),SeeU 不按位置操作;"
                        "按清单里的编号,或请用户把窗口露出来", route="借真鼠标")
    fr = _frame(w)
    _mark(w, x, y)
    r = dict(outcome="failed", route=None, tried=[("按控件", "辅助功能接口没有长按")], xy=(round(x), round(y)), png=None)
    g = _gate(r, allow, "鼠标长按一下", w)
    if g:
        return g
    before = _state(w, fr)
    return _borrowed(r, "借真鼠标长按", lambda: real.long_press(w, x, y, ms), lambda: _verify(w, fr, before))


def drag(app, pts, hold_ms=0, allow=None):
    """拖动:pts = 屏幕点列表(至少两个,起点在前),每个点都要在窗口里、没被挡。借真鼠标拖。浏览器里不做。"""
    try:
        w = _win(app)
    except safety.Refused as ex:
        return _refused(ex)
    if _is_browser(w):
        return _refused(NO_BROWSER)
    try:
        pts = [(float(p[0]), float(p[1])) for p in pts]
    except (TypeError, ValueError, IndexError):
        return dict(outcome="failed", route=None, tried=[], png=None, reason="拖动的点要写成 [x, y] 的列表")
    if len(pts) < 2:
        return dict(outcome="failed", route=None, tried=[], png=None, reason="拖动至少要起点、终点两个点")
    out = [p for p in pts if not (w["x"] <= p[0] < w["x"] + w["w"] and w["y"] <= p[1] < w["y"] + w["h"])]
    if out:
        return dict(outcome="failed", route=None, tried=[], png=None, reason=f"有点不在窗口里:{out[0]},SeeU 只在这个窗口里拖")
    hid = [p for p in pts if not W.point_visible(w, *p)]
    if hid:
        return _refused(f"有点被别的窗口挡着:{hid[0]},SeeU 不按位置拖;请用户把窗口露出来", route="借真鼠标")
    fr = _frame(w)
    r = dict(outcome="failed", route=None, tried=[("按控件", "辅助功能接口没有拖动")], png=None)
    g = _gate(r, allow, "鼠标拖一下", w)
    if g:
        return g
    before = _state(w, fr)
    out = _borrowed(r, "借真鼠标拖动", lambda: real.drag(w, pts, hold_ms), lambda: _verify(w, fr, before))
    _FIELD.pop(w["id"], None)
    return out


# ─────────────────────────────── 打字 ───────────────────────────────

def _field(app, w, at):
    """要写字的那个输入框。at:编号 / 名字;不给就用上一次写过的、或现在有焦点的。"""
    if at is not None:
        x, y, e = _resolve(app, at, w)
        if e is None:
            raise RuntimeError("写字要指定输入框(编号或名字),不能按屏幕位置")
        return e
    e = _FIELD.get(w["id"])
    if e is not None and atspi.still_there(e["acc"]):
        cx, cy = _center(e)
        return _relocate(dict(kind="ax", el=e, x=cx, y=cy), w)[2]      # 上次写过的框也重读现在的位置
    elems, _ = atspi.elements(_frame(w), _origin(w))
    foc = [x for x in elems if x["editable"] and x["focused"]]
    if foc:
        return foc[0]
    edits = [x for x in elems if x["editable"] and x.get("role") != "terminal"]   # 终端面板不算,免得编辑区挑不出来
    if len(edits) == 1:
        return edits[0]
    raise RuntimeError("不知道往哪个输入框写:用 at= 指定 see 清单里的编号或名字" +
                       (f"(这个窗口有 {len(edits)} 个输入框)" if edits else "(这个窗口里没读到输入框)"))


def _center(e):
    x, y, ww, hh = e["rect"]
    return x + ww / 2, y + hh / 2


def type(app, text, enter=False, at=None, allow=None):   # noqa: A001   跟 Mac / Windows 版同名
    """往输入框里写字:先在光标处插入(不经过键盘、不抢前台);框不让插(Chrome、Electron)→ 借真键盘(点进框里再打)。
    enter=True:写完核对对了再「回车」(单行框用它自己的确认动作,多行框加换行,都不行就借键盘按回车)。"""
    try:
        safety.check_text(text)
        w = _win(app)
        _no_user_browser(w)                 # 用户自己开着的浏览器不碰(绕开网页允许名单)
        e = _field(app, w, at)
    except safety.Refused as ex:
        return _refused(ex)
    except (RuntimeError, Stale) as ex:
        return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    if e["password"]:
        return _refused("这是密码框,SeeU 不往里写(这一步请你自己来)", route="写字")
    try:
        safety.check_control(e)                  # 内嵌终端
    except safety.Refused as ex:
        return _refused(ex, route="写字")
    if not e["editable"]:
        return _refused(f"「{e['name'] or e['role']}」不是能写字的框", route="写字")
    acc = e["acc"]
    old = atspi.text_of(acc) or ""
    cx, cy = _center(e)
    r = dict(outcome="failed", route=None, tried=[], png=None)
    pos = None
    sel = None
    if e.get("writable", True):
        _bg_cursor(cx, cy)
        try:
            sel = atspi.selected(acc)
            pos = atspi.insert(acc, text)
        except Exception as ex:   # noqa: BLE001
            r["tried"].append(("写字", f"error:{ex}"))
    else:
        # Chrome / Chromium / Electron 在 Linux 上不给「改文字」接口(实测:网页框、地址栏都没有 EditableText)
        r["tried"].append(("写字", "框不让辅助功能接口写"))

    def read():
        now = atspi.text_of(acc) or ""
        if pos is not None and now[pos:pos + len(text)] == text:
            return True
        # 借键盘时点进框里可能先全选了原来的字(Chrome 地址栏):不比长度,只看这段字比原来多出现了一次
        t, n, o = text.replace("\n", ""), now.replace("\n", ""), old.replace("\n", "")
        return bool(t) and n.count(t) > o.count(t)

    def wait_read():
        t0 = time.time()
        while time.time() - t0 < VERIFY_WAIT:
            try:
                if read():
                    return "delivered", "读回核对上了"
            except Exception:   # noqa: BLE001
                pass
            time.sleep(0.15)
        return "unverified", "读回对不上(有的程序读回会慢,或读不到)"

    if pos is not None:
        outcome, how = wait_read()
        if sel:
            how += f";替换了原来选中的 {sel[1] - sel[0]} 个字"
        r.update(outcome=outcome, route="写字", how=how)
        r["tried"].append(("写字", outcome))
    else:
        g = _gate(r, allow, "键盘", w)
        if g:
            if g["outcome"] == "refused" and not e.get("writable", True) and g.get("code") != "not_borrowable" and real.mode() == "off":   # 锁屏、弹框这类原因别盖掉
                g["reason"] = ("这个输入框不让辅助功能接口写字(VS Code 这类 Electron 程序在 Linux 上都这样),"
                               "又没借键盘(借用鼠标 = 关)。网页请用 SeeU 专用浏览器;要借键盘可以改设置")
            return g
        r = _borrowed(r, "借真键盘", lambda: real.type_text(w, text, click_at=(cx, cy), check=_focus_guard(w, e)), wait_read)
        if r["outcome"] in ("failed", "refused", "busy"):
            return r
    _FIELD[w["id"]] = e
    if enter:
        if r["outcome"] != "delivered":
            r["enter"] = "skipped"            # 没核实打进去就不回车(跟 Mac 一样)
        else:
            res = _enter(e)
            if res == "delivered":
                r["enter"] = res
            elif real.allowed(allow):
                try:
                    # 原来直接按回车,不点框也不核焦点(排队 + 等用户停手这几秒焦点可能换了,回车按到别处)。
                    # 照 press 带 at 的写法:先点进这个框、按之前核一遍焦点(在密码框 / 内嵌终端 / 别的框里就不按)。
                    # 多行框不点(点中间会把光标挪走,回车换行换错地方),只核焦点
                    real.key(_fresh_win(w), "return", click_at=None if _multiline(e) else (cx, cy),
                             check=_focus_guard(w, e, "return"))
                    r["enter"] = "delivered(借键盘)"
                except Exception as ex:   # noqa: BLE001
                    r["enter"] = f"failed:{ex}"
            else:
                r["enter"] = "skipped:这个框没有「确认」动作,按设置没借键盘按回车"
    return r


def _multiline(e):
    try:
        from gi.repository import Atspi
        return bool(e["acc"].get_state_set().contains(Atspi.StateType.MULTI_LINE))
    except Exception:   # noqa: BLE001
        return False


def _fresh_win(w):
    for x in W.list_windows():
        if x["id"] == w["id"]:
            return x
    return w


def _enter(e):
    acc = e["acc"]
    acts = [a.lower() for a in e["actions"]]
    for a in ("activate",):
        if a in acts:
            try:
                from gi.repository import Atspi
                Atspi.Action.do_action(acc, acts.index(a))
                return "delivered"
            except Exception:   # noqa: BLE001
                break
    try:
        from gi.repository import Atspi
        if e.get("writable", True) and acc.get_state_set().contains(Atspi.StateType.MULTI_LINE):
            atspi.insert(acc, "\n")
            return "delivered"
    except Exception:   # noqa: BLE001
        pass
    return "unsupported:这个框没有「确认」动作"


# ─────────────────────────────── 按键 / 滚动 ───────────────────────────────

def _focus_guard(w, e=None, key=None, mods=()):
    """借键盘真打 / 真按之前(排完队、点进框以后)再看一眼焦点:
    在密码框里(要打字、或要按会改内容的键)、在内嵌终端里 → 拒;点进去以后焦点落在别的框上 → 不打,请 AI 重新看。读不到焦点就放行。"""
    def check():
        try:
            elems, _ = atspi.elements(_frame(w), _origin(w), budget=1.0)
        except Exception:   # noqa: BLE001
            return
        foc = [x for x in elems if x.get("focused")]
        if any(x["password"] for x in foc) and (key is None or safety.key_enters(key, list(mods))):
            raise safety.Refused("光标在密码框里,SeeU 不打字、不按会改内容的键(这一步请你自己来)")
        for x in foc:
            safety.check_control(x)
        if e is not None and foc and not any(_overlap(x["rect"], e["rect"]) for x in foc):
            raise RuntimeError("点进去以后光标不在要写的那个框里(界面可能滚动或变了),SeeU 没打字;请重新 see 再按编号写")
    return check


def _overlap(a, b):
    """两个控件框(x, y, w, h)互相包含对方中心 = 当成同一个(Chrome 报焦点的常是框里面那一层)。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax <= bx + bw / 2 <= ax + aw and ay <= by + bh / 2 <= ay + ah) or \
           (bx <= ax + aw / 2 <= bx + bw and by <= ay + ah / 2 <= by + bh)


def _focused_terminal(w):
    """焦点在内嵌终端上就返回那个控件(给 safety.check_control);读不到返回 None。"""
    try:
        elems, _ = atspi.elements(_frame(w), _origin(w), budget=1.5)
        return next((x for x in elems if x["focused"] and x.get("role") == "terminal"), None)
    except Exception:   # noqa: BLE001
        return None


def _focused_password(w):
    try:
        elems, _ = atspi.elements(_frame(w), _origin(w), budget=1.5)
        return any(x["password"] and x["focused"] for x in elems)
    except Exception:   # noqa: BLE001
        return False


def press(app, key, *mods, at=None, allow=None):
    """按键:回车、Ctrl+A 先用控件接口代替(后台);别的键借真键盘(at = 先点进那个框)。"""
    try:
        safety.check_keys(key, mods)
        w = _win(app)
        _no_user_browser(w)                 # 用户自己开着的浏览器不碰(绕开网页允许名单)
    except safety.Refused as ex:
        return _refused(ex)
    k = safety.norm_key(key)
    m = set(safety.norm_mods(mods))
    r = dict(outcome="failed", route=None, tried=[])
    e = None
    if at is not None:
        try:
            e = _field(app, w, at)
        except (RuntimeError, Stale) as ex:
            return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    try:
        safety.check_control(e if e is not None else _focused_terminal(w))     # 内嵌终端不按键
        _check_name(e)
    except safety.Refused as ex:
        return _refused(ex, route="按键")
    if (e is not None and e["password"] or e is None and _focused_password(w)) and safety.key_enters(key, list(m)):
        return _refused("光标在密码框里,SeeU 不按会改内容的键(这一步请你自己来)", route="按键")
    if k == "return" and not m:
        try:
            fe = e or _field(app, w, None)
            if _enter(fe) == "delivered":
                return dict(outcome="unverified", route="控件确认动作", tried=[("控件确认动作", "unverified")],
                            how="用输入框自己的「确认」动作代替回车")
            r["tried"].append(("控件确认动作", "没有"))
        except (RuntimeError, Stale):
            pass
    if k == "a" and m == {"ctrl"}:
        try:
            fe = e or _field(app, w, None)
            from gi.repository import Atspi
            n = Atspi.Text.get_character_count(fe["acc"])
            # add_selection 返回 False = 没选上(原来不看返回值照报成功)→ 往下走借键盘按 Ctrl+A
            if Atspi.Text.add_selection(fe["acc"], 0, n):
                return dict(outcome="unverified", route="控件选中", tried=[("控件选中", "unverified")], how="用控件接口全选")
            r["tried"].append(("控件选中", "控件没接受"))
        except Exception as ex:   # noqa: BLE001
            r["tried"].append(("控件选中", f"error:{ex}"))
    try:
        real.keysym_of(key)
    except RuntimeError as ex:
        return dict(outcome="failed", route="借真键盘", tried=r["tried"], reason=str(ex))
    g = _gate(r, allow, "键盘", w)
    if g:
        return g
    fr = _frame(w)
    before = _state(w, fr)
    at_xy = _center(e) if e is not None else None
    return _borrowed(r, "借真键盘", lambda: real.key(w, key, sorted(m), click_at=at_xy, check=_focus_guard(w, e, key, sorted(m))),
                     lambda: _verify(w, fr, before, timeout=0.8))


def _bars(fr):
    bars, stack = [], [(fr, 0)]
    while stack and len(bars) < 20:
        acc, d = stack.pop()
        try:
            if acc.get_role_name() == "scroll bar":
                bars.append(acc)
            if d < 40:
                for i in range(min(acc.get_child_count(), 500)):
                    c = acc.get_child_at_index(i)
                    if c is not None:
                        stack.append((c, d + 1))
        except Exception:   # noqa: BLE001
            continue
    return bars


def scroll(app, dy=0, dx=0, at=None, allow=None):
    """滚动:先找窗口里的滚动条直接改它的位置(后台);没有滚动条可改的 → 借真鼠标滚轮(在 at 那一项上、或窗口中间)。"""
    try:
        w = _win(app)
        _no_user_browser(w)                 # 用户自己开着的浏览器不碰(绕开网页允许名单)
    except safety.Refused as ex:
        return _refused(ex)
    fr = _frame(w)
    r = dict(outcome="failed", route=None, tried=[])
    if at is None:
        from gi.repository import Atspi
        want_v = dy != 0
        for b in _bars(fr):
            try:
                st = b.get_state_set()
                if not st.contains(Atspi.StateType.SHOWING):
                    continue
                if st.contains(Atspi.StateType.VERTICAL) or st.contains(Atspi.StateType.HORIZONTAL):
                    vert = st.contains(Atspi.StateType.VERTICAL)
                else:                      # Qt 不报横竖(FeatherPad 实测)→ 按形状:高比宽大就是竖的
                    ex = b.get_extents(Atspi.CoordType.WINDOW)
                    vert = ex.height > ex.width
                if vert != want_v:
                    continue
                cur, lo, hi = Atspi.Value.get_current_value(b), Atspi.Value.get_minimum_value(b), Atspi.Value.get_maximum_value(b)
                px = -(dy if want_v else dx)             # dy 负 = 往下翻 = 滚动条往大走
                try:
                    inc = Atspi.Value.get_minimum_increment(b) or 1
                except Exception:   # noqa: BLE001
                    inc = 1
                # 滚动条的单位各家不一样:Qt 按行(FeatherPad 100 行是 0~89),GTK 按像素。范围小的按「一行约 20 像素」换算
                delta = px / 20.0 * max(1.0, inc) if (hi - lo) <= 1000 else px
                new = max(lo, min(hi, cur + delta))
                if new == cur:
                    return dict(outcome="ineffective", route="滚动条", tried=[("滚动条", "ineffective")], how="已经到头了")
                Atspi.Value.set_current_value(b, new)
                time.sleep(0.2)
                ok = abs(Atspi.Value.get_current_value(b) - new) < 1
                return dict(outcome="delivered" if ok else "unverified", route="滚动条",
                            tried=[("滚动条", "delivered" if ok else "unverified")], how=f"滚动条 {cur:.0f} → {new:.0f}")
            except Exception:   # noqa: BLE001
                continue
        r["tried"].append(("滚动条", "没有"))
        x, y = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    else:
        try:
            x, y, _ = _resolve(app, at, w)
        except (RuntimeError, Stale) as ex:
            return dict(outcome="failed", route=None, tried=[], reason=str(ex))
    g = _gate(r, allow, "鼠标", w)
    if g:
        return g
    before = _state(w, fr)
    return _borrowed(r, "借真鼠标", lambda: real.scroll(w, x, y, dy=dy, dx=dx), lambda: _verify(w, fr, before))


# ─────────────────────────────── 命令行 ───────────────────────────────

USAGE = """SeeU Linux 版(预览)
  python3 -m seeu windows                       列出窗口
  python3 -m seeu see <App>                     截图 + 编号清单
  python3 -m seeu tap <App> <编号|名字>          按控件点
  python3 -m seeu type <App> <文字> [--at 编号|名字] [--enter]
  python3 -m seeu press <App> <键> [修饰键…] [--at 编号]
  python3 -m seeu scroll <App> [dy] [dx]       dy 负 = 往下翻
  python3 -m seeu long_press <App> <编号|名字|x y> [--ms 毫秒]   长按(借真鼠标,默认 1000)
  python3 -m seeu drag <App> x1 y1 x2 y2 [x3 y3 …]          拖动(借真鼠标,屏幕坐标)
  python3 -m seeu menu <App> <菜单> <项> […]                点菜单栏(后台,按控件),例:menu featherpad File New
  python3 -m seeu 探一下 <App>                               只读体检:能不能用 SeeU、会走哪条路(英文 probe)
  python3 -m seeu open <App>                                后台打开程序(终端、设置、浏览器等不开)
  python3 -m seeu 检查 [--fix]                   查 / 装 GNOME 小插件、截图授权、远程操作授权、辅助功能接口
  python3 -m seeu 设置 [借用鼠标 开|问我|关]       后台做不到时借不借你的真鼠标键盘
  python3 -m seeu 更新 [--check]                 更新到 GitHub 上的新版(git clone 装的才行)"""


def _report(r):
    from seeu.linux.lang import say as print   # noqa: A001   打印给人看的走中英文
    if isinstance(r, Exception):
        if isinstance(r, safety.Refused):
            print(f"refused  {r}")
            return 3
        print(f"failed  {r}")
        return 1
    print(f"{r['outcome']}  路线={r.get('route')}  试过={r.get('tried')}")
    if r.get("png"):
        import builtins
        from seeu.linux.lang import tx
        builtins.print(tx("截图=") + str(r.get("png")))        # 路径是数据,不过对照表(中文文件夹名会被换掉)
    for k in ("reason", "how", "enter", "xy", "borrow"):
        if r.get(k):
            print(f"{k}  {r[k]}")
    return 0 if r["outcome"] == "delivered" else (3 if r["outcome"] == "refused" else 1)


# ─────────────────────────────── 多任务调度(照 Windows win/act.py 末尾;见 seeu/sched.py) ───────────────────────────────
# 同一个窗口一次一个任务(排队、动完接着占几秒),别的任务排队;不带输入框的打字 / 按键在别的任务动过焦点后不做(code=focus_moved)。
# 原来 Linux 只有专用浏览器和借鼠标排队,两个会话往同一个窗口写字会写串(Mac 踩过)。内部互相调用(type 里先点框)只在最外层占 / 让。
try:
    from seeu import sched as _sched

    def _by_pos(args, kwargs):
        """按位置点 → 那个屏幕点(排队太久先核窗口挪没挪);按编号 / 名字 → None(轮到时重新找控件)。"""
        t = args[0] if args else kwargs.get("target")
        return tuple(t[:2]) if isinstance(t, (tuple, list)) and len(t) >= 2 else None

    def _at_pos(at):
        """type / press 的 at 是屏幕点时,排队太久先核窗口挪没挪(同 tap 按位置点、同 Mac
        带位置打字)。at 是编号 / 名字 → None:轮到时 _resolve 会重读控件现在的位置。"""
        return tuple(at[:2]) if isinstance(at, (tuple, list)) and len(at) >= 2 else None

    see = _sched.scheduled("see", lease=False)(see)
    tap = _sched.scheduled("tap", positional=_by_pos, focus=True)(tap)
    menu = _sched.scheduled("menu", focus=True)(menu)
    long_press = _sched.scheduled("long_press", positional=_by_pos, focus=True)(long_press)
    drag = _sched.scheduled("drag", positional=lambda a, k: (lambda p: tuple(p[0][:2]) if p else True)(a[0] if a else k.get("pts")),
                            focus=True)(drag)
    type = _sched.scheduled("type", positional=lambda a, k: _at_pos(k.get("at", a[2] if len(a) > 2 else None)), focus=True,   # noqa: A001
                            focus_check=lambda a, k: k.get("at", a[2] if len(a) > 2 else None) is None)(type)
    press = _sched.scheduled("press", positional=lambda a, k: _at_pos(k.get("at")), focus=True,
                             focus_check=lambda a, k: k.get("at") is None)(press)
    scroll = _sched.scheduled("scroll")(scroll)
except Exception:   # noqa: BLE001 —— 调度模块出问题不影响 SeeU 本身
    pass


def main(argv=None):
    import builtins
    from seeu.linux import lang
    print = lang.say   # noqa: A001   打印给人看的走中英文;路径、控件上的字用 builtins.print 原样打
    a = list(sys.argv[1:] if argv is None else argv)
    try:
        if a[:1] == ["windows"]:
            safety.check_unlocked()
            for w in W.list_windows():
                why = safety.why_not(w)
                builtins.print(f"#{w['id']:<6} {(w['names'][0] if w['names'] else w['comm']):<28} {w['title'][:60]}"
                               + lang.tx(("" if w.get("active_ws", True) else "   (别的工作区)") + (f"   ⛔ {why}" if why else "")))
            return 0
        if len(a) < 2:
            print(lang.L(USAGE, lang.USAGE_EN))
            return 2
        cmd, app, rest = a[0], a[1], a[2:]
        if cmd == "see":
            v = see(app)
            builtins.print(lang.tx("窗口: ") + f"{v['window']['title']}  ({v['window']['comm']}, #{v['window']['id']})")
            builtins.print(describe(v["items"]))
            if v["windows"]:
                builtins.print(lang.tx("这个程序开着好几个窗口:"), " | ".join(v["windows"]))
            if v.get("note"):
                print(v["note"])
            builtins.print(lang.tx("截图:"), v["png"])
            return 0
        if cmd == "tap":
            t = (float(rest[0]), float(rest[1])) if len(rest) == 2 and all(
                x.replace(".", "").lstrip("-").isdigit() for x in rest) else " ".join(rest)
            return _report(tap(app, t))
        if cmd == "type":
            at = rest[rest.index("--at") + 1] if "--at" in rest else None
            words = [x for i, x in enumerate(rest) if x not in ("--enter", "--at") and not (i and rest[i - 1] == "--at")]
            return _report(type(app, " ".join(words), enter="--enter" in rest, at=at))
        if cmd == "press":
            at = rest[rest.index("--at") + 1] if "--at" in rest else None
            keys = [x for i, x in enumerate(rest) if x != "--at" and not (i and rest[i - 1] == "--at")]
            return _report(press(app, keys[0], *keys[1:], at=at))
        if cmd == "menu":
            return _report(menu(app, *rest))
        if cmd in ("探一下", "probe"):
            from seeu.linux import probe as _pr
            return _pr.main([app] + rest)
        if cmd in ("open", "打开"):
            from seeu.linux import openapp as _oa
            r = _oa.open_app(" ".join([app] + rest))
            builtins.print(r.get("outcome"), "·", r.get("name") or "", "\n" + lang.tx(r.get("note") or r.get("reason") or ""))
            return 0 if r.get("outcome") in ("delivered", "unverified") else 1
        if cmd == "long_press":
            ms = 1000
            if "--ms" in rest:
                i = rest.index("--ms")
                ms = int(float(rest[i + 1])) if i + 1 < len(rest) else 1000
                rest = rest[:i] + rest[i + 2:]
            t = (float(rest[0]), float(rest[1])) if len(rest) == 2 and all(
                x.replace(".", "").lstrip("-").isdigit() for x in rest) else " ".join(rest)
            return _report(long_press(app, t, ms=ms))
        if cmd == "drag":
            nums = [float(x) for x in rest]
            return _report(drag(app, list(zip(nums[0::2], nums[1::2]))))
        if cmd == "scroll":
            return _report(scroll(app, dy=float(rest[0]) if rest else -300, dx=float(rest[1]) if len(rest) > 1 else 0))
    except safety.Refused as ex:
        return _report(ex)
    except (RuntimeError, shell.NoHelper) as ex:
        return _report(ex)
    print(lang.L(USAGE, lang.USAGE_EN))
    return 2
