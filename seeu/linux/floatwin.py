# -*- coding: utf-8 -*-
"""SeeU Linux 版悬浮标(11-18 SeeU C-3.0):胶囊 ↔ 卡片 ↔ 多任务岛、按钮栏(灯光 / I See / 原因 / 看画面 / 收起)、能点能拖、
看画面拉边缩放、借鼠标变橙、屏幕四周光圈 —— 样子和规则跟 Mac / Windows 同一套。

分工(Wayland 下普通程序不能自己摆一个置顶、不抢前台的窗口,只能画在 GNOME Shell 里):
  - 这个显示进程(python3 -m seeu.linux.floatwin serve)照 Windows 版 win/floatwin.py 的 serve 跑同一套状态:
    收 SeeU 各处发来的消息(同一个 UDP 端口、同一套消息)、每帧用 **Windows 版的纯计算 scene / island** 算出画什么;
  - 画交给 GNOME 小插件(ext/seeu@seeu-computeruse/float.js):每帧一条 Float(json);小插件把鼠标移入 / 按下 / 拖 / 松开用 FloatEvent 信号报回来。
  所以改样子、改规则改 Windows 那份的纯计算,三边一起变;这里只放 Linux 自己的摆放、量字、事件。
看画面:小插件放一份被操作窗口的实时影子(不截图);一秒刷新跟着屏幕走,不用后台截图线程。
I See 按钮:🔴 只认用户亲手的真鼠标(小插件看按下那一下来自 /dev/input 下的硬件;SeeU 借鼠标走系统远程操作 = 虚拟设备,不算),
  而且这几秒浮标是「穿透」的(借鼠标时根本点不到浮标)。关谁都能关。

别的代码这样用(显示进程没起会自己拉起):
  from seeu.linux import floatwin as fw
  fw.browser("gnome-text-editor", "打字", note="写第一行", wid=123)
  fw.stuck(app, step, why, todo) / fw.borrow(app, "mouse") / fw.queue(...) / fw.tint("#RRGGBB") / fw.mark(fx, fy, wid)
命令行:python3 -m seeu.linux.floatwin serve | demo [秒] | expand | collapse | hide | quit
"""
import json
import math
import os
import socket
import subprocess
import sys
import time

if __name__ == "__main__":
    sys.modules.setdefault("seeu.linux.floatwin", sys.modules[__name__])   # 同 Windows:-m 拉起时别处再 import 是同一份

from seeu.win import floatwin as F   # noqa: E402   纯计算 + 消息格式(不依赖 Windows,任何平台都能导入)

PORT = F.PORT
FONT = "Noto Sans CJK SC"          # 跟小插件 float.js 的 FONT 一致(量字宽和画字要同一个字体)
SERVING = False
HAND_T = 0.0                        # 最近一次认出「手按」的时间(isee.on(by="overlay") 用)
send = F.send
who_name = F.who_name


def _off():
    return os.environ.get("SEEU_NO_WATCH") == "1" or not sys.platform.startswith("linux")


def _running():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


