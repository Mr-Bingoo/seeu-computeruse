#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
wait.py —— "等到某个画面状态出现"的通用工具,全部自带硬上限。

截图怎么截由调用方决定:传一个 shoot() 函数进来,每次调用返回一张新截图的路径
(比如 Mac 窗口用 sck_capture 画面流,安卓设备用 adb screencap),本模块只负责反复看、到点报错。
2026-10-01 新建:各项目原来都是手写 `for i in range(N): sleep; shot; ocr; 找字` 的循环。

    from seeu_lib import wait
    r = wait.wait_text(shoot, ["一键收取", "收取"], timeout=8)   # 返回 {hit, png, entries}
    wait.wait_text_gone(shoot, "加载中", timeout=15)
    wait.wait_template(shoot, "tpl/close_x.png", thr=0.85)       # 返回 {hit:(x,y,score), png}
    wait.wait_stable(shoot, timeout=6)                            # 画面不再变化,返回最后一张图
    wait.wait_until(lambda: 某个检查(), timeout=10, what="xx")    # 通用版
    r = wait.act_and_verify(shoot, lambda: 点击(), box=(0,60,w,h))  # 做动作并核实有没有反应
    if r["outcome"] == "ineffective": ...                           # 没反应:重试/换办法/交给 LLM(10-06 加)

