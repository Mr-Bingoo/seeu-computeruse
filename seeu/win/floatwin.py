# -*- coding: utf-8 -*-
"""SeeU Windows 版浮标(第一步):只写「SeeU」的胶囊 ↔ 单任务文字卡片。

样子照 Mac 版现在的样子(seeu_lib/watch_window.py;实地截图量的数):
  胶囊 92×32(紫色呼吸圆点 +「SeeU」,任何时候只写 SeeU,不写进度 / 个数);
  点一下从右上角长成卡片 300×68:第一行「项目 · App」小字,第二行「正在…」大字;卡住时 300×87:「卡住了: 原因」+「怎么办: …」。
  鼠标移到卡片上,右上角出现「收起」;按住能拖;深浅色跟系统。
做法:直接调系统接口(分层窗口 + GDI+,纯 ctypes,不装东西)。
🔴 窗口永远不抢前台、不拿键盘(WS_EX_NOACTIVATE + WM_MOUSEACTIVATE 返回不激活)。
做不到的:Mac 的模糊玻璃(Windows 的系统模糊不给胶囊形用),用接近不透明的底色代替。
已做:接进 MCP 动作(mcp_server.float_step)、借鼠标 / 键盘提示(borrow)、按钮栏(灯光三档 / I See / 原因 / 收起)、屏幕四周光圈。
I See 按钮:只在网页任务出现;🔴 只有用户亲手的真鼠标点击能开(发消息、后台点击都开不了,SeeU 的安全底线也不碰自己的浮标),关谁都能关。
多任务灵动岛:≥2 个任务同时在跑时换成岛(island / ordered / alive_tasks)。
看画面:普通程序的任务,按钮栏上点「看画面」,卡片换成被操作窗口的实时小画面(一秒 5 张,后台截、不抢前台),点击位置有波纹和小圆点;
  再点一下回文字卡,选过会记住。网页任务(专用浏览器没有窗口)、窗口最小化了、多任务岛上看不了。
还没做:文字微光、悬浮标在屏幕中间时从顶上撑开、多显示器、看画面的小窗拉边缩放。

别的程序这样用(显示进程没起会自己拉起):
  from seeu.win import floatwin as fw
  fw.browser("Chrome", "读网页", who="Demo")                    # 出现 / 续时,卡片写「正在读网页」
  fw.stuck("Chrome", "选下拉框", "找不到下拉框", "手动选一下")   # 卡住:自动展开说清楚
  fw.send("expand") / fw.send("collapse") / fw.send("hide") / fw.send("quit")
命令行:python -m seeu.win.floatwin serve | demo [秒] | expand | collapse | hide | quit
"""
import ctypes
import json
import math
import os
import socket
import subprocess
import sys
import time

if __name__ == "__main__":
    # 浮标用 `python -m seeu.win.floatwin serve` 拉起,这份代码在 sys.modules 里叫 __main__;别处再 import
    # seeu.win.floatwin 会另起一份(SERVING / HAND_T 对不上,I See 按钮开不了)→ 登记成同一个
    sys.modules.setdefault("seeu.win.floatwin", sys.modules[__name__])

PORT = 47833                 # 跟 Mac 版悬浮窗同一个号(各在各的机器上)
M = 16                       # 画布四周留给阴影和回弹
CAP_W, CAP_H = 92, 32
CARD_W, CARD_H, CARD_H_STUCK = 300, 68, 87
CARD_H_MAX = CARD_H_STUCK + 19                  # 两行小字时(原因 + I See 说明)
BORDER, PIC_R, PIC_MAX_H = 6, 10, 330           # 看画面:画面四周的边宽、画面圆角(同 Mac)、画面最高多少(太长的窗口缩着放)
RING_S, DOT_S = 0.6, 3.0                        # 点击波纹时长、最后一次点击位置的小圆点留多久(同 Mac)
VIEW_MIN_W, VIEW_MAX_W = 180, 700                # 看画面拉边缩放:卡片最窄 / 最宽(Mac 是 150~700;这里按钮栏 180 以下会叠)
VIEW_FIT, EDGE = 0.9, 6                         # 宽高都不超过屏幕可用区的九成;离卡片边这么近算「在边上」(同 Mac)
VIEW_FPS = 5                                    # 看画面时一秒截几次被操作的窗口
ISLAND_W, OPEN_R = 320, 18                      # 多任务岛展开宽(里面的顶卡 300 = 单任务卡片宽)、圆角(同 Mac)
MAX_ROWS = 2                                    # 岛上顶卡下面最多列几行,更多的叠起来(点一下展开全部)
MAX_ROWS_ALL = 8                                # 展开全部时最多列几行(再多不画,防止长出屏幕)
HOLD_S = 8                                      # 顶上那个任务至少停几秒才换(防几个任务一起跑时来回跳)
TASK_KEEP_S = 60                                # 任务这么久没动静就不算在跑了(卡住的留着等人处理)
CW, CH = ISLAND_W + 2 * M, CARD_H_MAX + 2 * M   # 画布:宽按岛算;高是单任务时的,岛更高时显示进程会换一块更高的
ISEE_NOTE = "我已知风险，授权 AI 执行 · 卡住时请立即报告！"   # I See 开着时卡片上的一行(同 Mac 版的原话)
ANIM_S = 0.38
H_ANIM_S = 0.25                                 # 卡片高度变了(文字卡 ↔ 画面、原因开关、多一行说明)过渡多久
NOTE_LINE = 15                                  # 原因折到第二行时多出来的高
SHIM_W, SHIM_SPEED, SHIM_PERIOD, ACTIVE_S = 48.0, 150.0, 5.0, 3.0   # 文字微光:亮带宽、每秒扫多远、几秒一轮;最近几秒有动作才扫(同 Mac)
BREATH_S = 2.2
HIDE_AFTER_S = 120           # 这么久没收到消息就消失(Mac:1 分钟收成悬浮标 + 再留 1 分钟)
STUCK_KEEP_S = 3600          # 卡住时展开着的悬浮窗最多留 1 小时(同 Mac);你点收起 / AI 接着干活照旧
SUB_A = 0.62                 # 小字透明度(同 Mac)
BORROW_HOLD_S = 2.5          # 借鼠标 / 键盘的提示:最后一次借用消息后留这么多秒再收回(同 Mac)
ORANGE = (255, 159, 10)      # 借用系统鼠标时的颜色(同 Mac)
TB_H, TB_FONT, ICON_R = 28, 13, 7      # 按钮栏高、字号、图标圆的半径(同 Mac)
LIGHT_H = 20                           # 灯光选项条高
LIGHTS = ("off", "real", "bg")         # 灯光三档:关 / 抢占(借用鼠标时亮,橙)/ 被控(只要在操作就亮,紫)
LIGHT_LABEL = {"off": "关", "real": "抢占", "bg": "被控"}
GLOW_W, GLOW_FADE_S, GLOW_PERIOD_S, GLOW_BREATH = 26, 0.35, 1.8, 0.55   # 屏幕四周光圈:宽、淡入淡出、呼吸一轮、呼吸幅度(同 Mac)
BORROW_TEXT = {"mouse": ("正在用你的鼠标", "别动鼠标,几秒后还你"), "keyboard": ("正在用你的键盘", "别碰键盘,几秒后还你")}

# ───────── 英文:代码里流转的还是中文,画出来之前才翻;语言跟 Mac 一样看 设置.json「语言」/ 环境变量 SEEU_LANG ─────────
# 能用 Mac 版 seeu/i18n.py 里现成译法的照用(定好的那套),这里只放 Windows 浮标自己多出来的
UI_EN = {
    "灯光": "Glow", "原因": "Why", "关": "Off", "抢占": "Takeover", "被控": "Controlled",
    "看操作": "Steps", "看画面": "Screen", "收起": "Hide", "等下一步": "Waiting", "折叠 ⌃": "Fold ⌃", "刚刚": "just now",
    ISEE_NOTE: "I accept the risks and authorize AI to act · report if stuck right away!",
    "正在用你的鼠标": "Using your mouse", "别动鼠标,几秒后还你": "Don't move the mouse, back in a few seconds",
    "正在用你的键盘": "Using your keyboard", "别碰键盘,几秒后还你": "Don't touch the keyboard, back in a few seconds",
    "隐身中,看不了画面": "Working hidden, no screen to show",
    "窗口最小化或关了,看不了画面": "Window gone, no screen to show",
    "不知道在操作哪个窗口,看不了画面": "Unknown window, no screen to show",
}
STEP_EN = {"点击": "Clicking", "打字": "Typing", "按键": "Pressing keys", "读网页": "Reading page", "勾选": "Checking",
           "选下拉框": "Choosing option", "滚动": "Scrolling", "长按": "Long-pressing", "开标签页": "Opening tab", "列标签页": "Listing tabs"}
_LANG = {"t": 0.0, "en": False}


def is_en():
    """现在是不是英文界面。问 seeu.i18n(它自己 2 秒才读一次设置);问不到就按中文。测试可设 SEEU_LANG=zh|en。"""
    try:
        from seeu.i18n import lang
        return lang() == "en"
    except Exception:   # noqa: BLE001
        return False


def tr(s):
    """界面上固定的那些词:英文界面时换成英文,没收录的原样。"""
    return UI_EN.get(s, s) if is_en() else s


def tr_step(step):
    """步骤名(调用方给的中文:点击 / 打字 / 点「xx」…)→ 当前语言。认不出的原样(AI 自己写的步骤本来就是它的语言)。"""
    if not step or not is_en():
        return step
    if step in STEP_EN:
        return STEP_EN[step]
    if step.startswith("点「") and step.endswith("」"):
        return "Clicking “%s”" % step[2:-1]
    return step


def tr_reason(s):
    """卡住的原因、怎么办(程序里写的中文)→ 英文界面时按 Mac 版给 AI 用的那张对照表转;没收录的片段原样留着。"""
    if not s or not is_en():
        return s
    try:
        from seeu.reason_en import to_en
        return to_en(s)
    except Exception:   # noqa: BLE001
        return s


def doing(step):
    """「正在xx」:英文是「xx…」(同 Mac 的 card.doing)。"""
    return (tr_step(step) + "…") if is_en() else ("正在" + step)


def stuck_line(why):
    return ("Stuck: " if is_en() else "卡住了: ") + tr_reason(why)


def todo_line(todo):
    return ("What to do: " if is_en() else "怎么办: ") + tr_reason(todo or "")
FONT = "Microsoft YaHei UI"
THEMES = {
    "dark": dict(glass=(42, 41, 49, 250), line=(255, 255, 255, 44), ink=(237, 237, 240), dot=(143, 137, 212)),
    "light": dict(glass=(238, 238, 243, 250), line=(255, 255, 255, 215), ink=(26, 28, 31), dot=(127, 119, 221)),   # 浅色没实地量,照 Mac 代码的字色
}


def _home(*p):
    return os.path.join(os.environ.get("SEEU_HOME") or os.path.expanduser("~/.seeu"), *p)


LIVE_FILE = _home("seeu_float_live.json")     # 浮标上的开关:light(灯光档位)、why_off(原因关着)


def live():
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_live(**kw):
    d = live()
    d.update(kw)
    try:
        os.makedirs(os.path.dirname(LIVE_FILE), exist_ok=True)
        tmp = LIVE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, LIVE_FILE)
    except OSError:
        pass


def light_level():
    """灯光档位;从没设过 = 抢占(只在借用鼠标时亮,同 Mac 默认「仅让路模式」)。"""
    v = live().get("light")
    return v if v in LIGHTS else "real"


SERVING = False     # 本进程是不是浮标显示进程(serve 里置真)
HAND_T = 0.0        # 最近一次认出「手按」的时间(isee.on(by="overlay") 用)


