#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
cursor_overlay.py —— "代理光标":纯显示的透明小窗口。

一个透明、不拦截鼠标、永远在最上层、所有桌面都显示的小窗口,里面画一个箭头光标,
跟着 move/click 消息走。跟系统鼠标毫无关系,纯显示——用户照常用自己的鼠标。

适用场景:跟 seeu_lib.sck_capture 一样,只适合"点击要对着 Mac 窗口走真实鼠标"的情形
(比如 iPhone 镜像,后台点击破解不了,只能真实鼠标点),让人看得出脚本在点哪里。
ADB 场景点击是直接发指令给设备、不挪 Mac 上的真实鼠标,不需要这个。
2026-09-29 从最早用它的项目里搬进来(项目专属的 demo 留在原项目,不属于公共库)。

名牌文字/颜色是项目相关的,库里只给不带个人信息的默认值,调用方通过
`main(argv, label=..., color=...)` 或环境变量 CURSOR_OVERLAY_LABEL /
CURSOR_OVERLAY_COLOR("r,g,b",0~1)覆盖。

用法(坐标一律是桌面点坐标,原点主屏左上,单位跟 mir.px_to_pt() 的输出一致):
  cursor_overlay.py serve            启动常驻显示进程(空闲 IDLE_EXIT_S 秒自动退出)
  cursor_overlay.py move <x> <y>     光标平滑移到 (x,y)
  cursor_overlay.py click <x> <y>    移过去 + 点击波纹
  cursor_overlay.show(kind,x,y,label,color)  Python 里调:每条消息可带自己的名牌和颜色(SeeU 按模式区分)
  cursor_overlay.py glow r,g,b [秒]  屏幕四周亮一圈光圈("电脑正在被 SeeU 操作"),到点淡出;glow_off 立刻关
  cursor_overlay.py toast 标题 [内容] [秒] [链接]  右上角提示条,点了打开链接(如会话链接),到点淡出;不进通知中心
  cursor_overlay.py hide             立刻藏起来(下次 move/click 再出现,直接到位)
  cursor_overlay.py quit             让常驻进程立刻退出
  命令行调用:capture_window 同类模式,serve 一般不用手动起,调用方(如 mir.py)的
  _overlay() 探测端口没人监听就自动拉起。
