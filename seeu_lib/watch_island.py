# -*- coding: utf-8 -*-
"""
watch_island.py —— 多任务「灵动岛」悬浮标(SeeU C-0.8,10-24)。由 watch_window.serve() 在 ≥2 个任务同时在跑时接管显示;
只有一个任务时不出现,照旧是原来的悬浮窗/悬浮标。界面是用户在桌面样品里定稿的(seeu/参考/灵动岛悬浮标/island_sample.py),规则见
seeu/SeeU-相关要点.md「灵动岛」节:
  收起胶囊 = 「SeeU · N 个任务」(+ 借鼠标中 / 有卡住 / 跳过 N 项);展开 = 顶栏 + 最活跃任务大卡片 + 下面一行一个(最多 3 条,更多的叠放);
  借鼠标永远第一,卡住自动展开(红),鼠标离开 3 秒自动收;颜色跟系统深浅色。
接口(watch_window 里用):
  init(hooks)                 一次;hooks = dict(tr, isee_get, isee_toggle, light_get, light_set, solo, log)
  sync(tasks, now)            每个 tick 调一次;tasks = 任务字典列表(字段见下),空 / 不到 2 个就传 [] 让岛藏起来
  hide()                      立刻藏
任务字典:key, who, app, kind(mirror|browser|app), step, steps(最近几步,新的在前), borrow, stuck(None 或 dict(why, todo)), last(最后动作时间),
          born, hidden(浏览器隐身中), wid
"""
import json
import math
import os
import time

import Quartz
from AppKit import (NSApp, NSApplication, NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua, NSAttributedString,
                    NSBackingStoreBuffered, NSColor, NSEvent, NSFont, NSFontAttributeName, NSGlassEffectView,
                    NSPanel, NSScreen, NSStatusWindowLevel, NSTrackingActiveAlways, NSTrackingArea,
                    NSTrackingInVisibleRect, NSTrackingMouseEnteredAndExited, NSTrackingMouseMoved, NSView,
                    NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSMakeRect, NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer
try:
    from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)
except ImportError:          # 当独立程序跑(python3 …/watch_window.py serve)时找不到 seeu_lib 包:同一取法兜底
    home = lambda *p: os.path.join(os.environ.get("SEEU_HOME") or os.path.expanduser("~/.seeu"), *p)   # noqa: E731

PURPLE, ORANGE, RED = (0.498, 0.467, 0.867), (1.0, 0.62, 0.18), (1.0, 0.35, 0.31)
DARK = (26 / 255, 28 / 255, 31 / 255)
OPEN_W = 320          # 10-27 用户:里面的顶卡 300 = 单任务卡片宽(原 330)
MAX_ROWS = 2              # 展开后顶卡下面最多列几行(连顶卡共 3 条,10-24 用户定);更多的叠在下面
HOLD_S = 8                # 顶上至少停几秒(展开期间不换)
LEAVE_S = 3               # 鼠标离开后几秒自动收(有借鼠标/卡住不收)
ISEE_LIVE = home("seeu_isee_live.json")
POS_FILE = home("watch_island.json")
ICON_R, TB_H, TB_FONT = 7, 28, 13
LIGHTS = ["off", "real", "bg"]
LIGHT_NAME = {"off": "关", "real": "抢占", "bg": "被控"}
MORPH_T, MORPH_BOUNCE, MORPH_FPS = 0.5, 0.2, 60     # 同真悬浮窗(10-20 用户在预览里定)
OPEN_R = 18

H = {}                    # init 传进来的 hooks
st = dict(open=False, top=None, top_since=0.0, last_sig=None, pick={}, psize=(100, 32), osize=(OPEN_W, 100))
tasks = []                # 本次 sync 的任务(已排好序前的原始列表)
hits = []
iwin = holder = glass = content = proot = oroot = lroot = morpher = None


def _tr(key, zh, **kw):
    f = H.get("tr")
    try:
        return f(key, zh, **kw) if f else (zh.format(**kw) if kw else zh)
    except Exception:
        return zh


def _log(msg):
    try:
        H["log"]("岛:" + msg)
    except Exception:
        pass


# ---------------------------------------------------------------- 数据
def skips():
    """本轮 I See 跳过的项数(seeu/isee.py 写的计数)。"""
    try:
        with open(ISEE_LIVE, encoding="utf-8") as f:
            return int(json.load(f).get("skips", 0))
    except Exception:
        return 0


def borrow(t):
    return bool(t.get("borrow"))


def stuck(t):
    return bool(t.get("stuck"))


