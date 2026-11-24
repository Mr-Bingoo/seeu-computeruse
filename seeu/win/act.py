# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 动作层(跟 Mac 版 seeu/act.py 同样的用法和返回格式)。

    import seeu
    v = seeu.see("Notepad")                  # 截图 + 编号清单(UIA 控件)
    seeu.tap("Notepad", "添加新标签页")       # 按名字 / 编号(上一次 see 的)/ 屏幕点 (x, y)
    seeu.type("Notepad", "你好", enter=True)
    seeu.scroll("Notepad", dy=-600)          # dy 负 = 往下翻
    seeu.press("Notepad", "a", "ctrl")

每个动作返回 dict:outcome = delivered(核实生效)| unverified(做了,没法核实)| ineffective(做了但没变化)
| refused(安全底线 / 设置不让)| failed(出错);route = 最后走的那条路;tried = 依次试过的路和结果;png = 最后一张截图。

退路(前一条没生效自动试下一条):
  点击:后台点击 → 借前台按下(UIA 按按钮会把目标拉到前台,马上还回去,约 0.1~0.2 秒;归「借用鼠标」设置管)
  打字、按键、滚动:后台(往窗口发消息)
坐标一律是屏幕物理像素。真鼠标那一档(SendInput + 让路)第 1 段还没做。
"""
import ctypes
import json
import os
import re
import sys
import tempfile
import time

from seeu.win import inputs, safety, uia, window as W

_last = {}
_TMP = [None]
KEEP_SHOTS = 200
MIN_CHANGE = 0.05       # 整个窗口变了百分之几算「有变化」(探路:几个字只占 0.1%,按键 0.01%,所以还要看读回和点击处附近)
NEAR_CHANGE = 1.0       # 点击处附近 ±60 像素变了百分之几算有变化(光标、高亮这种小变化)
# 画面是视频流、读不到控件的程序(按程序名):靠截图认字出清单。BlueStacks / MuMu / 雷电 / 夜神 模拟器
_LAG = {}               # 窗口号 → (记下的时间, 那时的小截图):做完一步「控件变了、画面没变」,截图暂时不可信(11-15)
LAG_TTL = 60            # 最多记 1 分钟(11-15 复查:原 10 分钟,误挂了卡太久)
LAG_CLEAR = 3.0         # 新截图跟记下那张差多少百分比算「画面跟上了」(转圈、闪烁的光标、按钮高亮不算;11-15 第五轮复查:原 1%,高亮就有 2%)
LAG_WHY = "上一步之后它的控件已经变了、画面还没跟上(程序画得慢,或者机器太忙)"
COVER_WHY = "它整个被别的窗口盖住了,Chrome / Electron 这类程序被盖住时不重画"
DESK_WHY = "它在另一个虚拟桌面上,Chrome / Electron 这类程序在别的桌面上可能不重画"
STALE_PIXEL = ("这个窗口的截图现在不可信:{why}。按截图位置操作会照着旧画面点到别的东西"
               "(11-15 Win10 实测:照旧图点,点中了另一张卡片的「连接」),SeeU 没做。{tip}")
LAG_TIP = "改用 see 列表里控件的编号操作(截图认字得来的编号同样不行);列表里没有的,等几秒再 see 一次,画面跟上了再按位置点"
COVER_TIP = "改用 see 列表里控件的编号操作(截图认字得来的编号同样不行);列表里没有的,请用户把这个窗口露出来一点,再 see"
DESK_TIP = "改用 see 列表里控件的编号操作(截图认字得来的编号同样不行);列表里没有的,请用户切到那个桌面或把窗口挪过来,再 see"
FRAME_NAMES = {"最小化", "最大化", "还原", "关闭", "系统", "Minimize", "Maximize", "Restore", "Close", "System"}
CANVAS_EXES = {"hd-player.exe", "mumuplayer.exe", "nemuplayer.exe", "dnplayer.exe", "nox.exe", "ldplayer.exe"}
# 环境变量 SEEU_SETTINGS_FILE:开发测试时把设置换到别的文件(虚拟机里的代码是共享目录,不设会改到开发机上真的设置;同 isee.SETTINGS)
from seeu.where import settings_file as _sf
_SETTINGS = _sf()   # SEEU_SETTINGS_FILE 优先(在 where 里);11-22 C-3.7:插件版存用户文件夹


# ─────────────────────────────── 小工具 ───────────────────────────────

def _pid_alive(pid):
    """进程还在不在(问不出来当还在,不删它的东西)。🔴 Windows 上不能用 os.kill(pid, 0),那会把对方杀掉;用 sched._alive。"""
    try:
        from seeu import sched as _sc
        return bool(_sc._alive(pid))
    except Exception:   # noqa: BLE001
        return True


def _tmp():
    """截图临时目录。11-23 C-3.9 整体复查(照 Mac act._tmp):目录名带进程号,主人进程还活着的不删
    (原来超一天就删、不看主人:长驻的 MCP 服务一天没截图,目录被别的 SeeU 进程删掉,此后 see 一直报错);
    自己的目录万一被删了(系统清临时文件等)就重建。"""
    if _TMP[0] is None:
        root = tempfile.gettempdir()
        now = time.time()
        try:
            names = os.listdir(root)
        except OSError:
            names = []
        for n in names:                   # 顺手删一天前别的进程留下的(命令行打印的截图路径 AI 还要读,所以退出时不删)
            p = os.path.join(root, n)
            if n.startswith("seeu_win_") and os.path.isdir(p):
                try:
                    if now - os.path.getmtime(p) <= 86400:
                        continue
                    m = re.match(r"seeu_win_(\d+)_", n)
                    if m and _pid_alive(int(m.group(1))):
                        continue
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
                except OSError:
                    pass
    if _TMP[0] is None or not os.path.isdir(_TMP[0]):
        _TMP[0] = tempfile.mkdtemp(prefix=f"seeu_win_{os.getpid()}_")
    return _TMP[0]


def _save_png(w, h, data):
    d = _tmp()
    shots = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    for old in shots[:-KEEP_SHOTS]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    p = os.path.join(d, "shot_%d_%03d.png" % (int(time.time() * 1000), len(shots) % 1000))
    with open(p, "wb") as f:
        f.write(W.png_bytes(w, h, data))
    return p


def _settings():
    """读 设置.json。没有这个文件 = 全用默认;文件在但读不出来(格式坏了、不是一组设置)→ 借用鼠标按「问我」算
    (11-14 复查:原来一律当成空,用户手改成「关」但存坏了的话会被当成「开」)。记事本存的带 BOM 的也认。"""
    try:
        with open(_SETTINGS, encoding="utf-8-sig") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("not a dict")
        return d
    except FileNotFoundError:
        return {}
    except Exception:
        return {"借用鼠标": "问我"}


def _mode_of(v):
    v = str(v if v is not None else "开").strip().lower() or "开"
    if v in ("关", "off", "0", "false", "no"):
        return "off"
    if v in ("问我", "ask"):
        return "ask"
    return "on"


SETTABLE = {"借用鼠标": {"开": "开", "on": "开", "问我": "问我", "ask": "问我", "关": "关", "off": "关"}}   # 同 Mac 版 act.SETTABLE
SET_ALIAS = {"borrow-mouse": "借用鼠标"}
EN_VAL = {"开": "on", "问我": "ask", "关": "off"}


def settings_cmd(args):
    """python -m seeu 设置 [借用鼠标 开|问我|关]:不带参数列出现在的值;带了就改 设置.json(只认 SETTABLE 里的键和值)。同 Mac 版。"""
    from collections import OrderedDict
    try:
        from seeu.i18n import lang
        en = lang() == "en"
    except Exception:
        en = False
    if not args:
        v = {"on": "开", "ask": "问我", "off": "关"}[_mode_of(_settings().get("借用鼠标"))]     # 跟 real_mode 一个认法,显示的就是生效的
        print(f"borrow-mouse: {EN_VAL[v]}  (on / ask / off)" if en else f"借用鼠标: {v}  (开 = on / 问我 = ask / 关 = off)")
        try:                                             # 文件在但读不出来:上面显示的是兜底的「问我」,说一声为什么
            with open(_SETTINGS, encoding="utf-8-sig") as f:
                if not isinstance(json.load(f), dict):
                    raise ValueError("not a dict")
        except FileNotFoundError:
            pass
        except Exception as ex:   # noqa: BLE001
            print(f"(the settings file can't be read, so \"ask\" is used until it is fixed: {_SETTINGS} · {ex})" if en else
                  f"(设置文件读不出来,修好之前先按「问我」算:{_SETTINGS} · {ex})")
        if os.environ.get("SEEU_REAL_MOUSE") is not None:
            print("(SEEU_REAL_MOUSE is set and wins: now " + real_mode() + ")" if en else
                  "(设了环境变量 SEEU_REAL_MOUSE,以它为准:现在是 " + real_mode() + ")")
        return 0
    args = [SET_ALIAS.get(args[0].lower(), args[0])] + list(args[1:])
    if len(args) != 2 or args[0] not in SETTABLE or args[1].lower() not in SETTABLE[args[0]]:
        print("Usage: python -m seeu set borrow-mouse on|ask|off" if en else "用法:python -m seeu 设置 借用鼠标 开|问我|关")
        return 2
    try:
        with open(_SETTINGS, encoding="utf-8-sig") as f:
            d = json.load(f, object_pairs_hook=OrderedDict)
        if not isinstance(d, dict):
            raise ValueError("not a dict")
    except FileNotFoundError:
        d = OrderedDict()
    except (OSError, ValueError) as ex:              # 读不出来就不写:别把用户别的设置盖掉
        print(f"Not changed: can't read the settings file ({ex}): {_SETTINGS}" if en else f"没改:设置文件读不出来({ex}):{_SETTINGS}")
        return 1
    d[args[0]] = SETTABLE[args[0]][args[1].lower()]
    tmp = f"{_SETTINGS}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, _SETTINGS)
    except OSError as ex:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print(f"Not changed: can't write the settings file ({ex})" if en else f"没改:设置文件写不进去({ex})")
        return 1
    print(f"Set: borrow-mouse = {EN_VAL[d[args[0]]]}" if en else "已改:借用鼠标 = " + d[args[0]])
    return 0


def real_mode():
    """借用鼠标(Windows 上也管「借前台」):on(默认)| off | ask。环境变量 SEEU_REAL_MOUSE 优先。"""
    v = os.environ.get("SEEU_REAL_MOUSE")
    if v is None:
        v = _settings().get("借用鼠标")
    return _mode_of(v)


_SESSION_AUTO = [False]


def real_allowed(allow=None):
    a = str(allow or "").strip().lower()
    if a in ("auto", "自动使用"):
        _SESSION_AUTO[0] = True
    if a in ("once", "仅此一次", "auto", "自动使用"):
        return True
    m = real_mode()
    return m == "on" or (m == "ask" and _SESSION_AUTO[0])


def _win(app):
    """找窗口 + 过安全底线 + 管理员窗口。返回 window.info。"""
    safety.check_unlocked()          # 11-23 C-3.9 整体复查:锁屏时什么都不做(原来没查;判断出错当没锁)
    win = W.find(app)
    safety.check_window(win)
    if win.get("elevated") and not W.self_elevated():
        # 系统规定:普通程序发不进管理员窗口(UIPI),后台消息、真输入都会被吞掉,干脆先说清楚
        raise safety.Refused(f"「{win['title'][:30]}」是以管理员身份运行的窗口,SeeU 没有管理员权限、碰不了(这一步请你自己来)")
    return win


# ─────────────────────────────── 代理光标(纯显示,11-14,照 Mac act._cursor) ───────────────────────────────
# 动手前在那个位置画一个箭头给人看:后台模式 = 紫色「SeeU」;借了用户的鼠标 / 前台 = 亮橙 + 署名。
# 位置被别的窗口挡住、或窗口在别的虚拟桌面上,就不画。出任何错都吞掉,绝不影响动作。SEEU_NO_CURSOR=1 不画。

def _hex(v, default):
    try:
        v = str(v).lstrip("#")
        return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:   # noqa: BLE001
        return default


def _cursor_style(mode):
    """mode = bg | real → (名牌, 颜色)。每次现读设置(署名 / 让路模式颜色 / 后台模式颜色,同 Mac)。"""
    from seeu.win import cursor as C
    st = _settings()
    if mode == "real":
        sign = str(st.get("署名") or "").strip() or ("@" + os.environ.get("USERNAME", "").strip() if os.environ.get("USERNAME") else "SeeU")
        return sign, _hex(st.get("让路模式颜色", ""), C.ORANGE)
    return "SeeU", _hex(st.get("后台模式颜色", ""), C.PURPLE)


def _task_key():
    """这个任务的光标名(sched 起的显示名:Claude、Claude2…;项目名照旧)。拿不到 = None(跟老写法共用一只)。"""
    try:
        from seeu import sched as _sc
        return _sc.cursor_key()
    except Exception:   # noqa: BLE001
        return None


def _cursor(h, kind, x, y, mode="bg"):
    """画光标并等它走到位(最多 1 秒,让波纹跟动作对上)。看不见就不画。"""
    if os.environ.get("SEEU_NO_CURSOR"):
        return
    try:
        from seeu.win import cursor as C
        if W.other_desktop(h):
            return
        if mode != "real":                     # 借前台时窗口马上会到最上面,不用查挡没挡
            import ctypes.wintypes as _wt
            from seeu.win import api
            top = W.top_of(int(api.user32.WindowFromPoint(_wt.POINT(int(x), int(y))) or 0))
            if top and int(top) != int(h) and W.cls(top) not in ("SeeUFloat", "SeeUCursor", "SeeUToast"):
                C.hide(_task_key())          # 11-17:只藏自己这只(别的任务的光标不受影响)
                return
        label, color = _cursor_style(mode)
        # 11-17 C-2.6(照 Mac):一个任务一只光标,key = 任务显示名;后台模式名牌按规则(只剩一只写 SeeU,多只写任务名)、颜色用任务色
        key = _task_key()
        if key and mode != "real":
            try:
                from seeu import sched as _sc
                label, color = key, _sc.cursor_color(color)
            except Exception:   # noqa: BLE001
                pass
        t = C.show(kind, x, y, label, color, owner=int(h), key=key, auto=mode != "real")
        time.sleep(min(1.0, t))
    except Exception:   # noqa: BLE001
        pass


def _refused(reason, route=None):
    return dict(outcome="refused", route=route, tried=[], png=None, reason=str(reason))


def _shot(hwnd):
    try:
        return W.capture(hwnd)
    except RuntimeError:
        return None


def _changed(a, b, near=None):
    """(有没有变化, 整窗变化百分比)。near = 屏幕点在窗口里的相对位置 (x, y),也看那附近。"""
    if not a or not b:
        return False, 0.0
    whole = W.diff_percent(a[2], b[2])
    if whole >= MIN_CHANGE:
        return True, whole
    if near and a[0] == b[0]:
        x, y = near
        box = (int(x) - 60, int(y) - 60, int(x) + 60, int(y) + 60)
        if W.diff_percent(a[2], b[2], box=box, w=a[0], step=2) >= NEAR_CHANGE:
            return True, whole
    return False, whole


def _small(cap):
    return W.shrink(*cap, max_side=320) if cap else None


def stale_why(h, cap=None):
    """这个窗口的截图现在可不可信(11-15):不可信返回原因,可信返回 None。cap = 刚截的图(没有就现截一张)。
    ① 做完一步只有控件变了、画面没变 → 记下;之后截图跟那时比明显变了(画面跟上了)或过了 1 分钟才放下。
    ② Chrome / Electron 窗口整个被盖住(不重画)。"""
    h = int(h)
    v = _LAG.get(h)
    if v and time.time() - v[0] > LAG_TTL:
        _LAG.pop(h, None)
        v = None
    if v:
        new = _small(cap if cap is not None else _shot(h))
        old = v[1]
        if new and old and (new[0] != old[0] or new[1] != old[1] or W.diff_percent(old[2], new[2]) >= LAG_CLEAR):
            _LAG.pop(h, None)
            v = None
    if v:
        return LAG_WHY
    if _is_chrome(h) and W.other_desktop(h):      # 11-15 第五轮复查:别的桌面上的 Chrome 类窗口当不可信(保守)
        return DESK_WHY
    return COVER_WHY if W.stale_shot(h) else None


def _stale_pixel(h):
    """按截图位置操作之前查一次;截图不可信就返回一个不做的结果(failed + 原因),可信返回 None。"""
    why = stale_why(h)
    if not why:
        return None
    tip = {COVER_WHY: COVER_TIP, DESK_WHY: DESK_TIP}.get(why, LAG_TIP)
    return dict(outcome="failed", route=None, tried=[], png=None, stale=True, reason=STALE_PIXEL.format(why=why, tip=tip))


def _sig(hwnd):
    """窗口标题 + 控件名字和值的指纹。🔴 Chrome 窗口被完全挡住时不重画,截到的是旧图(11-11 真机:点成功了却判没变,
    换下一档又点一次,按钮被点了 3 下)—— 所以画面没变时还要看这个。"""
    try:
        parts = [W.text(hwnd)] + [f"{e['name']}={e.get('value') or ''}" for e in uia.elements(hwnd, limit=400)]
        return hash("\n".join(parts))
    except Exception:
        return None


PAGE_SWAP = 0.3         # 控件名字有三成以上换了 = 换页了(11-15)
PAINT_SMALL = 3.0       # 换页了画面却只变了不到这么多百分比 = 画面没跟上(鼠标移过去的高亮这种小变化)


NAMES_CAP = 400


def _is_chrome(hwnd):
    try:
        return W.cls(hwnd).startswith(W.STALE_CLASSES)
    except Exception:   # noqa: BLE001
        return False


def _snap(hwnd, chrome):
    """一次遍历出两样:指纹(同 _sig)和控件名字集合(只给 Chrome / Electron,看「换没换页」;取满上限的不给 —— 截断了比不准,11-15 复查)。"""
    try:
        es = uia.elements(hwnd, limit=NAMES_CAP)
        parts = [f"{e['name']}={e.get('value') or ''}" for e in es]
        sig = hash("\n".join([W.text(hwnd)] + parts))
        names = frozenset(parts) if chrome and len(es) < NAMES_CAP else None
        return sig, names
    except Exception:   # noqa: BLE001
        return None, None


def _names(hwnd):
    return _snap(hwnd, True)[1]


def _swapped(a, b):
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / float(len(a | b))


def _verify(hwnd, act, near=None, read=None, timeout=2.5):
    """做 act,前后比画面、窗口标题和控件内容(和读回文字);返回 (outcome, png, 说明)。read = 无参函数,返回读回的文字或 None。"""
    before = _shot(hwnd)
    txt0 = read() if read else None
    title0 = W.text(hwnd)
    chrome = _is_chrome(hwnd)
    sig0, names0 = _snap(hwnd, chrome)

    def rebase():       # 11-17 C-2.8:借前台 / 借真鼠标排完队、等完用户停手,真动手前重拍「动作前」(原来那张是排队前的)
        nonlocal before, txt0, title0, sig0, names0
        b = _shot(hwnd)
        if b is None:
            return
        before, title0 = b, W.text(hwnd)
        txt0 = read() if read else None
        sig0, names0 = _snap(hwnd, chrome)
    from seeu.win import real as _rl
    _rl.REBASE.f = rebase
    try:
        act()
    finally:
        _rl.REBASE.f = None
    # 11-23 C-3.9 整体复查(照 Mac act._try 的 done):动作已经发出去了,之后核实 / 存截图出错(临时目录被删、窗口没了…)
    # 不能当成「这条路没走通」—— 那样 _ladder 会换下一档把同一个动作再做一遍(按钮最多被点 3 次)。一律按 unverified 返回。
    try:
        return _after(hwnd, before, near, read, timeout, txt0, title0, chrome, sig0, names0)
    except Exception as ex:   # noqa: BLE001
        return "unverified", None, f"{SENT_BUT}({ex})"


SENT_BUT = "动作已经发出去了,但核实时出了错;先 see 看一眼有没有生效,别直接重做"


def _safe_png(cap):
    """存截图;存不了(临时目录出问题)返回 None,不影响已经核实出来的结果。"""
    try:
        return _save_png(*cap)
    except Exception:   # noqa: BLE001
        return None


def _after(hwnd, before, near, read, timeout, txt0, title0, chrome, sig0, names0):
    """_verify 的后半段:动作做完之后比画面、标题、控件内容。"""
    if before is None:
        return "unverified", None, "窗口截不到(最小化了?)"
    t0 = time.time()
    after = before
    while time.time() - t0 < timeout:
        time.sleep(0.25)
        after = _shot(hwnd) or after
        ok, pct = _changed(before, after, near)
        if ok:
            note = f"画面变了 {pct}%"
            if names0 is not None and pct < PAINT_SMALL:
                # 11-15 Win10:真鼠标点「定时任务」,按钮高亮画面变了 2%,控件整页换了,画面却还是老页面 → 也算没跟上
                time.sleep(0.5)
                n1 = _names(hwnd)
                if n1 is not None and _swapped(names0, n1) >= PAGE_SWAP:
                    _LAG[int(hwnd)] = (time.time(), _small(_shot(hwnd) or after))
                    return "delivered", _safe_png(after), note + ";控件大半换了、画面只变了一点(画面可能没跟上)"
            if pct >= LAG_CLEAR:             # 画面明显跟着变了(≥3%),说明跟得上;按钮高亮这种小变化不算(11-15 复查)
                _LAG.pop(int(hwnd), None)
            return "delivered", _safe_png(after), note
        if read:
            txt1 = read()
            if txt1 is not None and txt1 != txt0:
                return "delivered", _safe_png(after), ("选中 / 勾选状态变了" if str(txt1).startswith("state:") else "读回的文字变了")
        if W.text(hwnd) != title0:
            return "delivered", _safe_png(after), "窗口标题变了"
        if sig0 is not None and time.time() - t0 > 0.5:
            s1 = _sig(hwnd)
            if s1 is not None and s1 != sig0:
                if chrome:      # 11-15:之后按截图位置点要先拦(见 stale_why);只对 Chrome / Electron(普通程序勾个框也是这样,不是没跟上)
                    _LAG[int(hwnd)] = (time.time(), _small(after))
                return "delivered", _safe_png(after), "控件内容变了(画面可能没重画)"
    return "ineffective", _safe_png(after), "画面、标题、控件内容都没变"


def _keep_front(hwnd, act, info):
    """后台动作做完盯 0.5 秒:前台被目标窗口拿走了就还回去。
    11-11 真机:用户在 Chrome 窗口 A 里,后台点 Chrome 窗口 B,Chrome 自己把 B 换到前台(同一个程序的窗口之间系统不拦)。"""
    def run():
        fg0 = W.foreground()
        act()
        if not fg0 or fg0 == hwnd:
            return
        try:        # 11-23 C-3.9 整体复查:动作已发出,盯前台这段出错不能让 _ladder 换下一档重做
            t0 = time.time()
            while time.time() - t0 < 0.5:
                if W.foreground() == hwnd:
                    ok, how = inputs.give_back(fg0)
                    info.update(front_taken=True, front_back=ok, front_how=how)
                    return
                time.sleep(0.01)
        except Exception:   # noqa: BLE001
            pass
    return run


def _ladder(hwnd, steps, near=None, read=None):
    tried, png, note = [], None, ""
    for name, act in steps:
        info = {}
        if name.startswith("后台"):
            act = _keep_front(hwnd, act, info)
        try:
            out, png, note = _verify(hwnd, act, near, read)
            if info:
                note = (note + ";" if note else "") + ("目标窗口自己跑到了前台,已还回去" if info.get("front_back")
                                                       else "目标窗口自己跑到了前台,没还回去")
        except safety.Refused as ex:
            tried.append((name, f"refused:{ex}"))
            return dict(outcome="refused", route=name, tried=tried, png=png, reason=str(ex))
        except Exception as ex:          # noqa: BLE001 这条路走不通 → 下一条
            tried.append((name, f"error:{ex}"))
            continue
        tried.append((name, out))
        if out in ("delivered", "unverified"):
            return dict(outcome=out, route=name, tried=tried, png=png, note=note)
    last = tried[-1][1] if tried else "failed"
    out = "ineffective" if last == "ineffective" else "failed"
    return dict(outcome=out, route=tried[-1][0] if tried else None, tried=tried, png=png, note=note)


# ─────────────────────────────── 看 ───────────────────────────────

def see(app):
    """返回 {png, items, windows}。items 每项:id、kind(uia)、text、role、x/y(屏幕点中心)、actions、uia(元素信息)。"""
    win = _win(app)
    h = win["hwnd"]
    cap = _shot(h)
    png = _save_png(*cap) if cap else None
    items = []
    elems = uia.elements(h)
    if win["class"] == "Chrome_WidgetWin_1" and not any(e["type"] == 50030 for e in elems):
        time.sleep(1.5)             # Chrome / Electron 第一次被 UIA 查时网页那部分是空的,隔一两秒才有(11-11 真机)
        elems = uia.elements(h)
    for e in elems:
        x, y, w, hh = e["rect"]
        val = " ".join(str(e.get("value") or "").split())
        if len(val) > 80:                       # 文档、长输入框的内容只给开头(11-11:记事本整篇 2 万字塞进了清单)
            val = val[:80] + f"…(共 {len(str(e['value']))} 字)"
        name = " ".join(e["name"].split())
        text = name if not val else f"{name} = {val}" if name else val
        items.append(dict(kind="uia", text=text, role=e["role"], x=x + w / 2, y=y + hh / 2, actions=e["actions"],
                          password=e["password"], uia=e))
    ocr_note = None
    canvas = win["exe"].lower() in CANVAS_EXES
    real_ = [i for i in items if i["role"] not in ("文字", "标题栏") and i["text"] not in FRAME_NAMES]
    if cap and (canvas or len(real_) < 3):
        # 11-15:窗口边框上的最小化 / 最大化 / 关闭不算(Win10 上 Trae、豆包只读得到这 3 个,原来正好够数、认字被跳过)
        # 读不到控件(模拟器、游戏、自绘界面):截图认字补清单(11-11,Windows 自带识字,要装语言包)
        from seeu.win import ocr
        r = ocr.recognize(W.png_bytes(*cap))
        if r["available"]:
            for ln in r["lines"]:
                items.append(dict(kind="ocr", text=ln["text"], role="认字", x=win["rect"][0] + ln["x"] + ln["w"] / 2,
                                  y=win["rect"][1] + ln["y"] + ln["h"] / 2, actions=[], password=False, uia=None))
        elif canvas:
            ocr_note = r.get("note")
    for i, it in enumerate(items, 1):
        it["id"] = i
        it["hwnd"] = int(h)          # 11-23 C-3.9 整体复查:记下这一项是哪个窗口的(同程序两个窗口时,动作那次找到的可能是另一个)
    _last[app] = items
    same = [w for w in W.list_windows() if w["exe"].lower() == win["exe"].lower()]
    wins = [w["title"] for w in same] if len(same) > 1 else []
    note = None
    stale = stale_why(h, cap) if cap else None
    if win.get("other_desktop"):
        note = ("这个窗口在另一个虚拟桌面上,控件可能读不全(有些程序只剩窗口边框那几项);可以看截图、按截图位置点(Chrome / Electron 类窗口除外)、"
                "直接打字和按键,清单里有的输入框也能按编号打字;但后台点不动时 SeeU 不借鼠标(会把用户切过去)。清单里没有要操作的东西时,请用户切到那个桌面或把窗口挪过来。")
    return {"png": png, "items": items, "windows": wins, "window": {k: win[k] for k in ("hwnd", "title", "exe", "rect")},
            "cap": cap, "ocr_note": ocr_note, "note": note, "stale": stale}


def describe(items):
    return "\n".join(f"{it['id']:>3}. {it.get('role', '')}  {it['text']}  ({it['x']:.0f},{it['y']:.0f})"
                     + ("  [密码框]" if it.get("password") else "") for it in items)


class Stale(RuntimeError):
    """按编号操作时发现画面已经不是 see 那时候的样子(那个控件不在了)。不点,让调用方重新 see。"""


def _still_there(it, hwnd=None):
    """按编号点之前核对(11-14,规则同 Mac 的 act._still_there):see 的时候那个控件还在不在、现在在哪。
    返回现在的中心点 (x, y);不在了抛 Stale(不退回去点老位置)。
      - 控件还在:用它现在的位置(滚动、挪窗口后也点得准),顺手更新清单里记的位置。
      - 控件对象失效:看原位置上现在是不是同一种、同名、还在这个窗口里的控件,是就照点(窗口被盖着时问不到,算不在)。
    认字得来的项(模拟器、自绘界面)没有控件可问,不核对。
    11-23 C-3.9 整体复查:先核对这一项是不是这次找到的这个窗口的(see 时记了窗口号)。同一个程序开着两个窗口、see 之后
    另一个窗口到了上面,同一个 App 名这次找到的就是另一个 —— 原来「控件对象还有效」就照点,点进了 see 的那个窗口。"""
    if hwnd is not None and it.get("hwnd") is not None and int(it["hwnd"]) != int(hwnd):
        raise Stale(WRONG_WINDOW.format(a=int(it["hwnd"]), b=int(hwnd)))
    e = it.get("uia")
    if not e:
        return it["x"], it["y"]
    cur = uia.current(e)
    if cur and cur[0] == e["type"]:
        x, y, w, h = cur[1]
        e["rect"] = cur[1]
        it["x"], it["y"] = x + w / 2, y + h / 2
        return it["x"], it["y"]
    now = uia.at_point(it["x"], it["y"]) if e.get("name") else None      # 没名字的控件认不出「是不是同一个」
    if now and now[0] == e["type"] and now[1] == e["name"] and (hwnd is None or _in_window(now[2], hwnd)):
        e["el"] = now[2]
        return it["x"], it["y"]
    raise Stale(f"画面变了:第 {it['id']} 项「{(it.get('text') or '')[:20]}」已经不在 see 时的位置,先 see 一次再操作")


WRONG_WINDOW = ("这次找到的窗口(#{b})不是上次 see 的那个(#{a}):这个程序开着好几个窗口,最上面的换了。"
                "先 see 一次再操作;要固定操作某一个窗口,App 写成「#窗口号」")


def _in_window(el, hwnd):
    """这个控件是不是 hwnd 这个窗口里的。目标窗口被别的窗口盖着时,那一点上问到的是别人的控件,同名也不算数。"""
    try:
        return uia.inside(el, uia.element(hwnd))
    except Exception:   # noqa: BLE001
        return False


def _resolve(app, target, hwnd):
    """target → (x, y, uia项或None)。"""
    if isinstance(target, (tuple, list)) and len(target) == 2:
        return float(target[0]), float(target[1]), None
    if isinstance(target, int) or (isinstance(target, str) and target.strip().isdigit()):
        items = _last.get(app) or see(app)["items"]
        n = int(target)
        it = next((i for i in items if i["id"] == n), None)
        if not it:
            raise RuntimeError(f"没有编号 {n},先 see 一次")
        x, y = _still_there(it, hwnd)
        return x, y, it.get("uia")
    try:
        e = uia.find(hwnd, str(target))
    except RuntimeError:
        # 控件里没有:按名字在认字的结果里找(模拟器、自绘界面)
        items = see(app)["items"]
        t = str(target)
        hits = [i for i in items if i["kind"] == "ocr" and i["text"] == t] or \
            [i for i in items if i["kind"] == "ocr" and t in i["text"]]
        if not hits:
            raise
        return hits[0]["x"], hits[0]["y"], None
    x, y, w, h = e["rect"]
    return x + w / 2, y + h / 2, e


def _rel(win, x, y):
    return x - win["rect"][0], y - win["rect"][1]


# ─────────────────────────────── 动作 ───────────────────────────────

ASK_REASON = ("后台没效果,要借用户的{what}(设置「借用鼠标」= 问我)。请问用户三选一:仅此一次 / 自动使用(这一轮不再问)/ 拒绝;"
              "选前两个就带上 allow_real=once 或 auto 再做一次这一步,拒绝就停手告诉用户卡在哪")
OFF_REASON = "后台做了但没效果;按设置(借用鼠标 = 关)没借用户的鼠标键盘。先 see 看是不是其实生效了,真没生效就停手告诉用户卡在哪"


def _gate(r, allow, what, h=None):
    """后台不行时,能不能往下借。能借返回 None;不能借返回填好原因的结果。
    h:目标窗口。在别的虚拟桌面上 → 借了也做不了(借鼠标 / 借前台都拒),别先问用户、等答应了才说做不了(11-14 复查)。"""
    try:
        if h and W.other_desktop(h):
            # 11-15 复查:报 refused(停下告诉用户),不是 ineffective(那会让 AI 换个目标白试一次)
            r.update(outcome="refused", code="other_desktop", reason=W.OTHER_DESKTOP)
            return r
    except Exception:   # noqa: BLE001
        pass
    if real_allowed(allow):
        return None
    if real_mode() == "ask":
        r.update(outcome="ask_user", reason=ASK_REASON.format(what=what))
        try:
            from seeu.i18n import T
            from seeu.win import cursor, lang
            cursor.toast(T("ask.title"), T("ask.body", what=lang.tx(what)), 12, color=cursor.ORANGE)
        except Exception:   # noqa: BLE001
            pass
    else:
        r["reason"] = OFF_REASON
    return r


SEEU_BUSY_MARK = "别的 SeeU 任务正在借用户的鼠标键盘"     # = sched.REAL_WHY 开头


def _is_busy(why):
    """_ladder 记下的错(「error:…」)是不是「用户在用电脑」/「别的 SeeU 任务在借鼠标」。"""
    w = str(why)
    return "用户正在用电脑" in w or SEEU_BUSY_MARK in w


def _busy(r, ex):
    from seeu.win import real as _rl
    if isinstance(ex, getattr(_rl, "SeeUBusy", ())) or SEEU_BUSY_MARK in str(ex):   # 11-17:别的 SeeU 任务在借鼠标,排不上 → busy(稍后重试),不是被拦
        r.update(outcome="busy", code="busy", reason=str(ex))
        return r
    r.update(outcome="refused", code="user_busy", reason=str(ex))
    return r


# 11-23 C-3.9 整体复查:点这几种有名字的控件前查危险名字(清空回收站 / 关机 / 注销 / 重启…,safety.check_menu);
# 按钮、菜单项、拆分按钮。列表项不查(资源管理器里的文件名会被误伤);按截图位置 / 认字得来的项没有控件名,查不了。
TAP_CHECK_TYPES = {50000, 50011, 50031}


def _check_name(e, win):
    if e is not None and e.get("type") in TAP_CHECK_TYPES and (e.get("name") or "").strip():
        safety.check_menu([e["name"]], win.get("exe") or "")


def tap(app, target, allow=None, real=True, stale_check=True):
    """点:后台点击 → 借前台按下(控件能按时,约 0.03~0.2 秒)→ 真鼠标(让路后约 0.2 秒,点完还原)。后两档归「借用鼠标」设置管。"""
    try:
        win = _win(app)
    except safety.Refused as ex:
        return _refused(ex)
    h = win["hwnd"]
    x, y, e = _resolve(app, target, h)
    try:
        _check_name(e, win)
    except safety.Refused as ex:
        return _refused(ex)
    if e is None and stale_check:    # 按截图位置(或截图认字)点:截图不可信就不点(11-15)
        bad = _stale_pixel(h)
        if bad:
            return bad
    _FIELD.pop(h, None)          # 点了别的地方,焦点可能已经不在原来的框里;要改内容得重新指定
    near = _rel(win, x, y)
    try:                         # 浮标「看画面」时在小画面上标出点的位置(只是显示,出错不管)
        from seeu.win import floatwin
        floatwin.mark(near[0] / float(win["rect"][2]), near[1] / float(win["rect"][3]), h)
    except Exception:   # noqa: BLE001
        pass
    _cursor(h, "click", x, y)
    st_read = _state_reader(h, e, x, y)          # 11-23 C-3.9:单选 / 勾选框按「选没选中」核实(见 _state_reader)
    r = _ladder(h, [("后台点击", lambda: inputs.click(h, round(x), round(y)))], near=near, read=st_read)
    r["xy"] = (round(x), round(y))
    if r["outcome"] not in ("ineffective", "failed") or not real:
        # real=False:只走后台(打字前点输入框用。点空输入框画面只多一个光标,常判「没变」,不能因此借用户的鼠标 —— 11-11 真机每次打字都借了一次)
        return r
    blocked = _gate(r, allow, "前台约 0.2 秒按下这个控件,或借鼠标点一下", h)
    if blocked:
        return blocked
    info = {}
    steps = []
    front_lost = []
    if e is not None and any(a in e["actions"] for a in ("invoke", "toggle", "select", "expand")):
        def borrow():
            if not W.other_desktop(h):
                _cursor(h, "click", x, y, "real")
            from seeu.win import real as _rl
            with _rl.slot():                     # 复查 11-17 C-2.6:借前台也会动前台窗口,跟借真鼠标一起排队
                _rl.rebase()                     # 11-17 C-2.8:排完队重拍「动作前」
                info.update(inputs.borrow_front(h, lambda: uia.press(e)))
            if info.get("stolen") and not info.get("back"):
                # 11-23 C-3.9 整体复查:原来在这抛错 → _ladder 当成这条路没走通,换真鼠标把同一个按钮再点一次。
                # 按下已经做成了:照常核实,只在 note 里说前台没还回去
                front_lost.append(1)
        steps.append(("借前台按下", borrow))

    def real_tap():
        from seeu.win import real
        if not W.other_desktop(h):
            _cursor(h, "click", x, y, "real")
        info.update(real.click(h, round(x), round(y)))
    steps.append(("真鼠标", real_tap))
    from seeu.win import real
    tried = list(r["tried"])
    for name, fn in steps:
        try:
            r2 = _ladder(h, [(name, fn)], near=near, read=st_read)
        except real.UserBusy as ex:
            return _busy(r, ex)
        tried += r2["tried"]
        busy = [t for t in r2["tried"] if _is_busy(t[1])]
        if busy:
            r2.update(tried=tried, xy=r["xy"])
            return _busy(r2, busy[0][1][len("error:"):])
        if r2["outcome"] in ("delivered", "unverified"):
            break
    r2.update(tried=tried, xy=r["xy"])
    if info:
        r2["borrow"] = info
    if front_lost:
        r2["note"] = (r2["note"] + ";" if r2.get("note") else "") + FRONT_LOST
    return r2


FRONT_LOST = "按下了,但前台没还回去(目标窗口留在了最前面)"


NO_BROWSER = ("浏览器里不长按 / 不拖动(这两样按屏幕位置操作,会绕开网页的允许名单);"
              "网页请用 SeeU 专用浏览器(seeu_web_open)按编号点")


def _real_step(r, h, name, fn, near, allow, what):
    """后台没效果时借真鼠标那一档(长按、拖动共用):过设置 → 让路 → 做 → 合并 tried。"""
    blocked = _gate(r, allow, what, h)
    if blocked:
        return blocked
    from seeu.win import real
    info = {}
    try:
        r2 = _ladder(h, [(name, lambda: info.update(fn()))], near=near)
    except real.UserBusy as ex:
        return _busy(r, ex)
    busy = [t for t in r2["tried"] if _is_busy(t[1])]
    r2["tried"] = list(r["tried"]) + r2["tried"]
    if busy:
        return _busy(r2, busy[0][1][len("error:"):])
    if info:
        r2["borrow"] = info
    return r2


def long_press(app, target, ms=1000, allow=None):
    """长按(11-12):后台按住 ms 毫秒 → 没效果再借真鼠标(归「借用鼠标」设置管)。浏览器里不做(跟 Mac 版一样)。"""
    try:
        win = _win(app)
    except safety.Refused as ex:
        return _refused(ex)
    if _is_browser(win):
        return _refused(NO_BROWSER)
    h = win["hwnd"]
    x, y, _e = _resolve(app, target, h)
    try:
        _check_name(_e, win)         # 11-23 C-3.9 整体复查:长按也是点,同样查危险名字
    except safety.Refused as ex:
        return _refused(ex)
    if _e is None:
        bad = _stale_pixel(h)
        if bad:
            return bad
    near = _rel(win, x, y)
    _cursor(h, "click", x, y)
    r = _ladder(h, [("后台长按", lambda: inputs.long_press(h, round(x), round(y), ms))], near=near)
    r["xy"] = (round(x), round(y))
    if r["outcome"] not in ("ineffective", "failed"):
        return r
    from seeu.win import real
    r2 = _real_step(r, h, "真鼠标长按", lambda: (_cursor(h, "click", x, y, "real"), real.long_press(h, round(x), round(y), ms))[1],
                    near, allow, "鼠标长按一下")
    r2["xy"] = r["xy"]
    return r2


def drag(app, pts, hold_ms=0, allow=None):
    """拖动(11-12):pts = 屏幕点列表(至少两个,起点在前),每个点都要在窗口里。后台拖 → 没效果再借真鼠标拖。浏览器里不做。"""
    try:
        win = _win(app)
    except safety.Refused as ex:
        return _refused(ex)
    if _is_browser(win):
        return _refused(NO_BROWSER)
    pts = [(float(p[0]), float(p[1])) for p in pts]
    if len(pts) < 2:
        return dict(outcome="failed", route=None, tried=[], png=None, reason="拖动至少要起点、终点两个点")
    x0, y0, x1, y1 = win["rect"][0], win["rect"][1], win["rect"][0] + win["rect"][2], win["rect"][1] + win["rect"][3]
    out = [p for p in pts if not (x0 <= p[0] < x1 and y0 <= p[1] < y1)]
    if out:
        return dict(outcome="failed", route=None, tried=[], png=None, reason=f"有点不在窗口里:{out[0]},SeeU 只在这个窗口里拖")
    h = win["hwnd"]
    bad = _stale_pixel(h)        # 拖动全靠截图位置
    if bad:
        return bad
    near = _rel(win, *pts[-1])
    _cursor(h, "move", *pts[0])
    r = _ladder(h, [("后台拖动", lambda: inputs.drag(h, pts, hold_ms))], near=near)
    _cursor(h, "move", *pts[-1])
    if r["outcome"] not in ("ineffective", "failed"):
        return r
    from seeu.win import real

    def real_drag():
        _cursor(h, "move", *pts[0], "real")
        out = real.drag(h, pts, hold_ms)
        _cursor(h, "move", *pts[-1], "real")
        return out
    return _real_step(r, h, "真鼠标拖动", real_drag, near, allow, "鼠标拖一下")


BROWSER_EXES = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "opera.exe", "chromium.exe"}
_FIELD = {}         # 窗口号 → SeeU 最近一次按 at 点进去的那个输入框(UIA 信息)
NEED_FIELD = ("这是用户自己的浏览器:后台时 SeeU 读不出光标在哪个框里(可能是密码框),所以网页里打字 / 按会改内容的键,"
              "要先用 at / target 指定输入框(SeeU 会先查它是不是密码框)。网页优先用 SeeU 专用浏览器(seeu_web_open)")
WEB_HINT = ("这是用户自己的浏览器:它没开网页内容的辅助功能时,后台打字 / 滚动它常常不认(11-11 真机,Chrome 157)。"
            "网页请改用 SeeU 专用浏览器(seeu_web_open),那条路稳")


def _is_browser(win):
    return win["exe"].lower() in BROWSER_EXES


def _address_el(win):
    """资源管理器窗口里正拿着键盘焦点的地址栏(UIA 元素);不是 / 找不到 None。
    11-23 C-3.9 虚拟机实测:Win11 资源管理器的地址栏在新式界面框架里,点进去后 focused_in 只读到一个没名字的容器,
    但「地址栏」这个输入框自己标着有键盘焦点(30008)、值就是里面的路径 → 直接找它。"""
    try:
        for it in uia.elements(win["hwnd"]):
            if it.get("type") == 50004 and safety.is_address(it.get("name")) and it["el"].GetCurrentPropertyValue(30008):
                return it["el"]
    except Exception:   # noqa: BLE001
        pass
    return None


def _in_address(win, field):
    """要打字 / 按回车的地方是不是资源管理器的地址栏(11-23 C-3.9)。at 点的那个框直接看名字;没给 at 就看地址栏有没有焦点;
    资源管理器里焦点完全读不出来 = 按地址栏算(宁可多拦)。别的程序一律 False。"""
    if (win.get("exe") or "").lower() != "explorer.exe":
        return False
    if field is not None and safety.is_address(field.get("name") or field.get("text")):
        return True
    # 11-23 C-4.0 Fable 复查:at 指的控件名字不像地址栏(面包屑、「上一个位置」按钮…)也可能把地址栏点进编辑状态 → 接着看焦点
    if _address_el(win) is not None:
        return True
    try:
        f = uia.focused_in(win["hwnd"])
    except Exception:   # noqa: BLE001
        f = None
    return True if f is None else safety.is_address(f.get("name"))


def _known_field(win, field):
    """浏览器里要改内容时,光标所在的框:这次 at 点的,或者上次 at 点的。都没有 → 认不出 → None。"""
    if field is not None:
        _FIELD[win["hwnd"]] = field
        return field
    return _FIELD.get(win["hwnd"])


def _secret_focus(h, target):
    """光标是不是在密码框里:UIA 有焦点的控件标了「是密码」,或老式输入框带密码样式。"""
    try:
        if target and W.cls(target).lower().startswith("edit"):
            if inputs.u.GetWindowLongW(target, -16) & 0x20:     # ES_PASSWORD
                return True
    except Exception:
        pass
    try:
        f = uia.focused_in(h)
        return bool(f and f["password"])
    except Exception:
        return False


# UIA 属性号:选中项是否选中、勾选状态,以及这两种能力有没有
P_IS_SELECTED, P_TOGGLE_STATE, P_HAS_SEL, P_HAS_TOG = 30079, 30086, 30036, 30041


def _state_reader(h, e, x, y):
    """11-23 C-3.9 整体复查(虚拟机实测):单选按钮、勾选框点中了,画面只变一小点(老程序在 200% 缩放下更明显),
    截图比对判「没变」→ 换真鼠标再点一次 = 按了两下(勾选框就是勾上又取消)。
    点的是这两种控件时,改成读它「选没选中」:点前点后不一样就算点成了(照 Mac 11-14 勾选框自我核实)。
    按编号点的直接用那个控件;按位置点的问一下那一点上是什么控件(只认这个窗口里的)。不是这两种 → None(照旧比截图)。"""
    try:
        el = (e or {}).get("el")
        if el is None:
            hit = uia.at_point(x, y)
            el = hit[2] if hit and _in_window(hit[2], h) else None
        if el is None:
            return None
        props = [p for p, has in ((P_IS_SELECTED, P_HAS_SEL), (P_TOGGLE_STATE, P_HAS_TOG)) if el.GetCurrentPropertyValue(has)]
        if not props:
            return None
    except Exception:   # noqa: BLE001
        return None

    def read():
        try:
            return "state:" + ",".join(str(el.GetCurrentPropertyValue(p)) for p in props)
        except Exception:   # noqa: BLE001
            return None
    return read


def _reader(h):
    def read():
        try:
            return uia.read_text(h)
        except Exception:
            return None
    return read


DIALOG_BLOCKS = ("挡着,字会打进弹窗、到不了后面的输入区,SeeU 没打。先 see 看弹窗内容,按用户的意思处理或关掉它"
                 "(登录、同意条款这类要先问用户),再打字")


def _blocking_dialog(h, field=None):
    """有模态弹窗挡着、而要打字的地方不在弹窗里 → 返回弹窗;否则 None。
    要打字的地方:先点过的输入框(field),没有就看窗口记的焦点。焦点读不出 = 按「不在弹窗里」算(弹窗挡着时字本来就进不去)。
    11-12 Win10 真机:VS Code 欢迎弹窗挡着,后台打字画面变了报 delivered,文件却是空的。"""
    try:
        dlg = uia.blocking_dialog(h)
    except Exception:
        return None
    if dlg is None:
        return None
    el = field.get("el") if field else None
    if el is None:
        f = uia.focused_in(h)
        el = f["el"] if f else None
    if el is not None and uia.inside(el, dlg["el"]):
        return None
    return dlg


def type(app, text, enter=False, at=None, allow=None):
    """后台打字。at = 先后台点一下的位置(编号 / 名字 / 屏幕点;Electron 程序打字前要先点,11-11 真机)。
    核实:读得回文字就看里面有没有打的字,读不回看画面。回车只在核实打进去后单独按。"""
    try:
        win = _win(app)
        safety.check_text(text)
    except safety.Refused as ex:
        return _refused(ex)
    h = win["hwnd"]
    r0, field = None, None
    if at is not None:
        ax_, ay_, field = _resolve(app, at, h)
        if field is not None and field.get("password"):
            return _refused("光标在密码框里,SeeU 不往里打字(这一步请你自己来)")
        try:
            _check_name(field, win)  # 11-23 C-4.0 Fable 复查:带 target 打字会先点它,危险名字的按钮同样不点
        except safety.Refused as ex:
            return _refused(ex)
        if field is None:            # at 是截图位置:截图不可信就不点也不打(11-15)
            bad = _stale_pixel(h)
            if bad:
                return bad
        r0 = tap(app, (ax_, ay_), real=False, stale_check=False)
        if r0["outcome"] in ("refused", "busy"):     # 11-17:排不上队也别接着打(框没点上,字会打到别处)
            return r0
        time.sleep(0.2)
    if _is_browser(win):
        f = _known_field(win, field)
        if f is None:
            return _refused(NEED_FIELD)
        if f.get("password"):
            return _refused("光标在密码框里,SeeU 不往里打字(这一步请你自己来)")
    if _in_address(win, field):            # 11-23 C-3.9:资源管理器地址栏只打已有文件夹的路径(见 safety.check_address_text)
        try:
            safety.check_address_text(text)
        except safety.Refused as ex:
            return _refused(ex)
    dlg = _blocking_dialog(h, field)
    if dlg is not None:
        return dict(outcome="failed", route=None, tried=[], png=None,
                    reason=f"窗口里有弹窗「{dlg['name'] or '没名字'}」{DIALOG_BLOCKS}")
    target = inputs.type_target(h)
    if _secret_focus(h, target):
        return _refused("光标在密码框里,SeeU 不往里打字(这一步请你自己来)")
    read = _reader(h)
    if field is not None and "value" in field.get("actions", []):
        def read():                     # 读刚点过的那个输入框本身(11-11:按焦点猜,Chrome 里读成了地址栏)
            try:
                return uia.read_element(field["el"])
            except Exception:
                return None
    before_val = read()
    r = _ladder(h, [("后台打字", lambda: inputs.type_text(h, text, target=target))], read=read)
    r["target"] = W.cls(target)
    if r0:
        r["at"] = {k: r0.get(k) for k in ("outcome", "route", "tried", "borrow", "note") if r0.get(k)}
    SAME = ("目标窗口自己跑到了前台" in str(r.get("note")) or "目标窗口自己跑到了前台" in str((r0 or {}).get("note")))
    if r["outcome"] == "ineffective" and SAME:
        r["reason"] = ("用户正在用同一个程序的另一个窗口(比如另一个 Chrome 窗口):后台一点,它自己把目标窗口换到前台,"
                       "SeeU 把前台还给了用户,输入焦点也跟着丢了,所以打不进。先告诉用户这一步后台做不了;"
                       "网页请用浏览器专用的路子(调试端口 / 插件),或等用户切到别的程序再试")
    elif r["outcome"] == "ineffective" and _is_browser(win):
        r["reason"] = WEB_HINT
    elif r["outcome"] == "ineffective" and at is None:
        r["reason"] = ("后台打了,画面和文字都没变:多半是输入框没有焦点(Chrome、VS Code 这类被切过前台后会丢焦点)。"
                       "带上 at=输入框的编号 / 名字再打一次(会先后台点一下),别不带 at 重打")
    if r["outcome"] == "delivered":
        tail = "".join(c for c in text if not c.isspace())[-3:]
        squash = lambda g: "".join(c for c in (g or "") if not c.isspace() and c not in ZERO_W)
        got = read()
        t1 = time.time()
        while got is not None and tail and tail not in squash(got) and time.time() - t1 < 1.2:
            time.sleep(0.3)             # Chrome 的网页结构比打字慢半拍(11-11 真机:字对了却读成「只打进一部分」)
            got = read()
        # 读回空串、或跟打字前一模一样 = 网页结构没跟上(11-11 Chrome 真机:一直读成空 / 读成打字前的旧内容),当「不知道」;
        # 只有内容真变了、却缺最后几个字,才报只打进一部分
        if got and squash(got) != squash(before_val) and tail and tail not in squash(got):
            r.update(outcome="partial", reason="读回的文字里找不到最后几个字,可能只打进去一部分;没按回车。先 see 看看")
            return r
        real_read = before_val is not None and (squash(before_val) or any(c in before_val for c in ZERO_W))
        if real_read and got is not None and tail and squash(got) == squash(before_val) and tail not in squash(got) \
                and not _is_browser(win) and "not accessible" not in got:
            # 只在打字前确实读到了输入框(有字,或网页编辑框空着时特有的隐形字符)时才判;读不到 / 读回空串退回看画面(11-15 复查)
            # 11-15 Win10:WorkBuddy 机器满载时字没进输入框,画面却有点小变化 → 原来报「成功」还按了回车。读回跟打字前一样就别说成功
            r.update(outcome="unverified", reason="打了,但读回的内容跟打字前一样,可能没打进去(程序忙、没接住);没按回车。先 see 看一眼,"
                                                   "没进去就等一会儿再打")
            if enter:
                r["enter"] = "skipped"
            return r
    if r["outcome"] == "ineffective" and not SAME:
        # 后台打字落空:读得回文字、确认一个字都没进去,才借真键盘(读不回就不借,免得其实打进去了、再打一遍叠出重复字)
        got = read()
        if got and text not in got:          # 读回是空串分不清是真空还是没读到,不借(免得叠字)
            blocked = _gate(r, allow, "键盘打这几个字(会把窗口拉到前台约 0.2 秒,打完还原)", h)
            if blocked:
                return blocked
            from seeu.win import real
            info = {}
            try:
                r2 = _ladder(h, [("真键盘", lambda: info.update(real.type_text(h, text)))], read=read)
            except real.UserBusy as ex:
                return _busy(r, ex)
            r2["tried"] = r["tried"] + r2["tried"]
            r2["borrow"] = info
            busy = [t for t in r2["tried"] if _is_busy(t[1])]
            if busy:
                return _busy(r2, busy[0][1][len("error:"):])
            r = r2
    if enter:
        if r["outcome"] == "delivered" and _in_address(win, field) and not _address_now_folder(win, field):
            r["enter"] = "skipped"      # 11-23 C-4.0 Fable 复查:地址栏里整串(不只是这次打的字)不是已有文件夹就不按回车
            r["note"] = safety.NOT_FOLDER_ENTER
        elif r["outcome"] == "delivered":
            inputs.key(h, "return", target=target)
            r["enter"] = "sent"
        else:
            r["enter"] = "skipped"
    return r


def _address_now_folder(win, field):
    """地址栏里现在的整串是不是已有文件夹(读不出来算不是)。"""
    try:
        el = _address_el(win)
        if el is None and field is not None and safety.is_address(field.get("name") or field.get("text")):
            el = field["el"]
        return safety.folder_ok(uia.read_element(el) if el is not None else None)
    except Exception:   # noqa: BLE001
        return False


EM_GETSEL = 0x00B0
CARET_KEYS = {"left", "right", "up", "down", "home", "end", "pageup", "pagedown"}
ZERO_W = "\u200b\u200c\u200d\ufeff"     # 看不见的字符:网页编辑框空着时读回来就是这些(11-15 WorkBuddy)


def _caret(h, target):
    """光标位置(起点, 选中长度),读不到 None(11-15)。标准编辑框(老记事本、RichEdit)直接问它选区;别的走 UIA 文本模式。只读。"""
    try:
        if target and W.cls(target).lower().startswith(("edit", "richedit")):
            out = ctypes.c_size_t(0)
            if inputs.u.SendMessageTimeoutW(target, EM_GETSEL, 0, 0, 0x0002, 500, ctypes.byref(out)):   # SMTO_ABORTIFHUNG
                v = out.value & 0xFFFFFFFF
                a, b = v & 0xFFFF, (v >> 16) & 0xFFFF       # 只给低 16 位(超过 6 万多字会绕回,只拿来比前后够用)
                return a, b - a
    except Exception:   # noqa: BLE001
        pass
    try:
        return uia.caret(h)
    except Exception:   # noqa: BLE001
        return None


def press(app, key, *mods, at=None):
    """后台按键。at = 先后台点一下的位置(Chrome / Electron 换了进程或被切过前台后,不先点收不到键,11-11 真机)。"""
    try:
        win = _win(app)
        safety.check_keys(key, mods, win["exe"])
    except (safety.Refused, ValueError) as ex:
        return _refused(ex)
    h = win["hwnd"]
    field = None
    if at is not None:
        ax_, ay_, field = _resolve(app, at, h)
        try:
            _check_name(field, win)  # 11-23 C-4.0 Fable 复查:带 target 按键会先点它,危险名字的按钮同样不点
        except safety.Refused as ex:
            return _refused(ex)
        if field is None:            # at 是截图位置:截图不可信就不点也不打(11-15)
            bad = _stale_pixel(h)
            if bad:
                return bad
        r0 = tap(app, (ax_, ay_), real=False, stale_check=False)
        if r0["outcome"] in ("refused", "busy"):     # 11-17:排不上队也别接着打(框没点上,字会打到别处)
            return r0
        time.sleep(0.2)
    if _is_browser(win):
        f = _known_field(win, field)
        if safety.key_enters(key, mods):
            if f is None:
                return _refused(NEED_FIELD)
            if f.get("password"):
                return _refused("光标在密码框里,这个键会改里面的内容,SeeU 不按(这一步请你自己来)")
    if (len(str(key)) == 1 or safety.norm_key(key) == "space") and not set(m.lower() for m in mods) - {"shift"} \
            and _in_address(win, field):
        return _refused(safety.NOT_ADDRESS_KEY)      # 11-23 C-4.0 Fable 复查:一个个按字符拼出命令,再打文件夹路径带回车就绕过去了
    if safety.norm_key(key) in ("return", "enter") and _in_address(win, field):
        # 11-23 C-3.9:地址栏里回车 = 运行里面的东西 → 只在地址栏里现在是已有文件夹时才按(读不出来也不按)
        cur = None
        try:
            el = _address_el(win)
            if el is None and field is not None and safety.is_address(field.get("name") or field.get("text")):
                el = field["el"]
            cur = uia.read_element(el) if el is not None else None
        except Exception:   # noqa: BLE001
            cur = None
        if not safety.folder_ok(cur):
            return _refused(safety.NOT_FOLDER_ENTER)
    target = inputs.type_target(h)
    if safety.key_enters(key, mods) and _secret_focus(h, target):
        return _refused("光标在密码框里,这个键会改里面的内容,SeeU 不按(这一步请你自己来)")
    mods = [safety.MOD_ALIAS.get(m.lower(), m.lower()) for m in mods]
    # 只给不带修饰键的挪光标键读(省时间;Shift+End 这种改的是选区,11-15 复查)
    car0 = _caret(h, target) if safety.norm_key(key) in CARET_KEYS and not mods else None
    r = _ladder(h, [("后台按键", lambda: inputs.key(h, safety.norm_key(key), mods, target=target))], read=_reader(h))
    if safety.moves_focus(key, mods):
        # 11-23 C-3.9 整体复查:Tab 这类键按完,光标可能已经到了别的框(比如密码框)—— 记住的那个输入框不能再当「光标所在的框」;
        # 之后在用户自己的浏览器里不带 target 打字会被要求重新指定输入框(那时会查它是不是密码框)
        _FIELD.pop(h, None)
    if r["outcome"] == "ineffective" and car0 is not None:
        # 11-15:End / Home / 方向键只挪光标,画面几乎不变 → 读光标位置核实(Win10 验收时各家按 End 全是「核实不了」)
        car1 = _caret(h, target)
        if car1 is not None and car1 != car0:
            r.update(outcome="delivered", note=f"光标从第 {car0[0]} 个字挪到了第 {car1[0]} 个字",
                     tried=r["tried"][:-1] + [(r["tried"][-1][0], "delivered")])
            return r
    if r["outcome"] == "ineffective":
        r.update(outcome="unverified", reason="按了,画面和文字没变(Tab、方向键这类常常就不变);要确认就 see 一下")
    return r


def scroll(app, dy=0, dx=0, at=None):
    try:
        win = _win(app)
    except safety.Refused as ex:
        return _refused(ex)
    h = win["hwnd"]
    if at is None:
        x0, y0, w, hh = win["rect"]
        at = (x0 + w / 2, y0 + hh * 0.55)
    elif not isinstance(at, (tuple, list)):
        x, y, _ = _resolve(app, at, h)
        at = (x, y)
    how = []
    _cursor(h, "move", at[0], at[1])
    steps = [("后台滚动", lambda: how.append(inputs.scroll(h, round(at[0]), round(at[1]), dy, dx)))]
    if win["class"] == "Chrome_WidgetWin_1":
        # Chrome 的滚动条消息要真鼠标在它窗口里才认(11-12 Win10 真机),不认就改走辅助功能的滚动接口
        def _uia_scroll():
            if not uia.scroll(h, round(at[0]), round(at[1]), dy, dx):
                raise RuntimeError("辅助功能里找不到能滚的区域")
            how.append("辅助功能滚动")
        steps.append(("后台滚动(辅助功能)", _uia_scroll))
    r = _ladder(h, steps)
    if how:
        r["how"] = how[-1]
    if r["outcome"] == "ineffective" and win["class"] == "Chrome_WidgetWin_1" and not any(
            c["class"] == "Chrome_RenderWidgetHostHWND" for c in W.children(h)):
        r["reason"] = ("这个 Chrome / Edge 窗口现在没开网页内容的辅助功能(没有网页内容子窗口),后台滚动它不认(11-11 真机:Chrome 157 "
                       "平时不建这个子窗口)。网页请改用 SeeU 专用浏览器(seeu_web_open),那条路能滚;或者借用户的鼠标滚")
    return r


# ─────────────────────────────── 命令行 ───────────────────────────────

USAGE = """SeeU(Windows 预览):python -m seeu see|tap|type|scroll|press|longpress|drag|windows|探一下 <App> ...
  python -m seeu windows                     列出开着的窗口(App 写程序名就行,如 Notepad、chrome)
  python -m seeu see Notepad                 截图 + 编号清单
  python -m seeu tap Notepad 3               按编号点(也可写名字,或屏幕点 x y)
  python -m seeu type Notepad "你好" [--enter] [--at 编号]
  python -m seeu scroll Notepad -600         负数 = 往下翻
  python -m seeu press Notepad a ctrl [--at 编号]   按键(可带 ctrl / shift / alt)
  python -m seeu longpress Notepad 3 [毫秒]      长按(编号 / 名字 / 屏幕点 x y,默认 1000 毫秒)
  python -m seeu drag Paint 100 200 400 200 [...] 拖动:屏幕点 x y 依次排(至少两个点)
  python -m seeu 探一下 Notepad              只读看看这个程序 SeeU 能怎么用
  python -m seeu 检查                        看这台电脑上 SeeU 能不能用、缺什么
  python -m seeu 设置 [借用鼠标 开|问我|关]    看 / 改设置
  python -m seeu isee on|off|status|report   I See(我知风险)开关;开只能你自己在 cmd / PowerShell 里敲
  python -m seeu 接入 claude|codex|cursor|trae|vscode   一键接进 AI 客户端(移除:python -m seeu 移除 …)
  python -m seeu 更新 [--check]              更新到 GitHub 上的新版(git clone 装的才行)
  python -m seeu 取证 [--shot]               出事时一键记下现场
  python -m seeu 版本