上限:timeout 秒和 tries 次,哪个先到就停,抛 WaitTimeout(带最后一张截图路径,方便交给 LLM 看)。
"""
import time

DEFAULT_TIMEOUT = 10.0
DEFAULT_INTERVAL = 0.8


class WaitTimeout(RuntimeError):
    def __init__(self, what, waited, tries, last_png=None):
        super().__init__(f"等「{what}」超时:{waited:.1f}s / {tries} 次" + (f",最后一张图 {last_png}" if last_png else ""))
        self.what = what
        self.waited = waited
        self.tries = tries
        self.last_png = last_png


def wait_until(check, timeout=DEFAULT_TIMEOUT, interval=DEFAULT_INTERVAL, tries=None, what="条件"):
    """反复调 check(),返回它第一次给出的真值。不截图的通用版;要等画面的用下面的专用函数(超时报错会带截图)。"""
    t0 = time.time()
    n = 0
    while True:
        n += 1
        got = check()
        if got:
            return got
        waited = time.time() - t0
        if (tries and n >= tries) or waited + interval > timeout:
            raise WaitTimeout(what, waited, n)
        time.sleep(interval)


def _as_list(needles):
    return [needles] if isinstance(needles, str) else list(needles)


def find_text(entries, needles, exclude=None):
    """OCR 结果里第一条包含任一 needle(且不含 exclude 里任何一个)的条目,没有返回 None。"""
    needles = _as_list(needles)
    excl = _as_list(exclude) if exclude else []
    for e in entries:
        t = e.get("text", "")
        if any(n in t for n in needles) and not any(x in t for x in excl):
            return e
    return None


def _shoot_loop(shoot, judge, timeout, interval, tries, what):
    t0 = time.time()
    n = 0
    png = None
    while True:
        n += 1
        png = shoot()
        got = judge(png)
        if got is not None:
            return got
        waited = time.time() - t0
        if (tries and n >= tries) or waited + interval > timeout:
            raise WaitTimeout(what, waited, n, png)
        time.sleep(interval)


def wait_text(shoot, needles, timeout=DEFAULT_TIMEOUT, interval=DEFAULT_INTERVAL, tries=None,
              exclude=None, box=None):
    """等画面上出现任一 needle。返回 {hit: OCR 条目(含 x/y), png, entries},entries 可直接复用,不用再识别一次。
    box=(x0,y0,x1,y1) 只识别这块区域(坐标仍是整图像素)。"""
    from seeu_lib import ocr

    def judge(png):
        entries = ocr.ocr(png, box)
        hit = find_text(entries, needles, exclude)
        return {"hit": hit, "png": png, "entries": entries} if hit else None

    return _shoot_loop(shoot, judge, timeout, interval, tries, f"出现 {_as_list(needles)}")


def wait_text_gone(shoot, needles, timeout=DEFAULT_TIMEOUT, interval=DEFAULT_INTERVAL, tries=None, box=None):
    """等画面上 needle 全部消失(比如"加载中")。返回 {png, entries}。"""
    from seeu_lib import ocr

    def judge(png):
        entries = ocr.ocr(png, box)
        return None if find_text(entries, needles) else {"png": png, "entries": entries}

    return _shoot_loop(shoot, judge, timeout, interval, tries, f"消失 {_as_list(needles)}")


def wait_template(shoot, tpl_path, thr=0.80, timeout=DEFAULT_TIMEOUT, interval=DEFAULT_INTERVAL, tries=None):
    """等某个图标(模板)出现。返回 {hit: (x, y, score), png}。"""
    import cv2
    from seeu_lib import match

    def judge(png):
        img = cv2.imread(png, cv2.IMREAD_COLOR)
        if img is None:
            return None
        hits = match.find(img, tpl_path, thr)
        return {"hit": hits[0], "png": png} if hits else None

    return _shoot_loop(shoot, judge, timeout, interval, tries, f"图标 {tpl_path}")


def frame_diff(png_a, png_b, size=160):
    """两张图缩成小灰度图后的平均像素差(0~255)。尺寸不同直接当作完全不同。"""
    import cv2
    a = cv2.imread(png_a, cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(png_b, cv2.IMREAD_GRAYSCALE)
    if a is None or b is None or a.shape != b.shape:
        return 255.0
    h, w = a.shape
    s = size / max(h, w)
    dims = (max(1, int(w * s)), max(1, int(h * s)))
    a = cv2.resize(a, dims, interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, dims, interpolation=cv2.INTER_AREA)
    return float(cv2.absdiff(a, b).mean())


def frame_change(png_a, png_b, box=None, size=160, pix_thr=25):
    """两张图里"明显变了"的像素占比(0~1)。比 frame_diff 更适合判小按钮、小弹窗这种局部变化。
    box=(x0,y0,x1,y1) 只比这块(整图像素),用来避开状态栏时钟这类自己会变的地方。尺寸不同当作全变。"""
    import cv2
    a = cv2.imread(png_a, cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(png_b, cv2.IMREAD_GRAYSCALE)
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    if box:
        x0, y0, x1, y1 = (int(v) for v in box)
        a, b = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
        if a.size == 0:
            return 0.0
    h, w = a.shape
    s = min(1.0, size / max(h, w))
    dims = (max(1, int(w * s)), max(1, int(h * s)))
    a = cv2.resize(a, dims, interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, dims, interpolation=cv2.INTER_AREA)
    return float((cv2.absdiff(a, b) > pix_thr).mean())


def act_and_verify(shoot, act, expect=None, box=None, min_change=0.003, timeout=3.0, interval=0.4, tries=None):
    """做一个动作并核实它真的起作用了(借鉴官方 Computer Use 的结果分级;它自己也会"报成功其实没生效")。

    先截一张"动作前",调 act(),再反复截图直到:
      - 给了 expect(png) → 它返回真值算生效(比如"弹窗那几个字消失了");
      - 没给 expect → 画面(或 box 区域)变化占比 ≥ min_change 算生效。
    返回 {outcome: "delivered"|"ineffective", png: 最后一张图, change: 变化占比, result: act() 的返回值}。
    🔴 没生效不抛错,交给调用方决定重试、换办法还是停手交给 LLM;动作本身抛错照常往外抛。
    🔴 shoot() 每次要返回新文件(或覆盖前已读完),"动作前"那张会先复制一份再比。
    提示:手机画面有状态栏时钟,不给 expect 时最好传 box 把它避开;画面一直在动的页面(动画、游动的背景、小游戏)
    不给 expect 会误判"已生效",要给 expect 或用 box 只框按钮附近。"""
    import os
    import shutil
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="verify_")
    try:
        before = os.path.join(tmpdir, "before.png")
        shutil.copyfile(shoot(), before)
        result = act()
        t0 = time.time()
        n = 0
        while True:
            time.sleep(interval)
            n += 1
            png = shoot()
            change = frame_change(before, png, box)
            ok = bool(expect(png)) if expect else change >= min_change
            if ok:
                return {"outcome": "delivered", "png": png, "change": change, "result": result}
            if (tries and n >= tries) or time.time() - t0 + interval > timeout:
                return {"outcome": "ineffective", "png": png, "change": change, "result": result}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def wait_stable(shoot, timeout=DEFAULT_TIMEOUT, interval=0.5, tries=None, thr=2.0, need=2):
    """等画面停止变化:连续 need 次相邻两帧差 < thr 就算稳定(动画放完、页面加载完)。返回最后一张图路径。
    🔴 shoot() 每次要返回**新文件**(不同路径或覆盖前已读完),否则永远和自己比、立刻判稳定。"""
    import os
    import shutil
    import tempfile
    state = {"prev": None, "calm": 0}
    tmpdir = tempfile.mkdtemp(prefix="wait_")

    def judge(png):
        keep = os.path.join(tmpdir, f"f{time.time_ns()}.png")
        shutil.copyfile(png, keep)
        prev, state["prev"] = state["prev"], keep
        if prev is None:
            return None
        d = frame_diff(prev, keep)
        os.remove(prev)
        state["calm"] = state["calm"] + 1 if d < thr else 0
        return png if state["calm"] >= need else None

    try:
        return _shoot_loop(shoot, judge, timeout, interval, tries, "画面稳定")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