# ───────── 调用方用的(不依赖 Windows,任何平台都能导入) ─────────
def send(*parts):
    """给显示进程发一条消息;发不出去不报错(浮标只是显示,不能拖累干活)。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(json.dumps(list(parts), ensure_ascii=False).encode("utf-8"), ("127.0.0.1", PORT))
        s.close()
    except OSError:
        pass


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
    """显示进程没起就拉起(无窗口、跟调用方脱钩);环境变量 SEEU_NO_WATCH=1 时不起(测试用,同 Mac)。"""
    if os.environ.get("SEEU_NO_WATCH") == "1" or sys.platform != "win32" or _running():
        return
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    env = dict(os.environ)
    lib = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
    args = [pyw if os.path.exists(pyw) else py, "-m", "seeu.win.floatwin", "serve"]
    for flags in (0x00000008 | 0x01000000 | 0x00000200, 0x00000008 | 0x00000200):   # 先试脱离作业,被拒(Codex 里)就不带
        try:
            subprocess.Popen(args, env=env, creationflags=flags, close_fds=True)
            break
        except OSError:
            continue
    for _ in range(40):          # 最多等 4 秒
        if _running():
            return
        time.sleep(0.1)


def who_name(who=None):
    """任务名:调用方传的 > 环境变量 SEEU_PROJECT(项目)> SEEU_TASK_DISPLAY(同 Mac:SeeU 调度起的显示名,
    AI 会话叫 Claude、Claude2…,跟排队提示、光标名牌对得上)。没有就 ""。"""
    return str(who if who is not None else (os.environ.get("SEEU_PROJECT") or os.environ.get("SEEU_TASK_DISPLAY") or "")).strip()


def browser(app, step="", who=None, note="", web=False, wid=0):
    """note = 这一步的原因(AI 填的 why),卡片上「正在…」下面一行灰字。
    web = 这是 SeeU 专用浏览器里的网页任务(按钮栏上才出 I See 按钮;I See 只管这条路,同 Mac「只在浏览器任务里出现」)。"""
    ensure_serve()
    send("browser", app, step, who_name(who), note or "", bool(web), int(wid or 0))


def queue(app, on=True, pos=1, holder="", who=None, color=None):
    """同 Mac watch_window.queue:这个任务在排队等 app(on=False 排完了)。pos = 排第几,holder = 谁占着,
    color = 任务光标色 "#RRGGBB"。岛把它放进下段「排队中」(变暗、右边 zZ)。旧版显示进程不认识,直接忽略。"""
    if os.environ.get("SEEU_NO_WATCH") == "1" or sys.platform != "win32":
        return
    if on:
        ensure_serve()
    send("queue", str(app or ""), 1 if on else 0, int(pos or 1), str(holder or ""), who_name(who), str(color or ""))


def tint(color, who=None):
    """这个任务的光标颜色("#RRGGBB"),岛上那行圆点跟它一致。没有任务名不发,不拉起显示进程。"""
    w = who_name(who)
    if not w or not color or os.environ.get("SEEU_NO_WATCH") == "1" or sys.platform != "win32":
        return
    send("tint", w, str(color))


def mark(fx, fy, wid=0):
    """画一下点击位置(看画面时才看得见);fx / fy = 在被操作窗口里的比例 0~1(左上为 0);wid = 点的是哪个窗口。不拉起显示进程。"""
    if sys.platform == "win32" and os.environ.get("SEEU_NO_WATCH") != "1":     # 别的系统上这个端口是别人的;测试时也不发
        send("mark", float(fx), float(fy), int(wid or 0))


def borrow(app="", kind="mouse"):
    """SeeU 要借用户的真鼠标(kind="mouse")或真键盘("keyboard")那几秒:浮标变橙、自动展开写「正在用你的鼠标 / 别动鼠标」,
    这期间浮标不接鼠标(不会挡住要点的地方);最后一次调用后 BORROW_HOLD_S 秒自己恢复原样。"""
    ensure_serve()
    send("borrow", app or "", kind)


def stuck(app, step, why, todo, who=None):
    ensure_serve()
    send("stuck", app, step, why, todo, who_name(who))


# ───────── 每一帧画什么(纯计算,Mac 上也能离线测) ─────────
def ease(x):
    x = max(0.0, min(1.0, x))
    c1 = 0.9
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def breath(t):
    p = 0.5 - 0.5 * math.cos(2 * math.pi * t / BREATH_S)
    return 1 - 0.28 * p, 1 - 0.30 * p


def _a(rgb, a):
    return (rgb[0], rgb[1], rgb[2], int(max(0, min(255, a))))


def fit(text, size, bold, width, measure):
    """太长就截断加「…」。"""
    if measure(text, size, bold) <= width:
        return text
    while len(text) > 1 and measure(text + "…", size, bold) > width:
        text = text[:-1]
    return text + "…"


def wrap2(text, size, width, measure):
    """一行放不下就折成两行(按字折,中文没有空格);第二行还放不下的截断加「…」。返回 1~2 行。"""
    if measure(text, size, False) <= width:
        return [text]
    n = 1
    while n < len(text) and measure(text[:n + 1], size, False) <= width:
        n += 1
    return [text[:n], fit(text[n:].lstrip(), size, False, width, measure)]


def shim_x(now, last):
    """文字微光的亮带此刻扫到哪(离文字左边多少点);最近没动作 = 不扫,返回 None。"""
    if now - last > ACTIVE_S:
        return None
    return -SHIM_W / 2 + SHIM_SPEED * (now % SHIM_PERIOD)


def _shim(prims, tx, cy, text, size, bold, ink, sx, measure, a=1.0):
    """亮带还在这行字的范围里就叠一层微光。"""
    if sx is not None and sx - SHIM_W / 2 < measure(text, size, bold) + 4:
        dark = sum(ink) < 384                      # 深色字上扫白光,浅色字上扫暗光(同 Mac)
        prims.append(("shim", tx, cy, text, size, bold, _a((255, 255, 255) if dark else (26, 26, 26), 255 * (0.85 if dark else 0.5) * a), sx))


EXPAND_EDGE = 40                                # 悬浮标离屏幕左 / 右边这么近算「贴边」(同 Mac,展开方式 C)


def anchor(capx, left, right, s=1.0):
    """悬浮标(左边在 capx,宽 CAP_W)展开时往哪边长:贴左边 "l" = 从左上角往右长;贴右边 "r" = 从右上角往左长;
    在中间 "c" = 像灵动岛从顶上正中往两边撑开。都是屏幕坐标(像素),s = 缩放。"""
    if capx - left < EXPAND_EDGE * s:
        return "l"
    if right - (capx + CAP_W * s) <= EXPAND_EDGE * s + 1:  # 默认位置正好离右边 40,算贴右边(多让 1 像素:位置取整会差零点几)
        return "r"
    return "c"


def shape_left(capx, w, mode, left, right, s=1.0):
    """外形(现在宽 w 点)的左边该在屏幕哪:按展开方式定,再夹在屏幕里(不出屏幕)。"""
    x = capx if mode == "l" else capx + (CAP_W - w) * s if mode == "r" else capx + (CAP_W - w) * s / 2.0
    return max(left, min(x, right - w * s))


def cap_from_shape(x, w, left, right, s=1.0):
    """反过来:外形被拖到 x(宽 w 点)后,悬浮标该记在哪 —— 贴边就收在那一角,其余收在顶上正中(同 Mac 的 cap_from_panel)。"""
    if x - left < EXPAND_EDGE * s:
        return x
    if right - (x + w * s) <= EXPAND_EDGE * s + 1:
        return x + (w - CAP_W) * s
    return x + (w - CAP_W) * s / 2.0


# ───────── 看画面的大小 + 拉边缩放(规则照 Mac 的 seeu_lib/watch_window.py;这里 aspect = 画面高 / 宽) ─────────
def view_h(w, aspect):
    """看画面时卡片宽 w → 卡片高:上面按钮栏 + 画面按比例 + 下面的边。"""
    return TB_H + (w - 2 * BORDER) * aspect + BORDER


def view_default_w(aspect):
    """没拉过时多宽:跟文字卡一样宽;太高的窗口(竖的)缩到画面最高 PIC_MAX_H。"""
    pw = min(CARD_W - 2 * BORDER, PIC_MAX_H / aspect)
    return max(VIEW_MIN_W, pw + 2 * BORDER)


def view_max_w(aspect, work_w, work_h):
    by_h = (VIEW_FIT * work_h - TB_H - BORDER) / aspect + 2 * BORDER      # 宽到这么多,高就顶到屏幕九成
    return max(VIEW_MIN_W, min(VIEW_MAX_W, VIEW_FIT * work_w, by_h))


def view_fit_w(w, aspect, work_w, work_h):
    return max(VIEW_MIN_W, min(view_max_w(aspect, work_w, work_h), w))


def view_port(aspect):
    return 1.0 / aspect < 0.95                    # 竖的画面;接近正方形归横的(同 Mac)


def view_saved_w(saved, aspect):
    """记住的大小 → 宽:竖的画面记卡片高、横的记卡片宽,各一份(同 Mac);没记过用默认。"""
    v = (saved or {}).get("view_port_h" if view_port(aspect) else "view_land_w")
    if not isinstance(v, (int, float)) or v <= 0:
        return view_default_w(aspect)
    return (v - TB_H - BORDER) / aspect + 2 * BORDER if view_port(aspect) else float(v)


def view_remember(w, aspect):
    return {"view_port_h": round(view_h(w, aspect), 1)} if view_port(aspect) else {"view_land_w": round(w, 1)}


def edge_at(lx, ly, card, e=EDGE):
    """鼠标(画布坐标)在卡片哪条边 / 哪个角上:"l" "r" "t" "b" "tl" "tr" "bl" "br",不在边上返回 ""。"""
    x, y, w, h = card
    if not (x - 2 <= lx <= x + w + 2 and y - 2 <= ly <= y + h + 2):
        return ""
    return ("t" if ly <= y + e else "b" if ly >= y + h - e else "") + ("l" if lx <= x + e else "r" if lx >= x + w - e else "")


def resize_w(edge, w0, dx, dy, aspect):
    """从宽 w0 开始,抓着 edge 拖了 (dx, dy) → 新的宽(还没夹范围)。画面保持比例:拉左右边按宽算,拉上下边由高反推宽,
    拉角取两种里大的(跟着鼠标走,不抖;同 Mac)。"""
    wx = w0 + (dx if "r" in edge else -dx if "l" in edge else 0)
    hy = view_h(w0, aspect) + (dy if "b" in edge else -dy if "t" in edge else 0)
    w_by_h = (hy - TB_H - BORDER) / aspect + 2 * BORDER
    if len(edge) == 2:
        return max(wx, w_by_h)
    return wx if edge in ("l", "r") else w_by_h


def card_lines(info):
    """info(一条任务)→ (名字行, 大字, 小字或 None, 卡片高, 第二行小字或 None)。"""
    name = (info.get("who") + " · " if info.get("who") else "") + (info.get("app") or "SeeU")
    if info.get("borrow"):                        # 借鼠标 / 键盘优先于别的(同 Mac:展开着也写)
        big, small = BORROW_TEXT.get(info["borrow"], BORROW_TEXT["mouse"])
        return name, tr(big), tr(small), CARD_H_STUCK, None
    if info.get("why"):
        return name, stuck_line(info["why"]), todo_line(info.get("todo")), CARD_H_STUCK, None
    step = (info.get("step") or "").strip()
    smalls = [x for x in ((info.get("note") or "").strip(), tr(ISEE_NOTE) if info.get("isee") and info.get("web") else "") if x]
    if step.startswith("正在"):
        step = step[2:]
    return (name, (doing(step) if step else tr("等下一步")), smalls[0] if smalls else None,
            CARD_H + 19 * len(smalls), smalls[1] if len(smalls) > 1 else None)


def bar_buttons(measure, has_why, web=False, W=CARD_W, x0=6):
    """按钮栏上的按钮(卡片内坐标,左上原点):[(名字, x0, x1)]。顺序同 Mac:灯光固定第一、I See 第二而且只在网页任务出现、
    原因(AI 任务才有)… 看画面、收起。"""
    out, x = [], x0
    lw = 4 + 2 * ICON_R + 4 + measure(tr("灯光"), TB_FONT, False) + 6
    out.append(("light", x, x + lw))
    x += lw + 4
    if web:
        iw = 4 + 2 * ICON_R + 4 + measure("I See", TB_FONT, False) + 6
        out.append(("isee", x, x + iw))
        x += iw + 4
    if has_why:
        out.append(("why", x, x + 4 + 2 * ICON_R + 4 + measure(tr("原因"), TB_FONT, False) + 6))
    out.append(("view", W - 58, W - 32))
    out.append(("collapse", W - 30, W - 4))
    return out


def light_items(measure, cur, x0=6):
    """灯光点开后的选项条:[(档, x0, x1)]。当前档原地不动,另两档从它右边伸出来(同 Mac)。"""
    x, out = x0, []
    for lvl in [cur] + [l for l in LIGHTS if l != cur]:
        iw = 4 + 2 * ICON_R + 4 + measure(tr(LIGHT_LABEL[lvl]), TB_FONT, False) + 8
        out.append((lvl, x, x + iw))
        x += iw
    return out


def _icon_light(P, cx, cy, lvl, ink, a=1.0):
    """灯光 = 圆里四个圆角(屏幕四角亮光圈)。关 = 外圈 + 淡四角;开 = 圆里填对应颜色、四角反白。"""
    if lvl == "off":
        mark = _a(ink, 255 * 0.55 * a)
    else:
        P.append(("dot", cx, cy, ICON_R + 0.75, _a(ORANGE if lvl == "real" else (127, 119, 221), 255 * a)))
        mark = (255, 255, 255, int(255 * a))
    P.append(("circ", cx, cy, ICON_R, _a(ink, 255 * 0.88 * a), 1.5))
    # 四个角照 Mac(seeu_lib/watch_island.py light_icon):竖一小段 → 半径 1.1 的圆角 → 横一小段(拐弯要圆的,跟 Mac 一致)
    d, L, R = 2.8, 1.6, 1.1
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.append(("line", cx + sx * d, cy + sy * (d - L), cx + sx * d, cy + sy * (d - R), mark, 1.1))
            P.append(("arc", cx + sx * (d - R), cy + sy * (d - R), R, 0 if sx > 0 else 180, 90 * sx * sy, mark, 1.1))
            P.append(("line", cx + sx * (d - R), cy + sy * d, cx + sx * (d - L), cy + sy * d, mark, 1.1))


def _icon_isee(P, cx, cy, on, ink, inv, a=1.0):
    """I See = 圆里一个点。开 = 实心圆里一个反色的点。"""
    if on:
        P.append(("dot", cx, cy, ICON_R, _a(ink, 255 * 0.95 * a)))
        P.append(("dot", cx, cy, 2.4, _a(inv, 255 * a)))
    else:
        P.append(("circ", cx, cy, ICON_R, _a(ink, 255 * 0.9 * a), 1.5))
        P.append(("dot", cx, cy, 2.4, _a(ink, 255 * 0.9 * a)))


def _icon_why(P, cx, cy, on, ink, inv, a=1.0):
    """原因 = 圆里再一个细圆,里面一大一小两个点斜排。开 = 实心圆 + 反色图形。"""
    if on:
        P.append(("dot", cx, cy, ICON_R, _a(ink, 255 * 0.95 * a)))
        c = _a(inv, 255 * a)
    else:
        c = _a(ink, 255 * 0.9 * a)
        P.append(("circ", cx, cy, ICON_R, c, 1.5))
    P.append(("circ", cx, cy, 3.4, c, 1.05))
    P.append(("dot", cx - 0.8, cy - 0.7, 1.0, c))
    P.append(("dot", cx + 1.2, cy + 1.2, 0.6, c))


def _icon_view(P, cx, cy, c):
    """看画面 = 镜头:圆里一个小圆环 + 中心点,右下一个小指示点。"""
    P.append(("circ", cx, cy, ICON_R, c, 1.5))
    P.append(("circ", cx, cy, 3.0, c, 1.1))
    P.append(("dot", cx, cy, 1.1, c))
    P.append(("dot", cx + 3.3, cy + 3.3, 0.8, c))


def _icon_steps(P, cx, cy, c):
    """看操作 = 三个大小不一的点,排成鼠标指针的三角(尖朝左上)。"""
    P.append(("circ", cx, cy, ICON_R, c, 1.5))
    k = 0.85
    P.append(("dot", cx - 2.2 * k, cy - 2.4 * k, 1.9 * k, c))
    P.append(("dot", cx + 2.6 * k, cy + 0.2 * k, 1.4 * k, c))
    P.append(("dot", cx - 0.9 * k, cy + 2.9 * k, 1.0 * k, c))


def _icon_collapse(P, cx, cy, c):
    """收起 = 圆里左右两道弧 ( )。"""
    P.append(("circ", cx, cy, ICON_R, c, 1.5))
    P.append(("arc", cx - 1.2, cy, 2.6, 120, 120, c, 1.3))
    P.append(("arc", cx + 1.2, cy, 2.6, -60, 120, c, 1.3))


VIEW_OFF = {"web": "隐身中,看不了画面", "gone": "窗口最小化或关了,看不了画面", "none": "不知道在操作哪个窗口,看不了画面"}


def _draw_bar(prims, bx, y, W, x0, measure, theme, ink, inv, light, lk, isee_on, why_on, has_why, web, view=None, mouse=None, view_off="none"):
    """画按钮栏(单任务卡片和多任务岛共用),返回能点的地方 [(名字, x, y, w, h)]。bx = 卡片 / 岛的左边,W = 它的宽。
    view:None = 看不了画面(图标灰着、不能点);"card" = 现在是文字卡(图标 = 看画面);"screen" = 现在在看画面(图标 = 回去看操作)。"""
    hits, tips = [], []
    cy = y + TB_H / 2
    white = _a(ink, 255 * 0.92)
    fa = 1.0 - min(1.0, lk)                       # 灯光选项条伸开时,看画面、收起淡出让位
    for nm, xa, xb in bar_buttons(measure, has_why, web, W, x0):
        ix = bx + xa + 4 + ICON_R
        if nm == "light":
            if lk > 0.001:
                continue                          # 选项条盖住原按钮(下面画)
            _icon_light(prims, ix, cy, light, ink)
            prims.append(("txt", bx + xa + 8 + 2 * ICON_R, cy, tr("灯光"), TB_FONT, False, white, "l"))
        elif nm == "isee":
            if lk > 0.5:
                continue
            _icon_isee(prims, ix, cy, isee_on, ink, inv, 1 - lk)
            prims.append(("txt", bx + xa + 8 + 2 * ICON_R, cy, "I See", TB_FONT, False,
                          _a(ink, 255 * (0.92 if isee_on else SUB_A) * (1 - lk)), "l"))
        elif nm == "why":
            if lk > 0.5:
                continue
            _icon_why(prims, ix, cy, why_on, ink, inv, 1 - lk)
            prims.append(("txt", bx + xa + 8 + 2 * ICON_R, cy, tr("原因"), TB_FONT, False,
                          _a(ink, 255 * (0.92 if why_on else SUB_A) * (1 - lk)), "l"))
        elif fa > 0.01:
            cx = bx + (xa + xb) / 2.0
            if nm == "view":
                if view is None:
                    _icon_view(prims, cx, cy, _a(ink, 255 * fa * 0.28))      # 看不了画面(网页任务 / 不知道是哪个窗口):灰着
                    label = tr(VIEW_OFF.get(view_off, VIEW_OFF["none"]))
                else:
                    (_icon_steps if view == "screen" else _icon_view)(prims, cx, cy, _a(ink, 255 * 0.9 * fa))
                    label = tr("看操作" if view == "screen" else "看画面")
            else:
                _icon_collapse(prims, cx, cy, _a(ink, 255 * 0.92 * fa))
                label = tr("收起")
            # 这两个按钮只有图标:鼠标移上去时在左边冒出名字;看画面灰着时写为什么看不了(同 Mac)
            if mouse and y <= mouse[1] <= y + TB_H and bx + xa <= mouse[0] <= bx + xb:
                label = fit(label, 12, False, W - 76, measure)
                lw_ = measure(label, 12, False)
                lx = bx + max(4.0, W - 62 - lw_)
                dark = sum(ink) < 384
                tips.append(("rr", lx - 6, cy - 10, lw_ + 12, 20, 10, (255, 255, 255, int(255 * 0.92 * fa)) if dark else (41, 41, 46, int(255 * 0.94 * fa))))
                tips.append(("txt", lx, cy, label, 12, False, _a(ink, 255 * 0.9 * fa), "l"))
            if nm == "view" and view is None:
                continue
        if (lk <= 0.5 or nm == "light") and not (nm == "view" and view is None):
            hits.append((nm, bx + xa, y, xb - xa, TB_H))
    if lk > 0.001:                                 # 灯光选项条:原地往右伸
        items = light_items(measure, light, x0)
        sx0, sx1 = bx + items[0][1], bx + items[-1][2]
        pw_ = max(LIGHT_H, (sx1 - sx0) * min(1.0, lk))
        prims.append(("rr", sx0, cy - LIGHT_H / 2, pw_, LIGHT_H, LIGHT_H / 2,
                      (255, 255, 255, 140) if theme == "light" else (0, 0, 0, 77)))
        prims.append(("ring", sx0, cy - LIGHT_H / 2, pw_, LIGHT_H, LIGHT_H / 2, _a(ink, 255 * 0.14), 1.0))
        hits = [hh for hh in hits if hh[0] != "light"]
        for lvl, xa, xb in items:
            if bx + xb > sx0 + pw_ + 0.5:
                break                             # 还没伸到的档先不画
            if lvl == light:
                prims.append(("rr", bx + xa + 1.5, cy - LIGHT_H / 2 + 1.5, xb - xa - 3, LIGHT_H - 3, LIGHT_H / 2 - 1.5,
                              _a(ink, 255 * 0.08)))
            _icon_light(prims, bx + xa + 4 + ICON_R, cy, lvl, ink)
            prims.append(("txt", bx + xa + 8 + 2 * ICON_R, cy, tr(LIGHT_LABEL[lvl]), TB_FONT, False,
                          _a(ink, 255 * (0.92 if lvl == light else SUB_A + 0.1)), "l"))
            hits.append(("light:" + lvl, bx + xa, y, xb - xa, TB_H))
    prims.extend(tips)                             # 小标签盖在别的按钮上面,最后画
    return hits


def scene(k, t, theme, measure, info, hover=False, ui=None):
    """k = 展开程度 0~1(回弹时略超 1);ui = dict(light 档位, light_k 选项条伸展 0~1, why 原因开没开)。
    返回 dict(shape, prims, hits, card):hits = 能点的地方 [(名字, x, y, w, h)](画布坐标)。"""
    T = THEMES[theme]
    ui = ui or {}
    light, lk, why_on = ui.get("light", "real"), ui.get("light_k", 0.0), ui.get("why", True)
    has_why = bool((info.get("note") or "").strip())
    shown = info if why_on or info.get("why") or info.get("borrow") else dict(info, note="")
    isee_on = bool(ui.get("isee"))
    shown = dict(shown, isee=isee_on)
    name, big, small, H, small2 = card_lines(shown)
    can_view = bool(info.get("wid")) and not info.get("web")          # 知道是哪个窗口、而且不是看不见的那份浏览器,才看得了画面
    pic = ui.get("pic") if ui.get("view") == "screen" and can_view and not info.get("borrow") and not info.get("why") else None
    Wt = CARD_W                                   # 卡片该多宽:文字卡固定;看画面时跟着画面(能拉边缩放)
    if pic:                                       # 看画面:上面一条(名字 / 按钮栏)+ 画面,四周留边
        asp_ = max(0.1, min(4.0, pic.get("aspect") or 0.62))
        Wt = ui.get("vw") or view_default_w(asp_)
        H = view_h(Wt, asp_)
    note2 = None
    note_shown = not pic and not info.get("why") and not info.get("borrow") and bool((shown.get("note") or "").strip())
    if note_shown:                                # 原因最多两行(同 Mac)
        nl = wrap2(small, 11.5, CARD_W - 30, measure)
        if len(nl) > 1:
            small, note2, H = nl[0], nl[1], H + NOTE_LINE
    target_h = H
    Wc = Wt
    if ui.get("h_from") is not None:              # 高度(宽度)刚变:从原来的过渡过去
        hk_ = max(0.0, min(1.0, ui.get("h_k", 1.0)))
        H = ui["h_from"] + (H - ui["h_from"]) * hk_
        if ui.get("w_from") is not None:
            Wc = ui["w_from"] + (Wt - ui["w_from"]) * hk_
    if pic:
        pw_ = Wc - 2 * BORDER
        ph_ = pw_ * asp_
    cw = ui.get("cw") or max(CW, Wc + 2 * M)       # 画布宽(显示进程按需要换大的;画布里外形一直靠右)
    w = CAP_W + (Wc - CAP_W) * k
    h = CAP_H + (H - CAP_H) * k
    x, y = cw - M - w, M
    r = min(16 + 2 * min(1.0, max(0.0, k)), h / 2)
    ink = T["ink"]
    inv = (255, 255, 255) if theme == "light" else (26, 26, 26)
    dotc = ORANGE if info.get("borrow") else T["dot"]
    prims = [("rr", x, y, w, h, r, T["glass"]), ("ring", x, y, w, h, r, T["line"], 1.0)]
    bs, ba = breath(t)
    a0 = max(0.0, 1 - 2.5 * k)
    a1 = max(0.0, min(1.0, (k - 0.35) / 0.5))
    if a0 > 0:
        if isee_on:                               # I See 开着:字换成「I See」、圆点换成眼睛,颜色不变(同 Mac)
            prims.append(("eye", x + 16.75, y + 16, 5.6, _a(dotc, 255 * a0 * ba)))
        else:
            prims.append(("dot", x + 16.75, y + 16, 6 * bs, _a(dotc, 255 * a0 * ba)))
        prims.append(("txt", x + 32, y + 16.25, "I See" if isee_on else "SeeU", 15, True, _a(ink, 255 * a0), "l"))
        if a0 > 0.9:
            _shim(prims, x + 32, y + 16.25, "I See" if isee_on else "SeeU", 15, True, ink, ui.get("shim"), measure)
    hits = []
    if a1 > 0:
        bx = cw - M - Wc
        A = 255 * a1
        bar = hover and k > 0.9 and not info.get("borrow")
        if not bar:                               # 平时第一行写「项目 · App」;鼠标移上来换成按钮栏(同 Mac)
            prims.append(("dot", bx + 14.75, y + 13.75, 5 * bs, _a(dotc, A * ba)))
            prims.append(("txt", bx + 27.5, y + 14, fit(name, 12.5, False, Wc - 27.5 - 14, measure), 12.5, False,
                          _a(ink, A * SUB_A), "l"))
        if pic:
            px_, py_ = bx + BORDER, y + TB_H
            if k > 0.85:
                prims.append(("img", px_, py_, pw_, ph_, PIC_R))
                mc = ORANGE if info.get("borrow") else T["dot"]
                for fx, fy, age in pic.get("marks") or []:            # 点击波纹
                    kk = age / RING_S
                    if 0 <= kk <= 1:
                        prims.append(("circ", px_ + fx * pw_, py_ + fy * ph_, 6 + 16 * kk, _a(mc, 255 * 0.9 * (1 - kk)), 2.5))
                dm = pic.get("dot")
                if dm and dm[2] < DOT_S:                              # 最后一次点击位置的小圆点
                    al = 1.0 if dm[2] < DOT_S - 0.5 else (DOT_S - dm[2]) / 0.5
                    prims.append(("dot", px_ + dm[0] * pw_, py_ + dm[1] * ph_, 4, _a(mc, 255 * 0.95 * al)))
                    prims.append(("circ", px_ + dm[0] * pw_, py_ + dm[1] * ph_, 4, (255, 255, 255, int(255 * 0.9 * al)), 1.2))
        elif small:
            bsz = 15 if info.get("why") and not info.get("borrow") else 16
            prims.append(("txt", bx + 15, y + 41.5, fit(big, bsz, True, Wc - 30, measure), bsz, True, _a(ink, A * 0.95), "l"))
            prims.append(("txt", bx + 14.5, y + 64, fit(small, 11.5, False, Wc - 30, measure), 11.5, False, _a(ink, A * SUB_A), "l"))
            dy = 0
            if note2:
                dy = NOTE_LINE
                prims.append(("txt", bx + 14.5, y + 64 + dy, note2, 11.5, False, _a(ink, A * SUB_A), "l"))
            if small2:
                prims.append(("txt", bx + 14.5, y + 83 + dy, fit(small2, 11, False, Wc - 30, measure), 11, False, _a(ink, A * SUB_A), "l"))
            if not info.get("why") and not info.get("borrow") and a1 >= 1:
                _shim(prims, bx + 15, y + 41.5, fit(big, bsz, True, Wc - 30, measure), bsz, True, ink, ui.get("shim"), measure)
        else:
            prims.append(("txt", bx + 15, y + 41.5, fit(big, 16, True, Wc - 30, measure), 16, True, _a(ink, A * 0.95), "l"))
            if a1 >= 1:
                _shim(prims, bx + 15, y + 41.5, fit(big, 16, True, Wc - 30, measure), 16, True, ink, ui.get("shim"), measure)
        if bar:
            hits = _draw_bar(prims, bx, y, Wc, 6, measure, theme, ink, inv, light, lk, isee_on, why_on, has_why,
                             bool(info.get("web")), ("screen" if pic else "card") if can_view and ui.get("pic_ok", True) else None,
                             ui.get("mouse"), "web" if info.get("web") else "none" if not info.get("wid") else "gone")
    return dict(shape=(x, y, w, h, r), prims=prims, hits=hits, card=(cw - M - Wc, y, Wc, H), target_h=target_h, target_w=Wt,
                close=next(((hx, hy, hw, hh) for nm, hx, hy, hw, hh in hits if nm == "collapse"), None))


def pic_ui(task, now, aspect, box=None):
    """看画面时交给 scene 的那份:窗口的高宽比 + 还在扩散的点击波纹 + 最后一次点击的小圆点(都换成「几秒前」)。
    box = 画面只放了整个窗口的哪一块(左, 上, 宽, 高,都是占整窗的比例;裁掉了看不见的那圈边)→ 点击位置跟着换算。"""
    bl, bt, bw, bh = box or (0.0, 0.0, 1.0, 1.0)

    def mp(fx, fy):
        return (max(0.0, min(1.0, (fx - bl) / bw)) if bw > 0 else fx, max(0.0, min(1.0, (fy - bt) / bh)) if bh > 0 else fy)
    marks = [mp(fx, fy) + (now - t_,) for fx, fy, t_ in task.get("marks") or [] if 0 <= now - t_ <= RING_S]
    d = task.get("dotm")
    return dict(aspect=aspect, marks=marks, dot=mp(d[0], d[1]) + (now - d[2],) if d and now - d[2] < DOT_S else None)


def add_mark(task, fx, fy, now):
    """记一次点击位置(比例,超出窗口的夹回边上);波纹只留最近几个。"""
    fx, fy = max(0.0, min(1.0, float(fx))), max(0.0, min(1.0, float(fy)))
    task["marks"] = [m_ for m_ in task.get("marks") or [] if now - m_[2] <= RING_S][-5:] + [(fx, fy, now)]
    task["dotm"] = (fx, fy, now)


# ───────── 多任务岛(≥2 个任务同时在跑;规则和排版照 Mac 的 seeu_lib/watch_island.py) ─────────
def task_key(who, app):
    return (who or "").strip() or (app or "").strip() or "SeeU"


Q_ALPHA = 0.55       # 排队那几行整体的淡度(同 Mac)
Q_FOLD = 2           # 排队超过这么多行就折成「还有 N 个在排队」


def hex_rgb(h):
    """"#RRGGBB" → (r, g, b) 0~255;认不出返回 None。"""
    try:
        h = str(h).strip().lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None
    except ValueError:
        return None


def queued(t):
    """同 Mac:在排队等别的任务用完同一个窗口(借鼠标 / 卡住优先,不算排队)。"""
    return bool(t.get("queued")) and not t.get("borrow") and not t.get("why")


def q_label():
    return "Queued" if is_en() else "排队中"


def q_detail(t):
    """排队行的小字:第几 · 等哪个程序。"""
    q = t.get("queued") or {}
    return ("#%d · waiting for %s" if is_en() else "第 %d · 等 %s") % (int(q.get("pos") or 1), q.get("app") or "")


def zz_alpha(tm):
    """右侧 zZ 的明暗:3 秒一个来回,1 → 0.4 → 1(同 Mac:按绝对时间算,重画不会从头播)。"""
    return 0.7 + 0.3 * math.cos(2 * math.pi * (tm % 3.0) / 3.0)


def kept_t(t):
    """1 小时从什么时候数起:卡住那一刻,或你最后一次碰悬浮窗(三端统一,同 Mac)。"""
    return max(t["last"], t.get("touch") or 0)


def stuck_touch(st, tasks, now):
    """你碰了展开着的悬浮窗(移上去、挪动、点、拖;停着不动不算):还在等人处理的卡住重新数 1 小时。"""
    if not st["open"] or not stuck_waiting(tasks, now):
        return
    for t in tasks.values():
        if t.get("why") and not t.get("ack"):
            t["touch"] = now
    st["last_msg"] = now


def stuck_waiting(tasks, now):
    """有没有卡住了还在等人处理的(你没点过收起、没满 STUCK_KEEP_S)。"""
    return any(t.get("why") and not t.get("ack") and now - kept_t(t) < STUCK_KEEP_S for t in tasks.values())


def hide_after(tasks, now, opened):
    """多久没消息就消失:卡住说明展开着 = STUCK_KEEP_S,平时 HIDE_AFTER_S。"""
    return STUCK_KEEP_S if opened and stuck_waiting(tasks, now) else HIDE_AFTER_S


def lone_stuck(alive):
    """只剩一个还在跑的任务、它卡住了在等人 → 它的键(悬浮窗该写它,不是最后发消息的那个已经停了的任务);否则 None。"""
    if len(alive) == 1 and alive[0].get("why") and not alive[0].get("ack"):
        return alive[0]["key"]
    return None


def stuck_ack(st, tasks, now):
    """你点了收起:单任务的卡住不再当「等人处理」留着(岛上的行照留);从现在起按平时的时间消失。"""
    if not stuck_waiting(tasks, now):
        return
    st["last_msg"] = now
    if not st["multi"]:
        for t in tasks.values():
            if t.get("why"):
                t["ack"] = True


def drop_old(tasks, now):
    """太久没动静的任务清掉:卡住没人管的最多 STUCK_KEEP_S,其他 10 分钟。"""
    for k in [k for k, t in tasks.items() if (now - kept_t(t) > STUCK_KEEP_S if t.get("why") and not t.get("ack") else now - t["last"] > 600)]:
        del tasks[k]


def alive_tasks(tasks, now):
    """还算在跑的任务:TASK_KEEP_S 内有动静,或卡住了在等人处理(同 Mac)。顺手把借鼠标的状态算出来。"""
    out = []
    for t in tasks.values():
        if now - t["last"] < TASK_KEEP_S or (t.get("why") and not t.get("ack")):
            out.append(dict(t, borrow=t.get("borrow_kind") if now < t.get("borrow_until", 0) else None))
    return out


def ordered(alive, now, ost):
    """排谁在顶上:最近有动作(或被点选)的在前;顶上那个至少停 HOLD_S 秒(展开着不换);借鼠标 > 卡住 > 其他。ost 记顶上是谁。"""
    pick = ost.setdefault("pick", {})
    a = sorted(alive, key=lambda t: -max(t["last"], pick.get(t["key"], 0)))
    cur = next((t for t in a if t["key"] == ost.get("top")), None)
    if cur and a[0] is not cur and (ost.get("open") or now - ost.get("top_since", 0) < HOLD_S) \
            and not (a[0].get("borrow") or a[0].get("why")) and not pick.get(a[0]["key"], 0) > pick.get(cur["key"], 0):
        a.remove(cur)
        a.insert(0, cur)
    a.sort(key=lambda t: (not t.get("borrow"), not t.get("why"), queued(t)))   # 借鼠标 > 卡住 > 最近有动作 > 排队中(排队的永远不上顶)
    if a and a[0]["key"] != ost.get("top"):
        ost["top"], ost["top_since"] = a[0]["key"], now
    return a


def t_title(t):
    return "%s · %s" % (t["who"], t["app"]) if t.get("who") and t["who"] != t["app"] else (t.get("app") or "SeeU")


def t_verb(t):
    """一行里写的那句(不带「正在」):借鼠标 / 卡住 / 等下一步 / 动作。"""
    if t.get("borrow"):
        return tr(BORROW_TEXT.get(t["borrow"], BORROW_TEXT["mouse"])[0])
    if t.get("why"):
        return stuck_line(t["why"])
    if queued(t):
        return q_label()
    step = (t.get("step") or "").strip()
    step = step[2:] if step.startswith("正在") else step
    return tr_step(step) if step else tr("等下一步")


def t_headline(t):
    if t.get("borrow") or t.get("why"):
        return t_verb(t)
    if queued(t):            # 全都在排队时顶卡写清楚排第几、等谁(同 Mac)
        return q_label() + " · " + q_detail(t)
    step = (t.get("step") or "").strip()
    step = step[2:] if step.startswith("正在") else step
    return doing(step) if step else tr("等下一步")


def t_ago(t, now):
    d = int(now - t["last"])
    if is_en():
        return "just now" if d < 3 else "%ds ago" % d if d < 60 else "%dm ago" % (d // 60)
    return "刚刚" if d < 3 else "%d 秒前" % d if d < 60 else "%d 分钟前" % (d // 60)


def island(k, tm, theme, measure, a, now, hover=False, ui=None):
    """多任务岛的一帧。a = ordered() 排好的任务(≥2 个);ui 同 scene,另有 more(展开全部)。返回同 scene,多一个 height(岛展开的高)。"""
    T = THEMES[theme]
    ui = ui or {}
    light, lk, isee_on = ui.get("light", "real"), ui.get("light_k", 0.0), bool(ui.get("isee"))
    ink = T["ink"]
    inv = (255, 255, 255) if theme == "light" else (26, 26, 26)
    dark = theme == "dark"
    sub = 0.72 if dark else 0.6
    lead, rest = a[0], a[1:]
    col = lambda t_: ORANGE if t_.get("borrow") else (t_.get("color") or T["dot"])   # noqa: E731   卡住不靠红色,靠文字说(同 Mac);圆点用任务光标色
    notes = []
    if lead.get("borrow"):
        notes.append(tr(BORROW_TEXT.get(lead["borrow"], BORROW_TEXT["mouse"])[1]))
    elif lead.get("why"):
        notes.append(todo_line(lead.get("todo")))
    if isee_on and lead.get("web"):
        notes.append(tr(ISEE_NOTE))
    steps = [x for x in (lead.get("steps") or [])[1:3] if x]
    card_h = 14 + 16 + 28 + 20 * len(notes) + (18 * len(steps) + 8 if steps else 0) + 8
    qrest = sorted((r_ for r_ in rest if queued(r_)), key=lambda r_: (r_.get("queued") or {}).get("t", 0))   # 排队的放下段,先排的在前
    rest = [r_ for r_ in rest if not queued(r_)]
    nq = len(qrest) + (1 if queued(lead) else 0)
    more_row = len(rest) > MAX_ROWS
    fold = more_row and not ui.get("more")
    shown = rest[:MAX_ROWS] if fold else rest[:MAX_ROWS_ALL]
    qfold = len(qrest) > Q_FOLD and not ui.get("qmore")
    qshown = qrest[:1] if qfold else qrest[:MAX_ROWS_ALL]
    q_h = (20 + 36 * (len(qshown) + (1 if qfold else 0)) + (26 if (not qfold and len(qrest) > Q_FOLD) else 0)) if qrest else 0
    HH = TB_H + card_h + 6 + len(shown) * 36 + 4 + ((12 if fold else 26) if more_row else 0) + q_h
    W = ISLAND_W
    capw = int(29 + measure("I See" if isee_on else "SeeU", 14.5, True) + 14 + 0.5)
    w = capw + (W - capw) * k
    h = CAP_H + (HH - CAP_H) * k
    x, y = CW - M - w, M
    r = min(16 + 2 * min(1.0, max(0.0, k)), h / 2)
    prims = [("rr", x, y, w, h, r, T["glass"]), ("ring", x, y, w, h, r, T["line"], 1.0)]
    bs, ba = breath(tm)
    a0 = max(0.0, 1 - 2.5 * k)
    a1 = max(0.0, min(1.0, (k - 0.35) / 0.5))
    if a0 > 0:                                    # 收起:只写 SeeU,多任务也不写个数
        if isee_on:
            prims.append(("eye", x + 16, y + 16, 5.2, _a(col(lead), 255 * a0 * ba)))
        else:
            prims.append(("dot", x + 16, y + 16, 5 * bs, _a(col(lead), 255 * a0 * ba)))
        prims.append(("txt", x + 29, y + 16.25, "I See" if isee_on else "SeeU", 14.5, True, _a(ink, 255 * a0), "l"))
    hits = []
    if a1 > 0:
        bx = CW - M - W
        A = 255 * a1
        cy = y + TB_H / 2
        if hover and k > 0.9 and not lead.get("borrow"):
            hits = _draw_bar(prims, bx, y, W, 8, measure, theme, ink, inv, light, lk, isee_on, True, False, bool(lead.get("web")),
                             "card", ui.get("mouse"))     # 岛上点「看画面」= 单看顶上那个任务(同 Mac)
        else:                                     # 平时顶栏写「SeeU · N 个任务」,开着的开关在角上留个小标记
            prims.append(("dot", bx + 18, cy, 4, _a(col(lead), A)))
            cap = ("SeeU · %d tasks" if is_en() else "SeeU · %d 个任务") % len(a)
            if nq:
                cap += (" · %d queued" if is_en() else " · 排队 %d") % nq
            prims.append(("txt", bx + 30, cy, cap, 12.5, True, _a(ink, A * sub), "l"))
            mx = bx + W - 16
            if light != "off":
                _icon_light(prims, mx, cy, light, ink, a1)
                mx -= 20
            if isee_on and lead.get("web"):
                _icon_isee(prims, mx, cy, True, ink, inv, a1)
        # 顶卡:最活跃的那个任务(排版照单任务卡片)
        cy0, L, CWd = y + TB_H, 10, W - 20
        box = lambda al: (255, 255, 255, int(255 * al * a1))   # noqa: E731
        prims.append(("rr", bx + L, cy0, CWd, card_h, 18, box(0.10 if dark else 0.35)))
        yy = cy0 + 21
        prims.append(("dot", bx + L + 22, yy, 5 * bs, _a(col(lead), A * ba)))
        prims.append(("txt", bx + L + 34, yy, fit(t_title(lead), 12, False, 170, measure), 12, False, _a(ink, A * sub), "l"))
        prims.append(("txt", bx + L + CWd - 18, yy, t_ago(lead, now), 11, False, _a(ink, A * sub * 0.8), "r"))
        yy += 27
        prims.append(("txt", bx + L + 18, yy, fit(t_headline(lead), 16.5, True, CWd - 36, measure), 16.5, True, _a(ink, A * 0.95), "l"))
        for n_ in notes:
            yy += 20
            prims.append(("txt", bx + L + 18, yy, fit(n_, 11.5, False, CWd - 36, measure), 11.5, False, _a(ink, A * sub), "l"))
        if steps:                                 # 顶卡下面列最近两步已做完的(前面一个对勾)
            yy += 8
            for stp in steps:
                yy += 18
                cx_ = bx + L + 22
                prims.append(("line", cx_ - 4, yy, cx_ - 1.5, yy + 3, _a(ink, A * sub), 1.4))
                prims.append(("line", cx_ - 1.5, yy + 3, cx_ + 4, yy - 3.5, _a(ink, A * sub), 1.4))
                prims.append(("txt", bx + L + 32, yy, fit(tr_step(stp), 12, False, CWd - 50, measure), 12, False, _a(ink, A * sub), "l"))
        # 其余任务一行一个
        ry = cy0 + card_h + 6
        row_a = 0.08 if dark else 0.3
        if more_row and not fold:                 # 展开全部时,右上一个小「折叠」
            lab = tr("折叠 ⌃")
            bw = measure(lab, 11, True) + 18
            prims.append(("rr", bx + W - 10 - bw, ry + 2, bw, 20, 10, box(row_a * 1.6)))
            prims.append(("txt", bx + W - 10 - bw / 2, ry + 12, lab, 11, True, _a(ink, A * sub), "c"))
            hits.append(("more", bx + W - 14 - bw, ry, bw + 14, 24))
            ry += 26
        for i, r_ in enumerate(shown):
            last_fold = fold and i == len(shown) - 1
            if last_fold:                         # 叠在后面的两层:一层比一层窄、淡
                prims.append(("rr", bx + 26, ry + 32 + 2, W - 52, 9, 5, box(row_a * 0.45)))
                prims.append(("rr", bx + 18, ry + 32 - 2, W - 36, 8, 5, box(row_a * 0.75)))
            prims.append(("rr", bx + 10, ry, W - 20, 32, 10, box(row_a + (0.04 if last_fold else 0))))
            mid = ry + 16
            prims.append(("dot", bx + 24, mid, 4, _a(col(r_), A)))
            nm = fit(r_.get("who") or r_.get("app") or "SeeU", 12.5, False, 50, measure)
            prims.append(("txt", bx + 34, mid, nm, 12.5, False, _a(ink, A * sub), "l"))
            prims.append(("txt", bx + 34 + min(measure(nm, 12.5, False), 50) + 8, mid, fit(t_verb(r_), 12.5, True, W - 160, measure),
                          12.5, True, _a(ink, A * 0.95), "l"))
            prims.append(("txt", bx + W - 24, mid, t_ago(r_, now), 11, False, _a(ink, A * sub * 0.8), "r"))
            hits.append(("more" if last_fold else "row:" + r_["key"], bx, ry, W, 32 + (12 if last_fold else 0)))
            ry += 36
        if qrest:
            if fold:
                ry += 12                          # 叠着的两层露在下面,让开
            ry = _draw_queue(prims, hits, qshown, qfold, len(qrest), bx, ry, W, tm, ink, sub, row_a, A, measure, box, col)
    return dict(shape=(x, y, w, h, r), prims=prims, hits=hits, card=(CW - M - W, y, W, HH), height=HH,
                close=next(((hx, hy, hw, hh) for nm, hx, hy, hw, hh in hits if nm == "collapse"), None))


def _draw_queue(prims, hits, qshown, qfold, nq, bx, ry, W, tm, ink, sub, row_a, A, measure, box, col):
    """岛下段「排队中」(同 Mac draw_queue):分隔线 + 一行一个,整行变暗;
    最右边(正在做的行写「刚刚」的那一栏)写 zZ,3 秒轻轻一亮一暗;超过 Q_FOLD 个折成「还有 N 个在排队」,点开看全部。返回画完的 y。"""
    lab = q_label()
    lw = measure(lab, 10.5, False)
    mid = ry + 10
    for x0, x1 in ((16, W / 2 - lw / 2 - 8), (W / 2 + lw / 2 + 8, W - 16)):
        if x1 > x0:
            prims.append(("line", bx + x0, mid, bx + x1, mid, _a(ink, A * 0.25 * sub), 1.0))
    prims.append(("txt", bx + W / 2, mid, lab, 10.5, False, _a(ink, A * sub * 0.75), "c"))
    ry += 20
    qa = Q_ALPHA
    za = zz_alpha(tm)
    for r_ in qshown:
        prims.append(("rr", bx + 10, ry, W - 20, 32, 10, box(row_a * qa)))
        m = ry + 16
        prims.append(("dot", bx + 24, m, 4, _a(col(r_), A * qa)))
        nm = fit(r_.get("who") or r_.get("app") or "SeeU", 12.5, False, 50, measure)
        nw = min(measure(nm, 12.5, False), 50)
        prims.append(("txt", bx + 34, m, nm, 12.5, False, _a(ink, A * sub * qa), "l"))
        show_lab = not is_en()                    # 中文照小样写「排队中」;英文行太挤,分隔线已写 Queued 就不重复(同 Mac)
        vw = measure(lab, 12.5, True) if show_lab else -8
        if show_lab:
            prims.append(("txt", bx + 34 + nw + 8, m, lab, 12.5, True, _a(ink, A * qa), "l"))
        dx = 34 + nw + 8 + vw + 8
        prims.append(("txt", bx + dx, m, fit(q_detail(r_), 11.5, False, max(0, W - dx - 58), measure), 11.5, False,
                      _a(ink, A * sub * qa), "l"))       # 太长截成「…」,右边留给 zZ
        prims.append(("txt", bx + W - 24, m, "zZ", 11, True, _a(ink, A * sub * 0.8 * za), "r"))
        hits.append(("row:" + r_["key"], bx, ry, W, 32))
        ry += 36
    if not qfold and nq > Q_FOLD:                 # 点开后要能收回
        fl = tr("折叠 ⌃")
        bw = measure(fl, 11, True) + 18
        prims.append(("rr", bx + W - 10 - bw, ry + 2, bw, 20, 10, box(row_a * 1.6)))
        prims.append(("txt", bx + W - 10 - bw / 2, ry + 12, fl, 11, True, _a(ink, A * sub), "c"))
        hits.append(("qmore", bx + W - 14 - bw, ry, bw + 14, 24))
        ry += 26
    if qfold:
        prims.append(("rr", bx + 10, ry, W - 20, 32, 10, box(row_a * qa)))
        m = ry + 16
        prims.append(("dot", bx + 24, m, 4, _a((140, 140, 148), A * qa)))
        more = ("%d more queued" if is_en() else "还有 %d 个在排队") % (nq - 1)
        prims.append(("txt", bx + 34, m, fit(more, 12.5, False, W - 120, measure), 12.5, False, _a(ink, A * sub * qa), "l"))
        hits.append(("qmore", bx, ry, W, 32))
        ry += 36
    return ry


def glow_wanted(light, mode):
    """灯光档位下,这种动作(mode = "real" 借用鼠标 / "bg" 后台操作)亮不亮光圈、什么颜色;不亮返回 None。"""
    if light == "bg":
        return ORANGE if mode == "real" else (127, 119, 221)
    if light == "real" and mode == "real":
        return ORANGE
    return None


# ───────── 显示进程(只在 Windows 上跑) ─────────
def serve():
    from ctypes import wintypes as wt
    u = ctypes.WinDLL("user32", use_last_error=True)
    g = ctypes.WinDLL("gdi32")
    k32 = ctypes.WinDLL("kernel32")
    gp = ctypes.WinDLL("gdiplus")
    P, F = ctypes.c_void_p, ctypes.c_float
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE), ("hIcon", P), ("hCursor", P), ("hbrBackground", P),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("a", wt.LONG), ("b", wt.LONG), ("c", wt.DWORD), ("d", wt.DWORD)]

    class BLEND(ctypes.Structure):
        _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]

    class RECTF(ctypes.Structure):
        _fields_ = [("x", F), ("y", F), ("w", F), ("h", F)]

    class GpStartup(ctypes.Structure):
        _fields_ = [("ver", ctypes.c_uint32), ("cb", P), ("a", wt.BOOL), ("b", wt.BOOL)]

    u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]; u.DefWindowProcW.restype = LRESULT
    u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, P, wt.HINSTANCE, P]
    u.CreateWindowExW.restype = wt.HWND
    u.GetDC.argtypes = [wt.HWND]; u.GetDC.restype = P
    u.ReleaseDC.argtypes = [wt.HWND, P]
    u.UpdateLayeredWindow.argtypes = [wt.HWND, P, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), P, ctypes.POINTER(wt.POINT),
                                      wt.DWORD, ctypes.POINTER(BLEND), wt.DWORD]
    u.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, P]
    u.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u.SetCapture.argtypes = [wt.HWND]
    u.LoadCursorW.argtypes = [P, P]; u.LoadCursorW.restype = P
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.GetDpiForWindow.argtypes = [wt.HWND]
    u.DestroyWindow.argtypes = [wt.HWND]
    g.CreateCompatibleDC.argtypes = [P]; g.CreateCompatibleDC.restype = P
    g.CreateDIBSection.argtypes = [P, P, wt.UINT, ctypes.POINTER(P), P, wt.DWORD]; g.CreateDIBSection.restype = P
    g.SelectObject.argtypes = [P, P]; g.SelectObject.restype = P
    k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]; k32.GetModuleHandleW.restype = wt.HINSTANCE

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", PORT))
        sock.setblocking(False)
    except OSError:
        return                                   # 已经有一个在跑
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:   # noqa: BLE001
        pass

    def argb(c):
        return ((c[3] & 255) << 24) | (c[0] << 16) | (c[1] << 8) | c[2]

    def sys_theme():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
        except OSError:
            return "dark"

    st = dict(info=None, open=False, a_from=0.0, a_t0=-9.0, theme="auto", theme_now=sys_theme(), theme_t=0.0, drag=None, moved=False,
              t0=time.time(), last_msg=0.0, last_draw=0.0, shown=False, close=None, card=None, hover=False, s=1.0,
              borrow=None, borrow_until=0.0, borrow_auto=False, through=False,
              light=light_level(), why=not live().get("why_off"), light_open=False, light_t0=-9.0, hits=[],
              isee=False, isee_t=0.0, real_down=False, more=False,
              view="screen" if live().get("view") == "screen" else "card",
              h_tgt=None, h_from=None, h_t0=-9.0, h_show=None, shim=False, solo=None, multi=False,
              w_tgt=None, w_from=None, w_show=None, rs=None, pic_on=False, view_geo=None)
    tasks = {}                # 任务名 -> 状态(多任务岛用;只有一个在跑时照旧是单任务卡片)
    tint_cache = {}           # 任务还没上岛时先收到的光标色,上岛时用
    ost = {}                  # 岛上谁排在顶上(ordered() 用)
    glow = dict(hwnd=None, mem=None, color=None, until=0.0, env=0.0, shown=False, alpha=-1, last=0.0, t=time.time())
    pos = wt.POINT()          # 浮标窗口(整块画布)现在在屏幕哪,每帧由悬浮标位置 cap + 展开方式算出来
    cap = dict(x=0, y=0, mode=None, shape=None)     # 悬浮标(收起时那个胶囊)的左上角,屏幕像素;拖动改的是它,记住的也是它
    keep_pos = os.environ.get("SEEU_FLOAT_NOPOS") != "1"      # 测试时不读不写记住的位置(每次都从默认的右上角开始)
    vsize = {k_: v_ for k_, v_ in live().items() if k_ in ("view_port_h", "view_land_w")} if keep_pos else {}   # 看画面拉过的大小

    class MONINFO(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("mon", wt.RECT), ("work", wt.RECT), ("flags", wt.DWORD)]
    u.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]; u.MonitorFromPoint.restype = P
    u.GetMonitorInfoW.argtypes = [P, ctypes.POINTER(MONINFO)]

    def work_area():
        """悬浮标所在那块屏幕的可用范围(不含任务栏):(左, 上, 右, 下) 像素。"""
        mi = MONINFO(ctypes.sizeof(MONINFO))
        hm = u.MonitorFromPoint(wt.POINT(int(cap["x"] + CAP_W * st["s"] / 2), int(cap["y"] + CAP_H * st["s"] / 2)), 2)   # 2 = 不在任何屏幕上就取最近的
        if hm and u.GetMonitorInfoW(hm, ctypes.byref(mi)):
            return mi.work.left, mi.work.top, mi.work.right, mi.work.bottom
        return 0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)

    def place(sc):
        """按悬浮标位置和现在的外形,算出窗口该放哪(写进 pos)。画布里外形一直靠右,所以挪的是整个窗口。"""
        s = st["s"]
        L_, T_, R_, B_ = work_area()
        x_, y_, w_, h_, _r = sc["shape"]
        rs = st["rs"]
        if rs:                                    # 正在拉边缩放:对面那条边不动(同系统窗口),别出屏幕
            left = rs["right"] - w_ * s if "l" in rs["edge"] else rs["left"]
            top = rs["bottom"] - h_ * s if "t" in rs["edge"] else rs["top"]
            left, top = max(L_, min(left, R_ - w_ * s)), max(T_, min(top, B_ - h_ * s))
        else:
            mode = cap["mode"] or anchor(cap["x"], L_, R_, s)
            left = shape_left(cap["x"], w_, mode, L_, R_, s)
            top = max(T_, min(cap["y"], B_ - h_ * s))             # 底边也别出屏幕
        pos.x, pos.y = int(round(left - x_ * s)), int(round(top - y_ * s))
        cap["shape"] = (left, top, w_)
    pt = {}
    cam = dict(wid=0, until=0.0, side=640, new=None, lock=__import__("threading").Lock())   # 看画面:后台线程截图,画的时候取最新一张

    u.IsWindow.argtypes = [wt.HWND]
    u.IsIconic.argtypes = [wt.HWND]
    u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

    try:
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, P, wt.DWORD]
    except OSError:
        dwm = None

    def win_box(wid):
        """窗口真正看得见的那一块在整个窗口矩形里的位置:(左, 上, 宽, 高) 像素 + 整窗 (宽, 高)。
        Windows 10 / 11 的窗口左右下各有一圈看不见的边(拖边缩放用),截图会把它截成空边,这里量出来好裁掉。"""
        r_ = wt.RECT()
        u.GetWindowRect(wid, ctypes.byref(r_))
        W_, H_ = r_.right - r_.left, r_.bottom - r_.top
        v_ = wt.RECT()
        if dwm is not None and dwm.DwmGetWindowAttribute(wid, 9, ctypes.byref(v_), ctypes.sizeof(v_)) == 0:
            l_, t_ = max(0, v_.left - r_.left), max(0, v_.top - r_.top)
            w_, h_ = min(W_ - l_, v_.right - v_.left), min(H_ - t_, v_.bottom - v_.top)
            if w_ > 0 and h_ > 0 and l_ <= 40 and t_ <= 40 and W_ - w_ <= 80 and H_ - h_ <= 80:    # 差得离谱就不信它
                return (l_, t_, w_, h_), (W_, H_)
        return (0, 0, W_, H_), (W_, H_)

    def win_aspect(wid):
        """被操作窗口的高宽比 + 看得见的那块占整窗的比例;窗口没了 / 最小化了(截不到画面)返回 None。"""
        if not wid or not u.IsWindow(wid) or u.IsIconic(wid):
            return None
        (l_, t_, w_, h_), (W_, H_) = win_box(wid)
        if w_ <= 0 or h_ <= 0:
            return None
        return h_ / float(w_), (l_ / float(W_), t_ / float(H_), w_ / float(W_), h_ / float(H_))

    def cam_loop():
        """后台线程:要看画面的那几秒里,一秒截 VIEW_FPS 次被操作的窗口(截图几十毫秒,放这里不卡浮标的动画)。没人看就空转。"""
        try:
            from seeu.win import window as Wn
        except Exception:   # noqa: BLE001
            return
        while True:
            time.sleep(1.0 / VIEW_FPS)
            wid = cam["wid"]
            if not wid or time.time() > cam["until"]:
                continue
            try:
                w_, h_, b_ = Wn.capture(wid)
                (l_, t_, vw, vh), (W_, H_) = win_box(wid)
                if (W_, H_) == (w_, h_) and (vw, vh) != (w_, h_):          # 裁掉四周看不见的那圈边
                    row = w_ * 4
                    b_ = b"".join(b_[y_ * row + l_ * 4:y_ * row + (l_ + vw) * 4] for y_ in range(t_, t_ + vh))
                    w_, h_ = vw, vh
                w_, h_, b_ = Wn.shrink(w_, h_, b_, cam["side"])
            except Exception:   # noqa: BLE001      窗口刚关 / 刚最小化:这一张不要,下一轮再说
                continue
            with cam["lock"]:
                cam["new"] = (wid, w_, h_, b_)

    def img_drop():
        if pt.get("img"):
            gp.GdipDisposeImage(pt["img"][0])
            pt["img"] = None

    def img_take():
        """把后台线程截到的最新一张换成能画的图(旧的那张释放掉)。"""
        with cam["lock"]:
            new, cam["new"] = cam["new"], None
        if not new:
            return
        wid, w_, h_, b_ = new
        buf = ctypes.create_string_buffer(b_, len(b_))            # 这块内存图在用,要跟图一起留着
        bmp = P()
        if gp.GdipCreateBitmapFromScan0(w_, h_, w_ * 4, 0x00022009, buf, ctypes.byref(bmp)) != 0 or not bmp:   # 32 位、不看透明度那一格
            return
        img_drop()
        pt["img"] = (bmp, buf, wid)

    g.DeleteObject.argtypes = [P]
    g.DeleteDC.argtypes = [P]

    def canvas(h_logical, w_logical=CW):
        """准备一块画布(至少宽 w_logical、高 h_logical);现有的不够大才换,只变大不变小。多任务岛更高、看画面拉大了更宽,用到时才换大的。"""
        s = st["s"]
        w_logical = max(w_logical, pt.get("cw", 0))
        pw, ph = int(w_logical * s), max(int(h_logical * s), pt.get("ph", 0))
        if pt.get("ph", 0) >= ph and pt.get("pw", 0) >= pw:
            return
        if pt.get("gr"):
            gp.GdipDeleteGraphics(pt["gr"]); gp.GdipDisposeImage(pt["bmp"])
            g.DeleteDC(pt["mem"]); g.DeleteObject(pt["dib"])
        mem = g.CreateCompatibleDC(None)
        bits = P()
        dib = g.CreateDIBSection(mem, ctypes.byref(BIH(ctypes.sizeof(BIH), pw, -ph, 1, 32, 0, 0, 0, 0, 0, 0)), 0, ctypes.byref(bits), None, 0)
        g.SelectObject(mem, dib)
        bmp, gr = P(), P()
        gp.GdipCreateBitmapFromScan0(pw, ph, pw * 4, 0x000E200B, bits, ctypes.byref(bmp))   # 32 位预乘透明度,直接指向位图像素
        gp.GdipGetImageGraphicsContext(bmp, ctypes.byref(gr))
        gp.GdipSetSmoothingMode(gr, 4)
        # 透明底上用普通抗锯齿,别用 ClearType。100% / 125% 缩放时字小,不对齐像素会发虚(用户报)→ 对齐像素;高分屏不用对齐
        gp.GdipSetTextRenderingHint(gr, 3 if s < 1.5 else 4)
        gp.GdipSetPixelOffsetMode(gr, 4)
        pt.update(pw=pw, ph=ph, cw=w_logical, mem=mem, dib=dib, bmp=bmp, gr=gr)

    def setup(hwnd):
        s = st["s"] = (u.GetDpiForWindow(hwnd) or 96) / 96.0
        tok = P()
        gp.GdiplusStartup(ctypes.byref(tok), ctypes.byref(GpStartup(1, None, False, False)), None)
        fam, gen, fmt = P(), P(), P()
        gp.GdipCreateFontFamilyFromName(FONT, None, ctypes.byref(fam))
        gp.GdipStringFormatGetGenericTypographic(ctypes.byref(gen))
        gp.GdipCloneStringFormat(gen, ctypes.byref(fmt))
        gp.GdipSetStringFormatFlags(fmt, 0x800 | 0x1000 | 0x4000)
        pt.update(fam=fam, fmt=fmt, fonts={})
        canvas(CH)
        pw = pt["pw"]
        sw = u.GetSystemMetrics(0)
        cap["x"], cap["y"] = int(sw - (40 + CAP_W) * s), int(80 * s)      # 默认右上角
        c_ = live().get("cap") if keep_pos else None
        if isinstance(c_, list) and len(c_) == 2 and all(isinstance(v_, (int, float)) for v_ in c_):
            cap["x"], cap["y"] = int(c_[0] * s), int(c_[1] * s)       # 记的是不带缩放的数,换屏幕 / 换缩放后还在差不多的地方
            L_, T_, R_, B_ = work_area()                              # 记住的位置现在在屏幕外(换了小屏幕):拉回来
            cap["x"] = int(max(L_, min(cap["x"], R_ - CAP_W * s)))
            cap["y"] = int(max(T_, min(cap["y"], B_ - CAP_H * s)))

    def font(size, bold):
        key = (size, bold)
        if key not in pt["fonts"]:
            f = P()
            gp.GdipCreateFont(pt["fam"], F(size * st["s"]), 1 if bold else 0, 2, ctypes.byref(f))
            pt["fonts"][key] = f
        return pt["fonts"][key]

    def measure_px(text, size, bold):
        box = RECTF()
        gp.GdipMeasureString(pt["gr"], text, len(text), font(size, bold), ctypes.byref(RECTF(0, 0, 4000, 400)), pt["fmt"],
                             ctypes.byref(box), None, None)
        return box.w, box.h

    def measure(text, size, bold):
        return measure_px(text, size, bold)[0] / st["s"]

    def path(x, y, w, h, r):
        s = st["s"]
        r = max(0.5, min(r, w / 2.0, h / 2.0))      # 圆角不能比半个边还大:大了四段弧会互相压住,两头变成直线带锯齿(用户报)
        x, y, w, h, d = x * s, y * s, w * s, h * s, 2 * r * s
        p = P()
        gp.GdipCreatePath(0, ctypes.byref(p))
        for ax, ay, a0 in ((x, y, 180), (x + w - d, y, 270), (x + w - d, y + h - d, 0), (x, y + h - d, 90)):
            gp.GdipAddPathArc(p, F(ax), F(ay), F(d), F(d), F(a0), F(90))
        gp.GdipClosePathFigure(p)
        return p

    def brush(c):
        b = P()
        gp.GdipCreateSolidFill(argb(c), ctypes.byref(b))
        return b

    def paint(sc):
        s, gr = st["s"], pt["gr"]
        gp.GdipResetClip(gr)
        gp.GdipGraphicsClear(gr, 0)
        x, y, w, h, r = sc["shape"]
        b = brush((0, 0, 0, 7))
        for i in range(8, 0, -1):                 # 阴影
            p = path(x - i, y - i + 3, w + 2 * i, h + 2 * i, r + i)
            gp.GdipFillPath(gr, b, p); gp.GdipDeletePath(p)
        gp.GdipDeleteBrush(b)
        clip = path(x, y, w, h, r)
        for pr in sc["prims"]:
            kind = pr[0]
            if kind == "rr":
                p, b = path(*pr[1:6]), brush(pr[6])
                gp.GdipFillPath(gr, b, p); gp.GdipDeleteBrush(b); gp.GdipDeletePath(p)
                if pr[1:6] == sc["shape"]:
                    gp.GdipSetClipPath(gr, clip, 1)
            elif kind == "ring":
                gp.GdipResetClip(gr)
                p, pen = path(pr[1] + .5, pr[2] + .5, pr[3] - 1, pr[4] - 1, pr[5] - .5), P()   # 描边往里收半个点,圆角跟着减
                gp.GdipCreatePen1(argb(pr[6]), F(pr[7] * s), 2, ctypes.byref(pen))
                gp.GdipDrawPath(gr, pen, p); gp.GdipDeletePen(pen); gp.GdipDeletePath(p)
                gp.GdipSetClipPath(gr, clip, 0)
            elif kind == "dot":
                _, cx, cy, rad, c = pr
                b = brush(c)
                gp.GdipFillEllipse(gr, b, F((cx - rad) * s), F((cy - rad) * s), F(2 * rad * s), F(2 * rad * s))
                gp.GdipDeleteBrush(b)
            elif kind == "eye":
                _, cx, cy, rad, c = pr
                p, pen, b = P(), P(), brush(c)
                gp.GdipCreatePath(0, ctypes.byref(p))
                x0_, x1_ = (cx - rad * 1.25) * s, (cx + rad * 1.25) * s
                for sg in (-1, 1):                # 上下两条弧线合成杏仁形眼眶
                    gp.GdipAddPathBezier(p, F(x0_ if sg < 0 else x1_), F(cy * s), F((cx + sg * rad * 0.5) * s), F((cy + sg * rad * 1.1) * s),
                                         F((cx - sg * rad * 0.5) * s), F((cy + sg * rad * 1.1) * s), F(x1_ if sg < 0 else x0_), F(cy * s))
                gp.GdipClosePathFigure(p)
                gp.GdipCreatePen1(argb(c), F(1.5 * s), 2, ctypes.byref(pen))
                gp.GdipSetPenLineJoin(pen, 2)
                gp.GdipDrawPath(gr, pen, p)
                pr_ = rad * 0.42
                gp.GdipFillEllipse(gr, b, F((cx - pr_) * s), F((cy - pr_) * s), F(2 * pr_ * s), F(2 * pr_ * s))
                gp.GdipDeletePen(pen); gp.GdipDeleteBrush(b); gp.GdipDeletePath(p)
            elif kind == "circ":
                _, cx, cy, rad, c, wd = pr
                pen = P()
                gp.GdipCreatePen1(argb(c), F(wd * s), 2, ctypes.byref(pen))
                gp.GdipDrawEllipse(gr, pen, F((cx - rad) * s), F((cy - rad) * s), F(2 * rad * s), F(2 * rad * s))
                gp.GdipDeletePen(pen)
            elif kind == "arc":
                _, cx, cy, rad, a0_, sweep, c, wd = pr
                pen = P()
                gp.GdipCreatePen1(argb(c), F(wd * s), 2, ctypes.byref(pen))
                gp.GdipSetPenStartCap(pen, 2); gp.GdipSetPenEndCap(pen, 2)
                gp.GdipDrawArc(gr, pen, F((cx - rad) * s), F((cy - rad) * s), F(2 * rad * s), F(2 * rad * s), F(a0_), F(sweep))
                gp.GdipDeletePen(pen)
            elif kind == "line":
                _, x1, y1, x2, y2, c, wd = pr
                pen = P()
                gp.GdipCreatePen1(argb(c), F(wd * s), 2, ctypes.byref(pen))
                gp.GdipSetPenStartCap(pen, 2); gp.GdipSetPenEndCap(pen, 2)
                gp.GdipDrawLine(gr, pen, F(x1 * s), F(y1 * s), F(x2 * s), F(y2 * s))
                gp.GdipDeletePen(pen)
            elif kind == "img":
                _, ix, iy, iw, ih, ir = pr
                p, b = path(ix, iy, iw, ih, ir), brush((0, 0, 0, 70))
                gp.GdipFillPath(gr, b, p); gp.GdipDeleteBrush(b)          # 底:第一张图还没到时先是一块暗的
                im = pt.get("img")
                if im and im[2] == sc.get("wid"):
                    # 把图当「颜料」填进圆角形状里:边缘是平滑的。(原来按圆角裁剪着贴图,裁剪边不带平滑,圆角有锯齿,用户报)
                    tb, iw_, ih_ = P(), ctypes.c_uint(), ctypes.c_uint()
                    gp.GdipGetImageWidth(im[0], ctypes.byref(iw_)); gp.GdipGetImageHeight(im[0], ctypes.byref(ih_))
                    gp.GdipSetInterpolationMode(gr, 7)
                    if iw_.value and ih_.value and gp.GdipCreateTexture(im[0], 3, ctypes.byref(tb)) == 0 and tb:   # 3 = 两个方向都镜像着铺(边上不露缝)
                        gp.GdipTranslateTextureTransform(tb, F(ix * s), F(iy * s), 0)
                        gp.GdipScaleTextureTransform(tb, F(iw * s / iw_.value), F(ih * s / ih_.value), 0)
                        gp.GdipFillPath(gr, tb, p)
                        gp.GdipDeleteBrush(tb)
                gp.GdipDeletePath(p)
            elif kind == "shim":                    # 文字微光:同样的字再叠一层亮的,只露出一条两头淡的竖带
                _, tx, cy, text, size, bold, c, sx = pr
                tw, th = measure_px(text, size, bold)
                n_ = 8
                for i in range(n_):
                    fa_ = 1 - abs(i + 0.5 - n_ / 2.0) / (n_ / 2.0)
                    x0_ = tx + sx - SHIM_W / 2 + i * SHIM_W / n_
                    gp.GdipSetClipPath(gr, clip, 0)
                    gp.GdipSetClipRect(gr, F(x0_ * s), F(cy * s - th), F(SHIM_W / n_ * s), F(2 * th), 1)
                    b = brush((c[0], c[1], c[2], int(c[3] * fa_)))
                    gp.GdipDrawString(gr, text, len(text), font(size, bold),
                                      ctypes.byref(RECTF(tx * s, cy * s - th / 2, tw + 8, th + 4)), pt["fmt"], b)
                    gp.GdipDeleteBrush(b)
                gp.GdipSetClipPath(gr, clip, 0)
            elif kind == "txt":
                _, tx, cy, text, size, bold, c, al = pr
                tw, th = measure_px(text, size, bold)
                px = tx * s - (tw if al == "r" else tw / 2 if al == "c" else 0)
                b = brush(c)
                gp.GdipDrawString(gr, text, len(text), font(size, bold),
                                  ctypes.byref(RECTF(px, cy * s - th / 2, tw + 8, th + 4)), pt["fmt"], b)
                gp.GdipDeleteBrush(b)
        gp.GdipDeletePath(clip)
        gp.GdipFlush(gr, 1)

    def k_now():
        x = (time.time() - st["a_t0"]) / ANIM_S
        target = 1.0 if st["open"] else 0.0
        return target if x >= 1 else st["a_from"] + (target - st["a_from"]) * ease(x)

    def toggle(to):
        if to != st["open"]:
            st["a_from"], st["open"], st["a_t0"] = k_now(), to, time.time()

    def frame(hwnd):
        now = time.time()
        if now - st["theme_t"] > 2:               # 系统深浅色变了跟着变
            st["theme_t"], st["theme_now"] = now, (sys_theme() if st["theme"] == "auto" else st["theme"])
        if now - st["isee_t"] > 1.5:              # I See 开没开:读设置(别处关了 / 到期了,浮标跟着变)
            st["isee_t"], st["isee"] = now, isee_active()
        info = st["info"] or {}
        if st["borrow"]:
            info = dict(info, borrow=st["borrow"])
        lk = min(1.0, (now - st["light_t0"]) / 0.22) if st["light_open"] else 0.0
        ui = dict(light=st["light"], light_k=ease(lk) if lk < 1 else 1.0, why=st["why"], isee=st["isee"], more=st["more"], qmore=st.get("qmore"), mouse=st.get("mouse"))
        al = alive_tasks(tasks, now)
        if st["solo"] and not any(t_["key"] == st["solo"] for t_ in al):
            st["solo"] = None                     # 单看的那个任务结束了:回到岛
        if st["solo"]:
            info = tasks[st["solo"]]              # 单看某个任务期间,别的任务只记着,不换上来(同 Mac)
            if st["borrow"]:
                info = dict(info, borrow=st["borrow"])
        st["multi"] = st["solo"] is None and len(al) >= 2
        lk_ = None if st["solo"] else lone_stuck(al)
        if lk_ in tasks and tasks[lk_] is not st["info"]:      # 岛退回单任务:换成还卡着的那个(同 Mac 重放它最后一条消息)
            st["info"] = tasks[lk_]
            info = dict(st["info"], borrow=st["borrow"]) if st["borrow"] else st["info"]
        if st["multi"]:                           # 两个以上任务同时在跑:换成多任务岛
            ost["open"] = st["open"]
            sc = island(k_now(), now - st["t0"], st["theme_now"], measure, ordered(al, now, ost), now,
                        st["hover"] and not st["borrow"], ui)
            st["h_tgt"] = st["h_from"] = st["w_tgt"] = st["w_from"] = None
            st["pic_on"] = False
            canvas(sc["height"] + 2 * M)
        else:
            wid = int(info.get("wid") or 0)
            if wid and not info.get("web"):
                asp = win_aspect(wid)
                if asp is None:
                    ui["pic_ok"] = False              # 窗口没了 / 最小化了:退回文字卡,按钮灰着
                elif st["view"] == "screen":
                    ui["view"], ui["pic"] = "screen", pic_ui(info, now, asp[0], asp[1])
                    a_ = max(0.1, min(4.0, asp[0]))
                    L_, T_, R_, B_ = work_area()
                    st["view_geo"] = (a_, (R_ - L_) / st["s"], (B_ - T_) / st["s"])
                    # 看画面时卡片多宽:正在拉就跟着鼠标,不然用记住的(竖 / 横各一份),都夹在屏幕九成以内
                    ui["vw"] = st["rs"]["w"] if st["rs"] else view_fit_w(view_saved_w(vsize, a_), *st["view_geo"])
            ui["shim"] = shim_x(now, info.get("last") or 0)
            hk = (now - st["h_t0"]) / H_ANIM_S
            if st["h_from"] is not None and hk < 1:
                ui["h_from"], ui["h_k"], ui["w_from"] = st["h_from"], 1 - (1 - hk) ** 3, st["w_from"]
            need = max(ui.get("vw") or 0, st["w_show"] or 0, st["w_from"] or 0, CARD_W) + 2 * M
            canvas(0, max(CW, 4 * math.ceil(need / 4.0)))          # 拉宽了:画布跟着换宽的
            ui["cw"] = pt["cw"]
            sc = scene(k_now(), now - st["t0"], st["theme_now"], measure, info, st["hover"] and not st["borrow"], ui)
            if sc["target_h"] != st["h_tgt"] or sc["target_w"] != st["w_tgt"]:   # 卡片该多大变了:展开着就从现在的大小过渡过去,别直接跳
                if (st["h_tgt"] is not None and st["h_show"] and st["open"] and k_now() > 0.99 and st["shown"]
                        and not st["rs"]):            # 拉边缩放时跟手,不过渡
                    st["h_from"], st["w_from"], st["h_t0"] = st["h_show"], st["w_show"], now
                    ui["h_from"], ui["h_k"], ui["w_from"] = st["h_from"], 0.0, st["w_from"]
                    sc = scene(k_now(), now - st["t0"], st["theme_now"], measure, info, st["hover"] and not st["borrow"], ui)
                else:
                    st["h_from"] = None
                st["h_tgt"], st["w_tgt"] = sc["target_h"], sc["target_w"]
            st["h_show"], st["w_show"] = sc["card"][3], sc["card"][2]
            st["pic_on"] = any(p_[0] == "img" for p_ in sc["prims"])
            if st["pic_on"]:                                       # 真在画画面:让后台线程接着截这个窗口,取最新一张
                cam["wid"], cam["until"] = wid, now + 1.0
                cam["side"] = min(2400, int(2 * max(sc["card"][2], sc["card"][3], CARD_W, PIC_MAX_H) * st["s"]))
                img_take()
                sc["wid"] = wid
            elif pt.get("img") and now > cam["until"] + 2:
                img_drop()                            # 不看了:图放掉
            canvas(max(sc["card"][3], sc["target_h"]) + 2 * M)     # 看画面比文字卡高
        st["shim"] = any(p_[0] == "shim" for p_ in sc["prims"])
        st["close"], st["card"], st["hits"] = sc["close"], sc["card"], sc["hits"]
        place(sc)
        paint(sc)
        hdc = u.GetDC(None)
        u.UpdateLayeredWindow(hwnd, hdc, ctypes.byref(pos), ctypes.byref(wt.SIZE(pt["pw"], pt["ph"])), pt["mem"],
                              ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(BLEND(0, 0, 255, 1)), 2)
        u.ReleaseDC(None, hdc)
        st["last_draw"] = now

    def show(hwnd, on):
        if on != st["shown"]:
            st["shown"] = on
            if on:
                frame(hwnd)
            u.ShowWindow(hwnd, 4 if on else 0)    # 4 = 显示但不激活

    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]

    def through(hwnd, on):
        """借鼠标那几秒整个浮标不接鼠标(点击直接穿到下面的窗口),借完恢复。"""
        if on != st["through"]:
            st["through"] = on
            ex_ = u.GetWindowLongPtrW(hwnd, -20)
            u.SetWindowLongPtrW(hwnd, -20, (ex_ | 0x20) if on else (ex_ & ~0x20))

    def borrow_end(hwnd):
        st["borrow"] = None
        through(hwnd, False)
        if st["borrow_auto"]:
            st["borrow_auto"] = False
            toggle(False)                         # 是为借鼠标自动弹开的 → 借完收回胶囊

    def isee_active():
        try:
            from seeu import isee
            return bool(isee.active())
        except Exception:   # noqa: BLE001
            return False

    def isee_click(real):
        """点了 I See 按钮。关:谁点都行。开:🔴 只认用户亲手的真鼠标点击(real)—— 发消息、后台点击(PostMessage)都开不了。"""
        try:
            from seeu import isee
            if isee.active():
                isee.off()
            elif real:
                isee.on(by="overlay")             # isee.on 自己也查「是不是用户亲手」,Windows 上由这里担保
        except Exception:   # noqa: BLE001      设置文件坏了之类:不开,样子不变
            pass
        st["isee"], st["isee_t"] = isee_active(), time.time()

    def glow_on(mode, secs):
        """按灯光档位亮屏幕四周的光圈(mode = "real" 借用鼠标 / "bg" 后台操作);动作持续就反复调来续时。"""
        col_ = glow_wanted(st["light"], mode)
        if not col_:
            return
        if glow["hwnd"] is None or glow["color"] != col_:
            glow_build(col_)
        glow["until"] = max(glow["until"], time.time() + max(0.2, min(float(secs), 600)))

    def glow_build(col_):
        s_ = st["s"]
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        if glow["hwnd"] is None:
            ex_ = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000   # 分层 | 不接鼠标 | 置顶 | 不进任务栏 | 不抢前台
            glow["hwnd"] = u.CreateWindowExW(ex_, "SeeUGlow", "", 0x80000000, 0, 0, sw, sh, None, None, hinst, None)
            glow["mem"] = g.CreateCompatibleDC(None)
            bits = P()
            dib = g.CreateDIBSection(glow["mem"], ctypes.byref(BIH(ctypes.sizeof(BIH), sw, -sh, 1, 32, 0, 0, 0, 0, 0, 0)), 0,
                                     ctypes.byref(bits), None, 0)
            g.SelectObject(glow["mem"], dib)
            glow["bits"], glow["size"] = bits, (sw, sh)
        sw, sh = glow["size"]
        bmp, gr = P(), P()
        gp.GdipCreateBitmapFromScan0(sw, sh, sw * 4, 0x000E200B, glow["bits"], ctypes.byref(bmp))
        gp.GdipGetImageGraphicsContext(bmp, ctypes.byref(gr))
        gp.GdipSetSmoothingMode(gr, 4)
        gp.GdipGraphicsClear(gr, 0)
        n = 10
        for i in range(n):                         # 沿四边一圈圈由外向内渐隐(同 Mac)
            kk = 1 - i / n
            inset = i * GLOW_W / n + 1
            p_, pen = path(inset, inset, sw / s_ - 2 * inset, sh / s_ - 2 * inset, 12), P()
            gp.GdipCreatePen1(argb(_a(col_, 255 * 0.85 * kk * kk)), F((GLOW_W / n + 0.6) * s_), 2, ctypes.byref(pen))
            gp.GdipDrawPath(gr, pen, p_)
            gp.GdipDeletePen(pen); gp.GdipDeletePath(p_)
        gp.GdipFlush(gr, 1)
        gp.GdipDeleteGraphics(gr); gp.GdipDisposeImage(bmp)
        glow["color"], glow["alpha"] = col_, -1
        hdc = u.GetDC(None)
        u.UpdateLayeredWindow(glow["hwnd"], hdc, ctypes.byref(wt.POINT(0, 0)), ctypes.byref(wt.SIZE(sw, sh)), glow["mem"],
                              ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(BLEND(0, 0, 0, 1)), 2)
        u.ReleaseDC(None, hdc)

    def glow_tick(now):
        if glow["hwnd"] is None:
            return
        dt, glow["t"] = min(0.1, now - glow["t"]), now
        tgt = 1.0 if now < glow["until"] else 0.0
        step = dt / GLOW_FADE_S
        env = glow["env"] = min(tgt, glow["env"] + step) if tgt > glow["env"] else max(tgt, glow["env"] - step)
        a = int(255 * env * (1 - GLOW_BREATH * (0.5 - 0.5 * math.cos(2 * math.pi * now / GLOW_PERIOD_S))))
        if a <= 1:
            if glow["shown"]:
                glow["shown"] = False
                u.ShowWindow(glow["hwnd"], 0)
            return
        if a != glow["alpha"] and now - glow["last"] >= 0.04:      # 只改整窗透明度,不重画(一秒最多 25 次)
            glow["alpha"], glow["last"] = a, now
            u.UpdateLayeredWindow(glow["hwnd"], None, None, None, None, None, 0, ctypes.byref(BLEND(0, 0, a, 1)), 2)
        if not glow["shown"]:
            glow["shown"] = True
            u.ShowWindow(glow["hwnd"], 4)

    def on_hit(hwnd, name, real=False):
        if real:                                   # 程序发来的(命令行换画面 / 灯光)不算你碰过
            stuck_touch(st, tasks, time.time())
        if name == "isee":
            isee_click(real)
        elif name == "collapse":
            st["light_open"] = st["more"] = False
            if not st["solo"]:                     # 单看时收起 = 回岛,岛上那行照留
                stuck_ack(st, tasks, time.time())
            st["solo"] = None                      # 单看一个任务时点收起 = 回到多任务岛(同 Mac)
            toggle(False)
        elif name == "more":                       # 岛:叠着的那几行展开 / 折叠
            st["more"] = not st["more"]
        elif name == "qmore":                      # 岛下段排队的那几行展开 / 折叠
            st["qmore"] = not st.get("qmore")
        elif name.startswith("row:"):              # 岛:点下面某一行 → 换到顶上
            ost.setdefault("pick", {})[name[4:]] = time.time()
        elif name == "light":
            st["light_open"], st["light_t0"] = True, time.time()
        elif name.startswith("light:"):
            st["light"], st["light_open"] = name[6:], False
            set_live(light=st["light"])
            if st["light"] == "off":
                glow["until"] = 0.0
        elif name == "why":
            st["why"] = not st["why"]
            set_live(why_off=not st["why"])
        elif name == "view" and st["multi"]:       # 岛上点看画面:只看顶上那个任务(单任务卡片接手),能放画面的直接放
            top = ordered(alive_tasks(tasks, time.time()), time.time(), ost)
            if top:
                st["solo"], st["more"] = top[0]["key"], False
                if top[0].get("wid") and not top[0].get("web") and st["view"] != "screen":
                    st["view"] = "screen"
                    set_live(view="screen")
        elif name == "view":                       # 看画面 ↔ 看操作(文字卡),选过记住
            st["view"] = "card" if st["view"] == "screen" else "screen"
            set_live(view=st["view"])
        frame(hwnd)

    def on_msg(hwnd, m):
        now = time.time()
        if not m:
            return
        def task(who, app):
            key = task_key(who, app)
            t_ = tasks.get(key)
            if t_ is None:
                t_ = tasks[key] = dict(key=key, who=who or "", app=app or "SeeU", step="", steps=[], born=now, last=now,
                                       color=tint_cache.pop(key, None))
            t_["who"], t_["app"], t_["last"] = who or "", app or "SeeU", now
            t_["queued"] = None                   # 有别的动作 = 不在排队了(同 Mac)
            return t_

        if m[0] == "browser" and len(m) >= 3:
            t_ = task(m[3] if len(m) > 3 else "", m[1])
            if m[2] and (not t_["steps"] or t_["steps"][0] != m[2]):
                t_["steps"].insert(0, m[2])       # 最近几步(新的在前),岛的顶卡下面列已做完的
                del t_["steps"][4:]
            t_.update(step=m[2], note=m[4] if len(m) > 4 else "", web=bool(m[5]) if len(m) > 5 else False,
                      wid=int(m[6]) if len(m) > 6 and isinstance(m[6], (int, float)) else 0)
            t_.pop("why", None); t_.pop("todo", None)
            st["info"] = t_
            st["last_msg"] = now
            if not st["shown"]:
                st["open"], st["a_from"], st["a_t0"] = False, 0.0, -9.0      # 每次都从胶囊开始(同 Mac)
            show(hwnd, True)
            glow_on("bg", 2.5)
        elif m[0] == "stuck" and len(m) >= 5:
            t_ = task(m[5] if len(m) > 5 else "", m[1])
            t_.update(step=m[2], why=m[3], todo=m[4], ack=False)
            st["info"] = t_
            st["last_msg"] = now
            st["borrow_auto"] = False             # 借鼠标弹开的那几秒里卡住:改由卡住管,别到点自动收
            show(hwnd, True)
            toggle(True)                          # 卡住:自动展开说清楚
        elif m[0] == "borrow":
            app_ = (m[1] if len(m) > 1 else "") or ""
            cand = sorted((x for x in tasks.values() if app_ and x["app"].lower() == app_.lower()), key=lambda x: -x["last"])
            t_ = cand[0] if cand else (st["info"] if st["info"] and st["info"].get("key") in tasks else task("", app_ or "SeeU"))
            if not st["info"]:
                st["info"] = t_
            if not st["shown"]:
                st["open"], st["a_from"], st["a_t0"] = False, 0.0, -9.0
            st["borrow"] = m[2] if len(m) > 2 and m[2] in BORROW_TEXT else "mouse"
            t_["borrow_kind"], t_["borrow_until"], t_["last"] = st["borrow"], now + BORROW_HOLD_S, now   # 岛上借鼠标的那个排第一
            st["borrow_until"] = st["last_msg"] = now
            st["borrow_until"] += BORROW_HOLD_S
            show(hwnd, True)
            through(hwnd, True)
            glow_on("real", BORROW_HOLD_S)
            if not st["open"]:
                st["borrow_auto"] = True
                toggle(True)
        elif m[0] == "queue" and len(m) >= 3:     # [queue, 程序, 开/关, 排第几, 谁占着, 任务名, 颜色](同 Mac)
            who_, app_ = (str(m[5]) if len(m) > 5 else ""), str(m[1] or "")
            key = task_key(who_, app_)
            t_ = tasks.get(key)
            on = bool(m[2])
            if on:
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
                    tasks.pop(key, None)          # 只排过队、没动过手(排不上就走了)→ 直接从岛上撤,别挂着「等下一步」(同 Mac 复查)
            if t_ is not None and len(m) > 6 and hex_rgb(m[6]):
                t_["color"] = hex_rgb(m[6])
        elif m[0] == "tint" and len(m) >= 3:      # 任务光标色(只记颜色,不算动作:不续命、不改步骤)
            key = task_key(str(m[1]), "")
            c_ = hex_rgb(m[2])
            if c_:
                if key in tasks:
                    tasks[key]["color"] = c_
                else:
                    tint_cache[key] = c_
                    if len(tint_cache) > 32:
                        tint_cache.clear()
        elif m[0] == "mark" and len(m) >= 3:          # 点击位置:记在点的那个窗口的任务上(没说是哪个窗口就记在当前任务上)
            wid = int(m[3]) if len(m) > 3 and isinstance(m[3], (int, float)) else 0
            t_ = next((x for x in tasks.values() if wid and x.get("wid") == wid), None) or st["info"]
            if t_:
                add_mark(t_, m[1], m[2], now)
        elif m[0] == "view" and len(m) > 1 and m[1] in ("card", "screen"):     # 命令行 / 测试也能换
            if st["view"] != m[1]:
                on_hit(hwnd, "view")
        elif m[0] == "expand" and st["shown"]:
            toggle(True)
        elif m[0] == "collapse" and st["shown"]:
            stuck_ack(st, tasks, now)
            toggle(False)
        elif m[0] == "hide":
            tasks.clear()
            st["info"], st["more"], st["solo"] = None, False, None
            glow["until"] = 0.0
            if st["borrow"]:
                borrow_end(hwnd)
            show(hwnd, False)
        elif m[0] == "light" and len(m) > 1 and m[1] in LIGHTS:      # 命令行 / 测试也能换档
            on_hit(hwnd, "light:" + m[1])
        elif m[0] == "theme" and len(m) > 1 and m[1] in ("dark", "light", "auto"):
            st["theme"], st["theme_t"] = m[1], 0.0
        elif m[0] == "quit":
            u.DestroyWindow(hwnd)

    def tick(hwnd):
        for _ in range(20):
            try:
                data = sock.recv(4096)
            except OSError:
                break
            try:
                on_msg(hwnd, json.loads(data.decode("utf-8")))
            except (ValueError, UnicodeDecodeError, TypeError, IndexError):
                pass
        now = time.time()
        if st["borrow"] and now > st["borrow_until"]:
            borrow_end(hwnd)
        glow_tick(now)
        if not st["shown"]:
            return
        if now - st["last_msg"] > hide_after(tasks, now, st["open"]) and not st["drag"] and not st["rs"]:
            tasks.clear()
            st["info"], st["more"], st["solo"] = None, False, None
            show(hwnd, False)
            return
        drop_old(tasks, now)
        hv = False
        if st["open"] and st["card"]:
            c = wt.POINT(); u.GetCursorPos(ctypes.byref(c))
            s, (cx, cy, cw_, ch_) = st["s"], st["card"]
            hv = pos.x + cx * s <= c.x <= pos.x + (cx + cw_) * s and pos.y + cy * s <= c.y <= pos.y + (cy + ch_) * s
        changed, st["hover"] = hv != st["hover"], hv
        if hv:                                     # 鼠标在卡片上:记下位置(画布坐标),按钮的小标签要用;挪了就重画
            mp_ = ((c.x - pos.x) / s, (c.y - pos.y) / s)
            changed, st["mouse"] = changed or mp_ != st.get("mouse"), mp_
        else:
            st["mouse"] = None
        if changed or st["drag"] or st["rs"]:
            stuck_touch(st, tasks, now)
        if not hv and st["light_open"]:
            st["light_open"] = False               # 鼠标离开卡片:灯光选项条收回
        if (changed or now - st["a_t0"] < ANIM_S + 0.1 or now - st["light_t0"] < 0.3 or now - st["h_t0"] < H_ANIM_S + 0.1
                or (st["shim"] and now - st["last_draw"] >= 0.03) or now - st["last_draw"] >= 0.066):   # 动画时每帧画,平时一秒 15 帧
            frame(hwnd)

    u.SetCursor.argtypes = [P]
    EDGE_CURSOR = {"l": 32644, "r": 32644, "t": 32645, "b": 32645, "tl": 32642, "br": 32642, "tr": 32643, "bl": 32643}   # 系统的「调整大小」箭头

    def msg_pt(lp):
        """鼠标消息里带的那一点(屏幕像素)。按下时用它、不用「光标现在在哪」:机器慢时消息处理得晚,
        光标早挪走了,按在边上的会被当成没按在边上(Win10 旧电脑实测:从最宽往回拉,三次有两次没拉动)。"""
        return wt.POINT(pos.x + ctypes.c_short(lp & 0xFFFF).value, pos.y + ctypes.c_short((lp >> 16) & 0xFFFF).value)

    def edge_now(c=None):
        """光标(不给就取真光标现在的位置)在不在看画面卡片的边上(只有单任务、展开着、真在看画面时才能拉):返回 (哪条边, 光标)。"""
        if c is None:
            c = wt.POINT(); u.GetCursorPos(ctypes.byref(c))
        if not (st["open"] and st["pic_on"] and not st["multi"] and st["card"] and st["view_geo"] and not st["borrow"] and k_now() > 0.99):
            return "", c
        return edge_at((c.x - pos.x) / st["s"], (c.y - pos.y) / st["s"], st["card"]), c

    @WNDPROC
    def proc(hwnd, msg, wp, lp):
        if msg == 0x0021:                         # WM_MOUSEACTIVATE:点它也不激活
            return 3
        if msg == 0x0020 and not st["rs"] and not st["drag"]:      # WM_SETCURSOR:移到卡片边 / 角上换成「调整大小」箭头(同 Mac)
            e_ = edge_now()[0]
            if e_:
                u.SetCursor(u.LoadCursorW(None, P(EDGE_CURSOR[e_])))
                return 1
        if msg == 0x0201:                         # 左键按在卡片边上:开始拉边缩放
            e_, c = edge_now(msg_pt(lp))
            if e_:
                s, (cx, cy, cw_, ch_) = st["s"], st["card"]
                left, top = pos.x + cx * s, pos.y + cy * s
                st["rs"] = dict(edge=e_, mx=c.x, my=c.y, w0=cw_, w=cw_, left=left, top=top, right=left + cw_ * s, bottom=top + ch_ * s)
                st["h_from"] = None
                u.SetCapture(hwnd)
                return 0
        if msg == 0x0200 and st["rs"]:
            rs = st["rs"]
            c = wt.POINT(); u.GetCursorPos(ctypes.byref(c))
            a_, ww_, wh_ = st["view_geo"]
            rs["w"] = view_fit_w(resize_w(rs["edge"], rs["w0"], (c.x - rs["mx"]) / st["s"], (c.y - rs["my"]) / st["s"], a_), a_, ww_, wh_)
            frame(hwnd)
            return 0
        if msg == 0x0202 and st["rs"]:
            u.ReleaseCapture()
            rs = st["rs"]
            if abs(rs["w"] - rs["w0"]) > 0.5:      # 真拉过:记住大小(竖 / 横各一份),悬浮标位置按外形现在停的地方反推(同拖动)
                vsize.update(view_remember(rs["w"], st["view_geo"][0]))
                L_, T_, R_, B_ = work_area()
                if cap["shape"]:
                    cap["x"], cap["y"] = int(round(cap_from_shape(cap["shape"][0], cap["shape"][2], L_, R_, st["s"]))), int(round(cap["shape"][1]))
                cap["mode"] = None
                if keep_pos:
                    set_live(cap=[round(cap["x"] / st["s"], 1), round(cap["y"] / st["s"], 1)], **vsize)
            st["rs"] = None
            frame(hwnd)
            return 0
        if msg == 0x0113:                         # WM_TIMER
            tick(hwnd)
            return 0
        if msg == 0x0201:                         # 左键按下:可能是点,也可能是拖
            c = msg_pt(lp)
            st["drag"], st["moved"] = (c.x, c.y, cap["x"], cap["y"]), False
            # 是不是真鼠标按下的:系统里这个键此刻真的按着(后台发来的鼠标消息不会让它按着)。左右键对调过的认另一个键
            # SendInput / mouse_event 模拟的点击也会让键「真的按着」→ 再问系统这条消息是不是硬件来的
            st["real_down"] = hand_down() and bool(u.GetAsyncKeyState(2 if u.GetSystemMetrics(23) else 1) & 0x8000)
            if st["real_down"]:
                global HAND_T
                HAND_T = time.time()           # isee.on(by="overlay") 认这个:本进程刚有一次手按
            u.SetCapture(hwnd)
            return 0
        if msg == 0x0200 and st["drag"]:
            c = wt.POINT(); u.GetCursorPos(ctypes.byref(c))
            dx, dy = c.x - st["drag"][0], c.y - st["drag"][1]
            if st["moved"] or abs(dx) + abs(dy) > 4 * st["s"]:
                if not st["moved"]:                # 开始拖:这一趟展开方式先定住,不然拖过屏幕边时会来回跳
                    cap["mode"] = anchor(cap["x"], *work_area()[0:3:2], st["s"])
                st["moved"] = True
                cap["x"], cap["y"] = st["drag"][2] + dx, st["drag"][3] + dy
                frame(hwnd)
            return 0
        if msg == 0x0202 and st["drag"]:
            u.ReleaseCapture()
            moved, st["drag"] = st["moved"], None
            if moved:                              # 拖完:按外形现在停的地方反推悬浮标位置(贴边收在那一角,其余收在顶上正中),记住
                L_, T_, R_, B_ = work_area()
                if cap["shape"]:
                    cap["x"], cap["y"] = int(cap_from_shape(cap["shape"][0], cap["shape"][2], L_, R_, st["s"])), int(cap["shape"][1])
                cap["mode"] = None
                if keep_pos:
                    set_live(cap=[round(cap["x"] / st["s"], 1), round(cap["y"] / st["s"], 1)])
                frame(hwnd)
            if not moved:
                lx, ly = (lp & 0xFFFF) / st["s"], ((lp >> 16) & 0xFFFF) / st["s"]
                if not st["open"]:
                    toggle(True)
                else:
                    nm = next((n_ for n_, hx, hy, hw_, hh_ in st["hits"] if hx <= lx <= hx + hw_ and hy <= ly <= hy + hh_), None)
                    if nm:
                        # 真点击 = 按下时系统里鼠标键真的按着,而且真光标此刻就在这个按钮上(消息里带的位置不算数)
                        c = wt.POINT(); u.GetCursorPos(ctypes.byref(c))
                        cxl, cyl = (c.x - pos.x) / st["s"], (c.y - pos.y) / st["s"]
                        at_ = next((n_ for n_, hx, hy, hw_, hh_ in st["hits"] if hx <= cxl <= hx + hw_ and hy <= cyl <= hy + hh_), None)
                        on_hit(hwnd, nm, real=st["real_down"] and at_ == nm)
                    elif st["light_open"]:
                        st["light_open"] = False
            return 0
        if msg == 0x0002:                         # WM_DESTROY
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(hwnd, msg, wp, lp)

    hinst = k32.GetModuleHandleW(None)
    wc = WNDCLASSW(0, proc, 0, 0, hinst, None, u.LoadCursorW(None, P(32649)), None, None, "SeeUFloat")
    u.RegisterClassW(ctypes.byref(wc))
    # 认「这次按下是不是手按的」用 GetCurrentInputMessageSource(Win8 起有;不挂全局钩子,不拖慢整机鼠标)
    class IMS(ctypes.Structure):
        _fields_ = [("dev", ctypes.c_int), ("origin", ctypes.c_int)]
    try:
        u.GetCurrentInputMessageSource.argtypes = [ctypes.POINTER(IMS)]
        u.GetCurrentInputMessageSource.restype = wt.BOOL
    except AttributeError:
        pass

    def hand_down():
        """正在处理的这条按下消息是不是硬件来的(IMO_HARDWARE = 1)。SendInput / mouse_event = 注入(2),
        PostMessage 发来的拿不到来源(0);读不到一律当「不是」(I See 开不了,关照样能关)。"""
        try:
            src = IMS()
            return bool(u.GetCurrentInputMessageSource(ctypes.byref(src))) and src.origin == 1
        except Exception:   # noqa: BLE001
            return False

    glow_proc = WNDPROC(lambda h_, m_, w_, l_: u.DefWindowProcW(h_, m_, w_, l_))     # 光圈窗口:什么消息都不管
    wc2 = WNDCLASSW(0, glow_proc, 0, 0, hinst, None, None, None, None, "SeeUGlow")
    u.RegisterClassW(ctypes.byref(wc2))
    ex = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000      # 分层 | 置顶 | 不进任务栏 | 不抢前台
    hwnd = u.CreateWindowExW(ex, "SeeUFloat", "", 0x80000000, 0, 0, 10, 10, None, None, hinst, None)
    setup(hwnd)
    global SERVING
    SERVING = True
    __import__("threading").Thread(target=cam_loop, daemon=True).start()
    u.SetTimer(hwnd, 1, 16, None)
    msg = wt.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))
    sock.close()


def demo(secs=60):
    """手动试用:像真任务一样隔几秒换一步,中间卡住一次。"""
    steps = ["读网页", "点导出", "等下载", "改文件名"]
    t0, i = time.time(), 0
    while time.time() - t0 < secs:
        if i == 5:
            stuck("Chrome", "选下拉框", "找不到下拉框", "手动选一下", who="Demo")
        else:
            browser("Chrome", steps[i % len(steps)], who="Demo")
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