Chrome、VS Code 这类:打字、按键前先 --at 输入框(被切过前台后不先点收不到)。
App 开着好几个窗口:写成 Notepad「标题里的几个字」。"""


USAGE_EN = """SeeU (Windows preview): python -m seeu see|tap|type|scroll|press|longpress|drag|windows|probe <App> ...
  python -m seeu windows                     list the open windows (App = the program name, e.g. Notepad, chrome)
  python -m seeu see Notepad                 screenshot + numbered list
  python -m seeu tap Notepad 3               click by number (or a name, or a screen point x y)
  python -m seeu type Notepad "hello" [--enter] [--at number]
  python -m seeu scroll Notepad -600         negative = scroll down
  python -m seeu press Notepad a ctrl [--at number]   press a key (with ctrl / shift / alt)
  python -m seeu longpress Notepad 3 [ms]    long-press (number / name / screen point x y, default 1000 ms)
  python -m seeu drag Paint 100 200 400 200 [...]  drag through screen points x y (at least two)
  python -m seeu probe Notepad               read-only look at how SeeU can work with this program
  python -m seeu check                       see whether SeeU can run on this PC and what's missing
  python -m seeu set [borrow-mouse on|ask|off]   show / change settings
  python -m seeu isee on|off|status|report   I See (I know the risks); only you can turn it on, typing it in cmd / PowerShell
  python -m seeu install claude|codex|cursor|trae|vscode   connect an AI client (remove: python -m seeu uninstall ...)
  python -m seeu update [--check]            update to the new version on GitHub (git clone installs only)
  python -m seeu evidence [--shot]           record what's on screen when something goes wrong
  python -m seeu version
