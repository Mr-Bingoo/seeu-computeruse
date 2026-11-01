#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
mac_input.py —— 对着某个 Mac 窗口发真实鼠标/键盘事件的底层:
找窗口、激活窗口、截图像素↔桌面点换算、Quartz 合成点击/拖动/滚轮、⌘+键、触发剪贴板同步。

适用场景:目标只吃真实输入的窗口(如 iPhone 镜像)。ADB 控制的安卓设备/模拟器不挪 Mac 鼠标,只用得上 trigger_paste_sync。
不含任何业务逻辑;应用名(owner)由调用方传。发事件前要不要把关(用户在用就让路等),
调用方自己调 seeu_lib.input_guard,这里只管"怎么发"。

坐标:桌面点 = 原点主屏左上,单位"点";截图像素 / scale + 窗口左上 = 桌面点(px_to_pt)。

用法:
    from seeu_lib import mac_input as mi
    g = mi.win_geo("iPhone Mirroring")            # {x,y,w,h,id} 或 None
    mi.activate("iPhone Mirroring")
    x, y = mi.px_to_pt(100, 200, g, scale=2)
    mi.qtap(x, y)                                  # 点完自动把鼠标挪开(park)
命令行(只读):python3 -m seeu_lib.mac_input geo <应用名> | front
"""
import json
import subprocess
import sys
import time

PARK_XY = (60, 60)            # 点完把光标甩到这里(镜像里停着不动会被当长按,09-08 实测)
TRIGGER_SYNC_MAX_ROUNDS = 8   # 硬上限


# ---------------------------------------------------------------- 窗口

# 应用自己藏着、但系统窗口列表里照样有的大窗:永远不当主窗口(属性跟真窗口一样,只能按标题认)。
HIDDEN_WINDOWS = {"Welcome to iPhone Mirroring"}


def win_geo(owner, min_w=200, min_h=400, all_spaces=False):
    """Quartz 找 owner 的主窗口(在屏上、够大的里面面积最大的)。返回 dict(x,y,w,h,id) 单位点,找不到 None。
    用 Quartz 不用 System Events:能拿到窗口号,截图才能按窗口截(抗遮挡)。min_w/min_h 跳过提示框/阴影小窗。
    all_spaces=True(用户切走桌面后窗口"找不到"→ 激活重试 → 会把用户拽回那个桌面,所以要能跨桌面找):
    不在当前桌面的窗口也找(在当前桌面的优先,其次窗口标题 = 应用名的,镜像有个隐藏的「Welcome」大窗),
    结果多一个 onscreen 字段。不传就跟以前一模一样(只找当前桌面,没有就 None)。"""
    import Quartz
    opt = Quartz.kCGWindowListOptionAll if all_spaces else Quartz.kCGWindowListOptionOnScreenOnly
    wins = Quartz.CGWindowListCopyWindowInfo(opt, Quartz.kCGNullWindowID) or []
    cand = []
    for w in wins:
        if w.get("kCGWindowOwnerName") != owner:
            continue
        if (w.get("kCGWindowName") or "") in HIDDEN_WINDOWS:   # 10-15:隐藏大窗,截到是纯白
            continue
        if all_spaces and w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        wd, ht = b.get("Width", 0), b.get("Height", 0)
        if wd < min_w or ht < min_h:
            continue
        d = dict(x=int(b["X"]), y=int(b["Y"]), w=int(wd), h=int(ht), id=int(w["kCGWindowNumber"]))
        if all_spaces:
            d["onscreen"] = bool(w.get("kCGWindowIsOnscreen"))
            d["_named"] = (w.get("kCGWindowName") or "") == owner
        cand.append(d)
    if not cand:
        return None
    if all_spaces:
        # 🔴 标题 = 应用名的排最前,再看在不在当前桌面。镜像切走桌面后,隐藏的「Welcome」大窗有时报"在当前桌面",
        # 原来"在屏优先"就选了它 → 截到一张纯白大图。
        cand.sort(key=lambda d: (d["_named"], d["onscreen"], d["w"] * d["h"]), reverse=True)
        cand[0].pop("_named")
        return cand[0]
    cand.sort(key=lambda d: d["w"] * d["h"], reverse=True)
    return cand[0]


def frontmost_name():
    """当前前台应用名。🔴 NSWorkspace 在没有事件循环的进程里会一直返回第一次查到的值(10-01 实测),
    先跑 20ms 事件循环收通知再查(跟 input_guard.frontmost_app 同一招)。查不到退回 System Events。"""
    try:
        from AppKit import NSWorkspace, NSRunLoop, NSDate
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
        a = NSWorkspace.sharedWorkspace().frontmostApplication()
        if a is not None:
            return a.localizedName()
    except Exception:
        pass
    return frontmost_name_osa()


def frontmost_name_osa():
    """走 System Events 查前台应用名(慢,约 0.1~0.3s,但不受上面的缓存问题影响)。"""
    return subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True).stdout.strip()


def activate(owner, wait_front_s=0):
    """把 owner 提到最前(别的窗口盖着时,合成点击会静默打到上层窗口)。已经是前台就直接返回,免得窗口一闪一闪。
    wait_front_s>0:激活后每 0.2 秒查一次,直到前台真是 owner(最多等这么久),返回 True/False;
    (真机实测:用户点过别的窗口后只发 activate 不核实,第一下点击只把窗口叫到前台,没传进手机)。"""
    if frontmost_name() == owner:
        return True
    subprocess.run(["osascript", "-e", f'tell application "{owner}" to activate'], capture_output=True)
    time.sleep(0.35)                 # 原 random.uniform(0.25, 0.45),10-31 SeeU 换固定值(不加随机,取中间值)
    if not wait_front_s:
        return None
    t0 = time.time()
    while time.time() - t0 < wait_front_s:
        if frontmost_name() == owner:
            time.sleep(0.2)          # 刚切到前台,再稳一下再发事件
            return True
        time.sleep(0.2)
    return frontmost_name() == owner


def key_cmd(owner, key):
    """先激活 owner,再按 ⌘+key(走 System Events keystroke)。"""
    activate(owner)
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to keystroke "{key}" using command down'],
                   capture_output=True)


def trigger_paste_sync(owner, away="Finder"):
    """"失焦→重新激活 owner"连续成功两次,让 Mac→手机/模拟器的剪贴板同步真正发生。返回 True/False,有硬上限。
    🔴 同步是靠焦点切换事件触发的,不是靠等时间(把 sleep 拉到 6 秒也没用);一次往往读到上一份剪贴板,
    要连续两次成功的切换才稳(iPhone 镜像和 BlueStacks 上都实测过)。away:临时切去的应用。"""
    ok_rounds = 0
    for i in range(TRIGGER_SYNC_MAX_ROUNDS):
        slow = i >= 4   # 前几轮抢输就放宽等待,不是无限加长
        subprocess.run(["osascript", "-e", f'tell application "{away}" to activate'], capture_output=True)
        time.sleep(1.5 if slow else 1.0)
        subprocess.run(["osascript", "-e", f'tell application "{owner}" to activate'], capture_output=True)
        time.sleep(2.7 if slow else 1.8)
        if frontmost_name_osa() == owner:
            ok_rounds += 1
            if ok_rounds >= 2:
                return True
        else:
            ok_rounds = 0
            time.sleep(1.0)
    return False


# ---------------------------------------------------------------- 坐标

def px_to_pt(px, py, g, scale):
    """截图像素 → 桌面点。g = win_geo() 的结果,scale = 截图像素宽 / 窗口点宽。"""
    return g["x"] + px / scale, g["y"] + py / scale


# ---------------------------------------------------------------- 合成鼠标事件(纯 Quartz)
# iPhone 镜像只吃 Quartz 合成的 CGEvent(09-08):cliclick 只收整数坐标,按住时发的是 mouseMoved,拖动/手势都失败。

def post(etype, x, y):
    import Quartz
    Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                       Quartz.CGEventCreateMouseEvent(None, etype, (float(x), float(y)), Quartz.kCGMouseButtonLeft))


def park(xy=PARK_XY):
    """把光标甩到 xy(默认桌面左上)。镜像里停着不动会被当长按,每次操作完都要 park。"""
    import Quartz
    post(Quartz.kCGEventMouseMoved, *xy)


def qtap(x, y, settle=0.12, hold=0.05):
    """桌面点 (x,y) 点一下再 park。瞬时点击镜像会吞,要 down → 停 ~50ms → up。"""
    import Quartz
    post(Quartz.kCGEventMouseMoved, x, y)
    time.sleep(settle)
    post(Quartz.kCGEventLeftMouseDown, x, y)
    time.sleep(hold)
    post(Quartz.kCGEventLeftMouseUp, x, y)
    park()


def qdrag(pts_pt, hold_ms=0, step_ms=280):
    """沿路径发真正的 leftMouseDragged(桌面点)。hold_ms=0 → 快速划(翻页/上划);
    >0 → 首点先长按再拖(手势解锁、拖图标)。首点按下 →(可选长按)→ 逐点拖过 → 末点抬起 → park。"""
    import Quartz
    x0, y0 = pts_pt[0]
    post(Quartz.kCGEventMouseMoved, x0, y0)
    time.sleep(0.2)
    post(Quartz.kCGEventLeftMouseDown, x0, y0)
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
        for _ in range(3):
            post(Quartz.kCGEventLeftMouseDragged, x0, y0)
            time.sleep(0.05)
    cx, cy = x0, y0
    for (nx, ny) in pts_pt[1:]:
        dist = max(abs(nx - cx), abs(ny - cy), 1)
        frames = max(6, int(dist / 12))
        for i in range(1, frames + 1):
            t = i / frames
            post(Quartz.kCGEventLeftMouseDragged, cx + (nx - cx) * t, cy + (ny - cy) * t)
            time.sleep((step_ms / 1000.0) / frames)
        if hold_ms:
            for _ in range(2):
                post(Quartz.kCGEventLeftMouseDragged, nx, ny)
                time.sleep(0.06)
        cx, cy = nx, ny
    time.sleep(0.08)
    post(Quartz.kCGEventLeftMouseUp, cx, cy)
    park()


def post_scroll(dy_pt, dx_pt=0):
    """在光标当前位置发一次像素单位的滚轮事件。"""
    import Quartz
    ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2, int(dy_pt), int(dx_pt))
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "geo":
        g = win_geo(argv[1])
        print(json.dumps(g, ensure_ascii=False))
        return 0 if g else 1
    if argv == ["front"]:
        print(frontmost_name())
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
