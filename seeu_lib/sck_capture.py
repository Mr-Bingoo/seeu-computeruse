#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
sck_capture.py —— 用 ScreenCaptureKit 画面流截一个窗口(不走 screencapture)。

为什么(真机实验):对 iPhone 镜像窗口用
`screencapture` 截图,iOS 上有的 App 会当成"用户截屏"→ 小程序页面弹分享弹窗;
改用 ScreenCaptureKit 画面流取帧(Codex/Gemini 的做法),同样的页面 0 次弹窗。

两种模式:
  - 常驻(默认):`serve` 进程一直开着流,截图请求直接取最新帧;空闲 IDLE_EXIT_S 秒才关流退出
    (仿 Codex:菜单栏紫色"窗口共享"图标不会每截一张就闪一次——用户 2026-09-26 反馈闪得眼睛疼)。
  - 一次性:常驻进程起不来时退路,"开流→取一帧→关流"。

依赖:系统 Python + `pyobjc-framework-ScreenCaptureKit`(会带上 CoreMedia 绑定);屏幕录制权限。
适用场景:截 Mac 上的**窗口**(如 iPhone 镜像)。有 ADB 的安卓设备/模拟器别用这个,直接 `adb exec-out screencap`。
通用,不含任何镜像/具体 App 的逻辑。

用法:
  capture_window(window_id, png_path) -> bool   先找常驻进程(没有就拉起),不行再一次性;失败返回 False 不抛
  last_error / last_via                          最近一次的失败原因 / 走的哪条路(调用方打日志用,见下)
  失败和"重试才成功"都会记一行到数据目录(默认 ~/.seeu)的 sck_capture.log(带原因),以后查偶发失败看这里。
  命令行:sck_capture.py <窗口id> <png路径>     截一张
          sck_capture.py serve                  常驻进程(一般不用手动起,capture_window 会自动拉)
          sck_capture.py quit                   让常驻进程立刻关流退出