def ordered(now):
    a = list(tasks)
    a.sort(key=lambda t: -max(t["last"], st["pick"].get(t["key"], 0)))
    cur = next((t for t in a if t["key"] == st["top"]), None)
    pick_top = st["pick"].get(a[0]["key"], 0) if a else 0
    if cur and a[0] is not cur and (st["open"] or now - st["top_since"] < HOLD_S) and not (borrow(a[0]) or stuck(a[0])) \
            and not pick_top > st["pick"].get(cur["key"], 0):
        a.remove(cur)
        a.insert(0, cur)
    a.sort(key=lambda t: (not borrow(t), not stuck(t)))   # 借鼠标 > 卡住 > 最近有动作(10-27 用户定:卡住的也排到顶上写全)
    if a and a[0]["key"] != st["top"]:
        st["top"], st["top_since"] = a[0]["key"], now
    return a


def color(t):
    return ORANGE if borrow(t) else PURPLE     # 10-27:卡住不靠红色(颜色用户自定,红可能撞色),靠文字说


def title(t):
    return f"{t['who']} · {t['app']}" if t.get("who") and t["who"] != t["app"] else t["app"]


def idle(t):
    """镜像 / 普通 App 任务:3 秒没点就是等下一步(10-27:不再写「操作 BlueStacks」)。"""
    return t.get("kind") != "browser" and time.time() - t.get("mark_t", 0) > 3


def verb(t):
    """一行写的那句(不带「正在」):借鼠标 / 卡住 / 等下一步 / 动作。"""
    if borrow(t):
        return _tr("card.borrow", "正在用你的鼠标")
    if stuck(t):
        return _tr("card.stuck_why", "卡住了: {why}", why=t["stuck"].get("why", ""))
    if idle(t) or not t.get("step"):
        return _tr("card.idle", "等下一步")
    return t["step"]


def headline(t):
    """顶卡大字:动作前面加「正在」;借鼠标 / 卡住 / 等下一步原样。"""
    v = verb(t)
    if borrow(t) or stuck(t) or idle(t) or not t.get("step"):
        return v
    return _tr("island.doing", "正在") + v


def ago(t, now):
    d = int(now - t["last"])
    return _tr("island.now", "刚刚") if d < 3 else _tr("island.sec", "{n} 秒前", n=d) if d < 60 else _tr("island.min", "{n} 分钟前", n=d // 60)


def clip(s, n=10):
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- 画
def look_dark():
    return "Dark" in str(NSApp.effectiveAppearance().bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua, NSAppearanceNameDarkAqua]))


def cg(rgb, a=1.0):
    return Quartz.CGColorCreateGenericRGB(rgb[0], rgb[1], rgb[2], a)


def font(size, bold):
    return NSFont.systemFontOfSize_weight_(size, 0.4 if bold else 0.0)


def text_w(s, size, bold):
    return NSAttributedString.alloc().initWithString_attributes_(s, {NSFontAttributeName: font(size, bold)}).size().width


def ink():
    return (1, 1, 1) if look_dark() else DARK


def text(root, s, size, bold, x, mid, w, a=1.0, rgb=None, right=False):
    f = font(size, bold)
    asc, desc, cap = f.ascender(), f.descender(), f.capHeight()
    t = Quartz.CATextLayer.layer()
    t.setString_(s); t.setFont_(f); t.setFontSize_(size); t.setContentsScale_(2.0)
    t.setForegroundColor_(cg(rgb or ink(), a)); t.setAlignmentMode_("right" if right else "left")
    t.setTruncationMode_("end")
    top = mid - cap / 2.0 - 0.5 + asc
    hh = asc - desc + 2
    t.setFrame_(Quartz.CGRectMake(x, top - hh, w, hh))
    root.addSublayer_(t)
    return t


def dot(root, cx, cy, r, rgb, breath=True):
    d = Quartz.CALayer.layer()
    d.setFrame_(Quartz.CGRectMake(cx - r, cy - r, 2 * r, 2 * r)); d.setCornerRadius_(r); d.setBackgroundColor_(cg(rgb))
    if breath:
        a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
        a.setFromValue_(1.0); a.setToValue_(0.3); a.setDuration_(0.9); a.setAutoreverses_(True); a.setRepeatCount_(1e9)
        d.addAnimation_forKey_(a, "b")
    root.addSublayer_(d)


def box(root, x, y, w, h, r, a, rgb=None, border=None):
    b = Quartz.CALayer.layer()
    b.setFrame_(Quartz.CGRectMake(x, y, w, h)); b.setCornerRadius_(r)
    b.setBackgroundColor_(cg(rgb or (1, 1, 1), a))
    if border:
        b.setBorderColor_(cg(border)); b.setBorderWidth_(2)
    root.addSublayer_(b)
    return b