Chrome, VS Code and the like: pass --at <field> before typing or pressing keys.
Several windows of one app: write Notepad「part of the title」."""


def _say(s):
    """命令行出口:英文界面时转英文(用给 AI 的那张对照表;11-14)。"""
    try:
        from seeu.win import lang
        if lang.is_en():
            from seeu.win import mcp_server
            s = mcp_server.en(str(s))
    except Exception:   # noqa: BLE001
        pass
    print(s)


def _usage():
    try:
        from seeu.win import lang
        print(USAGE_EN if lang.is_en() else USAGE)
    except Exception:   # noqa: BLE001
        print(USAGE)


def _report(r):
    if isinstance(r, Exception):
        if isinstance(r, safety.Refused):
            _say(f"refused  {r}")
            return 3
        _say(f"failed  {r}")
        return 1
    try:
        from seeu.win import lang
        en = lang.is_en()
    except Exception:   # noqa: BLE001
        en = False
    _say(f"{r['outcome']}  route={r.get('route')}  tried={r.get('tried')}" if en else
         f"{r['outcome']}  路线={r.get('route')}  试过={r.get('tried')}")
    print(("screenshot=" if en else "截图=") + str(r.get("png")))        # 路径是数据,不过对照表(中文文件夹名会被换掉)
    for k in ("note", "reason", "how", "borrow", "enter"):
        if r.get(k):
            _say(f"{k}  {r[k]}")
    return 0 if r["outcome"] == "delivered" else (3 if r["outcome"] == "refused" else 1)


def _bad_args(cmd, rest):
    """命令行参数够不够、该是数字的是不是数字。有问题返回一句说明,没问题返回 None。"""
    num = lambda x: x.replace(".", "", 1).lstrip("-").isdigit()       # noqa: E731
    if "--at" in rest and rest.index("--at") == len(rest) - 1:
        return "参数不全:--at 后面要写输入框的编号或名字"
    plain = [x for i, x in enumerate(rest) if x not in ("--enter", "--at") and not (i and rest[i - 1] == "--at")]
    if cmd in ("tap", "type", "press", "longpress", "长按") and not plain:
        return "参数不全:" + {"tap": "tap 要写点哪里(编号、名字,或屏幕点 x y)", "type": "type 要写打什么字",
                             "press": "press 要写按哪个键"}.get(cmd, "longpress 要写按哪里(编号、名字,或屏幕点 x y)")
    if cmd == "scroll" and not all(num(x) for x in rest[:2]):
        return "参数不对:scroll 后面要写数字(负数 = 往下翻)"
    if cmd in ("drag", "拖动") and not all(num(x) for x in rest):
        return "拖动要给屏幕点 x y,至少两个点:python -m seeu drag <App> x1 y1 x2 y2 [...]"
    return None


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if a[:1] == ["windows"]:
        for w in W.list_windows():
            why = safety.why_not(w) or ("管理员窗口,SeeU 碰不了" if w.get("elevated") and not W.self_elevated() else None)
            if why:                          # 只转「为什么不碰」那一句:窗口标题是数据,不过对照表(也免得把对齐的空格挤掉)
                try:
                    from seeu.win import lang as _lg
                    if _lg.is_en():
                        from seeu.win import mcp_server as _ms
                        why = _lg.tx(str(why), _ms.WIN_PHRASES)
                except Exception:   # noqa: BLE001
                    pass
            print(f"{w['hwnd']:>9}  {w['exe']:<24} {w['title'][:60]}" + (f"   ⛔ {why}" if why else ""))
        return 0
    if len(a) < 2:
        _usage()
        return 2
    cmd, app, rest = a[0], a[1], a[2:]
    bad = _bad_args(cmd, rest)       # 11-23 C-3.9 整体复查:参数不全 / 不是数字时给用法,不出 traceback
    if bad:
        _say(bad)
        _usage()
        return 2
    try:
        if cmd == "see":
            v = see(app)
            from seeu.win import lang as _lg
            print(_lg.L("窗口: ", "Window: ") + f"{v['window']['title']}  ({v['window']['exe']}, #{v['window']['hwnd']})")
            print(describe(v["items"]))
            if v["windows"]:
                print(_lg.L("这个程序开着好几个窗口:", "This program has several windows open:"), " | ".join(v["windows"]))
            if v.get("note"):
                _say(v["note"])
            if v.get("stale"):
                _say("截图可能是旧画面:" + v["stale"] + "。按编号操作照常;按截图位置点会先被拦下。"
                     + {COVER_WHY: "请让窗口露出来一点再 see", DESK_WHY: "请切到那个桌面再 see"}.get(v["stale"], "等几秒再 see"))
            print(_lg.L("截图:", "Screenshot:"), v["png"])
            return 0
        if cmd == "tap":
            t = (float(rest[0]), float(rest[1])) if len(rest) == 2 and all(
                x.replace(".", "").lstrip("-").isdigit() for x in rest) else rest[0]
            return _report(tap(app, t))
        if cmd == "type":
            at = rest[rest.index("--at") + 1] if "--at" in rest else None
            words = [x for i, x in enumerate(rest) if x not in ("--enter", "--at") and not (i and rest[i - 1] == "--at")]
            return _report(type(app, " ".join(words), enter="--enter" in rest, at=at))
        if cmd == "scroll":
            return _report(scroll(app, dy=float(rest[0]) if rest else -300, dx=float(rest[1]) if len(rest) > 1 else 0))
        if cmd in ("longpress", "长按"):
            num = lambda x: x.replace(".", "").lstrip("-").isdigit()       # noqa: E731
            if len(rest) >= 2 and num(rest[0]) and num(rest[1]):     # 屏幕点 x y [毫秒]
                t, more = (float(rest[0]), float(rest[1])), rest[2:]
            else:
                t, more = rest[0], rest[1:]
            ms = int(more[0]) if more and more[0].isdigit() else 1000
            return _report(long_press(app, t, ms))
        if cmd in ("drag", "拖动"):
            nums = [float(x) for x in rest]
            if len(nums) < 4 or len(nums) % 2:
                _say("拖动要给屏幕点 x y,至少两个点:python -m seeu drag <App> x1 y1 x2 y2 [...]")
                return 2
            return _report(drag(app, list(zip(nums[::2], nums[1::2]))))
        if cmd == "press":
            at = rest[rest.index("--at") + 1] if "--at" in rest else None
            keys = [x for i, x in enumerate(rest) if x != "--at" and not (i and rest[i - 1] == "--at")]
            return _report(press(app, keys[0], *keys[1:], at=at))
    except (RuntimeError, safety.Refused) as ex:
        return _report(ex)
    _usage()
    return 2


# ─────────────────────────────── 多任务调度(11-17 C-2.6,照 Mac act.py 末尾;见 seeu/sched.py) ───────────────────────────────
# 对外动作统一包一层:同一个窗口一次一个任务(排队、动完接着占几秒)、排太久按位置点先核画面、记录用时。
# Windows 按窗口分(打字、点击直投目标窗口,不同窗口互不干扰);内部互相调用(type 里先点框)按同一进程嵌套只在最外层占 / 让。

def shoot(app):
    """排队前先截一张(轮到时比画面用)。返回 W.capture 的 (w, h, BGRA);截不到 None。"""
    try:
        return _shot(_win(app)["hwnd"])
    except Exception:   # noqa: BLE001
        return None


STALE_BOX_PX = 60       # 防过时只比点击点上下左右这么多像素(同 _changed 的 near)


def _stale_change(app, before, pt=None):
    """排队前后这个窗口变了多少(0~1)。pt = 点击的屏幕点 → 只比它附近,别处一直在动(视频、转圈)不算。
    窗口大小变了算全变;截不到返回 None(不拦)。"""
    if not before:
        return None
    try:
        win = _win(app)
        after = _shot(win["hwnd"])
    except Exception:   # noqa: BLE001
        return None
    if not after:
        return None
    if before[0] != after[0] or before[1] != after[1]:
        return 1.0
    box = None
    if isinstance(pt, (tuple, list)) and len(pt) >= 2:
        rx, ry = _rel(win, float(pt[0]), float(pt[1]))
        r = STALE_BOX_PX
        box = (int(rx - r), int(ry - r), int(rx + r), int(ry + r))
    return W.diff_percent(before[2], after[2], box=box, w=after[0] if box else 0, step=2) / 100.0


try:
    from seeu import sched as _sched

    def _by_pos(args, kwargs):
        """按位置点 → 返回那个屏幕点(防过时只比它附近);按编号 / 名字 → None(轮到时会重新找控件)。"""
        t = args[0] if args else kwargs.get("target")
        return tuple(t[:2]) if isinstance(t, (tuple, list)) and len(t) >= 2 else None

    _raw_shot = _shot

    def _shot(hwnd):                                   # noqa: F811 —— 记截图用时(任务窗口协议的数据)
        t0 = time.time()
        try:
            return _raw_shot(hwnd)
        finally:
            _sched.add_heavy("shot", time.time() - t0)

    see = _sched.scheduled("see", lease=False)(see)
    tap = _sched.scheduled("tap", positional=_by_pos, focus=True)(tap)
    long_press = _sched.scheduled("long_press", positional=_by_pos, focus=True)(long_press)
    drag = _sched.scheduled("drag", positional=lambda a, k: (lambda p: tuple(p[0][:2]) if p else True)(a[0] if a else k.get("pts")),
                            focus=True)(drag)
    # 外部评审 11-17:不带输入框(at)的打字 / 按键往「当前焦点」里送 → 上一步之后别的任务动过焦点就不做;带 at 的一次占用里先点框再打
    # 11-23 C-3.9 整体复查:at 是屏幕点(按截图位置先点框)的打字 / 按键,排队太久才轮到也先核画面(跟单独按位置点一样;
    # Mac 是 mcp_server 里 sched.hold(app, pt=…) 做的)。at 是编号 / 名字 → None(轮到时重新找控件)
    def _at_pos(v):
        return tuple(v[:2]) if isinstance(v, (tuple, list)) and len(v) >= 2 else None

    type = _sched.scheduled("type", positional=lambda a, k: _at_pos(k.get("at", a[2] if len(a) > 2 else None)), focus=True,   # noqa: A001
                            focus_check=lambda a, k: k.get("at", a[2] if len(a) > 2 else None) is None)(type)
    press = _sched.scheduled("press", positional=lambda a, k: _at_pos(k.get("at")), focus=True,
                             focus_check=lambda a, k: k.get("at") is None)(press)
    scroll = _sched.scheduled("scroll")(scroll)
except Exception:   # noqa: BLE001 —— 调度模块出问题不影响 SeeU 本身
    pass