"""
import os
import math
import socket
import sys
import time
from urllib.parse import quote, unquote

PORT = 47831
WIN_W, WIN_H = 150, 90   # 窗口尺寸(点);C-1.3 加光晕后放大一圈
TIP = (40, 40)           # 光标尖端在窗口里的位置(左边/上边留出点击波纹、光晕的空间)
DEFAULT_LABEL = "Claude"           # 名牌文字默认值,调用方一般会覆盖成用户名
DEFAULT_COLOR = (0.50, 0.47, 0.87)  # 光标+名牌颜色默认值(紫,#7F77DD)
MOVE_S = 0.28        # 移动动画时长(老调用方等这么久;C-1.3 起按距离算,见 travel_s,最短约 0.22)
MOVE_MAX_S = 0.65    # C-1.3:离得越远走越久,最长这么多秒
RING_S = 0.45        # 点击波纹时长
FADE_AFTER_S = 60    # 多久没动作开始淡出(C-1.3 用户:8 → 60,跟悬浮窗一致;等待期间原地呼吸)
# ---- C-1.3 动效(用户在预览里定"五种全开 + Codex 同款原地摆")
ARC_K, ARC_MAX = 0.22, 90.0   # 弧线:控制点偏离直线 = 距离 × ARC_K,最多 ARC_MAX 点
OVERSHOOT = 1.25              # 惯性:到点冲过一点再回(easeOutBack 系数,0 = 不冲)
TILT_K, TILT_MAX = 0.04, 0.35 # 倾斜:每帧位移(点)× TILT_K 弧度,最多约 20°
GLOW_R = 30                   # 光晕半径(点)
PRESS_S = (0.09, 0.17)        # 点击按下:缩到 0.82 用时、弹回用时
# C-1.4 待机动作改成 SeeU 自己的(用户在预览里定,替掉 C-1.3 学 Codex 的原地摆):
# 停下 IDLE_AFTER_S 秒后箭头以尖端为中心呼吸(放大 BREATH_AMP、BREATH_S 秒一呼一吸,光晕同步);
# 每 FOCUS_EVERY 次呼吸,在缩回原大小的那 FOCUS_S 秒里,一道反光从尾部扫向尖端,回到原大小那一刻尖端闪一下。
IDLE_AFTER_S = 5.0            # 停下多久开始呼吸(C-1.3 原地摆是 1 秒,调用方约每秒点一下时两下之间总在晃)
BREATH_AMP, BREATH_S = 0.18, 2.8
FOCUS_EVERY, FOCUS_S = 3, 1.0
SHINE_TAIL, SHINE_TIP, SHINE_W = (12.5, 16.5), (0.8, 0.6), 5.0   # 反光起止点(相对尖端)、光带半宽
ARROW_C = (7.0, 9.0)          # 箭头中心(相对尖端),倾斜/按下的转轴
_last_xy = [None]             # 本进程上次送去的位置,用来估算这次要走多久(调用方据此等光标到位)


def travel_s(x0, y0, x1, y1):
    """从 (x0,y0) 走到 (x1,y1) 的动画时长:近的约 0.22 秒,远的最长 MOVE_MAX_S。显示进程和调用方用同一个算法。"""
    d = math.hypot(x1 - x0, y1 - y0)
    return min(MOVE_MAX_S, 0.22 + d * 0.0009)
TOAST_W, TOAST_H, TOAST_GAP = 340, 66, 10   # 提示条尺寸(点)
TOAST_BTN_W = 58                              # 右下角「打开 ›」按钮宽
GLOW_FADE_S = 0.35      # 屏幕边缘光圈淡入淡出
GLOW_W = 26             # 光圈宽度(点)
GLOW_PERIOD_S = 1.8     # 呼吸一个来回
GLOW_BREATH = 0.55      # 呼吸幅度:最暗时 = 1 - 0.55
OCCLUDE_CHECK_S = 0.2   # 带 owner 的光标多久查一次遮挡
SEE_THROUGH = ("Screenshot", "screencaptureui")   # 截图工具的全屏透明层,不算挡住
IDLE_EXIT_S = 600    # 硬上限:空闲 10 分钟自动退出,不留孤儿进程


def show(kind, x, y, label=None, color=None, owner=None):
    """move/click 带名牌和颜色(color = (r,g,b) 0~1)。名牌可含空格/中文。
    owner = 目标 App 名(如 "iPhone Mirroring"):显示进程每 OCCLUDE_CHECK_S 秒自己查光标下最上层窗口是不是它,
    不是(被别的窗口挡住 / 不在当前桌面)就立刻藏,露出来再显示。不带 owner 就不查(老调用不受影响)。"""
    parts = [kind, round(x, 1), round(y, 1),
             quote(label, safe="@") if label else "-",                       # "-" = 用默认
             ",".join(f"{c:.3f}" for c in color) if color else "-"]
    if owner:
        parts.append(quote(owner, safe=""))
    send(*parts)
    prev, _last_xy[0] = _last_xy[0], (float(x), float(y))
    # C-1.3:返回光标大约多久走到位(调用方等这么久再动手,波纹才对得上);第一次没有上一个位置,按老的 MOVE_S
    return travel_s(prev[0], prev[1], x, y) if prev else MOVE_S


def glow(color, secs=2.0):
    """屏幕四周亮一圈光圈("电脑正在被 SeeU 操作")secs 秒,到点自己淡出;动作持续就反复调来续时。color=(r,g,b) 0~1。"""
    send("glow", ",".join(f"{c:.3f}" for c in color), round(float(secs), 2))


def glow_off():
    send("glow_off")


def toast(title, body="", secs=6.0, link=None, color=None):
    """屏幕右上角提示条(代替系统通知:不进通知中心、不受专注模式管、点了不会打开脚本编辑器)。
    link:点一下用 `open` 打开它(如会话链接 claude://claude.ai/epitaxy/<id>,点了跳回那个会话);不给就点了只关掉。
    secs 秒后自己淡出(最多 60 秒)。color=(r,g,b) 左侧色条,默认紫色。
    10-15:显示进程没在跑(空闲 10 分钟会自己退)就先拉起,以前这种情况提示条会悄悄丢掉。"""
    ensure_serve()
    send("toast", quote(title or "", safe="") or "-", quote(body or "", safe="") or "-", round(float(secs), 1),
         quote(link, safe="") if link else "-", ",".join(f"{c:.3f}" for c in color) if color else "-")


def ensure_serve(wait_s=3.0):
    """显示进程没在跑就拉起(用户没传名牌/颜色时用默认值,每条消息自带的照旧生效)。有上限,起不来返回 False。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", PORT))      # 绑得上 = 没人在监听
    except OSError:
        return True
    finally:
        probe.close()
    import subprocess
    subprocess.Popen(["/usr/bin/python3", os.path.abspath(__file__), "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(0.1)
        p2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            p2.bind(("127.0.0.1", PORT))
        except OSError:
            time.sleep(0.3)
            return True
        finally:
            p2.close()
    return False


def send(*parts):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(" ".join(str(p) for p in parts).encode(), ("127.0.0.1", PORT))
    s.close()


def _owner_on_top(owner, x, y):
    """(x,y) 上最上层的窗口是不是 owner 的(复用 input_guard.window_at:跳过透明窗、Dock、代理光标自己)。查不了就当没挡。"""
    try:
        from seeu_lib import input_guard as ig
        top = ig.window_at(x, y, skip=SEE_THROUGH)
        return bool(top and top["owner"] == owner)
    except Exception:
        return True


def _parse_color(v):
    try:
        r, g, b = (float(x) for x in v.split(","))
        return (r, g, b)
    except Exception:
        return None


def _env_color():
    v = os.environ.get("CURSOR_OVERLAY_COLOR")
    if not v:
        return None
    try:
        r, g, b = (float(x) for x in v.split(","))
        return (r, g, b)
    except Exception:
        return None


def serve(label=None, color=None):
    label = label or os.environ.get("CURSOR_OVERLAY_LABEL") or DEFAULT_LABEL
    color = color or _env_color() or DEFAULT_COLOR

    import objc
    import Quartz
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBezierPath, NSPanel, NSGradient, NSImage,
                        NSColorSpace,
                        NSWindowStyleMaskNonactivatingPanel,
                        NSColor, NSScreen, NSView, NSFont, NSAttributedString,
                        NSFontAttributeName, NSForegroundColorAttributeName, NSWindow, NSBackingStoreBuffered,
                        NSWindowStyleMaskBorderless, NSScreenSaverWindowLevel,
                        NSWindowCollectionBehaviorCanJoinAllSpaces,
                        NSWindowCollectionBehaviorStationary,
                        NSWindowCollectionBehaviorFullScreenAuxiliary,
                        NSWindowCollectionBehaviorMoveToActiveSpace, NSWorkspace)
    from Foundation import NSBundle, NSObject, NSTimer, NSMakeRect, NSMakePoint, NSValue
    # 10-14:下面 NSScreen/sharedApplication 一碰就会先登记成前台、Dock 闪一下;先标 LSUIElement(能开窗、不进 Dock)
    NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    sock.setblocking(False)

    screen_h = NSScreen.screens()[0].frame().size.height
    st = dict(cur=None, frm=None, to=None, t0=0.0, ring_t0=None, dur=MOVE_S, ctl=None, tilt=0.0, sway=0.0,
              press_t0=None, arrive_t=0.0, redraw_n=0,
              last=time.time(), shown=False, label=label, color=color,
              owner=None, occluded=False, occ_t=0.0,
              glow_color=(1.0, 0.624, 0.039), glow_until=0.0, glow_last=0.0)

    class GlowView(NSView):
        """一整块屏幕大小的透明视图,只沿四边画一圈由外向内渐隐的光(不拦鼠标)。"""
        def drawRect_(self, rect):
            b = self.bounds()
            r_, g_, b_ = st["glow_color"]
            n = 10
            for i in range(n):
                k = 1 - i / n
                NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 0.85 * k * k).set()
                inset = i * GLOW_W / n + 1
                path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(b.origin.x + inset, b.origin.y + inset,
                               b.size.width - 2 * inset, b.size.height - 2 * inset), 12, 12)
                path.setLineWidth_(GLOW_W / n + 0.6)
                path.stroke()

    toasts = []   # 每项 dict(win, until, link, title, body, color)

    class ToastView(NSView):
        def isFlipped(self):
            return True

        def acceptsFirstMouse_(self, _e):
            return True                      # 不用先激活就能点

        def mouseDown_(self, e):
            t = next((t for t in toasts if t["win"].contentView() is self), None)
            if t:
                p = self.convertPoint_fromView_(e.locationInWindow(), None)
                w_, h_ = self.bounds().size.width, self.bounds().size.height
                if p.x >= w_ - 36 and p.y <= 36:                      # 右上角 36×36 点内 = 点 ×:只关掉
                    t["until"] = 0.0
                    return
                # 10-14 用户:整张卡片可点容易误跳 → 只有右下角「打开 ›」按钮才跳转,点别处不做任何事
                if t["link"] and p.x >= w_ - TOAST_BTN_W - 14 and p.y >= h_ - 30:
                    import subprocess
                    subprocess.Popen(["open", t["link"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    t["until"] = 0.0

        def drawRect_(self, rect):
            t = next((t for t in toasts if t["win"].contentView() is self), None)
            if not t:
                return
            b = self.bounds()
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.11, 0.13, 0.94).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 12, 12).fill()
            r_, g_, b_ = t["color"]
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 1.0).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(10, 12, 4, b.size.height - 24), 2, 2).fill()
            ta = {NSFontAttributeName: NSFont.systemFontOfSize_weight_(13, 0.4),
                  NSForegroundColorAttributeName: NSColor.whiteColor()}
            ba = {NSFontAttributeName: NSFont.systemFontOfSize_(12),
                  NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(0.82, 1.0)}
            NSAttributedString.alloc().initWithString_attributes_(t["title"], ta).drawInRect_(
                NSMakeRect(24, 11, b.size.width - 64, 18))
            # 右上角 ×(圆底 + 叉)
            cx, cy = b.size.width - 18, 18
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.18).set()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - 10, cy - 10, 20, 20)).fill()
            x_ = NSBezierPath.bezierPath()
            x_.moveToPoint_(NSMakePoint(cx - 4.5, cy - 4.5)); x_.lineToPoint_(NSMakePoint(cx + 4.5, cy + 4.5))
            x_.moveToPoint_(NSMakePoint(cx + 4.5, cy - 4.5)); x_.lineToPoint_(NSMakePoint(cx - 4.5, cy + 4.5))
            x_.setLineWidth_(1.8)
            NSColor.colorWithCalibratedWhite_alpha_(0.85, 1.0).set()
            x_.stroke()
            NSAttributedString.alloc().initWithString_attributes_(t["body"], ba).drawInRect_(
                NSMakeRect(24, 32, b.size.width - 90 if t["link"] else b.size.width - 36, b.size.height - 36))
            if t["link"]:
                bx = b.size.width - TOAST_BTN_W - 10
                btn = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(bx, b.size.height - 26, TOAST_BTN_W, 20), 10, 10)
                NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 0.95).set()
                btn.fill()
                light = 0.299 * r_ + 0.587 * g_ + 0.114 * b_ > 0.62
                ha = {NSFontAttributeName: NSFont.systemFontOfSize_weight_(11, 0.3),
                      NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.17, 0.27, 1.0)
                      if light else NSColor.whiteColor()}
                NSAttributedString.alloc().initWithString_attributes_("打开 ›", ha).drawAtPoint_(
                    NSMakePoint(bx + 13, b.size.height - 23.5))

    def toast_layout():
        vf = NSScreen.mainScreen().visibleFrame()
        top = vf.origin.y + vf.size.height - 16
        x = vf.origin.x + vf.size.width - TOAST_W - 16
        try:   # 10-15 监看悬浮窗显示在提示条那一列时,提示条从它下面开始叠(用户定:悬浮窗右上角,提示条让位)
            from seeu_lib import watch_window as ww
            f = ww.visible_frame()
            if f and f[0] < x + TOAST_W and f[0] + f[2] > x and f[1] < top:
                top = min(top, f[1] - TOAST_GAP)
        except Exception:
            pass
        st["toast_top"] = top
        for i, t in enumerate(toasts):
            y = top - TOAST_H - i * (TOAST_H + TOAST_GAP)
            t["win"].setFrameOrigin_(NSMakePoint(x, y))

    def toast_new(title, body, secs, link, col, now):
        w = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, TOAST_W, TOAST_H), NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        w.setOpaque_(False)
        w.setBackgroundColor_(NSColor.clearColor())
        w.setHasShadow_(True)
        w.setLevel_(NSScreenSaverWindowLevel)
        w.setHidesOnDeactivate_(False)
        w.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                 | NSWindowCollectionBehaviorStationary
                                 | NSWindowCollectionBehaviorFullScreenAuxiliary)
        w.setContentView_(ToastView.alloc().initWithFrame_(NSMakeRect(0, 0, TOAST_W, TOAST_H)))
        w.setAlphaValue_(0.0)
        toasts.insert(0, dict(win=w, until=now + max(1.0, min(secs, 60)), link=link, title=title, body=body,
                              color=col))
        for old in toasts[4:]:               # 最多叠 4 条
            old["win"].orderOut_(None)
        del toasts[4:]
        toast_layout()
        w.orderFrontRegardless()

    glows = []

    def build_glows():
        for w in glows:
            w.orderOut_(None)
        glows[:] = []
        for sc in NSScreen.screens():
            f = sc.frame()
            gw = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                f, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
            gw.setOpaque_(False)
            gw.setBackgroundColor_(NSColor.clearColor())
            gw.setHasShadow_(False)
            gw.setIgnoresMouseEvents_(True)
            gw.setLevel_(NSScreenSaverWindowLevel)
            gw.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                      | NSWindowCollectionBehaviorStationary
                                      | NSWindowCollectionBehaviorFullScreenAuxiliary)
            gw.setContentView_(GlowView.alloc().initWithFrame_(NSMakeRect(0, 0, f.size.width, f.size.height)))
            gw.setFrame_display_(f, False)
            gw.setAlphaValue_(0.0)
            glows.append(gw)
        st["glow_screens"] = len(NSScreen.screens())

    class CursorView(NSView):
        def isFlipped(self):
            return True

        def drawRect_(self, rect):
            cx, cy = TIP
            r_, g_, b_ = st["color"]
            if st["ring_t0"] is not None and time.time() >= st["ring_t0"]:
                p = min(1.0, (time.time() - st["ring_t0"]) / RING_S)
                r = 5 + 20 * p
                NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 0.8 * (1 - p)).set()
                ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))
                ring.setLineWidth_(2.5)
                ring.stroke()
            # C-1.3 起箭头、光晕、名牌都是图层(见 build_layers),这里只画点击波纹

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIN_W, WIN_H), NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(False)   # C-1.3:有光晕后窗口阴影会把半透明光晕投成一圈深色圆盘
    win.setIgnoresMouseEvents_(True)
    win.setLevel_(NSScreenSaverWindowLevel)
    # 10-14 C-1.1(实测切桌面残影):光标窗口不再"跨所有桌面",改成"显示时跟到当前桌面":
    # 用户切走时它留在原桌面、跟着原桌面一起滑走,不会在新桌面上停一下;再出现时 orderFront 把它带到当前桌面。
    win.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace
                               | NSWindowCollectionBehaviorStationary
                               | NSWindowCollectionBehaviorFullScreenAuxiliary)
    view = CursorView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
    win.setContentView_(view)
    win.setAlphaValue_(0.0)

    # ---- C-1.3 箭头 / 光晕 / 名牌做成图层:原地摆、光晕呼吸交给系统动画,Python 不用每帧重画
    # (实测每帧重画时进程 ~9%,旧版不画 ~2.7%)。图层坐标统一成 y 朝下(跟 TIP 一致)。
    view.setWantsLayer_(True)
    _root = view.layer()
    host = Quartz.CALayer.layer()
    host.setFrame_(_root.bounds())
    host.setGeometryFlipped_(not _root.isGeometryFlipped())
    _root.addSublayer_(host)
    _scale = NSScreen.mainScreen().backingScaleFactor() if NSScreen.mainScreen() else 2.0
    glow_l, arrow_l, pill_l = Quartz.CALayer.layer(), Quartz.CALayer.layer(), Quartz.CALayer.layer()
    for _l in (glow_l, arrow_l, pill_l):
        _l.setContentsScale_(_scale)
        host.addSublayer_(_l)
    APAD = 3.0                                    # 箭头图片四周留白(白描边不被裁)
    AW, AH = 18 + 2 * APAD, 21 + 2 * APAD

    def _img(w, h, draw):
        def handler(rect):
            draw()
            return True
        return NSImage.imageWithSize_flipped_drawingHandler_((w, h), True, handler)

    def _contents(layer, img):
        layer.setContents_(img.layerContentsForContentsScale_(_scale))

    def build_layers():
        """按当前颜色/名牌重做三张图。只在颜色或名牌变了时调用。"""
        r_, g_, b_ = st["color"]
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        R = GLOW_R

        def dglow():
            NSGradient.alloc().initWithStartingColor_endingColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 1.0),
                NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 0.0)
            ).drawFromCenter_radius_toCenter_radius_options_(NSMakePoint(R, R), 0, NSMakePoint(R, R), R, 0)
        _contents(glow_l, _img(2 * R, 2 * R, dglow))
        glow_l.setBounds_(Quartz.CGRectMake(0, 0, 2 * R, 2 * R))
        glow_l.setPosition_((TIP[0] + 6, TIP[1] + 8))

        def darrow():
            def P(x, y):
                return NSMakePoint(APAD + x, APAD + y)

            def quad(path, ctrl, end):
                path.curveToPoint_controlPoint1_controlPoint2_(P(*end), P(*ctrl), P(*ctrl))
            path = NSBezierPath.bezierPath()
            path.moveToPoint_(P(0.5, 1.5))
            path.lineToPoint_(P(4, 17.5))
            quad(path, (4.6, 19.8), (6.2, 18.2))
            path.lineToPoint_(P(9.2, 13.5))
            path.lineToPoint_(P(14.8, 12.6))
            quad(path, (17, 12.1), (15.3, 10.6))
            path.lineToPoint_(P(2, 0))
            quad(path, (0, -0.8), (0.5, 1.5))
            path.closePath()
            path.setLineJoinStyle_(1)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 1.0).set()
            path.fill()
            NSColor.whiteColor().set()
            path.setLineWidth_(1.6)
            path.stroke()
        _contents(arrow_l, _img(AW, AH, darrow))
        arrow_l.setBounds_(Quartz.CGRectMake(0, 0, AW, AH))
        # 转轴 = 箭头中心 ARROW_C;position 放在 TIP + ARROW_C,尖端就落在 TIP
        arrow_l.setAnchorPoint_(((APAD + ARROW_C[0]) / AW, (APAD + ARROW_C[1]) / AH))
        arrow_l.setPosition_((TIP[0] + ARROW_C[0], TIP[1] + ARROW_C[1]))

        # 名牌(样式 B):箭头右下方的小胶囊;10-14:浅色底用深色字,深色底用白字
        light = 0.299 * r_ + 0.587 * g_ + 0.114 * b_ > 0.62
        fg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.17, 0.27, 1.0) if light else NSColor.whiteColor()
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_weight_(10, 0.23), NSForegroundColorAttributeName: fg}
        text = NSAttributedString.alloc().initWithString_attributes_(st["label"], attrs)
        tw, th = text.size().width, text.size().height
        pw, ph = tw + 12, th + 4

        def dpill():
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r_, g_, b_, 1.0).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(0, 0, pw, ph), ph / 2, ph / 2).fill()
            text.drawAtPoint_(NSMakePoint(6, 2))
        _contents(pill_l, _img(pw, ph, dpill))
        pill_l.setFrame_(Quartz.CGRectMake(TIP[0] + 13, TIP[1] + 17, pw, ph))
        Quartz.CATransaction.commit()

    def _basic(key, frm, to, dur, auto=True, repeat=1e9, ease="easeInEaseOut"):
        a = Quartz.CABasicAnimation.animationWithKeyPath_(key)
        a.setFromValue_(frm)
        a.setToValue_(to)
        a.setDuration_(dur)
        a.setAutoreverses_(auto)
        a.setRepeatCount_(repeat)
        a.setRemovedOnCompletion_(False)
        a.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(ease))
        return a

    # 光晕呼吸:透明度 0.19~0.41 来回(原来 0.55 ×(0.55±0.2)),半个来回 0.45π 秒
    glow_l.addAnimation_forKey_(_basic("opacity", 0.19, 0.41, 0.45 * math.pi), "breath")

    def press_now():
        """点击按下:箭头缩到 0.82 再弹回,光晕放大一下。"""
        k = Quartz.CAKeyframeAnimation.animationWithKeyPath_("transform.scale")
        tot = PRESS_S[0] + PRESS_S[1]
        k.setValues_([1.0, 0.82, 1.0])
        k.setKeyTimes_([0.0, PRESS_S[0] / tot, 1.0])
        k.setDuration_(tot)
        arrow_l.addAnimation_forKey_(k, "press")
        g = Quartz.CAKeyframeAnimation.animationWithKeyPath_("transform.scale")
        g.setValues_([1.0, 1.27, 1.0])
        g.setKeyTimes_([0.0, 0.25, 1.0])
        g.setDuration_(0.4)
        glow_l.addAnimation_forKey_(g, "press")

    # ---- C-1.4 待机呼吸 + 聚焦:反光层、尖端亮点挂在箭头图层下面(跟着一起缩放),只建一次
    def _cgpath_arrow():
        cp = Quartz.CGPathCreateMutable()
        P = lambda x, y: (APAD + x, APAD + y)
        Quartz.CGPathMoveToPoint(cp, None, *P(0.5, 1.5))
        Quartz.CGPathAddLineToPoint(cp, None, *P(4, 17.5))
        Quartz.CGPathAddQuadCurveToPoint(cp, None, *P(4.6, 19.8), *P(6.2, 18.2))
        Quartz.CGPathAddLineToPoint(cp, None, *P(9.2, 13.5))
        Quartz.CGPathAddLineToPoint(cp, None, *P(14.8, 12.6))
        Quartz.CGPathAddQuadCurveToPoint(cp, None, *P(17, 12.1), *P(15.3, 10.6))
        Quartz.CGPathAddLineToPoint(cp, None, *P(2, 0))
        Quartz.CGPathAddQuadCurveToPoint(cp, None, *P(0, -0.8), *P(0.5, 1.5))
        Quartz.CGPathCloseSubpath(cp)
        return cp

    shine_box = Quartz.CALayer.layer()           # 只露出箭头形状里的那部分反光
    shine_box.setFrame_(Quartz.CGRectMake(0, 0, AW, AH))
    _mask = Quartz.CAShapeLayer.layer()
    _mask.setFrame_(Quartz.CGRectMake(0, 0, AW, AH))
    _mask.setPath_(_cgpath_arrow())
    shine_box.setMask_(_mask)
    band_l, flash_l = Quartz.CALayer.layer(), Quartz.CALayer.layer()
    for _l in (band_l, flash_l):
        _l.setContentsScale_(_scale)
        _l.setOpacity_(0.0)
    shine_box.addSublayer_(band_l)
    arrow_l.addSublayer_(shine_box)
    arrow_l.addSublayer_(flash_l)
    _ux, _uy = SHINE_TIP[0] - SHINE_TAIL[0], SHINE_TIP[1] - SHINE_TAIL[1]
    _ul = math.hypot(_ux, _uy)
    _ux, _uy = _ux / _ul, _uy / _ul
    BS = 48.0

    def dband():
        clear = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.0)
        NSGradient.alloc().initWithColors_atLocations_colorSpace_(
            [clear, NSColor.whiteColor(), clear], [0.0, 0.5, 1.0], NSColorSpace.genericRGBColorSpace()
        ).drawFromPoint_toPoint_options_(NSMakePoint(BS / 2 - _ux * SHINE_W, BS / 2 - _uy * SHINE_W),
                                         NSMakePoint(BS / 2 + _ux * SHINE_W, BS / 2 + _uy * SHINE_W), 0)
    _contents(band_l, _img(BS, BS, dband))
    band_l.setBounds_(Quartz.CGRectMake(0, 0, BS, BS))
    band_l.setPosition_((APAD + SHINE_TAIL[0], APAD + SHINE_TAIL[1]))
    FR = 4.5

    def dflash():
        NSGradient.alloc().initWithStartingColor_endingColor_(
            NSColor.whiteColor(), NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.0)
        ).drawFromCenter_radius_toCenter_radius_options_(NSMakePoint(FR, FR), 0, NSMakePoint(FR, FR), FR, 0)
    _contents(flash_l, _img(2 * FR, 2 * FR, dflash))
    flash_l.setBounds_(Quartz.CGRectMake(0, 0, 2 * FR, 2 * FR))
    flash_l.setPosition_((APAD + 1.4, APAD + 1.5))

    def _loop(key, times, values, total):
        a = Quartz.CAKeyframeAnimation.animationWithKeyPath_(key)
        a.setValues_(values)
        a.setKeyTimes_([t / total for t in times])
        a.setDuration_(total)
        a.setRepeatCount_(1e9)
        a.setRemovedOnCompletion_(False)
        return a

    def breathe(on):
        """待机呼吸 + 每 FOCUS_EVERY 次聚焦到尖端。全交给系统动画,Python 只在开始/停下时调一次。"""
        if on == st.get("breathing"):
            return
        st["breathing"] = on
        if not on:
            for l, k in ((arrow_l, "breath"), (glow_l, "breath2"), (band_l, "pos"), (band_l, "op"), (flash_l, "op")):
                l.removeAnimationForKey_(k)
            return
        total = BREATH_S * FOCUS_EVERY
        n = 24 * FOCUS_EVERY
        ts = [total * i / n for i in range(n + 1)]
        bs = [0.5 - 0.5 * math.cos(2 * math.pi * t / BREATH_S) for t in ts]
        tr = []
        for b in bs:      # 以尖端为中心缩放:绕转轴(箭头中心)放大后,再把尖端挪回原处
            k = 1 + BREATH_AMP * b
            tr.append(NSValue.valueWithCATransform3D_(Quartz.CATransform3DScale(
                Quartz.CATransform3DMakeTranslation((k - 1) * ARROW_C[0], (k - 1) * ARROW_C[1], 0), k, k, 1)))
        arrow_l.addAnimation_forKey_(_loop("transform", ts, tr, total), "breath")
        g = Quartz.CAAnimationGroup.animation()   # 光晕同步:透明度 0.19~0.41、略放大
        g.setAnimations_([_loop("opacity", ts, [0.19 + 0.22 * b for b in bs], total),
                          _loop("transform.scale", ts, [1 + 0.1 * b for b in bs], total)])
        g.setDuration_(total)
        g.setRepeatCount_(1e9)
        g.setRemovedOnCompletion_(False)
        glow_l.addAnimation_forKey_(g, "breath2")
        # 反光:最后 FOCUS_S 秒(缩回原大小)从尾部扫到尖端,越近越亮;到点尖端闪一下,下一轮开头 0.45 秒淡掉
        f0 = total - FOCUS_S
        st_ = [f0 + FOCUS_S * i / 10 for i in range(11)]
        ss = [i / 10 for i in range(11)]
        ee = [s_ * s_ * (3 - 2 * s_) for s_ in ss]
        pos = [NSValue.valueWithPoint_(NSMakePoint(APAD + SHINE_TAIL[0] + (SHINE_TIP[0] - SHINE_TAIL[0]) * e,
                                                          APAD + SHINE_TAIL[1] + (SHINE_TIP[1] - SHINE_TAIL[1]) * e))
               for e in ee]
        p_start = pos[0]
        band_l.addAnimation_forKey_(_loop("position", [0.0, f0] + st_, [p_start, p_start] + pos, total), "pos")
        band_l.addAnimation_forKey_(_loop("opacity", [0.0, f0 - 0.001] + st_,
                                          [0.0, 0.0] + [0.35 + 0.6 * e for e in ee[:-1]] + [0.0], total), "op")
        flash_l.addAnimation_forKey_(_loop("opacity", [0.0, 0.45, total - 0.15, total],
                                           [0.9, 0.0, 0.0, 0.9], total), "op")

    def set_tilt(a):
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        arrow_l.setAffineTransform_(Quartz.CGAffineTransformMakeRotation(a))
        Quartz.CATransaction.commit()

    build_layers()

    def place(x, y):
        win.setFrameOrigin_(NSMakePoint(x - TIP[0], screen_h - y - (WIN_H - TIP[1])))

    class Ticker(NSObject):
        def spaceChanged_(self, _n):
            # 切桌面:带 owner 的光标下一帧马上重查遮挡(不等 0.2 秒一轮)
            st["occ_t"] = 0.0

        def tick_(self, _t):
            now = time.time()
            for _ in range(50):              # 读完积压的消息(每帧最多 50 条,有上限)
                try:
                    msg = sock.recv(8192).decode().split()
                except BlockingIOError:
                    break
                if len(msg) >= 3 and msg[0] in ("move", "click"):
                    x, y = float(msg[1]), float(msg[2])
                    # 10-14 可选第 4/5 段:名牌(URL 编码)、颜色 "r,g,b";不带就回到启动时的默认(老发法不受影响)
                    lab = unquote(msg[3]) if len(msg) >= 4 and msg[3] != "-" else label
                    col = _parse_color(msg[4]) if len(msg) >= 5 and msg[4] != "-" else None
                    st["owner"] = unquote(msg[5]) if len(msg) >= 6 else None
                    st["occluded"], st["occ_t"] = False, 0.0
                    col = col or color
                    if (lab, col) != (st["label"], st["color"]):
                        st["label"], st["color"] = lab, col
                        build_layers()
                        view.setNeedsDisplay_(True)
                    st["frm"] = st["cur"] or (x, y)
                    st["to"], st["t0"], st["last"] = (x, y), now, now
                    # C-1.3 弧线:控制点在中点往一侧偏(距离 × ARC_K),时长按距离算
                    fx_, fy_ = st["frm"]
                    d_ = math.hypot(x - fx_, y - fy_)
                    st["dur"] = travel_s(fx_, fy_, x, y) if st["cur"] else 0.0
                    side = 1 if (int(now * 1000) % 2) else -1
                    off = min(ARC_MAX, d_ * ARC_K) * side
                    nx_, ny_ = (-(y - fy_) / d_, (x - fx_) / d_) if d_ > 1 else (0.0, 0.0)
                    st["ctl"] = ((fx_ + x) / 2 + nx_ * off, (fy_ + y) / 2 + ny_ * off)
                    st["arrive_t"] = now + st["dur"]
                    st["ring_t0"] = now + st["dur"] if msg[0] == "click" else st["ring_t0"]
                    st["press_t0"] = now + st["dur"] if msg[0] == "click" else st["press_t0"]
                elif msg and msg[0] == "hide":    # 10-14 SeeU:目标位置被挡/不在当前桌面 → 立刻藏,下次出现直接到位不滑过来
                    st["cur"], st["ring_t0"], st["last"] = None, None, now - FADE_AFTER_S - 2
                elif len(msg) == 3 and msg[0] == "glow":   # 10-14 屏幕边缘光圈:glow r,g,b 秒数
                    col = _parse_color(msg[1]) or st["glow_color"]
                    if not glows or st.get("glow_screens") != len(NSScreen.screens()):
                        build_glows()                       # 显示器插拔后重建
                    if col != st["glow_color"]:
                        st["glow_color"] = col
                        for gw in glows:
                            gw.contentView().setNeedsDisplay_(True)
                    st["glow_until"] = now + max(0.2, min(float(msg[2]), 600))   # 单次最多 10 分钟,有上限
                    st["glow_last"] = now
                elif len(msg) == 6 and msg[0] == "toast":     # 10-14 提示条:toast 标题 内容 秒 链接 颜色
                    dq = lambda v: "" if v == "-" else unquote(v)
                    toast_new(dq(msg[1]), dq(msg[2]), float(msg[3]), dq(msg[4]) or None,
                              _parse_color(msg[5]) or (0.498, 0.467, 0.867), now)
                    st["glow_last"] = now
                elif msg and msg[0] == "glow_off":
                    st["glow_until"] = 0.0
                elif msg and msg[0] == "quit":
                    NSApplication.sharedApplication().terminate_(None)
            if toasts and now - st.get("toast_chk", 0) > 1.0:   # 悬浮窗出现/收起/被拖动后,提示条跟着让位
                st["toast_chk"] = now
                toast_layout()
            if toasts:
                gone = []
                for t in toasts:
                    a, tgt = t["win"].alphaValue(), (1.0 if now < t["until"] else 0.0)
                    if abs(a - tgt) > 0.01:
                        step = (1 / 60.0) / 0.25
                        t["win"].setAlphaValue_(min(tgt, a + step) if tgt > a else max(tgt, a - step))
                    elif tgt == 0.0:
                        gone.append(t)
                for t in gone:
                    t["win"].orderOut_(None)
                    toasts.remove(t)
                if gone:
                    toast_layout()
            if glows:
                # 包络:到点前 1、到点后 0,按 GLOW_FADE_S 渐变;亮着时再乘一个"呼吸"(明暗缓慢起伏)
                env = st.get("glow_env", 0.0)
                tgt = 1.0 if now < st["glow_until"] else 0.0
                step = (1 / 60.0) / GLOW_FADE_S
                env = min(tgt, env + step) if tgt > env else max(tgt, env - step)
                st["glow_env"] = env
                breath = 1 - GLOW_BREATH * (0.5 - 0.5 * math.cos(2 * math.pi * now / GLOW_PERIOD_S))
                a = env * breath
                for gw in glows:
                    if abs(gw.alphaValue() - a) > 0.005:
                        gw.setAlphaValue_(a)
                        if a > 0 and not gw.isVisible():
                            gw.orderFrontRegardless()
            moving = False
            if st["to"]:
                p = min(1.0, (now - st["t0"]) / st["dur"]) if st["dur"] > 0 else 1.0
                if OVERSHOOT > 0:                # 惯性:冲过一点再回(easeOutBack)
                    q = p - 1
                    e = q * q * ((OVERSHOOT + 1) * q + OVERSHOOT) + 1
                else:
                    e = 1 - (1 - p) ** 3
                u = min(e, 1.15)
                fx, fy = st["frm"]
                tx, ty = st["to"]
                kx, ky = st["ctl"] or ((fx + tx) / 2, (fy + ty) / 2)
                nxt = ((1 - u) ** 2 * fx + 2 * (1 - u) * u * kx + u * u * tx,
                       (1 - u) ** 2 * fy + 2 * (1 - u) * u * ky + u * u * ty)
                vx = nxt[0] - st["cur"][0] if st["cur"] else 0.0
                moving = p < 1.0
                if nxt != st["cur"]:
                    st["cur"] = nxt
                    place(*nxt)
                want = max(-TILT_MAX, min(TILT_MAX, vx * TILT_K)) if moving else 0.0
                old_tilt = st["tilt"]
                st["tilt"] += (want - st["tilt"]) * 0.18
                if abs(st["tilt"]) < 0.002 and not moving:
                    st["tilt"] = 0.0
                if moving:
                    breathe(False)
                if st["tilt"] != old_tilt:
                    set_tilt(st["tilt"])           # 只在移动/回正时每帧改一下图层角度,不重画
                # 待机呼吸:停下 IDLE_AFTER_S 秒后交给系统动画(停多久呼吸多久,Python 不管)
                if not moving and st["tilt"] == 0.0 and now - st["arrive_t"] >= IDLE_AFTER_S:
                    breathe(True)
                if st["press_t0"] is not None and now >= st["press_t0"]:
                    st["press_t0"] = None
                    press_now()
            idle = now - st["last"]
            # 10-14:两次动作之间窗口变了(用户开浏览器挡住、切桌面)也要自己藏,别等下一次动作
            if st["owner"] and st["to"] and idle < FADE_AFTER_S + 1 and now - st["occ_t"] >= OCCLUDE_CHECK_S:
                st["occ_t"] = now
                st["occluded"] = not _owner_on_top(st["owner"], *st["to"])
            target_alpha = 1.0 if idle < FADE_AFTER_S else max(0.0, 1 - (idle - FADE_AFTER_S))
            if st["occluded"]:
                target_alpha = 0.0
            if st["to"] and abs(win.alphaValue() - target_alpha) > 0.01:
                if target_alpha > 0 and (not st["shown"] or win.alphaValue() < 0.01):
                    win.orderFrontRegardless()     # 从藏着到显示:顺带把窗口带到当前桌面
                    st["shown"] = True
                win.setAlphaValue_(target_alpha)
            if st["ring_t0"] is not None:
                if now - st["ring_t0"] > RING_S:
                    st["ring_t0"] = None
                view.setNeedsDisplay_(True)
            if idle > IDLE_EXIT_S and now - st["glow_last"] > IDLE_EXIT_S and now > st["glow_until"] and not toasts:
                NSApplication.sharedApplication().terminate_(None)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)   # 不出 Dock 图标、不抢焦点
    ticker = Ticker.alloc().init()
    NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
        ticker, "spaceChanged:", "NSWorkspaceActiveSpaceDidChangeNotification", None)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1 / 60.0, ticker, "tick:", None, True)
    print(f"cursor_overlay 已启动,监听 127.0.0.1:{PORT},空闲 {IDLE_EXIT_S}s 自动退出")
    app.run()


def main(argv=None, label=None, color=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "serve":
        serve(label, color)
    elif cmd in ("move", "click") and len(argv) == 3:
        send(cmd, float(argv[1]), float(argv[2]))
    elif cmd in ("quit", "hide", "glow_off"):
        send(cmd)
    elif cmd == "toast" and len(argv) >= 2:
        toast(argv[1], argv[2] if len(argv) >= 3 else "", float(argv[3]) if len(argv) >= 4 else 6.0,
              argv[4] if len(argv) >= 5 else None)
    elif cmd == "glow" and len(argv) >= 2:
        glow(_parse_color(argv[1]) or (1.0, 0.624, 0.039), float(argv[2]) if len(argv) >= 3 else 2.0)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