def _shape(root, path, stroke=None, fill=None, lw=1.5):
    l = Quartz.CAShapeLayer.layer()
    l.setPath_(path); l.setContentsScale_(2.0); l.setLineWidth_(lw); l.setLineCap_("round"); l.setLineJoin_("round")
    l.setStrokeColor_(cg(stroke[0], stroke[1]) if stroke else None)
    l.setFillColor_(cg(fill[0], fill[1]) if fill else None)
    root.addSublayer_(l)


def _circle(cx, cy, r):
    return Quartz.CGPathCreateWithEllipseInRect(Quartz.CGRectMake(cx - r, cy - r, 2 * r, 2 * r), None)


def ring(root, cx, cy, a=0.9, r=ICON_R, lw=1.5):
    _shape(root, _circle(cx, cy, r), stroke=(ink(), a), lw=lw)


def isee_icon(root, cx, cy, on):
    if on:
        _shape(root, _circle(cx, cy, ICON_R), fill=(ink(), 0.95))
        _shape(root, _circle(cx, cy, 2.4), fill=(DARK if look_dark() else (1, 1, 1), 1))
    else:
        ring(root, cx, cy)
        _shape(root, _circle(cx, cy, 2.4), fill=(ink(), 0.9))


def light_icon(root, cx, cy, lvl):
    if lvl != "off":
        _shape(root, _circle(cx, cy, ICON_R + 0.75), fill=(ORANGE if lvl == "real" else PURPLE, 1))
    ring(root, cx, cy, 0.88)
    c = ((1, 1, 1), 1) if lvl != "off" else (ink(), 0.55)
    d, L = 2.8, 1.6        # 10-30 用户:四个角别贴着圆(原 3.3, 2.1),跟悬浮窗一起改
    p = Quartz.CGPathCreateMutable()
    for sx in (-1, 1):
        for sy in (-1, 1):
            Quartz.CGPathMoveToPoint(p, None, cx + sx * d, cy + sy * (d - L))
            Quartz.CGPathAddArcToPoint(p, None, cx + sx * d, cy + sy * d, cx + sx * (d - L), cy + sy * d, 1.1)
            Quartz.CGPathAddLineToPoint(p, None, cx + sx * (d - L), cy + sy * d)
    _shape(root, p, stroke=c, lw=1.1)


def screen_icon(root, cx, cy):
    ring(root, cx, cy); ring(root, cx, cy, 0.9, 3.0, 1.1)
    _shape(root, _circle(cx, cy, 1.1), fill=(ink(), 0.9)); _shape(root, _circle(cx + 3.3, cy - 3.3, 0.8), fill=(ink(), 0.9))


def collapse_icon(root, cx, cy):
    ring(root, cx, cy)
    p = Quartz.CGPathCreateMutable()
    Quartz.CGPathAddArc(p, None, cx - 2.0, cy, 3.0, 2.094, 4.189, False)
    q = Quartz.CGPathCreateMutable()
    Quartz.CGPathAddArc(q, None, cx + 2.0, cy, 3.0, -1.047, 1.047, False)
    _shape(root, p, stroke=(ink(), 0.9), lw=1.3); _shape(root, q, stroke=(ink(), 0.9), lw=1.3)