"""
import os
import socket
import subprocess
import sys
import threading
import time

PORT = 47832
IDLE_EXIT_S = 180      # 常驻:多久没有截图请求就关流退出(09-26 用户定先试 3 分钟)
SETTLE_S = 0.12        # 常驻:取帧前再等一下,让刚发生的画面变化送到
WAIT_FRAMES = 2        # 一次性/新开流:等到第几帧再取(第一帧偶尔是空白/旧画面)
FRAME_TIMEOUT_S = 3.0  # 硬上限:这么久还没拿到帧就放弃
API_TIMEOUT_S = 5.0    # 硬上限:系统回调(拿窗口列表/开流/停流)
CLIENT_TIMEOUT_S = 6.0 # 硬上限:客户端等常驻进程回复
SPAWN_WAIT_S = 4.0     # 硬上限:拉起常驻进程后等它就绪
RETRY_GAP_S = 0.2      # 常驻进程回 err 后隔多久再要一次
try:
    from seeu_lib import home as _home
except ImportError:                    # 长进程里老版 seeu_lib 没有 home():照旧 ~/.seeu
    _home = lambda *p: os.path.join(os.environ.get("SEEU_HOME") or os.path.expanduser("~/.seeu"), *p)
LOG_FILE = _home("sck_capture.log")

# 最近一次 capture_window 的结果,调用方用 getattr(sck_capture, "last_error", None) 读,老版本没有也不报错:
last_error = None      # 成功且没重试 = None;否则是原因,如 "serve:err write; serve:ok"(重试后成功)
last_via = None        # "serve" 常驻进程 / "once" 一次性 / None 都失败
_open_err = None       # _open_stream 最近一次返回 None 的原因(给 serve/一次性记日志)

_Output = None


def _pump(sec):
    from Foundation import NSRunLoop, NSDate
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(sec))


def _wait(ev, timeout):
    t0 = time.time()
    while not ev.is_set():
        if time.time() - t0 > timeout:
            return False
        _pump(0.02)
    return True


def _output_class():
    global _Output
    if _Output is None:
        import objc
        import CoreMedia
        import Quartz
        from Foundation import NSObject

        class SCKFrameOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
            def init(self):
                self = objc.super(SCKFrameOutput, self).init()
                self.n = 0
                self.img = None
                return self

            def stream_didOutputSampleBuffer_ofType_(self, stream, sb, typ):
                if typ != 0:          # 0 = 画面帧
                    return
                pb = CoreMedia.CMSampleBufferGetImageBuffer(sb)
                if pb is None:        # 画面没变化时系统会送"空帧",没有图像
                    return
                self.img = Quartz.CIImage.imageWithCVImageBuffer_(pb)
                self.n += 1
        _Output = SCKFrameOutput
    return _Output


def _open_stream(window_id, fps=30, max_w=None, background=True, out_cls=None):
    """开一路窗口画面流,返回 (stream, output, (宽px,高px));失败返回 None。
    10-15 加参数(老调用不变):fps 帧率上限;max_w 画面最宽多少像素(按比例缩小,省 CPU);
    background=False 给要开自己窗口的进程用(如 watch_window),不改它的应用类型;out_cls 换自己的取帧类。"""
    import CoreMedia
    import ScreenCaptureKit as SCK
    from AppKit import NSApplication
    from Foundation import NSBundle
    # 独立进程里没碰过窗口服务时,ScreenCaptureKit 会断言崩溃(CGS_REQUIRE_INIT),先建立连接
    # 同时设成"禁止型"App:不在 Dock 出图标、不跳动、不抢焦点(用户 09-26 反馈 Dock 上 Python 火箭一直跳)
    # 🔴 10-14:光靠 setActivationPolicy 太晚,sharedApplication 一调就先登记成前台,Dock 闪 ~14ms;
    #    先在 Info 里标 LSBackgroundOnly,出生就是后台(lsappinfo listen 实测不再有 Foreground)
    if background:
        NSBundle.mainBundle().infoDictionary()["LSBackgroundOnly"] = "1"
        NSApplication.sharedApplication().setActivationPolicy_(2)   # NSApplicationActivationPolicyProhibited
    done, box = threading.Event(), {}

    def got(content, err):
        box["c"], box["e"] = content, err
        done.set()
    SCK.SCShareableContent.getShareableContentWithCompletionHandler_(got)
    global _open_err
    _open_err = None
    if not _wait(done, API_TIMEOUT_S) or box.get("e") is not None:
        _open_err = "窗口列表超时" if not done.is_set() else f"窗口列表出错 {box.get('e')}"
        return None
    win = next((w for w in box["c"].windows() if w.windowID() == int(window_id)), None)
    if win is None:
        _open_err = f"找不到窗口 {window_id}"
        return None
    flt = SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(win)
    rect, scale = flt.contentRect(), flt.pointPixelScale()
    size = (int(round(rect.size.width * scale)), int(round(rect.size.height * scale)))
    if max_w and size[0] > max_w:
        size = (int(max_w), int(round(size[1] * max_w / size[0])))
    cfg = SCK.SCStreamConfiguration.alloc().init()
    cfg.setWidth_(size[0])
    cfg.setHeight_(size[1])
    cfg.setShowsCursor_(False)
    cfg.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, int(fps)))
    cfg.setPixelFormat_(1111970369)   # 'BGRA'
    stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(flt, cfg, None)
    out = (out_cls or _output_class()).alloc().init()
    ok, _err = stream.addStreamOutput_type_sampleHandlerQueue_error_(out, 0, None, None)
    if not ok:
        _open_err = "addStreamOutput 失败"
        return None
    started, sbox = threading.Event(), {}

    def on_start(err):
        sbox["e"] = err
        started.set()
    stream.startCaptureWithCompletionHandler_(on_start)
    if not _wait(started, API_TIMEOUT_S) or sbox.get("e") is not None:
        _open_err = "开流超时" if not started.is_set() else f"开流出错 {sbox.get('e')}"
        return None
    t0 = time.time()
    while out.n < WAIT_FRAMES and time.time() - t0 < FRAME_TIMEOUT_S:
        _pump(0.02)
    return stream, out, size


def _close_stream(stream):
    stopped = threading.Event()
    try:
        stream.stopCaptureWithCompletionHandler_(lambda e: stopped.set())
        _wait(stopped, API_TIMEOUT_S)
    except Exception:
        pass


def _write_png(img, png_path):
    import Quartz
    from Foundation import NSURL
    if img is None:
        return False
    ctx = Quartz.CIContext.contextWithOptions_(None)
    res = ctx.writePNGRepresentationOfImage_toURL_format_colorSpace_options_error_(
        img, NSURL.fileURLWithPath_(png_path), Quartz.kCIFormatBGRA8,
        Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB), None, None)
    return bool(res[0] if isinstance(res, tuple) else res)


def _log(line):
    """失败/重试记一行;日志超过 200KB 轮换一份,写不了就算了(不能因为记日志让截图失败)。"""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            os.replace(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')} [{os.getpid()}] {line}\n")
    except Exception:
        pass


def _window_px(window_id):
    """窗口当前像素尺寸(点 × 缩放),用来发现窗口被缩放后要重开流。"""
    import Quartz
    info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow,
                                             int(window_id)) or []
    if not info:
        return None
    b = info[0].get("kCGWindowBounds") or {}
    # 10-28:窗口点尺寸不变、但显示器换了(真屏 2x ↔ 关屏后的虚拟屏 1x)时也要重开,
    # 否则流一直按旧缩放出图(显示器开回来截图还是 1x)。把每块屏的像素模式一起比。
    disp = []
    try:
        err, ids, n = Quartz.CGGetActiveDisplayList(16, None, None)
        for d in (ids or [])[:n]:
            m = Quartz.CGDisplayCopyDisplayMode(d)
            disp.append((d, Quartz.CGDisplayModeGetPixelWidth(m) if m else None))
    except Exception:
        pass
    return (b.get("Width"), b.get("Height"), tuple(disp))


# ---------------------------------------------------------------- 一次性
def _once(window_id, png_path):
    """一次性取帧,返回 (成功, 失败原因)。"""
    stream = None
    try:
        r = _open_stream(window_id)
        if r is None:
            return False, f"开流失败({_open_err})"
        stream, out, _size = r
        if out.img is None:
            return False, "没等到帧"
        return (True, None) if _write_png(out.img, png_path) else (False, "写图失败")
    except Exception as e:
        if os.environ.get("SCK_DEBUG"):
            import traceback
            traceback.print_exc()
        return False, f"异常 {type(e).__name__}: {e}"
    finally:
        if stream is not None:
            _close_stream(stream)


def capture_once(window_id, png_path):
    return _once(window_id, png_path)[0]


# ---------------------------------------------------------------- 常驻
def serve():
    import select
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(4)
    srv.setblocking(False)
    cur = {"wid": None, "pt": None, "stream": None, "out": None}
    last = time.time()

    def ensure(wid):
        pt = _window_px(wid)
        if cur["stream"] is not None and cur["wid"] == wid and cur["pt"] == pt:
            return True
        if cur["stream"] is not None:
            _close_stream(cur["stream"])
            cur["stream"] = None
        r = _open_stream(wid)
        if r is None:
            cur.update(wid=None, pt=None, out=None)
            return False
        cur.update(wid=wid, pt=pt, stream=r[0], out=r[1])
        return True

    try:
        while time.time() - last < IDLE_EXIT_S:
            _pump(0.02)
            rd, _, _ = select.select([srv], [], [], 0.03)
            if not rd:
                continue
            conn, _addr = srv.accept()
            conn.settimeout(2)
            try:
                req = conn.recv(1024).decode().strip().split(" ", 2)
                if req[0] == "quit":
                    conn.sendall(b"ok\n")
                    break
                why = "坏请求"
                if len(req) == 3 and req[0] == "grab":
                    last = time.time()
                    if not ensure(int(req[1])):
                        why = f"开流失败({_open_err})"
                    else:
                        _pump(SETTLE_S)
                        if cur["out"].img is None:
                            why = "没等到帧"
                        elif _write_png(cur["out"].img, req[2]):
                            why = None
                        else:
                            why = "写图失败"
                        if why:
                            # 流可能已经坏了(系统停流等):关掉,下一次请求重开
                            _close_stream(cur["stream"])
                            cur.update(wid=None, pt=None, stream=None, out=None)
                # 10-20:err 后面带原因(老客户端只比 == "ok",不受影响)
                conn.sendall(b"ok\n" if why is None else f"err {why}\n".encode())
                if why:
                    _log(f"serve 回 err:{why}")
            except Exception as e:
                _log(f"serve 处理请求异常 {type(e).__name__}: {e}")
                try:
                    conn.sendall(f"err 异常 {type(e).__name__}\n".encode())
                except Exception:
                    pass
            finally:
                conn.close()
    finally:
        if cur["stream"] is not None:
            _close_stream(cur["stream"])
        srv.close()


def _ask(msg):
    s = socket.create_connection(("127.0.0.1", PORT), timeout=0.5)
    try:
        s.settimeout(CLIENT_TIMEOUT_S)
        s.sendall((msg + "\n").encode())
        return s.recv(512).decode(errors="replace").strip()
    finally:
        s.close()


def _grab_serve(window_id, png_path):
    """找常驻进程要一张(没有就拉起),返回 (成功, 失败原因)。"""
    msg = f"grab {int(window_id)} {png_path}"
    try:
        r = _ask(msg)
    except ConnectionRefusedError:
        # 没有常驻进程(或刚空闲退出)→ 拉起(独立会话,调用方退出也不影响),等它就绪
        try:
            subprocess.Popen(["/usr/bin/python3", os.path.abspath(__file__), "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except Exception as e:
            return False, f"拉起常驻进程失败 {type(e).__name__}"
        t0, r = time.time(), None
        while r is None and time.time() - t0 < SPAWN_WAIT_S:
            time.sleep(0.1)
            try:
                r = _ask(msg)
            except ConnectionRefusedError:
                continue
            except Exception as e:
                return False, f"新常驻进程没回 {type(e).__name__}"
        if r is None:
            return False, "常驻进程拉起超时"
    except Exception as e:
        return False, f"常驻进程没回 {type(e).__name__}"
    if r == "ok":
        return True, None
    return False, r or "空回复"


def capture_window(window_id, png_path):
    """常驻进程取帧;回 err 隔 RETRY_GAP_S 再要一次(常驻进程这时已把坏流关掉重开),还不行走一次性。
    以前回一次 err 就直接 False,调用方会退回 screencapture 触发 App 的分享弹窗。"""
    global last_error, last_via
    png_path = os.path.abspath(png_path)
    tried = []
    for attempt in range(2):
        if attempt:
            time.sleep(RETRY_GAP_S)
        ok, why = _grab_serve(window_id, png_path)
        if ok:
            last_via = "serve"
            last_error = "; ".join(tried + ["serve:ok"]) if tried else None
            if tried:
                _log(f"窗口 {window_id} 重试后成功:{last_error}")
            return True
        tried.append(f"serve:{why}")
    ok, why = _once(window_id, png_path)
    tried.append("once:ok" if ok else f"once:{why}")
    last_via = "once" if ok else None
    last_error = "; ".join(tried)
    _log(f"窗口 {window_id} {'退到一次性才成功' if ok else '全部失败'}:{last_error}")
    return ok


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if a == ["serve"]:
        serve()
    elif a == ["quit"]:
        try:
            print(_ask("quit"))
        except OSError:
            print("常驻进程本来就没在跑")
    elif len(a) == 2:
        t = time.time()
        ok = capture_window(int(a[0]), a[1])
        print(f"{'ok' if ok else 'FAILED'} {time.time() - t:.2f}s" + (f" ({last_error})" if last_error else ""))
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