def ensure_serve():
    """显示进程没起就拉起(跟调用方脱钩);SEEU_NO_WATCH=1 时不起(测试用)。小插件不在(没装 / 锁屏)也照样起,它会等。"""
    if _off() or _running():
        return
    env = dict(os.environ)
    lib = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
    try:
        subprocess.Popen([sys.executable, "-m", "seeu.linux.floatwin", "serve"], env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except OSError:
        return
    for _ in range(40):          # 最多等 4 秒
        if _running():
            return
        time.sleep(0.1)


def browser(app, step="", who=None, note="", web=False, wid=0):
    if _off():
        return
    ensure_serve()
    send("browser", app, step, who_name(who), note or "", bool(web), int(wid or 0))


def stuck(app, step, why, todo, who=None):
    if _off():
        return
    ensure_serve()
    send("stuck", app, step, why, todo, who_name(who))


def borrow(app="", kind="mouse"):
    if _off():
        return
    ensure_serve()
    send("borrow", app or "", kind)


def queue(app, on=True, pos=1, holder="", who=None, color=None):
    if _off():
        return
    if on:
        ensure_serve()
    send("queue", str(app or ""), 1 if on else 0, int(pos or 1), str(holder or ""), who_name(who), str(color or ""))


def tint(color, who=None):
    w = who_name(who)
    if not w or not color or _off():
        return
    send("tint", w, str(color))


def mark(fx, fy, wid=0):
    if not _off():
        send("mark", float(fx), float(fy), int(wid or 0))


# ───────── 信号是谁发的(11-23 C-3.9 整体复查)─────────
# 「手按」(real=true)是小插件用 FloatEvent 信号报上来的。小插件不在时(锁屏、被停用)org.seeu.SeeU 这个名字谁都能占,
# 占了发一条假的 real=true 就能开 I See。所以每条信号都核对发送方是不是 gnome-shell,两条路过一条就认:
#   ① 问总线它的进程号,那个进程的程序文件名字是 gnome-shell、归 root、别人改不了(普通程序造不出这样的文件);
#   ② 程序文件读不到时(有的发行版给 gnome-shell 加了特权,/proc/<pid>/exe 不让同账号读):它得同时是总线上
#      org.gnome.Shell 这个名字的主人(gnome-shell 整个会话都占着,锁屏时也在),而且进程名是 gnome-shell。
# 都核不了一律当「不是手按」。
_SHELL_NAMES = ("gnome-shell", ".gnome-shell-wrapped", "gnome-shell-wayland")
SHELL_BUS_NAME = "org.gnome.Shell"
_sender_ok = {}                     # 总线上的唯一名(:1.23,用过不会再发给别人)→ (是不是 gnome-shell, 查的时间)
SENDER_RECHECK_S = 5.0              # 判成「不是」的隔这么久重查一次;判成「是」的一直算数


def _exe_is_shell(link, uid, mode):
    """link = /proc/<pid>/exe 指向哪;uid / mode = 那个文件的属主和权限。"""
    name = os.path.basename(str(link or "").replace(" (deleted)", ""))       # 系统更新换掉文件后会带 (deleted)
    return name in _SHELL_NAMES and uid == 0 and not (mode & 0o022)


def _pid_is_shell(pid):
    """True / False = 程序文件读到了,是 / 不是;None = 不让读(走第 ② 条路)。"""
    try:
        st = os.stat(f"/proc/{int(pid)}/exe")
        return _exe_is_shell(os.readlink(f"/proc/{int(pid)}/exe"), st.st_uid, st.st_mode)
    except PermissionError:
        return None
    except (OSError, ValueError, TypeError):
        return False


def _comm_is_shell(pid):
    try:
        with open(f"/proc/{int(pid)}/comm", encoding="utf-8") as f:
            return f.read().strip() == "gnome-shell"
    except (OSError, ValueError, TypeError):
        return False


def sender_is_shell(sender, pid_of, owner_of=None, now=None, exe_check=None, comm_check=None):
    """发信号的是不是 gnome-shell。sender = 总线唯一名;pid_of(sender) → 进程号;owner_of(名字) → 占着它的唯一名
    (问不到都可以抛错)。exe_check / comm_check 测试时换替身。"""
    now = time.time() if now is None else now
    if not sender or not str(sender).startswith(":"):
        return False
    hit = _sender_ok.get(sender)
    if hit and (hit[0] or now - hit[1] < SENDER_RECHECK_S):
        return hit[0]
    try:
        pid = int(pid_of(sender))
        ok = (exe_check or _pid_is_shell)(pid) if pid > 1 else False
        if ok is None:
            ok = bool(owner_of) and owner_of(SHELL_BUS_NAME) == sender and bool((comm_check or _comm_is_shell)(pid))
    except Exception:   # noqa: BLE001
        ok = False
    ok = bool(ok)
    if len(_sender_ok) > 200:
        _sender_ok.clear()
    _sender_ok[sender] = (ok, now)
    return ok


# ───────── 显示进程 ─────────
def _hex(c):
    return "#%02X%02X%02X" % tuple(int(v) for v in c[:3])


def _r(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, (list, tuple)):
        return [_r(x) for x in v]
    return v


def serve():
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gio, GLib, Pango, PangoCairo
    from seeu.linux import shell

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", PORT))
        sock.setblocking(False)
    except OSError:
        return                                   # 已经有一个在跑
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)

    # 量字宽:跟小插件画字同一个字体、同一种算法(Pango)
    fm = PangoCairo.FontMap.get_default()
    pctx = fm.create_context()
    fonts, wcache = {}, {}

    def measure(text, size, bold):
        k = (text, size, bold)
        if k in wcache:
            return wcache[k]
        fk = (size, bold)
        if fk not in fonts:
            fd = Pango.FontDescription.from_string(FONT)
            fd.set_absolute_size(size * Pango.SCALE)
            fd.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
            fonts[fk] = fd
        lay = Pango.Layout.new(pctx)
        lay.set_font_description(fonts[fk])
        lay.set_text(str(text), -1)
        w = lay.get_extents()[1].width / Pango.SCALE
        if len(wcache) > 4000:
            wcache.clear()
        wcache[k] = w
        return w

    geo = dict(t=0.0, v=None)

    def floatgeo():
        now = time.time()
        if geo["v"] is None or now - geo["t"] > 2:
            try:
                geo["v"] = json.loads(shell._call("FloatGeo")[0])
            except Exception:   # noqa: BLE001     小插件不在(锁屏 / 老版本):用上次的,没有就猜一个
                geo["v"] = geo["v"] or dict(x=0, y=32, w=1280, h=768, dark=True)
            geo["t"] = now
        return geo["v"]

    def sys_theme():
        return "dark" if floatgeo().get("dark", True) else "light"

    st = dict(info=None, open=False, a_from=0.0, a_t0=-9.0, theme="auto", theme_now=sys_theme(), theme_t=0.0, drag=None, moved=False,
              t0=time.time(), last_msg=0.0, last_draw=0.0, shown=False, close=None, card=None, hover=False, s=1.0,
              borrow=None, borrow_until=0.0, borrow_auto=False, through=False,
              light=F.light_level(), why=not F.live().get("why_off"), light_open=False, light_t0=-9.0, hits=[],
              isee=False, isee_t=0.0, real_down=False, more=False,
              view="screen" if F.live().get("view") == "screen" else "card",
              h_tgt=None, h_from=None, h_t0=-9.0, h_show=None, shim=False, solo=None, multi=False,
              w_tgt=None, w_from=None, w_show=None, rs=None, pic_on=False, view_geo=None,
              inside=False, mp=None, cursor="", sent_hidden=False, wid=0)
    tasks, tint_cache, ost = {}, {}, {}
    glow = dict(until=0.0, color=None, sent=0.0)
    pos = dict(x=0, y=0)
    cap = dict(x=0, y=0, mode=None, shape=None)
    keep_pos = os.environ.get("SEEU_FLOAT_NOPOS") != "1"
    vsize = {k_: v_ for k_, v_ in F.live().items() if k_ in ("view_port_h", "view_land_w")} if keep_pos else {}
    pt = dict(cw=F.CW, ph=F.CH)
    rcache = dict(t=0.0, v=[])
    DEBUG = os.environ.get("SEEU_FLOAT_DEBUG") == "1"
    dbg = dict(t=0.0)

    def work_area():
        g = floatgeo()
        return g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"]

    def place(sc):
        L_, T_, R_, B_ = work_area()
        x_, y_, w_, h_, _r_ = sc["shape"]
        rs = st["rs"]
        if rs:
            left = rs["right"] - w_ if "l" in rs["edge"] else rs["left"]
            top = rs["bottom"] - h_ if "t" in rs["edge"] else rs["top"]
            left, top = max(L_, min(left, R_ - w_)), max(T_, min(top, B_ - h_))
        else:
            mode = cap["mode"] or F.anchor(cap["x"], L_, R_, 1.0)
            left = F.shape_left(cap["x"], w_, mode, L_, R_, 1.0)
            top = max(T_, min(cap["y"], B_ - h_))
        pos["x"], pos["y"] = int(round(left - x_)), int(round(top - y_))
        cap["shape"] = (left, top, w_)

    def win_of(wid):
        now = time.time()
        if now - rcache["t"] > 0.5:
            try:
                rcache["v"] = shell.rects()
            except Exception:   # noqa: BLE001
                rcache["v"] = []
            rcache["t"] = now
        return next((w for w in rcache["v"] if w.get("id") == wid), None)

    def win_aspect(wid):
        """被操作窗口的高宽比;窗口没了 / 最小化了返回 None。小插件的影子已经按外框裁好,box 是整窗。"""
        w = win_of(wid) if wid else None
        if not w or w.get("minimized") or w.get("w", 0) <= 0 or w.get("h", 0) <= 0:
            return None
        return w["h"] / float(w["w"]), (0.0, 0.0, 1.0, 1.0)

    def canvas(h_logical, w_logical=F.CW):
        pt["cw"] = max(w_logical, pt["cw"])
        pt["ph"] = max(int(h_logical), pt["ph"])

    def dbus(method, sig, args):
        try:
            bus.call(shell.NAME, shell.PATH, shell.IFACE, method, GLib.Variant(sig, args), None,
                     Gio.DBusCallFlags.NO_AUTO_START, 1000, None, None, None)
        except Exception:   # noqa: BLE001
            pass

    def paint(sc):
        T = F.THEMES[st["theme_now"]]
        m = dict(show=True, x=pos["x"], y=pos["y"], w=pt["cw"], h=pt["ph"], shape=_r(list(sc["shape"])),
                 prims=_r([list(p) for p in sc["prims"]]), through=st["through"], cursor=st["cursor"],
                 wid=sc.get("wid") or 0, glass=list(T["glass"]), shim_w=F.SHIM_W)
        st["sent_hidden"] = False
        dbus("Float", "(s)", (json.dumps(m, ensure_ascii=False, separators=(",", ":")),))

    def k_now():
        x = (time.time() - st["a_t0"]) / F.ANIM_S
        target = 1.0 if st["open"] else 0.0
        return target if x >= 1 else st["a_from"] + (target - st["a_from"]) * F.ease(x)

    def toggle(to):
        if to != st["open"]:
            st["a_from"], st["open"], st["a_t0"] = k_now(), to, time.time()

    def frame():
        now = time.time()
        if now - st["theme_t"] > 2:
            st["theme_t"], st["theme_now"] = now, (sys_theme() if st["theme"] == "auto" else st["theme"])
        if now - st["isee_t"] > 1.5:
            st["isee_t"], st["isee"] = now, isee_active()
        info = st["info"] or {}
        if st["borrow"]:
            info = dict(info, borrow=st["borrow"])
        lk = min(1.0, (now - st["light_t0"]) / 0.22) if st["light_open"] else 0.0
        ui = dict(light=st["light"], light_k=F.ease(lk) if lk < 1 else 1.0, why=st["why"], isee=st["isee"], more=st["more"],
                  qmore=st.get("qmore"), mouse=st.get("mouse"))
        al = F.alive_tasks(tasks, now)
        if st["solo"] and not any(t_["key"] == st["solo"] for t_ in al):
            st["solo"] = None
        if st["solo"]:
            info = tasks[st["solo"]]
            if st["borrow"]:
                info = dict(info, borrow=st["borrow"])
        st["multi"] = st["solo"] is None and len(al) >= 2
        lk_ = None if st["solo"] else F.lone_stuck(al)
        if lk_ in tasks and tasks[lk_] is not st["info"]:
            st["info"] = tasks[lk_]
            info = dict(st["info"], borrow=st["borrow"]) if st["borrow"] else st["info"]
        wid = 0
        if st["multi"]:
            ost["open"] = st["open"]
            sc = F.island(k_now(), now - st["t0"], st["theme_now"], measure, F.ordered(al, now, ost), now,
                          st["hover"] and not st["borrow"], ui)
            st["h_tgt"] = st["h_from"] = st["w_tgt"] = st["w_from"] = None
            st["pic_on"] = False
            canvas(sc["height"] + 2 * F.M)
        else:
            wid = int(info.get("wid") or 0)
            if wid and not info.get("web"):
                asp = win_aspect(wid)
                if asp is None:
                    ui["pic_ok"] = False
                elif st["view"] == "screen":
                    ui["view"], ui["pic"] = "screen", F.pic_ui(info, now, asp[0], asp[1])
                    a_ = max(0.1, min(4.0, asp[0]))
                    L_, T_, R_, B_ = work_area()
                    st["view_geo"] = (a_, float(R_ - L_), float(B_ - T_))
                    ui["vw"] = st["rs"]["w"] if st["rs"] else F.view_fit_w(F.view_saved_w(vsize, a_), *st["view_geo"])
            ui["shim"] = F.shim_x(now, info.get("last") or 0)
            hk = (now - st["h_t0"]) / F.H_ANIM_S
            if st["h_from"] is not None and hk < 1:
                ui["h_from"], ui["h_k"], ui["w_from"] = st["h_from"], 1 - (1 - hk) ** 3, st["w_from"]
            need = max(ui.get("vw") or 0, st["w_show"] or 0, st["w_from"] or 0, F.CARD_W) + 2 * F.M
            canvas(0, max(F.CW, 4 * math.ceil(need / 4.0)))
            ui["cw"] = pt["cw"]
            sc = F.scene(k_now(), now - st["t0"], st["theme_now"], measure, info, st["hover"] and not st["borrow"], ui)
            if sc["target_h"] != st["h_tgt"] or sc["target_w"] != st["w_tgt"]:
                if (st["h_tgt"] is not None and st["h_show"] and st["open"] and k_now() > 0.99 and st["shown"]
                        and not st["rs"]):
                    st["h_from"], st["w_from"], st["h_t0"] = st["h_show"], st["w_show"], now
                    ui["h_from"], ui["h_k"], ui["w_from"] = st["h_from"], 0.0, st["w_from"]
                    sc = F.scene(k_now(), now - st["t0"], st["theme_now"], measure, info, st["hover"] and not st["borrow"], ui)
                else:
                    st["h_from"] = None
                st["h_tgt"], st["w_tgt"] = sc["target_h"], sc["target_w"]
            st["h_show"], st["w_show"] = sc["card"][3], sc["card"][2]
            st["pic_on"] = any(p_[0] == "img" for p_ in sc["prims"])
            if st["pic_on"]:
                sc["wid"] = wid
            canvas(max(sc["card"][3], sc["target_h"]) + 2 * F.M)
        st["shim"] = any(p_[0] == "shim" for p_ in sc["prims"])
        st["close"], st["card"], st["hits"] = sc["close"], sc["card"], sc["hits"]
        place(sc)
        paint(sc)
        st["last_draw"] = now
        if DEBUG and now - dbg["t"] > 0.2:      # 测试用:把这一帧的位置和按钮写出来(SEEU_FLOAT_DEBUG=1 才写)
            dbg["t"] = now
            try:
                with open(F._home("seeu_float_debug.json"), "w", encoding="utf-8") as f_:
                    json.dump(dict(pos=[pos["x"], pos["y"]], shape=list(sc["shape"]), card=list(sc["card"]), hits=sc["hits"],
                                   open=st["open"], hover=st["hover"], view=st["view"], pic=st["pic_on"], through=st["through"],
                                   multi=st["multi"], isee=st["isee"], light=st["light"], cap=[cap["x"], cap["y"]],
                                   borrow=st["borrow"], t=now), f_, ensure_ascii=False)
            except OSError:
                pass

    def show(on):
        if on != st["shown"]:
            st["shown"] = on
            if on:
                frame()
            else:
                st["cursor"] = ""
                dbus("Float", "(s)", (json.dumps(dict(show=False)),))
                st["sent_hidden"] = True

    def through(on):
        if on != st["through"]:
            st["through"] = on
            if on:
                st["drag"] = st["rs"] = None
                st["inside"], st["hover"], st["mouse"] = False, False, None

    def borrow_end():
        st["borrow"] = None
        through(False)
        if st["borrow_auto"]:
            st["borrow_auto"] = False
            toggle(False)

    def isee_active():
        try:
            from seeu import isee
            return bool(isee.active())
        except Exception:   # noqa: BLE001
            return False

    def isee_click(real):
        """I See 按钮。关:谁点都行。开:🔴 只认用户亲手的真鼠标(real),isee.on(by="overlay") 自己再查一遍本进程刚有手按。"""
        try:
            from seeu import isee
            if isee.active():
                isee.off()
            elif real:
                isee.on(by="overlay")
        except Exception:   # noqa: BLE001
            pass
        st["isee"], st["isee_t"] = isee_active(), time.time()

    def glow_on(mode, secs):
        col_ = F.glow_wanted(st["light"], mode)
        if not col_:
            return
        now = time.time()
        until = now + max(0.2, min(float(secs), 600))
        if col_ != glow["color"] or until > glow["until"] + 0.3 or now - glow["sent"] > 5:
            glow["color"], glow["sent"] = col_, now
            glow["until"] = max(glow["until"], until)
            dbus("Glow", "(sd)", (_hex(col_), float(glow["until"] - now)))

    def glow_off():
        if glow["until"] > time.time():
            dbus("Glow", "(sd)", (_hex(glow["color"] or F.ORANGE), 0.0))
        glow["until"] = 0.0

    def on_hit(name, real=False):
        if real:                                   # 程序发来的不算你碰过(同 Windows)
            F.stuck_touch(st, tasks, time.time())
        if name == "isee":
            isee_click(real)
        elif name == "collapse":
            st["light_open"] = st["more"] = False
            if not st["solo"]:
                F.stuck_ack(st, tasks, time.time())
            st["solo"] = None
            toggle(False)
        elif name == "more":
            st["more"] = not st["more"]
        elif name == "qmore":
            st["qmore"] = not st.get("qmore")
        elif name.startswith("row:"):
            ost.setdefault("pick", {})[name[4:]] = time.time()
        elif name == "light":
            st["light_open"], st["light_t0"] = True, time.time()
        elif name.startswith("light:"):
            st["light"], st["light_open"] = name[6:], False
            F.set_live(light=st["light"])
            if st["light"] == "off":
                glow_off()
        elif name == "why":
            st["why"] = not st["why"]
            F.set_live(why_off=not st["why"])
        elif name == "view" and st["multi"]:
            top = F.ordered(F.alive_tasks(tasks, time.time()), time.time(), ost)
            if top:
                st["solo"], st["more"] = top[0]["key"], False
                if top[0].get("wid") and not top[0].get("web") and st["view"] != "screen":
                    st["view"] = "screen"
                    F.set_live(view="screen")
        elif name == "view":
            st["view"] = "card" if st["view"] == "screen" else "screen"
            F.set_live(view=st["view"])
        frame()

    def task(who, app, now):
        key = F.task_key(who, app)
        t_ = tasks.get(key)
        if t_ is None:
            t_ = tasks[key] = dict(key=key, who=who or "", app=app or "SeeU", step="", steps=[], born=now, last=now,
                                   color=tint_cache.pop(key, None))
        t_["who"], t_["app"], t_["last"] = who or "", app or "SeeU", now
        t_["queued"] = None
        return t_

    def on_msg(m):
        now = time.time()
        if not m:
            return
        if m[0] == "browser" and len(m) >= 3:
            t_ = task(m[3] if len(m) > 3 else "", m[1], now)
            if m[2] and (not t_["steps"] or t_["steps"][0] != m[2]):
                t_["steps"].insert(0, m[2])
                del t_["steps"][4:]
            t_.update(step=m[2], note=m[4] if len(m) > 4 else "", web=bool(m[5]) if len(m) > 5 else False,
                      wid=int(m[6]) if len(m) > 6 and isinstance(m[6], (int, float)) else 0)
            t_.pop("why", None); t_.pop("todo", None)
            st["info"] = t_
            st["last_msg"] = now
            if not st["shown"]:
                st["open"], st["a_from"], st["a_t0"] = False, 0.0, -9.0
            show(True)
            glow_on("bg", 2.5)
        elif m[0] == "stuck" and len(m) >= 5:
            t_ = task(m[5] if len(m) > 5 else "", m[1], now)
            t_.update(step=m[2], why=m[3], todo=m[4], ack=False)
            st["info"] = t_
            st["last_msg"] = now
            st["borrow_auto"] = False
            show(True)
            toggle(True)
        elif m[0] == "borrow":
            app_ = (m[1] if len(m) > 1 else "") or ""
            cand = sorted((x for x in tasks.values() if app_ and x["app"].lower() == app_.lower()), key=lambda x: -x["last"])
            t_ = cand[0] if cand else (st["info"] if st["info"] and st["info"].get("key") in tasks else task("", app_ or "SeeU", now))
            if not st["info"]:
                st["info"] = t_
            if not st["shown"]:
                st["open"], st["a_from"], st["a_t0"] = False, 0.0, -9.0
            st["borrow"] = m[2] if len(m) > 2 and m[2] in F.BORROW_TEXT else "mouse"
            t_["borrow_kind"], t_["borrow_until"], t_["last"] = st["borrow"], now + F.BORROW_HOLD_S, now
            st["borrow_until"] = st["last_msg"] = now
            st["borrow_until"] += F.BORROW_HOLD_S
            show(True)
            through(True)
            glow_on("real", F.BORROW_HOLD_S)
            if not st["open"]:
                st["borrow_auto"] = True
                toggle(True)
        elif m[0] == "queue" and len(m) >= 3:
            who_, app_ = (str(m[5]) if len(m) > 5 else ""), str(m[1] or "")
            key = F.task_key(who_, app_)
            t_ = tasks.get(key)
            if bool(m[2]):
                if t_ is None:
                    t_ = tasks[key] = dict(key=key, who=who_, app=app_ or "SeeU", step="", steps=[], born=now, last=now,
                                           color=tint_cache.pop(key, None))
                t_["queued"] = dict(app=app_, pos=int(m[3]) if len(m) > 3 and isinstance(m[3], (int, float)) else 1,
                                    holder=str(m[4]) if len(m) > 4 else "", t=now)
                t_["last"] = now
                st["last_msg"] = now
            elif t_ is not None:
                t_["queued"] = None
                if not t_.get("step") and not t_.get("steps") and not t_.get("wid") and not t_.get("why"):
                    tasks.pop(key, None)
            if t_ is not None and len(m) > 6 and F.hex_rgb(m[6]):
                t_["color"] = F.hex_rgb(m[6])
        elif m[0] == "tint" and len(m) >= 3:
            key = F.task_key(str(m[1]), "")
            c_ = F.hex_rgb(m[2])
            if c_:
                if key in tasks:
                    tasks[key]["color"] = c_
                else:
                    tint_cache[key] = c_
                    if len(tint_cache) > 32:
                        tint_cache.clear()
        elif m[0] == "mark" and len(m) >= 3:
            wid = int(m[3]) if len(m) > 3 and isinstance(m[3], (int, float)) else 0
            t_ = next((x for x in tasks.values() if wid and x.get("wid") == wid), None) or st["info"]
            if t_:
                F.add_mark(t_, m[1], m[2], now)
        elif m[0] == "view" and len(m) > 1 and m[1] in ("card", "screen"):
            if st["view"] != m[1]:
                on_hit("view")
        elif m[0] == "expand" and st["shown"]:
            toggle(True)
        elif m[0] == "collapse" and st["shown"]:
            F.stuck_ack(st, tasks, now)
            toggle(False)
        elif m[0] == "hide":
            tasks.clear()
            st["info"], st["more"], st["solo"] = None, False, None
            glow_off()
            if st["borrow"]:
                borrow_end()
            show(False)
        elif m[0] == "light" and len(m) > 1 and m[1] in F.LIGHTS:
            on_hit("light:" + m[1])
        elif m[0] == "theme" and len(m) > 1 and m[1] in ("dark", "light", "auto"):
            st["theme"], st["theme_t"] = m[1], 0.0
        elif m[0] == "quit":
            loop.quit()

    # ───── 鼠标(小插件报上来的,屏幕逻辑像素)─────
    def edge_now(x, y):
        if not (st["open"] and st["pic_on"] and not st["multi"] and st["card"] and st["view_geo"] and not st["borrow"] and k_now() > 0.99):
            return ""
        return F.edge_at(x - pos["x"], y - pos["y"], st["card"])

    def hit_at(lx, ly):
        return next((n_ for n_, hx, hy, hw_, hh_ in st["hits"] if hx <= lx <= hx + hw_ and hy <= ly <= hy + hh_), None)

    def on_event(kind, x, y, real):
        global HAND_T
        if st["through"] or not st["shown"]:
            return
        if kind in ("enter", "motion"):
            st["inside"], st["mp"] = True, (x, y)
            if st["rs"]:
                rs = st["rs"]
                a_, ww_, wh_ = st["view_geo"]
                rs["w"] = F.view_fit_w(F.resize_w(rs["edge"], rs["w0"], x - rs["mx"], y - rs["my"], a_), a_, ww_, wh_)
                frame()
                return
            if st["drag"]:
                dx, dy = x - st["drag"][0], y - st["drag"][1]
                if st["moved"] or abs(dx) + abs(dy) > 4:
                    if not st["moved"]:
                        L_, _T, R_, _B = work_area()
                        cap["mode"] = F.anchor(cap["x"], L_, R_, 1.0)
                    st["moved"] = True
                    cap["x"], cap["y"] = st["drag"][2] + dx, st["drag"][3] + dy
                    frame()
                return
            e_ = edge_now(x, y)
            if e_ != st["cursor"]:
                st["cursor"] = e_
                frame()
        elif kind == "leave":
            if not st["drag"] and not st["rs"]:
                st["inside"], st["mp"] = False, None
                if st["cursor"]:
                    st["cursor"] = ""
                    frame()
        elif kind == "press":
            e_ = edge_now(x, y)
            if e_:
                cx, cy, cw_, ch_ = st["card"]
                left, top = pos["x"] + cx, pos["y"] + cy
                st["rs"] = dict(edge=e_, mx=x, my=y, w0=cw_, w=cw_, left=left, top=top, right=left + cw_, bottom=top + ch_)
                st["h_from"] = None
                return
            st["drag"], st["moved"] = (x, y, cap["x"], cap["y"]), False
            st["real_down"] = bool(real)
            if real:
                HAND_T = time.time()
        elif kind == "release":
            if st["rs"]:
                rs = st["rs"]
                if abs(rs["w"] - rs["w0"]) > 0.5:
                    vsize.update(F.view_remember(rs["w"], st["view_geo"][0]))
                    L_, T_, R_, B_ = work_area()
                    if cap["shape"]:
                        cap["x"], cap["y"] = int(round(F.cap_from_shape(cap["shape"][0], cap["shape"][2], L_, R_, 1.0))), int(round(cap["shape"][1]))
                    cap["mode"] = None
                    if keep_pos:
                        F.set_live(cap=[round(cap["x"], 1), round(cap["y"], 1)], **vsize)
                st["rs"] = None
                frame()
                return
            if not st["drag"]:
                return
            moved, d0, st["drag"] = st["moved"], st["drag"], None
            if moved:
                L_, T_, R_, B_ = work_area()
                if cap["shape"]:
                    cap["x"], cap["y"] = int(F.cap_from_shape(cap["shape"][0], cap["shape"][2], L_, R_, 1.0)), int(cap["shape"][1])
                cap["mode"] = None
                if keep_pos:
                    F.set_live(cap=[round(cap["x"], 1), round(cap["y"], 1)])
                frame()
                return
            if not st["open"]:
                toggle(True)
                return
            nm = hit_at(d0[0] - pos["x"], d0[1] - pos["y"])
            if nm:
                # 真点击 = 按下、松开都来自硬件,而且松开时还在同一个按钮上
                on_hit(nm, real=st["real_down"] and bool(real) and hit_at(x - pos["x"], y - pos["y"]) == nm)
            elif st["light_open"]:
                st["light_open"] = False

    def pid_of(sender):
        r = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetConnectionUnixProcessID",
                          GLib.Variant("(s)", (sender,)), None, Gio.DBusCallFlags.NONE, 500, None)
        return int(r.unpack()[0])

    def owner_of(name):
        r = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner",
                          GLib.Variant("(s)", (name,)), None, Gio.DBusCallFlags.NONE, 500, None)
        return str(r.unpack()[0])

    def sig_cb(_conn, _sender, _path, _iface, _name, params):
        try:
            kind, x, y, real = params.unpack()
            # 11-23 C-3.9 整体复查:real 只在发信号的确实是 gnome-shell 时才认(别的程序占了名字发的假信号 → 当不是手按)
            real = bool(real) and sender_is_shell(_sender, pid_of, owner_of)
            on_event(kind, float(x), float(y), real)
        except Exception as ex:   # noqa: BLE001
            oops("event", ex)

    bus.signal_subscribe(shell.NAME, shell.IFACE, "FloatEvent", shell.PATH, None, Gio.DBusSignalFlags.NONE, sig_cb)

    err = {"t0": 0.0, "log": 0.0}

    def oops(where, ex):
        """定时回调 / 事件里出错:记一行日志(最多 10 秒一条,文件超过 200KB 清掉重写),不往外抛。"""
        now = time.time()
        if now - err["log"] < 10:
            return
        err["log"] = now
        try:
            import traceback
            p_ = F._home("seeu_float_err.log")
            mode = "w" if os.path.exists(p_) and os.path.getsize(p_) > 200_000 else "a"
            with open(p_, mode, encoding="utf-8") as f_:
                f_.write(f"{time.strftime('%m-%d %H:%M:%S')} {where}: {ex!r}\n{traceback.format_exc()}\n")
        except Exception:   # noqa: BLE001
            pass

    def tick():
        """11-23 C-3.9 整体复查:原来 tick 里(frame() 等)一抛错,GLib 就把这个定时回调摘掉 → 悬浮标冻在屏幕上、再也不动。
        现在整个包起来:出错记日志、照常返回 True;连着错超过 3 秒就先让小插件把悬浮标藏了(恢复后下一帧自己再画出来)。"""
        try:
            tick_body()
            err["t0"] = 0.0
        except Exception as ex:   # noqa: BLE001
            oops("tick", ex)
            now = time.time()
            err["t0"] = err["t0"] or now
            if now - err["t0"] > 3 and not st.get("sent_hidden"):
                dbus("Float", "(s)", (json.dumps(dict(show=False)),))
                st["sent_hidden"] = True
        return True

    def tick_body():
        for _ in range(20):
            try:
                data = sock.recv(4096)
            except OSError:
                break
            try:
                on_msg(json.loads(data.decode("utf-8")))
            except (ValueError, UnicodeDecodeError, TypeError, IndexError, KeyError):
                pass
        now = time.time()
        if st["borrow"] and now > st["borrow_until"]:
            borrow_end()
        if not st["shown"]:
            return True
        if now - st["last_msg"] > F.hide_after(tasks, now, st["open"]) and not st["drag"] and not st["rs"]:
            tasks.clear()
            st["info"], st["more"], st["solo"] = None, False, None
            show(False)
            return True
        F.drop_old(tasks, now)
        hv, mp_ = False, None
        if st["open"] and st["card"] and st["inside"] and st["mp"] and not st["through"]:
            cx, cy, cw_, ch_ = st["card"]
            lx, ly = st["mp"][0] - pos["x"], st["mp"][1] - pos["y"]
            hv = cx <= lx <= cx + cw_ and cy <= ly <= cy + ch_
            mp_ = (lx, ly) if hv else None
        changed = hv != st["hover"] or mp_ != st.get("mouse")
        st["hover"], st["mouse"] = hv, mp_
        if changed or st["drag"] or st["rs"]:
            F.stuck_touch(st, tasks, now)
        if not hv and st["light_open"]:
            st["light_open"] = False
        if (changed or now - st["a_t0"] < F.ANIM_S + 0.1 or now - st["light_t0"] < 0.3 or now - st["h_t0"] < F.H_ANIM_S + 0.1
                or (st["shim"] and now - st["last_draw"] >= 0.03) or now - st["last_draw"] >= 0.066):
            frame()
        return True

    # 起始位置:右上角(顶栏下面),记住过的用记住的
    L_, T_, R_, B_ = work_area()
    cap["x"], cap["y"] = int(R_ - 40 - F.CAP_W), int(T_ + 48)
    c_ = F.live().get("cap") if keep_pos else None
    if isinstance(c_, list) and len(c_) == 2 and all(isinstance(v_, (int, float)) for v_ in c_):
        cap["x"] = int(max(L_, min(c_[0], R_ - F.CAP_W)))
        cap["y"] = int(max(T_, min(c_[1], B_ - F.CAP_H)))

    global SERVING
    SERVING = True
    loop = GLib.MainLoop()
    GLib.timeout_add(16, tick)
    # 11-23 C-3.9 整体复查:被 kill(SIGTERM)/ 终端关掉(SIGHUP)/ Ctrl+C 时也走下面的 finally,把悬浮标藏了再退
    # (原来直接死,最后一帧留在屏幕上)。被强杀(SIGKILL)拦不了,靠小插件自己「多久没新帧就藏」。
    try:
        import signal
        for sg in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sg, lambda *_a: (loop.quit(), True)[1])
    except Exception:   # noqa: BLE001
        pass
    try:
        loop.run()
    finally:
        try:
            st["shown"] = False
            dbus("Float", "(s)", (json.dumps(dict(show=False)),))       # 不管记的状态是什么都发一次隐藏
            glow_off()
            bus.flush_sync(None)                 # 消息是后台线程发的,等它真发出去再退
        except Exception:   # noqa: BLE001
            pass
        sock.close()


def demo(secs=60):
    steps = ["读网页", "点导出", "等下载", "改文件名"]
    t0, i = time.time(), 0
    while time.time() - t0 < secs:
        if i == 5:
            stuck("gnome-text-editor", "选下拉框", "找不到下拉框", "手动选一下", who="Demo")
        else:
            browser("gnome-text-editor", steps[i % len(steps)], who="Demo")
        i += 1
        time.sleep(4)
    send("hide")


def main(argv=None):
    a = (argv or sys.argv)[1:]
    cmd = a[0] if a else ""
    if cmd == "serve":
        serve()
    elif cmd == "demo":
        demo(int(a[1]) if len(a) > 1 else 60)
    elif cmd in ("expand", "collapse", "hide", "quit"):
        send(cmd)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