class WatchIslandView(NSView):
    def updateTrackingAreas(self):
        for ta in list(self.trackingAreas()):
            self.removeTrackingArea_(ta)
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), NSTrackingMouseEnteredAndExited | NSTrackingMouseMoved | NSTrackingActiveAlways | NSTrackingInVisibleRect, self, None))

    def mouseMoved_(self, ev):
        p = self.convertPoint_fromView_(ev.locationInWindow(), None)
        h = self.bounds().size.height
        on = st["open"] and p.y >= h - TB_H
        hv = next((k for (x0, x1, y0, y1, k) in hits if k.startswith("tb_") and x0 <= p.x <= x1 and y0 <= p.y <= y1), None) if on else None
        if on != st.get("hover") or hv != st.get("hover_btn"):
            st["hover"], st["hover_btn"] = on, hv
            render(time.time(), force=True)

    def mouseEntered_(self, ev):
        st["left_at"] = None

    def mouseExited_(self, ev):
        st["left_at"] = time.time()
        st["hover"], st["hover_btn"] = False, None
        st["light_open"] = False
        render(time.time(), force=True)

    def acceptsFirstMouse_(self, ev):
        return True

    # 按住拖 = 挪位置(记住右上角,展开/收起都以它为准);没拖动松开 = 点击
    def mouseDown_(self, ev):
        st["drag"] = (NSEvent.mouseLocation(), self.window().frame(), False)

    def mouseDragged_(self, ev):
        p0, f0, moved = st["drag"]
        p = NSEvent.mouseLocation()
        dx, dy = p.x - p0.x, p.y - p0.y
        if abs(dx) + abs(dy) < 4 and not moved:
            return
        st["drag"] = (p0, f0, True)
        self.window().setFrameOrigin_((f0.origin.x + dx, f0.origin.y + dy)); st["last_frame"] = None
        st["anchor"] = (f0.origin.x + f0.size.width + dx, f0.origin.y + f0.size.height + dy)

    def mouseUp_(self, ev):
        now = time.time()
        if st.get("drag") and st["drag"][2]:
            st["drag"] = None
            _save_pos()
            return
        p = self.convertPoint_fromView_(ev.locationInWindow(), None)
        if not st["open"]:
            st["open"] = True
            st["auto_open"] = None           # 你自己点开的:不会因为借完鼠标被收回
        else:
            for (x0, x1, y0, y1, who) in hits:
                if x0 <= p.x <= x1 and y0 <= p.y <= y1:
                    if who in ("close", "tb_collapse"):
                        st["open"] = False; st["light_open"] = False
                    elif who == "more":
                        st["more"] = not st.get("more")
                    elif who == "tb_light":
                        st["light_open"] = not st.get("light_open")
                    elif who.startswith("lv_"):
                        H["light_set"](who[3:]); st["light_open"] = False
                    elif who in ("isee", "tb_isee"):
                        H["isee_toggle"]()
                    elif who in ("view", "tb_view"):
                        a = ordered(now)
                        if a and a[0].get("hidden"):
                            st["tip"] = (a[0]["key"], now + 3)
                        elif a:
                            H["solo"](a[0]["key"])           # 回到单任务悬浮窗,看这个任务的画面/文字卡
                    else:
                        st["pick"][who] = now + 1e6          # 点某一行 = 它换到顶上
                    break
            else:
                if st.get("light_open"):
                    st["light_open"] = False
                elif p.y >= self.bounds().size.height - TB_H:     # 点顶栏空白处 = 收起
                    st["open"] = False
        render(now, force=True)


def _save_pos():
    try:
        os.makedirs(os.path.dirname(POS_FILE), exist_ok=True)
        with open(POS_FILE, "w") as f:
            json.dump({"anchor": list(st["anchor"])}, f)
    except Exception:
        pass


def set_anchor(pt, save=True):
    """10-27:跟单任务悬浮标共用一个位置(右上角)。岛出现时从悬浮标那里长出来,不再跳回自己记的老位置。"""
    st["anchor"] = (float(pt[0]), float(pt[1]))
    st["last_frame"] = None
    if save:
        _save_pos()


def anchor():
    """岛现在的右上角(屏幕坐标);掉回单任务时悬浮标照这个摆。"""
    return tuple(_anchor())


def _clamp(right, top, w, h):
    """展开后别伸出屏幕(悬浮标拖到左边/下边时,岛往右/往上让一让;记住的位置不改)。"""
    for s in NSScreen.screens():
        f = s.frame()
        if f.origin.x <= right <= f.origin.x + f.size.width and f.origin.y <= top <= f.origin.y + f.size.height:
            v = s.visibleFrame()
            right = max(right, v.origin.x + w + 4)
            top = max(min(top, v.origin.y + v.size.height), v.origin.y + h + 4)
            break
    return right, top


def _anchor():
    scr = NSScreen.mainScreen().visibleFrame()
    a = st.get("anchor")
    if a:
        # 记住的位置不在任何屏幕里了(换了显示器)就回默认
        for s in NSScreen.screens():
            f = s.frame()
            if f.origin.x <= a[0] <= f.origin.x + f.size.width and f.origin.y <= a[1] <= f.origin.y + f.size.height:
                return a
    return (scr.origin.x + scr.size.width - 14, scr.origin.y + scr.size.height - 10)


def _draw(now, force=False):
    """画两份内容:收起的胶囊(proot)和展开的窗口(oroot);窗口大小和谁显示由 place()/形变动画管。"""
    global lroot
    a = ordered(now)
    n_skip = skips()
    isee = H["isee_get"]()
    light = H["light_get"]()
    sig = json.dumps([st["open"], look_dark(), isee, n_skip, str(st.get("tip")), st.get("hover"), st.get("hover_btn"), light,
                      st.get("light_open"), st.get("more"),
                      [(t["key"], t.get("step"), borrow(t), stuck(t), ago(t, now), t.get("hidden")) for t in a]], ensure_ascii=False)
    if sig == st["last_sig"] and not force:
        return False
    st["last_sig"] = sig
    if not a:
        iwin.orderOut_(None)
        return False
    iwin.orderFrontRegardless()
    glass.setAppearance_(None)
    glass.setTintColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(*PURPLE, 0.08))
    for root in (proot, oroot):
        for l in list(root.sublayers() or []):
            l.removeFromSuperlayer()
    hits.clear()
    lead = a[0]
    # ---- 收起胶囊 ----
    lroot = proot
    s = "SeeU"         # 10-27 用户定:悬浮标只写 SeeU,多任务也不写个数;借鼠标 / 卡住自动展开说
    w, h = 29 + text_w(s, 14.5, True) + 14, 32
    st["psize"] = (w, h)
    dot(lroot, 16, h / 2, 5, color(lead))
    text(lroot, s, 14.5, True, 29, h / 2, w - 29)
    # ---- 展开 ----
    lroot = oroot
    t, rest = lead, a[1:]
    notes = []
    if borrow(t):
        notes.append(_tr("card.borrow_note", "别动鼠标,几秒后还你"))
    elif stuck(t):
        notes.append(_tr("card.todo", "怎么办: {todo}", todo=t["stuck"].get("todo", "")))
    elif t.get("hidden"):
        notes.append(_tr("card.hidden_note", "{app} 在后台隐身干活,别点开它", app=t["app"]))
    if isee and t.get("kind") == "browser":
        notes.append(_tr("card.isee_note", "我已知风险，授权 AI 执行 · 卡住时请立即报告！"))
        if n_skip:
            notes.append(_tr("island.skipped", "已跳过 {n} 项,做完一起告诉你", n=n_skip))
    tip = st.get("tip")
    if tip and tip[0] == t["key"] and now < tip[1]:
        notes.append(_tr("card.screen_hidden", "隐身中,看不了画面"))
    steps = (t.get("steps") or [])[1:3]               # 顶卡下面列最近两步已做完的
    steps_h = 18 * len(steps)
    card_h = 14 + 16 + 28 + 20 * len(notes) + (steps_h + 8 if steps_h else 0) + 8
    W = OPEN_W
    fold = len(rest) > MAX_ROWS and not st.get("more")
    shown = rest[:MAX_ROWS] if fold else rest
    more_row = len(rest) > MAX_ROWS
    HH = TB_H + card_h + 6 + len(shown) * 36 + 4 + ((12 if fold else 26) if more_row else 0)
    st["osize"] = (W, HH)
    sub = 0.72 if look_dark() else 0.6
    topbar(HH, W, t, len(a), isee, light)
    cy0 = HH - TB_H - card_h
    # 10-27 用户:顶卡排版照单任务卡片(卡片左边 10 起算:圆点 22、小字 34、大字 18、右边留 18、圆角 18),不加橙/红边
    L, CW = 10, W - 20
    box(lroot, L, cy0, CW, card_h, 18, 0.10 if look_dark() else 0.35)
    y = HH - TB_H - 14 - 7
    dot(lroot, L + 22, y, 5, color(t))
    text(lroot, title(t), 12, False, L + 34, y, 200, sub)
    text(lroot, ago(t, now), 11, False, L + CW - 18 - 92, y, 92, sub * 0.8, right=True)
    y -= 27
    text(lroot, headline(t), 16.5, True, L + 18, y, CW - 36)
    for n in notes:
        y -= 20
        text(lroot, n, 11.5, False, L + 18, y, CW - 36, sub)
    if steps_h:
        y -= 8
        for stp in steps:
            y -= 18
            text(lroot, "✓ " + stp, 12, False, L + 18, y + 4, CW - 36, sub)
    # 其余一行一个
    ry = cy0 - 6
    row_a = 0.08 if look_dark() else 0.3
    if more_row and not fold:      # 展开全部:右上一个小「折叠」胶囊(用户定叫折叠;收起 = 整个岛缩回浮标)
        lab = _tr("island.fold", "折叠 ⌃")
        bw = text_w(lab, 11, True) + 18
        box(lroot, W - 10 - bw, ry - 22, bw, 20, 10, row_a * 1.6)
        text(lroot, lab, 11, True, W - 10 - bw + 9, ry - 12, bw, sub)
        hits.append((W - 14 - bw, W, ry - 24, ry, "more"))
        ry -= 26
    for i, r in enumerate(shown):
        last_fold = fold and i == len(shown) - 1
        if last_fold:              # 叠在后面的两层:一层比一层窄、淡,露出 6 / 5 点
            bottom = ry - 32
            for (x, y0, hh, a_) in ((18, bottom - 6, 6, 0.75), (26, bottom - 11, 5, 0.45)):
                e = box(lroot, x, y0, W - 2 * x, hh, min(hh, 6), row_a * a_)
                e.setMaskedCorners_(Quartz.kCALayerMinXMinYCorner | Quartz.kCALayerMaxXMinYCorner)
        box(lroot, 10, ry - 32, W - 20, 32, 10, row_a if not last_fold else row_a + 0.04)
        mid = ry - 16
        dot(lroot, 24, mid, 4, color(r), breath=False)
        nm = r.get("who") or r["app"]
        text(lroot, nm, 12.5, False, 34, mid, 50, sub)
        text(lroot, verb(r), 12.5, True, 34 + min(text_w(nm, 12.5, False), 50) + 8, mid, W - 160)
        text(lroot, ago(r, now), 11, False, W - 110, mid, 86, sub * 0.8, right=True)
        hits.append((0, W, ry - 32 - (12 if last_fold else 0), ry, "more" if last_fold else r["key"]))
        ry -= 36


def topbar(HH, W, t, n, isee, light):
    """顶部按钮栏(照真悬浮窗):平时写「SeeU · N 个任务」;鼠标移上来换成 I See / 灯光 / …… / 看画面 / 收起。看画面、收起只有图标。"""
    cy = HH - TB_H / 2
    sub = 0.72 if look_dark() else 0.6
    if not st.get("hover") and not st.get("light_open"):
        dot(lroot, 18, cy, 4, color(t))
        text(lroot, _tr("island.cap", "SeeU · {n} 个任务", n=n), 12.5, True, 30, cy, 200, sub)
        isee_here = isee and t.get("kind") == "browser"
        if isee_here or light != "off":    # 开着的开关在角上留个小标记(I See 只管浏览器,顶卡不是浏览器就不放)
            x = W - 16
            if light != "off":
                light_icon(lroot, x, cy, light); x -= 20
            if isee_here:
                isee_icon(lroot, x, cy, True)
        return
    x = 8
    # 10-24 用户定:灯光第一位(固定),I See 第二,只在顶卡是浏览器任务时出现
    btns = [("tb_light", _tr("btn.light", "灯光"), lambda cx: light_icon(lroot, cx, cy, light))]
    if t.get("kind") == "browser":
        btns.append(("tb_isee", "I See", lambda cx: isee_icon(lroot, cx, cy, isee)))
    for key, lab, draw in btns:
        w = 4 + 2 * ICON_R + 4 + text_w(lab, TB_FONT, False) + 6
        draw(x + 4 + ICON_R)
        text(lroot, lab, TB_FONT, False, x + 8 + 2 * ICON_R, cy, w)
        hits.append((x, x + w, HH - TB_H, HH, key))
        x += w + 4
    if st.get("light_open"):          # 灯光选项条:当前档在原位,另两档往右伸出来
        lx = [h for h in hits if h[4] == "tb_light"][0][0]
        names = {"off": _tr("btn.light_off", "关"), "real": _tr("btn.halo_real", "抢占"), "bg": _tr("btn.halo_bg", "被控")}
        bar_w = sum(4 + 2 * ICON_R + 4 + text_w(names[l], TB_FONT, False) + 8 for l in LIGHTS)
        box(lroot, lx, cy - 10, bar_w, 20, 10, 0.95, rgb=(0.2, 0.2, 0.23) if look_dark() else (1, 1, 1))
        for lvl in [light] + [l for l in LIGHTS if l != light]:
            w = 4 + 2 * ICON_R + 4 + text_w(names[lvl], TB_FONT, False) + 8
            light_icon(lroot, lx + 4 + ICON_R, cy, lvl)
            text(lroot, names[lvl], TB_FONT, lvl == light, lx + 8 + 2 * ICON_R, cy, w, 1 if lvl == light else sub)
            hits.insert(0, (lx, lx + w, HH - TB_H, HH, "lv_" + lvl))
            lx += w
        return
    hv = st.get("hover_btn")
    for key, cx, draw, lab in (("tb_view", W - 45, screen_icon, _tr("btn.view_screen", "看画面")),
                               ("tb_collapse", W - 17, collapse_icon, _tr("btn.collapse", "收起"))):
        draw(lroot, cx, cy)
        hits.append((cx - 13, cx + 13, HH - TB_H, HH, key))
        if hv == key:
            lw = text_w(lab, 11.5, False) + 14
            box(lroot, cx - 13 - lw - 2, cy - 10, lw, 20, 10, 0.95, rgb=(0.2, 0.2, 0.23) if look_dark() else (1, 1, 1))
            text(lroot, lab, 11.5, False, cx - 13 - lw + 5, cy, lw)


# ---------------------------------------------------------------- 形变(同真悬浮窗:弹簧 + 交叉淡化)
def _spring(t):
    z, w = 1 - MORPH_BOUNCE, 2 * math.pi / MORPH_T
    wd = w * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + z * w / wd * math.sin(wd * t))


def apply_frame(w, h, p_a, o_a):
    """窗口按右上角定位;胶囊内容、展开内容都贴右上角(窗口小的时候展开内容被裁掉 = 从胶囊里长出来)。"""
    w, h = round(max(24.0, w)), round(max(20.0, h))     # 取整:小数尺寸会让边框每帧抖
    right, top = _clamp(*_anchor(), w, h)
    right, top = round(right), round(top)
    if st.get("last_frame") != (right, top, w, h):      # 没变就不碰窗口和玻璃
        st["last_frame"] = (right, top, w, h)
        iwin.setFrame_display_(NSMakeRect(right - w, top - h, w, h), True)
        for v in (holder, glass, content):
            v.setFrame_(NSMakeRect(0, 0, w, h))
        r = min(h / 2.0, OPEN_R)
        glass.setCornerRadius_(r)
        glass.layer().setCornerRadius_(r)
    pw, ph = st["psize"]
    W, HH = st["osize"]
    Quartz.CATransaction.begin(); Quartz.CATransaction.setDisableActions_(True)
    for root, cw, chh in ((proot, pw, ph), (oroot, W, HH)):
        sc = min(1.6, max(0.35, min(w / cw, h / chh) if root is oroot else w / cw))
        root.setAnchorPoint_((1, 1)); root.setBounds_(Quartz.CGRectMake(0, 0, cw, chh))
        root.setPosition_((w, h)); root.setTransform_(Quartz.CATransform3DMakeScale(sc, sc, 1))
    proot.setOpacity_(p_a); oroot.setOpacity_(o_a)
    Quartz.CATransaction.commit()


class IslandMorpher(NSObject):
    def step_(self, _t):
        m = st.get("morph")
        if not m:
            return
        t = time.time() - m["t0"]
        a, b = m["from"], (st["osize"] if m["opening"] else st["psize"])
        done = t >= MORPH_T * (2.2 if m["opening"] else 1.6)
        k = 1.0 if done else _spring(t)
        w, h = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        if m["opening"]:      # 胶囊字先淡出,窗口内容在后半段淡入
            p_a = max(0.0, 1 - t / 0.15); o_a = min(1.0, max(0.0, (k - 0.35) / 0.45))
        else:                 # 窗口内容先淡出,快缩到胶囊大小时胶囊字淡入
            o_a = max(0.0, 1 - t / 0.25); p_a = min(1.0, max(0.0, (t - 0.12) / 0.15))
        apply_frame(w, h, p_a, o_a)
        if done:
            m["timer"].invalidate(); st["morph"] = None
            render(time.time(), force=True); place()


def morph(opening):
    global morpher
    morpher = morpher or IslandMorpher.alloc().init()
    old = st.get("morph")
    if old:
        old["timer"].invalidate()
    f = iwin.frame()
    st["morph"] = m = dict(t0=time.time(), opening=opening, **{"from": (f.size.width, f.size.height)})
    m["timer"] = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1.0 / MORPH_FPS, morpher, "step:", None, True)
    NSRunLoop.currentRunLoop().addTimer_forMode_(m["timer"], NSRunLoopCommonModes)


def place():
    """没在形变时:按当前状态摆好窗口(内容变了高度跟着变)。"""
    if st.get("morph"):
        return
    w, h = st["osize"] if st["open"] else st["psize"]
    apply_frame(w, h, 0.0 if st["open"] else 1.0, 1.0 if st["open"] else 0.0)


def render(now, force=False):
    if st.get("morph"):
        if st["open"] == st["morph"]["opening"]:
            st["dirty"] = True
            return
        st.pop("morph")["timer"].invalidate()      # 动画中途反向点 = 从当前大小掉头
    Quartz.CATransaction.begin(); Quartz.CATransaction.setDisableActions_(True)
    drew = _draw(now, force or st.pop("dirty", False))
    Quartz.CATransaction.commit()
    if not tasks:
        return
    if st["open"] != st.get("shown_open"):
        first = st.get("shown_open") is None
        st["shown_open"] = st["open"]
        if not first:
            morph(st["open"])
            return
    if drew is not False:
        place()


# ---------------------------------------------------------------- 窗口
class WatchIslandPanel(NSPanel):
    def canBecomeKeyWindow(self):      # 🔴 纯显示浮窗不抢键盘(10-15 坑)
        return False

    def canBecomeMainWindow(self):
        return False

    def _hasActiveAppearance(self):   # 照真悬浮窗:玻璃按"激活"样子画边框光晕(私有方法,只改外观不改焦点)
        return True


def init(hooks):
    global iwin, holder, glass, content, proot, oroot, lroot
    H.update(hooks)
    try:
        with open(POS_FILE) as f:
            a = json.load(f).get("anchor")
            if a:
                st["anchor"] = tuple(a)
    except Exception:
        pass
    iwin = WatchIslandPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 100, 32), NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered, False)
    iwin.setLevel_(NSStatusWindowLevel); iwin.setOpaque_(False); iwin.setBackgroundColor_(NSColor.clearColor())
    iwin.setHasShadow_(False)      # 窗口阴影会在玻璃外多一圈深色细边(深色模式下像锯齿)
    iwin.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
    holder = WatchIslandView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 32)); holder.setWantsLayer_(True)
    glass = NSGlassEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 32))
    content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 32)); content.setWantsLayer_(True)
    glass.setContentView_(content); holder.addSubview_(glass); iwin.setContentView_(holder)
    glass.setWantsLayer_(True); glass.layer().setMasksToBounds_(True)
    try:
        glass.layer().setCornerCurve_("continuous")
    except Exception:
        pass
    content.layer().setMasksToBounds_(True)
    proot = Quartz.CALayer.layer(); content.layer().addSublayer_(proot)
    oroot = Quartz.CALayer.layer(); content.layer().addSublayer_(oroot)
    lroot = proot


def window_number():
    return int(iwin.windowNumber()) if iwin is not None else 0


def set_ignore_mouse(on):
    """借用系统鼠标那几秒不接鼠标(同悬浮窗/悬浮标)。"""
    if iwin is not None:
        iwin.setIgnoresMouseEvents_(bool(on))
        if on:
            st["hover"] = False


def is_visible():
    return iwin is not None and bool(iwin.isVisible())


def hide():
    global tasks
    tasks = []
    st["last_sig"] = None
    st["shown_open"] = None
    if st.get("morph"):
        st.pop("morph")["timer"].invalidate()
    if iwin is not None and iwin.isVisible():
        iwin.orderOut_(None)


def frame():
    """岛正显示时的窗口范围 (x, y, w, h)(Cocoa 坐标),否则 None —— 给提示条让位用。"""
    if iwin is None or not iwin.isVisible():
        return None
    f = iwin.frame()
    return (f.origin.x, f.origin.y, f.size.width, f.size.height)


def sync(task_list, now):
    """每个 tick 调一次。10-27 用户定:点开后一直开着,点「收起」才收(去掉鼠标离开自动收);
    新卡住 / 新借鼠标 → 自动展开;借鼠标弹开的,借完自动收回(卡住弹开的一直开着等处理)。"""
    global tasks
    was_stuck = {t["key"] for t in tasks if stuck(t)}
    was_borrow = {t["key"] for t in tasks if borrow(t)}
    tasks = list(task_list)
    if not tasks:
        hide()
        return
    for t in tasks:
        if stuck(t) and t["key"] not in was_stuck:
            st["open"] = True
            st["auto_open"] = None             # 卡住弹开的不自动收
        if borrow(t) and t["key"] not in was_borrow and not st["open"]:
            st["open"] = True
            st["auto_open"] = "borrow"
    if st["open"] and st.get("auto_open") == "borrow" and not any(borrow(t) or stuck(t) for t in tasks):
        st.update(open=False, auto_open=None, more=False, light_open=False)
    render(now)


def test(what):
    """测试用:不动鼠标也能开合 / 看按钮栏 / 展开全部。"""
    if what == "open":
        st["open"] = True
    elif what == "close":
        st.update(open=False, light_open=False, more=False)
    elif what == "hover":
        st["hover"] = True
    elif what == "unhover":
        st["hover"] = False
    elif what == "more":
        st["more"] = not st.get("more")
    elif what == "solo":
        a = ordered(time.time())
        if a:
            H["solo"](a[0]["key"])
    render(time.time(), force=True)
