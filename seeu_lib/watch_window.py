#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
watch_window.py —— SeeU 监看「悬浮窗」+ 收起后的「悬浮标」(用户 10-15 定的叫法)。

悬浮窗:置顶小窗实时播一个窗口的画面(如 iPhone 镜像),画出点击位置。纯显示,点它不会操作被监看的窗口。
  - SeeU 动手时出现(收到 show),HIDE_AFTER_S 秒没再收到就缩成悬浮标并关画面流(省 CPU),悬浮标再留 LINGER_S 秒才淡出;
  - 独立于其他窗口,能拖、能拉边缩放(保持比例),位置大小记在 STATE_FILE;所有桌面都显示(跟着用户走);
  - SeeU C-0.3(10-21 用户定):悬浮标、悬浮窗、卡片都是浅色液态玻璃 + 深色字;画面四周一圈玻璃边,上面一条玻璃栏平时写 App 名,
    鼠标移上去换成按钮栏:I See / 灯光 / ……(空)/ 看画面 / 收起
      灯光    —— 屏幕四周光圈三档:关(灭灯泡)/ 抢占(橙,借用系统鼠标时亮)/ 被控(紫,只要在操作就亮);点一下原地往右弹出选项条
      看画面  —— 文字卡 ↔ 实时画面(镜像默认画面,点了换成「正在点击」文字卡;浏览器默认文字卡,知道窗口号才能看画面,不知道就灰)
      收起    —— 缩成悬浮标。看画面、收起只有图标,鼠标移上去才显示名字
    运行中:圆点呼吸 + 文字微光(学 Codex,不要沿边滚动的流光)。字走 seeu/i18n.py 中英两套。
悬浮标:胶囊(紫色呼吸小圆点 + "SeeU");点一下展开,拖动它悬浮窗也跟着挪。展开方式 C(10-30 用户定):
  悬浮标在中间 → 像灵动岛从顶部正中往两边撑开;贴屏幕左/右边 → 从那一角往里长。收起时缩回悬浮标原处。
  收起状态会记住(下一轮开跑还是悬浮标);一轮结束 HIDE_AFTER_S + LINGER_S 秒后悬浮标也消失。收起时不抓画面。
浏览器操作(SeeU C-0.1,10-20 用户定):SeeU 操作浏览器时也弹悬浮标(后台标签页没画面可播);点开是一张小卡片写正在做哪一步。
  这时按钮栏 = 「I See」开关 + 抢占提示 + 被控提示 + 收起(卡片 300 宽写得下全称;镜像那边按钮栏不变)。
  I See 开着时悬浮标上:字换成「I See」、呼吸圆点换成眼睛;颜色不变(紫 = 后台 / 橙 = 借用系统鼠标,不另加颜色)。
🔴 两个窗口都**永远不能成为键盘窗口**(10-15 用户报"控制不了输入框/无限回车":可缩放窗口点一下会抢键盘)。

开关的共享状态 LIVE_FILE(项目读它决定亮不亮光圈;问卷开跑时写初始值,悬浮窗上随时改):
  from seeu_lib import watch_window as ww
  ww.set_live(halo_real=True, halo_bg=False)   # 开跑时按问卷写初始值
  ww.halo_allowed("real" | "bg")               # 现在这种模式该不该亮光圈;从没设过返回 None(调用方用自己的默认)

Python:
  ww.show(window_id)          # 出现 / 续时(进程没起会自动拉起)
                              # 项目名:开跑时设环境变量 SEEU_PROJECT=项目名(或传 who=),顶上写「项目名 · App 名」
  ww.mark("click", fx, fy)    # 画点击位置;fx/fy = 在目标窗口里的比例 0~1(左上为 0)
  ww.browser("Safari", "读网页")   # 浏览器操作:弹悬浮标(没有画面流),卡片上写这一步
  ww.stuck("Safari", "选下拉框", 原因, 怎么办, isee_helps)   # 普通模式卡住:自动展开卡片说清楚(10-20 用户定)
  ww.visible_frame()          # 悬浮窗/悬浮标正显示时返回 (x, y, w, h)(Cocoa 坐标),否则 None —— 提示条用来让位
  ww.passthrough_wids()       # 正在"不接鼠标"的悬浮窗口编号(借用系统鼠标那几秒);查"最上层窗口挡没挡"时跳过它们
命令行:
  python3 -m seeu_lib.watch_window demo ["应用名"] [秒数]   手动试用:连续显示一阵(默认 iPhone Mirroring、60 秒)
  python3 -m seeu_lib.watch_window show <窗口id>     手动看一眼(60 秒后自己收)
  python3 -m seeu_lib.watch_window hide | quit | reset | expand | collapse    reset = 位置大小回默认;expand/collapse = 展开/收起
"""
import json
import os
import socket
import subprocess
import sys
import time
try:
    from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)
except ImportError:          # 当独立程序跑(python3 …/watch_window.py serve)时找不到 seeu_lib 包:同一取法兜底
    home = lambda *p: os.path.join(os.environ.get("SEEU_HOME") or os.path.expanduser("~/.seeu"), *p)   # noqa: E731

PORT = 47833
DEFAULT_W = 220          # 默认宽(点);高按目标窗口比例(10-15 用户要按钮写全称,220 刚好放得下)
MIN_W, MAX_W = 150, 700   # 10-15 用户:缩太小按钮会叠,最小宽提到 150(高度按比例一起限,见 place)
MARGIN = 16              # 默认位置离屏幕右边/上边
FPS = 10
STREAM_MAX_W = 1600      # 画面流最宽像素(10-31 用户报横屏糊:原来固定 600,2 倍屏横屏窗要 1370 → 改按窗口实际像素取,这里只是上限)
STREAM_MIN_W = 300       # 下限
STREAM_REOPEN = 1.2      # 窗口变大超过两成(或缩到 1/1.6 以下)才重开流,拖一点不重开
HIDE_AFTER_S = 60        # 多久没收到 show 就收起(10-15 定 10 秒;C-1.3 用户:两次操作间常隔十几秒,关了又开体验差,改 60)
LINGER_S = 60            # SeeU C-0.4 用户定(1 分钟画面 + 1 分钟悬浮标;原定 300 用户嫌久):到点先缩成悬浮标(不直接消失),再留这么多秒才淡出;点开看的是实时画面
IDLE_EXIT_S = 600        # 硬上限:空闲 10 分钟退出
RING_S = 0.6             # 点击波纹时长
DOT_S = 3.0              # 最后一次点击位置的小圆点留多久
TB_H = 28                # 顶部按钮栏高
TB_FONT = 13             # 按钮栏字号(用户 10-15:原来 11 号太小)
CLOSE_ANIM_S = 0.22      # 点收起:图标两边先合拢再缩回悬浮标(SeeU C-0.3 用户要)
LIGHT_H = 20             # 灯光选项条高(SeeU C-0.3 用户:24 高顶满按钮栏、看着超出)
ICON_R = 7               # 按钮栏三个圆(两个开关 + 收起)统一半径(10-15 用户:原来大小不一致)
FULL_W = 210             # 悬浮窗宽于这个才写全称,窄了只画圆点和图标
EDGE = 6                 # 离边缘多少点以内显示"调整大小"箭头
CAP_W, CAP_H = 92, 32    # 悬浮标尺寸(10-15 用户:原来 72×26 小了);浏览器带进度时往左加宽(SeeU C-0.5)
CAP_STEP_MAX = 10        # 悬浮标上进度最多几个字,多了截成「…」(SeeU C-0.5 用户在样品里定)
GLASS_TINT_A = 0.08      # 液态玻璃染色浓度(模式色)。SeeU C-0.3 用户在样品里定"很淡":原来 0.32 + 白字在浅色背景上看不清
DARK = (26 / 255.0, 28 / 255.0, 31 / 255.0)   # 浅色玻璃上的字/图标颜色(Codex 实测)
LIGHT_TXT = (0.96, 0.96, 0.97)   # 暗黑模式深色玻璃上的字/图标(SeeU C-0.4:Codex 跟系统外观,白天黑字、暗黑白字)
BORROW_HOLD_S = 2.5      # 借鼠标弹开的卡片:最后一次借鼠标消息后这么多秒没再借就收回(10-27)
PASS_S = 8.0            # 收到 show(…,"real")(借用系统鼠标)后这么多秒内悬浮窗/悬浮标不接鼠标,点击穿过去(SeeU C-0.4 实测:手势解锁拖着悬浮窗走了)
FIT_SCREEN = 0.9         # 悬浮窗宽、高都不超过屏幕可用区的这么多(SeeU C-0.4 用户报:记住的大宽度 + 竖屏比例 → 比屏幕还高)
SUB_A = 0.62             # 小字(第二行、浏览器名)透明度
SHIMMER_W, SHIMMER_SPEED, SHIMMER_PERIOD = 48.0, 150.0, 5.0   # 运行中文字微光:亮带宽(点)、扫过速度(点/秒)、一轮秒数(Codex 实测)
BREATH_S = 0.9           # 圆点呼吸:由亮到暗的秒数(来回 1.8 秒,同原来)
PANEL_R = 16             # 悬浮窗/卡片玻璃圆角
BORDER = 6               # 悬浮窗画面四周的玻璃边宽(上边是按钮栏 TB_H)
PIC_R = 10               # 画面圆角
WHY_HOLD_S = 15.0        # AI 说的动作名(why 消息带的「打字」等)收到后多久内算数;原因文字本身跟着动作走(见 why_now)
WHY_SIZE = 12            # 原因小字字号(文字卡灰字、画面底边字幕带都用)
ACTIVE_S = 3.0           # 最近这么多秒内有动作(show/mark)= 正在动手,文字微光扫;否则 = 等下一步,只留圆点呼吸
PURPLE = (0.498, 0.467, 0.867)   # #7F77DD 后台模式
ORANGE = (1.0, 0.624, 0.039)     # #FF9F0A 借用系统鼠标(10-15 用户定:原浅天蓝不醒目;比官方 Computer Use 的砖橙 #D97757 更亮偏黄,分得开)
# 🔴 跟 seeu/设置.json「让路模式颜色」「后台模式颜色」保持一致(SeeU 的代理光标、屏幕光圈读那边)
STATE_FILE = home("watch_window.json")
LIVE_FILE = home("seeu_live.json")
LOG_FILE = home("watch_window.log")
SPAWN_WAIT_S = 3.0       # 硬上限:拉起进程后等它就绪
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEU_SETTINGS = os.path.join(ROOT, "seeu", "设置.json")   # I See 开关存这里(seeu/isee.py 管;这里只读,改走命令)
BROWSER_W = 300          # 浏览器卡片宽(10-20 用户:按钮栏四个都写全称)
BROWSER_H, BROWSER_H_ISEE = 68, 90   # 卡片高:顶部一行(浏览器名 / 鼠标移上来换按钮栏)+ 步骤;I See 开着多一行说明
EXPAND_EDGE = 40         # 悬浮标离屏幕左/右边这么近就算"贴边",从那一角展开(展开方式 C,10-30 用户定)
MORPH_T, MORPH_BOUNCE = 0.5, 0.2   # 展开/收起学 iPhone 灵动岛:弹簧变形(10-20 用户在预览里定默认值)
MORPH_FPS = 60
XFADE_S = 0.15           # 悬浮标 ↔ 深色窗口交叉淡化时长
PULSE_S = 8.0            # 卡住且 I See 能解决时,按钮栏的 I See 闪多久


# ---------------------------------------------------------------- 调用方
def send(*parts):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(" ".join(str(p) for p in parts).encode(), ("127.0.0.1", PORT))
    finally:
        s.close()


def _running():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", PORT))     # 绑得上 = 没人在监听
        return False
    except OSError:
        return True
    finally:
        probe.close()


def ensure_serve():
    if _running():
        return True
    subprocess.Popen(["/usr/bin/python3", os.path.abspath(__file__), "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < SPAWN_WAIT_S:
        time.sleep(0.1)
        if _running():
            time.sleep(0.2)
            return True
    return False


def who_name(who=None):
    """项目名(SeeU C-0.4 用户定):调用方传 who,或开跑时设环境变量 SEEU_PROJECT(如「项目甲」「个人」)。
    最多 4 个汉字 / 8 个字母,超了截掉;没有就返回 ""(悬浮窗照旧只写 App 名)。"""
    s = str(who if who is not None else os.environ.get("SEEU_PROJECT", "")).strip().replace(" ", "")
    out, n = "", 0
    for ch in s:
        n += 2 if ord(ch) > 0x2E80 else 1
        if n > 8:
            break
        out += ch
    return out


def why(app, text, who=None, act=""):
    """AI 每一步的原因(SeeU 10-30,MCP 的 why 参数):文字卡「正在…」下面一行灰字,看画面时压在底边字幕带上。
    app = 这一步操作的 App(跟悬浮窗正在显示的对得上才写);text 空 = 这一步没写原因(清掉上一句)。
    act = 这一步是什么动作(打字 / 滚动 / 按键…,中文步骤名):悬浮窗用它代替「点击」(按编号打字前会先后台点一下框,10-30 用户:应写打字);
    点击类不传,照旧认点击处的字。
    旧版悬浮窗不认识这条消息,直接忽略。"""
    ensure_serve()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        w = who_name(who)
        s.sendto(("why " + json.dumps([str(app or ""), str(text or "")[:300], w, str(act or "")],
                                      ensure_ascii=False)).encode(), ("127.0.0.1", PORT))
    finally:
        s.close()


def show(window_id, mode="bg", who=None):
    """mode = bg(后台操作)| real(借用系统鼠标):悬浮标、点击标记跟着变色(紫 / 橙)。
    who = 项目名(不传读环境变量 SEEU_PROJECT):悬浮窗顶上写「项目名 · iPhone Mirroring」,窄了只写项目名。"""
    ensure_serve()
    w = who_name(who)
    send("show", int(window_id), "real" if mode == "real" else "bg", *([w] if w else []))


def mark(kind, fx, fy, who=None):
    """who(项目名,不传读 SEEU_PROJECT):多个任务同时在跑时,让悬浮标知道是谁点的;没有就算最近发消息的那个任务。"""
    w = who_name(who)
    send("mark", kind, round(float(fx), 4), round(float(fy), 4), *([w] if w else []))


def browser(app, step="", wid=None, who=None):
    """浏览器操作:弹悬浮标(后台模式紫色)。app / step 可以带空格(整条按 JSON 发)。
    wid = 正在操作的浏览器窗口号(SeeU C-0.3):卡片上点「看画面」播这个窗口;不传 = 不知道是哪个窗口/可能是后台标签页,按钮变灰。"""
    ensure_serve()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        w = who_name(who)
        arr = [str(app), str(step)] + ([int(wid) if wid else 0, w] if w else ([int(wid)] if wid else []))
        s.sendto(("browser " + json.dumps(arr, ensure_ascii=False)).encode(),
                 ("127.0.0.1", PORT))
    finally:
        s.close()


def stuck(app, step, why, todo, isee_helps=False, who=None):
    """普通模式某一步卡住:卡片自动展开,写卡在哪、为什么、怎么办;I See 能解决时按钮栏的 I See 闪一会。
    who = 项目名(不传读 SEEU_PROJECT):多任务时红色标在对应那一行。"""
    ensure_serve()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        w = who_name(who)
        s.sendto(("stuck " + json.dumps([str(app), str(step), str(why), str(todo), bool(isee_helps)] + ([w] if w else []),
                                        ensure_ascii=False)).encode()[:4000], ("127.0.0.1", PORT))
    finally:
        s.close()


def isee_on():
    """读 seeu/设置.json 的 I See(过期当关;真正的到期处理在 seeu.isee)。环境变量看不到别的进程,这里只认设置文件。"""
    d = _read_json(SEEU_SETTINGS)
    if str(d.get("I See", "关")) not in ("开", "on", "1", "true"):
        return False
    until = d.get("I See 到期")
    try:
        return not until or time.time() < time.mktime(time.strptime(until, "%Y-%m-%d %H:%M"))
    except ValueError:
        return True


def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            os.replace(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_json(path, **kw):
    st = _read_json(path)
    st.update(kw)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def _read_state():
    return _read_json(STATE_FILE)


def _write_state(**kw):
    _write_json(STATE_FILE, **kw)


def live():
    """悬浮窗上的开关状态:collapsed(收起成悬浮标)、halo_real(抢占光圈)、halo_bg(被控光圈)。没设过的键不在里面。"""
    return _read_json(LIVE_FILE)


def set_live(**kw):
    """项目开跑时按问卷写初始值(halo_real/halo_bg);悬浮窗按钮也写这里。"""
    _write_json(LIVE_FILE, updated=time.time(), **kw)


def halo_allowed(mode):
    """mode = real(借用系统鼠标)| bg(后台)。被控光圈开着 → 两种都亮;抢占光圈开着 → 只有 real 亮。
    两个都没设过返回 None,调用方用自己的默认(环境变量 / 设置文件)。"""
    lv = live()
    if "halo_real" not in lv and "halo_bg" not in lv:
        return None
    return bool(lv.get("halo_bg")) or (mode == "real" and bool(lv.get("halo_real")))


def passthrough_wids():
    """借用系统鼠标那几秒(show(…,"real") 后 PASS_S 秒内)悬浮窗/悬浮标不接鼠标、点击穿到下面的窗口(SeeU C-0.4)。
    返回这时的窗口编号集合(其余时候空集)。调用方查"点的位置最上层是谁"时把它们跳过:它们还在窗口清单里,但不挡点击。"""
    lv = live()
    if time.time() > float(lv.get("pass_until") or 0):
        return set()
    return {int(x) for x in (lv.get("pass_wids") or [])}


def visible_frame():
    st = _read_state()
    fr = st.get("shown_frame") or st.get("frame")
    if st.get("visible") and fr and time.time() - st.get("updated", 0) < 10:   # 显示期间每 3 秒续一次
        return tuple(fr)
    return None


# ---------------------------------------------------------------- 显示进程
NEAR_PT = (80, 35)      # 点击处四周各取多少点认字(左右 / 上下)
NEAR_MAX_PT = 10        # 认到的字(字框边)离点击处超过这么多点就不算(10-27 截图实测:关闭 X 离旁边一行字约 12 点,20 点会误认)
NEAR_CONF = 0.3
NEAR_ON_PT = 5          # 点击处离字框不超过这么多点就算「点在字上」,卡片不写「附近」(10-28 用户定:点准了别让人误会)


def near_text(wid, fx, fy):
    """点击处附近认字(SeeU 10-27 定「自动推」:卡片写「正在点『X』附近」;只给悬浮窗显示用,不影响点击)。
    截窗口走 sck_capture(ScreenCaptureKit,不会被 App 当成截屏)→ 只认点四周一小块(准档 30~90 毫秒)→ 取离点最近、够近的一条。
    返回 (字, 点在字上没有);认不到 / 太远返回 ("", False)。fx, fy = 点在窗口里的比例(mark 消息同款)。"""
    import tempfile
    import Quartz
    from seeu_lib import sck_capture as sck_, ocr as ocr_
    png = os.path.join(tempfile.gettempdir(), f"seeu_near_{os.getpid()}.png")
    if not sck_.capture_window(int(wid), png):
        return "", False
    im = ocr_.CIImage.imageWithContentsOfURL_(ocr_.NSURL.fileURLWithPath_(png))
    if im is None:
        return "", False
    W_, H_ = im.extent().size.width, im.extent().size.height
    info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
    bw = float((info[0].get("kCGWindowBounds") or {}).get("Width") or 0) if info else 0
    k = W_ / bw if bw else 2.0                      # 像素 / 点
    x, y = fx * W_, fy * H_
    x0, y0 = max(0, x - NEAR_PT[0] * k), max(0, y - NEAR_PT[1] * k)
    x1, y1 = min(W_, x + NEAR_PT[0] * k), min(H_, y + NEAR_PT[1] * k)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return "", False
    crop = im.imageByCroppingToRect_(((x0, H_ - y1), (x1 - x0, y1 - y0)))
    req = ocr_.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)                      # 准档(快档认不出中文,10-27 实测)
    req.setRecognitionLanguages_(["zh-Hans", "en"])
    req.setUsesLanguageCorrection_(True)
    ocr_.VNImageRequestHandler.alloc().initWithCIImage_options_(crop, None).performRequests_error_([req], None)
    best, best_d = "", None
    for o in req.results() or []:
        c = o.topCandidates_(1)
        if not c or float(c[0].confidence()) < NEAR_CONF:
            continue
        bb = o.boundingBox()                         # 归一化,原点左下
        bx0 = x0 + bb.origin.x * (x1 - x0)
        bx1 = bx0 + bb.size.width * (x1 - x0)
        by1 = y1 - bb.origin.y * (y1 - y0)
        by0 = by1 - bb.size.height * (y1 - y0)
        d = (max(bx0 - x, 0, x - bx1) ** 2 + max(by0 - y, 0, y - by1) ** 2) ** 0.5   # 点到字框的距离(在框里 = 0)
        if best_d is None or d < best_d:
            best, best_d = str(c[0].string()).strip(), d
    if best_d is None or best_d > NEAR_MAX_PT * k:
        return "", False
    return (best if len(best) <= 12 else best[:11] + "…"), best_d <= NEAR_ON_PT * k


def serve():
    import objc
    import Quartz
    import CoreMedia
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSAttributedString, NSBezierPath,
                        NSColor, NSEvent, NSFloatingWindowLevel, NSFont, NSFontAttributeName,
                        NSForegroundColorAttributeName, NSGraphicsContext, NSPanel, NSScreen, NSTrackingArea, NSView,
                        NSBackingStoreBuffered, NSWindowStyleMaskBorderless, NSWindowStyleMaskResizable,
                        NSWindowStyleMaskNonactivatingPanel, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWorkspace,
                        NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowCollectionBehaviorStationary)
    from Foundation import (NSBundle, NSMakePoint, NSMakeRect, NSMakeSize, NSObject, NSRunLoop,
                            NSRunLoopCommonModes, NSTimer, NSDistributedNotificationCenter)
    from seeu_lib import sck_capture as sck
    from seeu_lib import watch_island as isl      # 多任务灵动岛(C-0.8);只有显示进程用得到 AppKit

    NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"   # 不进 Dock、不抢前台(同 cursor_overlay)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    sock.setblocking(False)

    # 10-15 实测:每帧 CIImage → CGImage 再画,内存每秒涨约 30MB;改成把画面流的显存缓冲(IOSurface)直接交给图层。
    class WatchOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
        def init(self):
            self = objc.super(WatchOutput, self).init()
            self.n = 0
            self.pb = None
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, sb, typ):
            if typ != 0:
                return
            pb = CoreMedia.CMSampleBufferGetImageBuffer(sb)
            if pb is None:            # 画面没变时系统送空帧
                return
            self.pb = pb
            self.n += 1

    lv0 = live()
    st = dict(wid=None, px=None, stream=None, out=None, n=-1, aspect=None,
              last_show=0.0, last_act=0.0, last_touch=0.0, last_msg=time.time(), alpha=0.0, cap_alpha=0.0, marks=[], dot=None,
              hover=False, collapsed=True, live=lv0, live_t=0.0,     # 10-27 用户定:不记上次展开/收起,每次从悬浮标开始
              browser=None, b_expanded=False, isee=isee_on(),
              mview="screen", stream_wid=None, title="", light=None, mouse=None, last_mark=None, why=None)   # mview:镜像看画面/看操作

    def mode_color():
        """当前模式的颜色:借用系统鼠标 = 橙,后台 = 紫(悬浮标、点击标记都用它)。"""
        return ORANGE if st.get("mode") == "real" else PURPLE

    def col(rgb, a):
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], a)

    def text(s, size, color, x, y, bold=False):
        f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        a = {NSFontAttributeName: f, NSForegroundColorAttributeName: color}
        s_ = NSAttributedString.alloc().initWithString_attributes_(s, a)
        s_.drawAtPoint_(NSMakePoint(x, y))
        return s_.size().width

    def text_h(s, size, w, lines=2):
        """多行文字折行后的高度(最多 lines 行)。"""
        a = {NSFontAttributeName: NSFont.systemFontOfSize_(size)}
        r = NSAttributedString.alloc().initWithString_attributes_(s, a).boundingRectWithSize_options_(
            NSMakeSize(w, 1000), 1 | 2)      # 1 = 按行折, 2 = 用字体行距
        return min(float(r.size.height) + 2, size * 1.35 * lines)

    def text_box(s, size, color, x, y, w, h, bold=False):
        """多行文字(自动折行,超出 h 截掉)。"""
        f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        a = {NSFontAttributeName: f, NSForegroundColorAttributeName: color}
        NSAttributedString.alloc().initWithString_attributes_(s, a).drawInRect_(NSMakeRect(x, y, w, h))

    def win_h(w, aspect):
        """悬浮窗宽 w 时的高:画面按比例 + 上面按钮栏 + 下面玻璃边(SeeU C-0.3)。"""
        return (w - 2 * BORDER) / aspect + TB_H + BORDER

    def pic_rect(w, h):
        """画面区(翻转坐标):x, y, 宽, 高。"""
        return BORDER, TB_H, w - 2 * BORDER, h - TB_H - BORDER

    def default_frame(aspect):
        vf = NSScreen.mainScreen().visibleFrame()
        w = DEFAULT_W
        h = win_h(w, aspect)
        return (vf.origin.x + vf.size.width - w - MARGIN, vf.origin.y + vf.size.height - h - MARGIN, w, h)

    # ---- 悬浮窗上层视图:点击标记 + 顶部按钮栏 + 接鼠标
    # ---- 按钮栏(SeeU C-0.3 改版,用户 10-21 在预览里定,见 seeu/SeeU-相关要点.md「灯光按钮定稿」):
    # I See / 灯光 / ……(空)/ 看画面 / 收起。看画面、收起只有圆形图标,鼠标移上去才显示名字。
    LIGHTS = ("off", "real", "bg")

    def tr(key, zh, **kw):
        """中英对照(seeu/i18n.py,设置.json「语言」);取不到就用中文默认。"""
        try:
            if ROOT not in sys.path:
                sys.path.insert(0, ROOT)
            from seeu.i18n import T as _T
            s_ = _T(key, **kw)
            if s_ != key:
                return s_
        except Exception:
            pass
        try:
            return zh.format(**kw) if kw else zh
        except Exception:
            return zh

    def tr_step(name):
        try:
            from seeu.i18n import step as _s
            return _s(name)
        except Exception:
            return name

    def doing(stp):
        """「正在点击」这类(10-20 用户:光写「点击」有歧义,点了?要点?)。步骤名按当前语言。"""
        stp = (stp or "").strip()
        if not stp:
            return tr("card.idle", "等下一步")
        if stp.startswith("正在"):
            stp = stp[2:]
        return tr("card.doing", "正在{step}", step=tr_step(stp))

    def light_level():
        """灯光三档:off = 两个光圈都关 / real = 只在抢占真鼠标时亮 / bg = 被控就亮(包含抢占)。"""
        lv = st["live"]
        return "bg" if lv.get("halo_bg") else ("real" if lv.get("halo_real") else "off")

    def light_label(lvl):
        return {"off": tr("btn.light_off", "关"), "real": tr("btn.halo_real", "抢占"),
                "bg": tr("btn.halo_bg", "被控")}[lvl]

    def in_browser():
        return st.get("browser") is not None

    def is_card():
        """现在显示的是文字卡(浏览器默认 / 镜像点了「看操作」/ 借鼠标自动弹开),不是实时画面。"""
        if st.get("borrow_auto"):
            return True
        if in_browser():
            return st["stream"] is None
        return st["mview"] == "steps"

    def card_info():
        """文字卡的内容:dict(app, step, stuck?)。镜像没有步骤信息,按最近一次点击标记写「正在点击」/「等下一步」。"""
        if st.get("borrow_auto") or borrowing():     # 借鼠标(10-27 自动弹开;10-30 展开着也写):「正在用你的鼠标」+「别动鼠标」
            lm = st.get("last_mark")
            # 10-30 实测:借鼠标在空白处拖动解卡(没发点击标记),卡片却写了十几秒前后台点的「取消」→ 只认 ACTIVE_S 内的点击
            x, on = near_label() if lm is not None and time.time() - lm[1] < ACTIVE_S else ("", False)
            return dict(app=(st.get("browser") or {}).get("app") or st.get("title") or "SeeU",
                        step="__borrow__", line=((tr("card.borrow_on", "正在用你的鼠标(点「{x}」)", x=x) if on
                                                  else tr("card.borrow_at", "正在用你的鼠标(点「{x}」附近)", x=x)) if x
                                                 else tr("card.borrow", "正在用你的鼠标")))
        if in_browser():
            return st["browser"]
        lm = st.get("last_mark")
        act = lm is not None and time.time() - lm[1] < ACTIVE_S
        x, on = near_label()
        stp = (near_step(x, on) if x else "点击") if act else ""
        wa = why_act(st.get("title"))
        if stp and wa:              # 10-30:AI 这一步说了是打字 / 滚动…,别写成「点击」
            stp = tr_step(wa)
        return dict(app=st.get("title") or "SeeU", step=stp)

    def near_label():
        """最近一次点击处认到的字和点在字上没有(跟最近一次点击对得上才算);没有返回 ("", False)。"""
        n, lm = st.get("near"), st.get("last_mark")
        if not n or not lm or n[1] < lm[1] - 0.05:
            return "", False
        return n[0], n[2]

    def near_step(x, on):
        """点在字上写「点『X』」,在字旁边写「点『X』附近」(10-28 用户定)。"""
        return tr("card.on", "点「{x}」", x=x) if on else tr("card.near", "点「{x}」附近", x=x)

    hid_cache = {}

    def browser_hidden(app):
        """浏览器在不在"隐身"干活:整个 App 隐藏着,或者一个正常窗口都没开(10-22 用 AppleScript 拉起的 Safari 就是这样)。
        窗口在别的桌面不算(窗口还在)。1 秒内查过就用上次的。"""
        now = time.time()
        c = hid_cache.get(app)
        if c and now - c[0] < 1.0:
            return c[1]
        hid = False
        try:
            a = next((x for x in NSWorkspace.sharedWorkspace().runningApplications() if x.localizedName() == app), None)
            if a is not None:
                pid = a.processIdentifier()
                wins = [w for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, 0) or []
                        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0
                        and (w.get("kCGWindowBounds") or {}).get("Width", 0) > 100
                        and (w.get("kCGWindowBounds") or {}).get("Height", 0) > 100]
                hid = bool(a.isHidden()) or not wins
        except Exception:
            hid = False
        hid_cache[app] = (now, hid)
        return hid

    def borrowing():
        """正在借系统鼠标(收到 show … real,BORROW_HOLD_S 内)。10-30 用户报:悬浮窗已展开成卡片时借鼠标没提示、写「等下一步」
        → 不管收着 / 展开卡片 / 看画面,借鼠标时都写「正在用你的鼠标」。"""
        return st.get("mode") == "real" and time.time() < st.get("borrow_until", 0)

    def card_notes():
        """卡片步骤下面的小字说明:借鼠标一条(10-27);I See 开着一条;浏览器隐身(没开窗口/隐藏)一条(SeeU C-0.5 用户定)。"""
        b = st.get("browser") or {}
        out = []
        if st.get("borrow_auto") or borrowing():
            out.append(tr("card.borrow_note", "别动鼠标,几秒后还你"))
            return out
        if b.get("hidden"):
            out.append(tr("card.hidden_note", "{app} 在后台隐身干活,别点开它", app=b.get("app") or "浏览器"))
        if st["isee"]:
            out.append(tr("card.isee_note", "我已知风险，授权 AI 执行 · 卡住时请立即报告！"))
        return out

    WHY_ALIAS = {"iphone mirroring": "mirror", "iphone 镜像": "mirror", "镜像": "mirror"}

    def _app_norm(s):
        s = str(s or "").strip().lower()
        return WHY_ALIAS.get(s, s)

    def why_task():
        """有 AI 任务(60 秒内收到过 why 消息,10-30):按钮栏才出「原因」按钮;不发 why 的自动化程序看不到。"""
        w = st.get("why")
        return bool(w) and time.time() - w["t"] < HIDE_AFTER_S

    def why_act(name):
        """AI 这一步的动作名(why 消息带来的,如「打字」);过时 / 不是同一个 App / 没给 → ""。不管「原因」开没开。"""
        w = st.get("why")
        if not w or not w.get("act") or time.time() - w["t"] > WHY_HOLD_S:
            return ""
        a, n = _app_norm(w["app"]), _app_norm(name)
        return "" if (a and n and not (a in n or n in a)) else w["act"]

    def why_shown():
        """「原因」按钮开着没有(默认开;关了记在 live 文件 why_off)。"""
        return not st["live"].get("why_off")

    def why_now(name):
        """悬浮窗正在显示的 App(name)这一步的原因;没有 / 关着 / 过时 / 不是同一个 App → ""。
        10-30 用户:原因跟着动作走 —— 动作那行还在就一直写,到下一句原因来了才换;任务停了(HIDE_AFTER_S 没新原因)才算过时。
        (原来 15 秒就过时,动作还挂着原因先没了,一会有一会没有。)看画面字幕带另有「动手 3 秒内」的条件,照旧会淡掉。"""
        w = st.get("why")
        if not w or not w["text"] or not why_shown() or time.time() - w["t"] > HIDE_AFTER_S:
            return ""
        a, n = _app_norm(w["app"]), _app_norm(name)
        if a and n and not (a in n or n in a):
            return ""
        return w["text"]

    def fit_lines(s, size, w, n):
        """把 s 截到 w 宽里折 n 行放得下(放不下末尾加「…」);n <= 0 返回 ""。"""
        if n <= 0 or not s:
            return ""
        lim = size * 1.35 * n + 1
        f = {NSFontAttributeName: NSFont.systemFontOfSize_(size)}

        def h_(x):
            return float(NSAttributedString.alloc().initWithString_attributes_(x, f).boundingRectWithSize_options_(
                NSMakeSize(w, 1000), 1 | 2).size.height)
        if h_(s) <= lim:
            return s
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if h_(s[:mid] + "…") <= lim:
                lo = mid
            else:
                hi = mid - 1
        return s[:lo].rstrip() + "…"

    def card_why():
        """文字卡上「正在…」下面那行原因(最多 2 行,已截好);卡住 / 借鼠标 / 没有原因 → ""。"""
        if not is_card() or st.get("borrow_auto") or borrowing():
            return ""
        info = card_info()
        if info.get("stuck"):
            return ""
        return fit_lines(why_now(info.get("app")), WHY_SIZE, BROWSER_W - 28, 2)

    def screen_ok():
        """「看画面」能不能点:镜像一直能;浏览器要知道窗口号(网页模块那条路可能是后台标签页 → 灰,用户 10-21 定);
        浏览器隐身干活时也灰(SeeU C-0.5,10-22 用户定:点了看画面后 Safari 跑到前台、之后抢键盘)。
        已经在看画面了就让点(好切回文字卡)。"""
        if not in_browser() or not is_card():
            return True
        b = st["browser"]
        return bool(b.get("wid")) and not b.get("hidden")

    def tw(s, size=TB_FONT):
        return NSAttributedString.alloc().initWithString_attributes_(
            s, {NSFontAttributeName: NSFont.systemFontOfSize_(size)}).size().width

    def buttons(w):
        """按钮区域(翻转坐标,左上原点):[(名字, x0, x1)]。窄(< FULL_W)时 灯光 / I See 只画圆;I See 只在浏览器任务出现。"""
        full = w >= FULL_W
        out, x = [], 6
        # 10-24 用户定:灯光放第一位(位置固定),I See 排第二,而且只在浏览器任务里出现(I See 只管浏览器那条路,镜像下没作用)
        lw = 4 + 2 * ICON_R + ((4 + tw(tr("btn.light", "灯光")) + 6) if full else 6)
        out.append(("light", x, x + lw))
        x += lw + 4
        if in_browser():
            iw = 4 + 2 * ICON_R + ((4 + tw("I See") + 6) if full else 6)
            out.append(("isee", x, x + iw))
            x += iw + 4
        if why_task():          # 10-30:AI 任务才有「原因」按钮
            ww_ = 4 + 2 * ICON_R + ((4 + tw(tr("btn.why", "原因")) + 6) if full else 6)
            out.append(("why", x, x + ww_))
        out.append(("view", w - 58, w - 32))
        out.append(("collapse", w - 30, w - 4))
        return out

    def light_items(w):
        """灯光展开后的选项条:[(档, x0, x1)]。当前档原地不动(用户:固定顺序会把当前档挤走、看出"移位"),另两档从它右边伸出来。"""
        full = w >= FULL_W
        x = [b for b in buttons(w) if b[0] == "light"][0][1]
        cur = light_level()
        out = []
        for lvl in [cur] + [l for l in LIGHTS if l != cur]:
            iw = 4 + 2 * ICON_R + ((4 + tw(light_label(lvl)) + 8) if full else 6)
            out.append((lvl, x, x + iw))
            x += iw
        return out

    def light_k():
        """选项条伸展进度 0~1+(弹簧,同悬浮窗展开 0.5 秒/弹性 0.2;收回 0.2 秒)。"""
        L = st.get("light")
        if not L:
            return 0.0
        t = time.time() - L["t0"]
        if L["open"]:
            return 1.0 if t >= MORPH_T * 2.2 else _spring(t)
        return max(0.0, 1.0 - t / 0.2)

    # ---- 图标(SeeU C-0.3 用户 10-21 在样品里定「全部用点来重构」,样品 seeu/参考/Codex悬浮条/icon_sample.py)
    def _oval(cx, cy, r):
        return NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))

    def _arc(cx, cy, r, a0, a1, c, lw):
        c.set()
        p = NSBezierPath.bezierPath()
        p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(NSMakePoint(cx, cy), r, a0, a1, False)
        p.setLineWidth_(lw)
        p.setLineCapStyle_(1)
        p.stroke()

    def ring_at(cx, cy, c, lw=1.5, r=ICON_R):
        c.set()
        p = _oval(cx, cy, r)
        p.setLineWidth_(lw)
        p.stroke()

    def isee_icon(cx, cy, on, a=1.0):
        """I See = 圆里一个点(收起后悬浮标的呼吸点刚好在这个位置)。开 = 深色实心圆里一个白点。"""
        if on:
            col(txt_rgb, 0.95 * a).set()
            _oval(cx, cy, ICON_R).fill()
            col((1, 1, 1) if txt_rgb == DARK else (0.1, 0.1, 0.1), a).set()
            _oval(cx, cy, 2.4).fill()
        else:
            ring_at(cx, cy, col(txt_rgb, 0.9 * a))
            _oval(cx, cy, 2.4).fill()

    def why_icon(cx, cy, on, a=1.0):
        """原因 = 圆里再一个细圆,里面一大一小两个点斜排(大 = AI 在说,小 = 你在听;10-30 用户在小样「原因图标6」里定 G4。
        之前试过两行字太重、两点对称像脸、椭圆像猪鼻子、E6 气泡)。开 = 深色实心圆 + 白色图形(跟 I See 一个规矩)。"""
        if on:
            col(txt_rgb, 0.95 * a).set()
            _oval(cx, cy, ICON_R).fill()
            c = col((1, 1, 1) if txt_rgb == DARK else (0.1, 0.1, 0.1), a)
        else:
            ring_at(cx, cy, col(txt_rgb, 0.9 * a))
            c = col(txt_rgb, 0.9 * a)
        ring_at(cx, cy, c, 1.05, 3.4)
        c.set()
        _oval(cx - 0.8, cy - 0.7, 1.0).fill()     # 翻转坐标:左上大点
        _oval(cx + 1.2, cy + 1.2, 0.6).fill()     # 右下小点

    def light_icon(cx, cy, lvl, a=1.0):
        """灯光 = 圆里四个圆角(屏幕四角亮光圈;用户 10-21 在样品里定:去掉中间的点,真实大小下太挤看不清)。
        关 = 深色外圈 + 淡深色四角;开 = 圆里填满对应颜色(抢占橙 / 被控紫)、四角反成白色,外圈照样留深色边(跟其他按钮一个轮廓)。"""
        if lvl == "off":
            ring_at(cx, cy, col(txt_rgb, 0.88 * a))
            mark_c = col(txt_rgb, 0.55 * a)
        else:
            col(ORANGE if lvl == "real" else PURPLE, a).set()
            _oval(cx, cy, ICON_R + 0.75).fill()
            ring_at(cx, cy, col(txt_rgb, 0.88 * a))
            mark_c = col((1, 1, 1), a)
        mark_c.set()
        d, L = 2.8, 1.6        # 10-30 用户:四个角别贴着圆(原 3.3, 2.1),在「全部图标」小样里定
        for sx in (-1, 1):
            for sy in (-1, 1):
                p = NSBezierPath.bezierPath()
                p.moveToPoint_(NSMakePoint(cx + sx * d, cy + sy * (d - L)))
                p.appendBezierPathWithArcFromPoint_toPoint_radius_(NSMakePoint(cx + sx * d, cy + sy * d),
                                                                   NSMakePoint(cx + sx * (d - L), cy + sy * d), 1.1)
                p.lineToPoint_(NSMakePoint(cx + sx * (d - L), cy + sy * d))
                p.setLineWidth_(1.1)
                p.setLineCapStyle_(1)
                p.setLineJoinStyle_(1)
                p.stroke()

    def screen_icon(cx, cy, c):
        """看画面 = 镜头:圆里正中一个小圆环 + 中心点,右下一个小指示点。
        SeeU C-0.5(10-22 用户):原来镜头偏上 0.6 点,演示视频放大后看着没对齐参考圆,改成跟外圈同心。"""
        ring_at(cx, cy, c)
        ring_at(cx, cy, c, 1.1, 3.0)
        c.set()
        _oval(cx, cy, 1.1).fill()
        _oval(cx + 3.3, cy + 3.3, 0.8).fill()

    def steps_icon(cx, cy, c):
        """看操作 = 三个大小不一的点,排成鼠标指针的三角(尖朝左上)。"""
        ring_at(cx, cy, c)
        c.set()
        k = 0.85            # 10-30 用户:大点太贴圆圈,三个点位置和大小一起往中心收(小样「全部图标」里定)
        _oval(cx - 2.2 * k, cy - 2.4 * k, 1.9 * k).fill()
        _oval(cx + 2.6 * k, cy + 0.2 * k, 1.4 * k).fill()
        _oval(cx - 0.9 * k, cy + 2.9 * k, 1.0 * k).fill()

    def collapse_icon(cx, cy, c, k=0.0):
        """收起 = 圆里左右两道弧 ( );k = 0~1 两边往中间合拢(收起来时从两边收)。"""
        ring_at(cx, cy, c)
        # 10-30 用户:两道弧别贴着圆(原离中心 2、半径 3 → 1.2、2.6,用户在小样里拖定),合拢终点不变
        off = 2.2 * (1 - k) + 0.6 * k
        _arc(cx - off + 1.0, cy, 2.6, 120, 240, c, 1.3)
        _arc(cx + off - 1.0, cy, 2.6, -60, 60, c, 1.3)

    def edge_of(view, p):
        """鼠标在悬浮窗哪条边/哪个角上(翻转坐标):返回 NSCursorFrameResizePosition 或 None。"""
        b = view.bounds()
        w, h = b.size.width, b.size.height
        top, bot, left, right = p.y <= EDGE, p.y >= h - EDGE, p.x <= EDGE, p.x >= w - EDGE
        import AppKit as A
        table = {(1, 0, 1, 0): "TopLeft", (1, 0, 0, 1): "TopRight", (0, 1, 1, 0): "BottomLeft",
                 (0, 1, 0, 1): "BottomRight", (1, 0, 0, 0): "Top", (0, 1, 0, 0): "Bottom",
                 (0, 0, 1, 0): "Left", (0, 0, 0, 1): "Right"}
        k = table.get((int(top), int(bot), int(left), int(right)))
        return getattr(A, "NSCursorFrameResizePosition" + k, None) if k else None

    def set_cursor(pos):
        """边缘换成"调整大小"箭头(10-15 用户:移到边角不变样式)。悬浮窗不当键盘窗口,系统不会自动换,自己换。"""
        try:
            import AppKit as A
            if pos is None:
                A.NSCursor.arrowCursor().set()
            elif hasattr(A.NSCursor, "frameResizeCursorFromPosition_inDirections_"):
                A.NSCursor.frameResizeCursorFromPosition_inDirections_(pos, A.NSCursorFrameResizeDirectionsAll).set()
            else:
                A.NSCursor.resizeLeftRightCursor().set()
        except Exception as e:
            _log(f"换鼠标样式出错:{e!r}")

    def draw_eye(cx, cy, r, color, filled=True):
        """眼睛图标(I See):杏仁形眼眶 + 瞳孔。翻转/不翻转坐标都对称,两处共用。"""
        color.set()
        eye = NSBezierPath.bezierPath()
        eye.moveToPoint_(NSMakePoint(cx - r * 1.25, cy))
        eye.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(cx + r * 1.25, cy), NSMakePoint(cx - r * 0.5, cy - r * 1.1),
                                                     NSMakePoint(cx + r * 0.5, cy - r * 1.1))
        eye.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(cx - r * 1.25, cy), NSMakePoint(cx + r * 0.5, cy + r * 1.1),
                                                     NSMakePoint(cx - r * 0.5, cy + r * 1.1))
        eye.closePath()
        eye.setLineWidth_(1.5 if r > 4.5 else 1.1)
        eye.setLineJoinStyle_(1)
        eye.stroke()
        pr = r * 0.42
        pupil = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - pr, cy - pr, 2 * pr, 2 * pr))
        if filled:
            pupil.fill()
        else:
            pupil.setLineWidth_(1.2)
            pupil.stroke()

    class WatchView(NSView):
        def isFlipped(self):
            return True

        def acceptsFirstMouse_(self, ev):
            return True

        def updateTrackingAreas(self):
            for t in list(self.trackingAreas()):
                self.removeTrackingArea_(t)
            # 0x01 进出 | 0x02 移动 | 0x80 不管是不是键盘窗口都跟踪 | 0x200 跟着可见区变
            self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None))
            objc.super(WatchView, self).updateTrackingAreas()

        def mouseEntered_(self, ev):
            st["hover"] = True
            touch()
            self.setNeedsDisplay_(True)

        def mouseMoved_(self, ev):
            touch()
            p = self.convertPoint_fromView_(ev.locationInWindow(), None)
            pos = edge_of(self, p)
            if pos != st.get("cursor_pos"):
                st["cursor_pos"] = pos
                set_cursor(pos)
            old = st.get("mouse")
            st["mouse"] = (p.x, p.y)
            if p.y <= TB_H or (old and old[1] <= TB_H):
                self.setNeedsDisplay_(True)      # 图标名字跟着鼠标出现/消失

        def mouseExited_(self, ev):
            st["hover"] = False
            st["mouse"] = None
            if (st.get("light") or {}).get("open"):
                st["light"] = dict(open=False, t0=time.time())     # 移出去 = 不选,收回
            touch()
            if st.get("cursor_pos") is not None:
                st["cursor_pos"] = None
                set_cursor(None)
            self.setNeedsDisplay_(True)

        def mouseDown_(self, ev):
            touch()
            p = self.convertPoint_fromView_(ev.locationInWindow(), None)
            if p.y <= TB_H and edge_of(self, p) is None:
                w = self.bounds().size.width
                if (st.get("light") or {}).get("open"):
                    for lvl, x0, x1 in light_items(w):
                        if x0 <= p.x <= x1:
                            on_button("light_" + lvl)
                            return
                    st["light"] = dict(open=False, t0=time.time())     # 点别处 = 不选,收回
                    self.setNeedsDisplay_(True)
                    return
                for name, x0, x1 in buttons(w):
                    if x0 <= p.x <= x1:
                        if name == "collapse":
                            if not st.get("close_anim"):
                                st["close_anim"] = time.time()     # 先播图标合拢,tick 里到点再真收起
                                self.setNeedsDisplay_(True)
                            return
                        on_button(name)
                        return
            self.window().performWindowDragWithEvent_(ev)   # 其余地方按住拖动

        def drawRect_(self, rect):
            b = self.bounds()
            w, h = b.size.width, b.size.height
            now = time.time()
            # 点击位置换算到画面区:SeeU C-0.3 画面四周加了玻璃边,上面是按钮栏(翻转坐标,左上原点)
            px0, py0, pw, ph = pic_rect(w, h)

            def P(fx, fy):
                return px0 + fx * pw, py0 + fy * ph
            if not is_card():
                for kind, fx, fy, t0 in st["marks"]:
                    k = (now - t0) / RING_S
                    if 0 <= k <= 1:
                        r = 6 + 16 * k
                        col(mode_color(), 0.9 * (1 - k)).set()
                        mx, my = P(fx, fy)
                        pth = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(mx - r, my - r, 2 * r, 2 * r))
                        pth.setLineWidth_(2.5)
                        pth.stroke()
                if st["dot"] and now - st["dot"][2] < DOT_S:
                    fx, fy, t0 = st["dot"]
                    a = 1.0 if now - t0 < DOT_S - 0.5 else (DOT_S - (now - t0)) / 0.5
                    mx, my = P(fx, fy)
                    col(mode_color(), 0.95 * a).set()
                    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(mx - 4, my - 4, 8, 8)).fill()
                    NSColor.colorWithCalibratedWhite_alpha_(1, 0.9 * a).set()
                    ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(mx - 4, my - 4, 8, 8))
                    ring.setLineWidth_(1.2)
                    ring.stroke()
            stuck_ = False
            if is_card():      # 文字卡:没有画面,写正在做哪一步
                # 10-20 用户说排版怪:顶部一行平时写名字(移上来换按钮栏),下面步骤,I See 开着再加一行,高度跟着内容
                info = card_info()
                grey = col(txt_rgb, SUB_A)
                white95 = col(txt_rgb, 0.95)
                sk = info.get("stuck")
                stuck_ = bool(sk)
                if sk:      # 卡住了(10-20 用户定:自动展开,说清卡在哪 / 为什么 / 怎么办)
                    # 10-27 改成大字「卡住了: 原因」+ 小字「怎么办: …」(不靠红色)
                    big = tr("card.stuck_why", "卡住了: {why}", why=sk["why"])
                    todo = tr("card.todo", "怎么办: {todo}", todo=sk["todo"])
                    h1 = text_h(big, 15, w - 28, 3)     # 原因几行就占几行,下面紧跟
                    text_box(big, 15, white95, 14, TB_H + 4, w - 28, h1 + 4, bold=True)
                    text_box(todo, 11.5, grey, 14, TB_H + 10 + h1, w - 28,
                             text_h(todo, 11.5, w - 28, 3) + 4)   # 多给一点,最后一行别被裁
                else:
                    # 名字、正在做的步骤是图层(panel_build:呼吸圆点 + 文字微光);下面的小字说明一行一条
                    wt = card_why()          # 10-30:AI 这一步的原因,「正在…」下面一行灰字(最多 2 行)
                    wh = 0.0
                    if wt:
                        wh = text_h(wt, WHY_SIZE, w - 28, 2) + 2
                        text_box(wt, WHY_SIZE, grey, 14, TB_H + 27, w - 28, wh + 2)
                    for i, note in enumerate(card_notes()):
                        text(note, 11, grey, 14, TB_H + 30 + wh + 20 * i)
            k = light_k()
            if not st["hover"] and k <= 0.001:
                return
            # 顶部按钮栏(鼠标移上来才画;10-27 用户选:卡住时也平时写「项目 · App」,不再一直摆按钮)。画在玻璃上,字和图标用深色
            full = w >= FULL_W
            white = col(txt_rgb, 0.92)
            ty = (TB_H - TB_FONT * 1.25) / 2          # 文字竖直居中
            cy = TB_H / 2
            m = st.get("mouse")
            for name, x0, x1 in buttons(w):
                if name == "isee":
                    on = st["isee"]
                    # 10-20 用户:眼睛原来比圆点大一圈不协调 → 宽度跟圆点一样(2.5r = 2*ICON_R)
                    a_ = 1.0
                    sk = (st.get("browser") or {}).get("stuck")
                    if sk and sk.get("helps") and not on and now - sk["t"] < PULSE_S:
                        import math
                        a_ = 0.35 + 0.65 * (0.5 + 0.5 * math.cos(2 * math.pi * (now - sk["t"]) / 1.2))
                    isee_icon(x0 + 4 + ICON_R, cy, on, a_)
                    if full:
                        text("I See", TB_FONT, white if on else col(txt_rgb, SUB_A), x0 + 8 + 2 * ICON_R, ty)
                elif name == "why":
                    on = why_shown()
                    why_icon(x0 + 4 + ICON_R, cy, on)
                    if full:
                        text(tr("btn.why", "原因"), TB_FONT, white if on else col(txt_rgb, SUB_A), x0 + 8 + 2 * ICON_R, ty)
                elif name == "light":
                    if k > 0.001:
                        continue                         # 展开的选项条盖住原按钮(下面画)
                    light_icon(x0 + 4 + ICON_R, cy, light_level())
                    if full:
                        text(tr("btn.light", "灯光"), TB_FONT, white, x0 + 8 + 2 * ICON_R, ty)
                else:
                    fa = 1.0 - min(1.0, k)               # 灯光展开时,看画面、收起淡出让位
                    if fa <= 0.01:
                        continue
                    cx = (x0 + x1) / 2.0
                    if name == "view":
                        ok = screen_ok()
                        c = col(txt_rgb, fa * (0.9 if ok else 0.28))
                        (screen_icon if is_card() else steps_icon)(cx, cy, c)   # 文字卡上 = 看画面;画面上 = 回去看操作
                        label = (tr("btn.view_screen", "看画面") if is_card() else tr("btn.view_steps", "看操作"))
                        if not ok:
                            label = (tr("card.screen_hidden", "隐身中,看不了画面") if (st.get("browser") or {}).get("hidden")
                                     else tr("card.screen_off", "网页模块操作的可能是后台标签页,不放画面"))
                    else:
                        ca = st.get("close_anim")
                        kc = 0.0 if not ca else min(1.0, (now - ca) / CLOSE_ANIM_S)
                        collapse_icon(cx, cy, col(txt_rgb, 0.92 * fa), 1 - (1 - kc) ** 2)   # 先快后慢合拢
                        label = tr("btn.collapse", "收起")
                    if full and m and m[1] <= TB_H and x0 <= m[0] <= x1:
                        # 名字只在鼠标移上去时显示(用户定);窄窗口不弹(SeeU C-0.4 用户报:标签往左伸、盖住 I See / 灯光)
                        lw_ = tw(label, 12)
                        lx = max(4.0, w - 62 - lw_)
                        bg_ = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                            NSMakeRect(lx - 6, cy - 10, min(lw_, w - 70) + 12, 20), 10, 10)
                        (col((1, 1, 1), 0.85 * fa) if txt_rgb == DARK else col((0.16, 0.16, 0.18), 0.9 * fa)).set()
                        bg_.fill()
                        text_box(label, 12, col(txt_rgb, 0.9 * fa), lx, cy - 8, min(lw_ + 2, w - 68), 17)
            if k > 0.001:      # 灯光选项条:原地往右伸展(弹簧),当前档在最左 = 原按钮位置
                items = light_items(w)
                sx0, sx1 = items[0][1], items[-1][2]
                pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(sx0, cy - LIGHT_H / 2, max(LIGHT_H, (sx1 - sx0) * k), LIGHT_H), LIGHT_H / 2, LIGHT_H / 2)
                (col((1, 1, 1), 0.55) if txt_rgb == DARK else col((0, 0, 0), 0.3)).set()
                pill.fill()
                col(txt_rgb, 0.14).set()
                pill.setLineWidth_(1)
                pill.stroke()
                NSGraphicsContext.saveGraphicsState()
                pill.addClip()
                cur = light_level()
                for lvl, x0, x1 in items:
                    if lvl == cur:
                        col(txt_rgb, 0.08).set()
                        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                            NSMakeRect(x0 + 1.5, cy - LIGHT_H / 2 + 1.5, x1 - x0 - 3, LIGHT_H - 3),
                            LIGHT_H / 2 - 1.5, LIGHT_H / 2 - 1.5).fill()
                    light_icon(x0 + 4 + ICON_R, cy, lvl)
                    if full:
                        text(light_label(lvl), TB_FONT, white if lvl == cur else col(txt_rgb, SUB_A + 0.1),
                             x0 + 8 + 2 * ICON_R, ty)
                NSGraphicsContext.restoreGraphicsState()

    def clip_glass(g, r):
        """玻璃图层自己裁圆角(SeeU C-0.4:开了激活样子后,圆角外会多出一块方形底,裁掉;光晕不受影响,实测)。"""
        g.setWantsLayer_(True)
        g.layer().setCornerRadius_(r)
        g.layer().setMasksToBounds_(True)

    class NoKeyPanel(NSPanel):
        # 🔴 10-15 用户报「几乎控制不了输入框 / 输入框无限回车」:可缩放的窗口点一下会成为键盘窗口抢走输入框。永远不要键盘。
        def canBecomeKeyWindow(self):
            return False

        def canBecomeMainWindow(self):
            return False

        def _hasActiveAppearance(self):
            # SeeU C-0.4:液态玻璃只在窗口"激活"时画边框光晕 + 提亮(Codex 那样),不抢焦点的面板默认是暗淡版。
            # 私有方法(只改外观,不改焦点);系统不认就退回暗淡版。实测见 seeu/SeeU-相关要点.md 10-21 液态玻璃节。
            return True

    def make_panel(w, h, resizable):
        mask = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        if resizable:
            mask |= NSWindowStyleMaskResizable
        p = NoKeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, w, h), mask, NSBackingStoreBuffered, False)
        p.setLevel_(NSFloatingWindowLevel)
        p.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
                                 | NSWindowCollectionBehaviorFullScreenAuxiliary)
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)
        p.setHidesOnDeactivate_(False)
        p.setAlphaValue_(0.0)
        return p

    panel = make_panel(DEFAULT_W, DEFAULT_W * 2, True)
    # 10-31 用户报斜拉不好点到角:圆角外那一小块全透明,系统让点击穿透到后面窗口 → 底色铺 1%(看不出来),角上也能抓住拉
    panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.01))
    panel.setMinSize_(NSMakeSize(MIN_W, MIN_W))
    panel.setMaxSize_(NSMakeSize(MAX_W, MAX_W * 3))
    root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, DEFAULT_W, DEFAULT_W * 2))
    root.setWantsLayer_(True)
    root.setAutoresizingMask_(18)
    rl = root.layer()
    # SeeU C-0.3 用户定:悬浮窗/卡片也用悬浮标那套液态玻璃(画面四周一圈玻璃边、上面按钮栏也是玻璃),画面本身不蒙玻璃。
    pglass = None
    try:
        import AppKit as _A
        if hasattr(_A, "NSGlassEffectView"):
            pglass = _A.NSGlassEffectView.alloc().initWithFrame_(root.bounds())
            pglass.setCornerRadius_(PANEL_R)
            clip_glass(pglass, PANEL_R)
            pglass.setContentView_(root)
            panel.setContentView_(pglass)
            panel.setHasShadow_(False)          # 同悬浮标:窗口阴影会在玻璃外多一圈深色细边
    except Exception as e:
        _log(f"悬浮窗液态玻璃不可用,用深色底:{e!r}")
        pglass = None
    if pglass is None:
        rl.setCornerRadius_(12)
        rl.setMasksToBounds_(True)
        rl.setBorderWidth_(1)
        rl.setBorderColor_(Quartz.CGColorCreateGenericRGB(1, 1, 1, 0.18))
        rl.setBackgroundColor_(Quartz.CGColorCreateGenericRGB(0.08, 0.08, 0.08, 1))
        panel.setContentView_(root)
    img_layer = Quartz.CALayer.layer()
    _b0 = root.bounds()
    img_layer.setFrame_(Quartz.CGRectMake(BORDER, BORDER, _b0.size.width - 2 * BORDER, _b0.size.height - TB_H - BORDER))
    img_layer.setContentsGravity_(Quartz.kCAGravityResize)
    img_layer.setCornerRadius_(PIC_R)
    img_layer.setMasksToBounds_(True)
    img_layer.setAutoresizingMask_(Quartz.kCALayerWidthSizable | Quartz.kCALayerHeightSizable)   # 边距不变,跟着窗口伸缩
    rl.addSublayer_(img_layer)
    ttl_layer = Quartz.CALayer.layer()          # 标题行/步骤文字图层的容器(变形动画时跟画面一起淡入淡出)
    ttl_layer.setFrame_(root.bounds())
    ttl_layer.setAutoresizingMask_(Quartz.kCALayerWidthSizable | Quartz.kCALayerHeightSizable)
    rl.addSublayer_(ttl_layer)
    view = WatchView.alloc().initWithFrame_(root.bounds())
    view.setAutoresizingMask_(18)
    root.addSubview_(view)

    def set_panel_radius(r):
        if pglass is not None:
            pglass.setCornerRadius_(r)
            clip_glass(pglass, r)
        else:
            rl.setCornerRadius_(r)
    _saved = _read_state().get("frame")
    if _saved:
        panel.setFrame_display_(NSMakeRect(*_saved), False)   # 先摆到记住的位置(比例等开画面流时再校正)
        st["placed"] = True

    # ---- 悬浮标
    class CapView(NSView):
        def acceptsFirstMouse_(self, ev):
            return True

        def updateTrackingAreas(self):
            for t in list(self.trackingAreas()):
                self.removeTrackingArea_(t)
            self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None))   # 进出 | 移动 | 一直跟踪 | 跟可见区
            objc.super(CapView, self).updateTrackingAreas()

        def mouseEntered_(self, ev):
            touch()

        def mouseMoved_(self, ev):
            touch()

        def mouseDown_(self, ev):
            touch()
            self._start = NSEvent.mouseLocation()
            self._orig = self.window().frame().origin
            self._moved = False

        def mouseDragged_(self, ev):
            touch()
            m = NSEvent.mouseLocation()
            dx, dy = m.x - self._start.x, m.y - self._start.y
            if abs(dx) + abs(dy) > 3:
                self._moved = True
            self.window().setFrameOrigin_(NSMakePoint(self._orig.x + dx, self._orig.y + dy))

        def mouseUp_(self, ev):
            if self._moved:
                cap_moved()
            else:
                on_button("expand")

        def drawRect_(self, rect):
            b = self.bounds()
            if st.get("glass") is None:          # 系统没有液态玻璃(macOS 26 以前)才自己画深色胶囊
                pth = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(0.5, 0.5, b.size.width - 1, b.size.height - 1), b.size.height / 2, b.size.height / 2)
                NSColor.colorWithCalibratedWhite_alpha_(0.1, 0.86).set()
                pth.fill()
                col(mode_color(), 0.55).set()
                pth.setLineWidth_(1)
                pth.stroke()
            if st["isee"]:          # I See 开着:字换成 I See;呼吸点外面加一个圈(SeeU C-0.3 图标改成"圆里一个点",跟按钮栏一套)
                c_ = col(mode_color(), 0.9)
                c_.set()
                rg = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(17 - 9, b.size.height / 2 - 9, 18, 18))
                rg.setLineWidth_(1.5)
                rg.stroke()
            # 圆点、文字、微光都是图层(见下面 cap_build),交给系统动画,不占 Python

    cap = make_panel(CAP_W, CAP_H, False)
    cap_view = CapView.alloc().initWithFrame_(NSMakeRect(0, 0, CAP_W, CAP_H))
    # C-1.3 用户:悬浮标参考 Codex 浮标用系统**液态玻璃**(NSGlassEffectView,macOS 26 起的公开接口),按模式染色(紫/橙);
    # 去掉窗口阴影(否则玻璃外面多一圈深色细边)。系统没有就退回原来的深色胶囊。
    # SeeU C-0.3 用户在样品里定:玻璃「常规」+ 染色很淡 + 深色字;运行中 = 圆点呼吸 + 文字微光(不要原来沿边滚动的流光)。
    st["glass"] = None
    try:
        import AppKit as _A
        if hasattr(_A, "NSGlassEffectView"):
            gl = _A.NSGlassEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, CAP_W, CAP_H))
            gl.setCornerRadius_(CAP_H / 2.0)
            clip_glass(gl, CAP_H / 2.0)
            gl.setContentView_(cap_view)
            cap.setContentView_(gl)
            cap.setHasShadow_(False)
            st["glass"] = gl
    except Exception as e:
        _log(f"液态玻璃不可用,用深色胶囊:{e!r}")
        st["glass"] = None
    if st["glass"] is None:
        cap.setContentView_(cap_view)
    def sys_dark():
        try:
            ap = NSApplication.sharedApplication().effectiveAppearance().bestMatchFromAppearancesWithNames_(["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"])
            return ap == "NSAppearanceNameDarkAqua"
        except Exception:
            return False

    def look_txt():
        """字/图标颜色:没玻璃(深色胶囊)一直白字;有玻璃跟系统外观(玻璃自己会随外观变深浅)。"""
        if st["glass"] is None:
            return (1.0, 1.0, 1.0)
        return LIGHT_TXT if sys_dark() else DARK
    txt_rgb = look_txt()
    _scale = (NSScreen.mainScreen().backingScaleFactor() if NSScreen.mainScreen() else 2.0)

    def cgc(rgb, a=1.0):
        return Quartz.CGColorCreateGenericRGB(rgb[0], rgb[1], rgb[2], a)

    def ui_font(size, bold):
        return NSFont.systemFontOfSize_weight_(size, 0.4 if bold else 0.0)

    def text_layer(s, size, bold, rgb, a=1.0):
        t = Quartz.CATextLayer.layer()
        t.setString_(s)
        t.setFont_(ui_font(size, bold))
        t.setFontSize_(size)
        t.setForegroundColor_(cgc(rgb, a))
        t.setContentsScale_(_scale)
        t.setAlignmentMode_("left")
        return t

    def place_text(t, size, bold, x, mid, w):
        """按字的实际高度摆(SeeU C-0.3 用户报圆点和字没对齐、字偏上):大写字母/汉字的竖直中心落在 mid。
        图层坐标 y 朝上;CATextLayer 从框的顶边往下排字。"""
        f = ui_font(size, bold)
        base = mid - f.capHeight() / 2.0 - 0.5          # 汉字比大写字母略高,往下压半点视觉更正
        hh = f.ascender() - f.descender() + 2
        t.setFrame_(Quartz.CGRectMake(x, base + f.ascender() - hh, w, hh))

    def text_w(s, size, bold):
        return NSAttributedString.alloc().initWithString_attributes_(s, {NSFontAttributeName: ui_font(size, bold)}).size().width

    def shimmer_layer(s, size, bold, fr):
        """运行中的文字微光(学 Codex,实测见 seeu/SeeU-相关要点.md 10-21):同样的字叠一层白,用一条渐变带当遮罩从左扫到右。
        返回这层(调用方用 opacity 开关)。"""
        hi = text_layer(s, size, bold, (1.0, 1.0, 1.0) if txt_rgb == DARK else DARK, 0.85 if txt_rgb == DARK else 0.5)
        hi.setFrame_(fr)
        band = Quartz.CAGradientLayer.layer()
        band.setFrame_(Quartz.CGRectMake(-SHIMMER_W, 0, SHIMMER_W, fr.size.height))
        band.setStartPoint_((0, 0.5))
        band.setEndPoint_((1, 0.5))
        band.setColors_([cgc((0, 0, 0), 0), cgc((0, 0, 0), 1), cgc((0, 0, 0), 0)])
        hi.setMask_(band)
        tw = min(fr.size.width, text_w(s, size, bold) + 4)
        sweep = (tw + SHIMMER_W) / SHIMMER_SPEED
        a = Quartz.CABasicAnimation.animationWithKeyPath_("position.x")
        a.setFromValue_(-SHIMMER_W / 2)
        a.setToValue_(tw + SHIMMER_W / 2)
        a.setDuration_(sweep)
        g = Quartz.CAAnimationGroup.animation()
        g.setAnimations_([a])
        g.setDuration_(max(SHIMMER_PERIOD, sweep + 1))
        g.setRepeatCount_(1e9)
        g.setRemovedOnCompletion_(False)
        band.addAnimation_forKey_(g, "shimmer")
        hi.setOpacity_(0.0)
        return hi

    def breathe(layer):
        a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
        a.setFromValue_(1.0)
        a.setToValue_(0.3)
        a.setDuration_(BREATH_S)
        a.setAutoreverses_(True)
        a.setRepeatCount_(1e9)
        a.setRemovedOnCompletion_(False)
        a.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionEaseInEaseOut))
        layer.addAnimation_forKey_(a, "breathe")

    cap_view.setWantsLayer_(True)
    cap_root = Quartz.CALayer.layer()
    cap_root.setFrame_(cap_view.bounds())
    cap_view.layer().addSublayer_(cap_root)
    capL = dict(dot=None, txt=None, shim=None, key=None)

    def cap_label():
        """悬浮标上的字:「SeeU」;浏览器操作时带进度「SeeU · 录入第 5 行」(SeeU C-0.5 用户定,最多 CAP_STEP_MAX 个字)。"""
        base = "I See" if st["isee"] else "SeeU"
        return base            # 10-27 用户定:悬浮标任何时候只写 SeeU(不写进度/动作/个数),细节点开看;下面老逻辑留着不走
        stp = ((st.get("browser") or {}).get("step") or "").strip() if in_browser() else ""
        if stp.startswith("正在"):
            stp = stp[2:]
        stp = tr_step(stp) if stp else ""
        if not stp or (st.get("browser") or {}).get("stuck"):
            return base
        if len(stp) > CAP_STEP_MAX:
            stp = stp[:CAP_STEP_MAX - 1] + "…"
        return f"{base} · {stp}"

    def cap_w():
        return st.get("cap_w") or CAP_W

    def cap_build():
        """重建悬浮标的圆点 / 文字 / 微光图层(模式色、I See、进度字变了才调)。字变长了悬浮标往左加宽,右上角不动。"""
        label = cap_label()
        key = (st.get("mode"), st["isee"], txt_rgb, label)
        if key == capL["key"]:
            return
        capL["key"] = key
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        for l in list(cap_root.sublayers() or []):
            l.removeFromSuperlayer()
        r = 6.0
        mid = CAP_H / 2.0
        dot = Quartz.CALayer.layer()
        dot.setFrame_(Quartz.CGRectMake(17 - r, mid - r, 2 * r, 2 * r))
        dot.setCornerRadius_(r)
        dot.setBackgroundColor_(cgc(mode_color()))
        r_ = 4.5 if st["isee"] else r                # I See 开着:点小一圈,外面套个圈(drawRect 画)
        dot.setFrame_(Quartz.CGRectMake(17 - r_, mid - r_, 2 * r_, 2 * r_))
        dot.setCornerRadius_(r_)
        breathe(dot)
        cap_root.addSublayer_(dot)
        nw = max(CAP_W, int(31 + text_w(label, 15, True) + 14 + 0.5))
        if nw != cap_w():
            f = cap.frame()
            right = f.origin.x + f.size.width
            st["cap_w"] = nw
            cap.setFrame_display_(NSMakeRect(right - nw, f.origin.y, nw, CAP_H), False)
            cap_view.setFrame_(NSMakeRect(0, 0, nw, CAP_H))
            if st.get("glass") is not None:
                st["glass"].setFrame_(NSMakeRect(0, 0, nw, CAP_H))
            cap_root.setFrame_(Quartz.CGRectMake(0, 0, nw, CAP_H))
        t = text_layer(label, 15, True, txt_rgb, 0.95)
        place_text(t, 15, True, 31, mid, nw - 31 - 4)
        cap_root.addSublayer_(t)
        sh = shimmer_layer(label, 15, True, t.frame())
        sh.setOpacity_(1.0 if st.get("shim_on") else 0.0)
        cap_root.addSublayer_(sh)
        capL.update(dot=dot, txt=t, shim=sh)
        Quartz.CATransaction.commit()
        if st.get("glass") is not None:
            st["glass"].setTintColor_(col(mode_color(), GLASS_TINT_A))
        if pglass is not None:
            pglass.setTintColor_(col(mode_color(), GLASS_TINT_A))
        cap_view.setNeedsDisplay_(True)

    pnl = dict(key=None)

    def panel_build():
        """悬浮窗/卡片标题行的图层:呼吸圆点 + 名字;卡片再加一行"正在做哪步"(带微光)。鼠标移上来时标题行让给按钮栏。
        只在内容变了时重建(30 帧/秒的 tick 里调)。"""
        brw = is_card()                          # 文字卡(浏览器默认 / 镜像「看操作」)
        info = card_info() if brw else (st.get("browser") or {})
        stuck_ = brw and bool(info.get("stuck"))
        if brw:
            line, name = (info.get("line") or doing(info.get("step", ""))), info.get("app", "")
        else:
            line = doing(info.get("step", "")) if in_browser() else ""      # 浏览器画面:底下压一行步骤
            name = (info.get("app") if in_browser() else None) or st.get("title") or "SeeU"
        f = panel.frame()
        w, h = f.size.width, f.size.height
        why_t = ""          # 10-30:看画面时压在底边字幕带上的原因(AI 任务才有)
        if not brw:
            pw_, ph_ = w - 2 * BORDER, h - TB_H - BORDER
            why_n = 0 if ph_ < 160 else (1 if pw_ < 200 or pw_ > ph_ else 2)    # 画面太矮不写;窄或横屏 1 行;否则 2 行
            if not in_browser() and borrowing():      # 10-30:看画面时借鼠标也写清楚
                line = card_info().get("line") or tr("card.borrow", "正在用你的鼠标")
            elif not in_browser():
                # 镜像画面平时不压字;AI 任务有原因、正在动手时才压「正在…」+ 原因
                ci = card_info()
                w0 = why_now(ci.get("app")) if ci.get("step") and time.time() - st["last_act"] < ACTIVE_S else ""
                if w0:
                    line, why_t = doing(ci["step"]), w0
            elif line:
                why_t = why_now(name)
            why_t = fit_lines(why_t, WHY_SIZE, pw_ - 24, why_n) if why_t else ""
        lk = light_k() > 0.001
        key = (brw, name, line, why_t, stuck_, st["hover"] or lk, st.get("mode"), st["isee"], round(w), round(h), txt_rgb,
               st.get("who"))
        if st.get("morph"):
            # 10-31 用户截图:点开浮标时鼠标就在上面 → 按钮栏「灯光」跟没来得及藏的标题叠在一起,动画放完重画才消失。
            # 变形期间不重画(防闪,宽高每帧都在变),只按鼠标在不在上面直接藏/显标题行;别的变化等动画放完重画
            Quartz.CATransaction.begin()
            Quartz.CATransaction.setDisableActions_(True)    # 用户:标题是慢慢淡掉的,还能看到叠字 → 关掉图层自带的淡出
            for l in pnl.get("title_layers") or []:
                l.setHidden_(bool(key[5]))
            Quartz.CATransaction.commit()
            return
        if key == pnl["key"]:
            return
        pnl["key"] = key
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        for l in pnl.get("layers") or []:
            l.removeFromSuperlayer()
        layers, shims, title_ls = [], [], []
        top = h - TB_H / 2.0                      # 标题行竖直中线(图层坐标 y 朝上)
        if not st["hover"] and not lk:          # 10-27:卡住时顶上也写「项目 · App」(用户在小样里选的)
            r = 5.0
            dot = Quartz.CALayer.layer()
            dot.setFrame_(Quartz.CGRectMake(15 - r, top - r, 2 * r, 2 * r))
            dot.setCornerRadius_(r)
            dot.setBackgroundColor_(cgc(mode_color()))
            breathe(dot)
            layers.append(dot)
            size, bold, a = (12, False, SUB_A) if brw else (12.5, True, 0.95)
            who = st.get("who")
            if who:     # SeeU C-0.4:「项目名 · iPhone Mirroring」;写不下就只写项目名(项目名才是区分谁在跑的关键)
                full = f"{who} · {name}"
                name = full if text_w(full, size, bold) <= w - 27 - 10 else who
            t = text_layer(name, size, bold, txt_rgb, a)
            place_text(t, size, bold, 27, top, w - 27 - 10)
            layers.append(t)
            title_ls = [dot, t]
            if not brw:                           # 看画面时标题行就是状态,让它扫微光
                shims.append(shimmer_layer(name, size, bold, t.frame()))
                title_ls.append(shims[-1])
        if brw and not stuck_:
            mid = h - TB_H - 14
            t = text_layer(line, 16, True, txt_rgb, 0.95)
            place_text(t, 16, True, 14, mid, w - 28)
            layers.append(t)
            shims.append(shimmer_layer(line, 16, True, t.frame()))
        if line and not brw:           # 浏览器画面底下压一行步骤(用户 10-21 定):画面底边一条半透明深色带 + 白字
            band = Quartz.CALayer.layer()
            wl = text_h(why_t, WHY_SIZE, w - 2 * BORDER - 24, 3) if why_t else 0.0
            bh_ = 22 + (wl + 4 if why_t else 0)     # 有原因:动作一行 + 原因几行(10-30)
            band.setFrame_(Quartz.CGRectMake(BORDER, BORDER, w - 2 * BORDER, bh_))
            band.setBackgroundColor_(cgc((0, 0, 0), 0.5))
            band.setCornerRadius_(PIC_R)
            band.setMaskedCorners_(Quartz.kCALayerMinXMinYCorner | Quartz.kCALayerMaxXMinYCorner)
            band.setAutoresizingMask_(Quartz.kCALayerWidthSizable | Quartz.kCALayerMaxYMargin)
            ttl_layer.addSublayer_(band)
            px = BORDER + (12 if why_t else 8)      # 有原因时左右多留,第二行别碰到画面圆角(10-30 用户)
            t = text_layer(line, 12, True, (1, 1, 1), 0.95)
            place_text(t, 12, True, px, BORDER + bh_ - 11, w - 2 * BORDER - (24 if why_t else 16))
            t.setAutoresizingMask_(Quartz.kCALayerMaxYMargin)
            ttl_layer.addSublayer_(t)
            layers_bottom = [band, t]
            if why_t:
                wy = text_layer(why_t, WHY_SIZE, False, (1, 1, 1), 0.82)
                wy.setWrapped_(True)
                wy.setFrame_(Quartz.CGRectMake(px, BORDER + 6, w - 2 * BORDER - 24, wl + 2))
                wy.setAutoresizingMask_(Quartz.kCALayerMaxYMargin)
                ttl_layer.addSublayer_(wy)
                layers_bottom.append(wy)
        else:
            layers_bottom = []
        for l in layers + shims:
            l.setAutoresizingMask_(Quartz.kCALayerMinYMargin)    # 拉边缩放时贴着上边
            ttl_layer.addSublayer_(l)
        for l in shims:
            l.setOpacity_(1.0 if st.get("shim_on") else 0.0)
        pnl["layers"] = layers + shims + layers_bottom
        pnl["title_layers"] = title_ls
        st["panel_shims"] = shims
        Quartz.CATransaction.commit()

    def shim_update(now):
        """动手中 → 文字微光渐显;等下一步 → 0.4 秒淡出(圆点一直呼吸)。悬浮标和卡片/悬浮窗标题一起开关。"""
        on = now - st["last_act"] < ACTIVE_S and (st["cap_alpha"] > 0 or st["alpha"] > 0)
        cap_build()
        if on != st.get("shim_on"):
            st["shim_on"] = on
            Quartz.CATransaction.begin()
            Quartz.CATransaction.setAnimationDuration_(0.4)
            for l in [capL["shim"]] + list(st.get("panel_shims") or []):
                if l is not None:
                    l.setOpacity_(1.0 if on else 0.0)
            Quartz.CATransaction.commit()

    def big_frame():
        f = _read_state().get("frame")
        if f:
            return f
        fr = panel.frame()
        return [fr.origin.x, fr.origin.y, fr.size.width, fr.size.height]

    # ---- 展开方式 C(10-30 用户在预览里定):悬浮标在中间 → 像灵动岛从顶部正中往两边撑开;
    #      贴屏幕左边 / 右边(EXPAND_EDGE 点以内)→ 从贴边那一角往里长,悬浮标原地不动。窗口不出屏幕。
    #      位置以悬浮标为准:panel_from_cap 由悬浮标推窗口,cap_from_panel 反过来(窗口被拖过时用)。
    def _vf():
        return NSScreen.mainScreen().visibleFrame()

    def panel_from_cap(cx, ctop, w, h):
        """悬浮标左边 cx、顶边 ctop → 窗口 (x, y)。"""
        vf, cw = _vf(), cap_w()
        left, right = vf.origin.x, vf.origin.x + vf.size.width
        if cx - left < EXPAND_EDGE:
            x = cx
        elif right - (cx + cw) < EXPAND_EDGE:
            x = cx + cw - w
        else:
            x = cx + cw / 2.0 - w / 2.0
        x = max(left, min(x, right - w))
        return x, max(vf.origin.y, ctop - h)       # 10-30:底边也别出屏幕(换小屏幕后)

    def cap_from_panel(x, y, w, h):
        """窗口 → 悬浮标 (左边, 底边):贴边时收在那一角,其余收在顶部正中。"""
        vf, cw = _vf(), cap_w()
        left, right = vf.origin.x, vf.origin.x + vf.size.width
        if x - left < EXPAND_EDGE:
            cx = x
        elif right - (x + w) < EXPAND_EDGE:
            cx = x + w - cw
        else:
            cx = x + w / 2.0 - cw / 2.0
        return cx, y + h - CAP_H

    def get_cap():
        """悬浮标位置 (左边, 底边):单独记在状态文件 cap 里(窗口被屏幕边挤偏时反推会跳,10-30);没记过才从窗口反推。"""
        sv = _read_state()
        c = sv.get("cap")
        if c and len(c) == 2:
            # 10-30:屏幕从 2560×1440 换成 1920×1080 后,记住的 (841, 1311) 在屏幕顶上外面,悬浮窗看不见 → 拉回当前屏幕
            vf = _vf()
            cx = max(vf.origin.x, min(float(c[0]), vf.origin.x + vf.size.width - cap_w()))
            cy = max(vf.origin.y, min(float(c[1]), vf.origin.y + vf.size.height - CAP_H))
            return cx, cy
        x, y, w, h = big_frame()
        if sv.get("frame"):         # 老版本只记了窗口(悬浮标在它右上角):悬浮标留在用户熟悉的老地方
            cx, cy = x + w - cap_w(), y + h - CAP_H
            set_cap(cx, cy)
            return cx, cy
        return cap_from_panel(x, y, w, h)

    def set_cap(cx, cy):
        _write_state(cap=[round(cx, 1), round(cy, 1)])

    def refit(w, h):
        """换了窗口大小(画面比例 / 文字卡):按悬浮标位置重新摆。"""
        cx, cy = get_cap()
        return panel_from_cap(cx, cy + CAP_H, w, h)

    def place_cap():
        cap.setFrameOrigin_(NSMakePoint(*get_cap()))

    def cap_moved():
        """拖了悬浮标:悬浮窗跟着挪(按展开方式 C 摆),展开时就从悬浮标那里长出来。"""
        c = cap.frame()
        x, y, w, h = big_frame()
        set_cap(c.origin.x, c.origin.y)
        nx, ny = panel_from_cap(c.origin.x, c.origin.y + CAP_H, w, h)
        _write_state(frame=[nx, ny, w, h])
        panel.setFrame_display_(NSMakeRect(nx, ny, w, h), False)
        st["placed"] = True
        save_frame()

    def share_pos(to_island):
        """10-27 用户报:悬浮标拖到左边,第二个任务上岛时岛跳回右上角默认位置,掉回一个又瞬间飘回左边。
        两边都按右上角定位 → 切换时把位置交给对方:岛从悬浮标那里长出来;岛被拖过,悬浮标/悬浮窗跟到岛那里。"""
        try:
            x, y, w, h = big_frame()
            cx, cy = get_cap()
            if to_island:
                fn = getattr(isl, "set_anchor", None)
                if fn:
                    fn((cx + cap_w(), cy + CAP_H))        # 10-30:交接按悬浮标右上角(窗口不再总是右上角对齐)
                return
            fn = getattr(isl, "anchor", None)
            if not fn:
                return
            right, top = fn()
            if abs(right - (cx + cap_w())) < 1 and abs(top - (cy + CAP_H)) < 1:
                return
            set_cap(right - cap_w(), top - CAP_H)
            nx, ny = panel_from_cap(right - cap_w(), top, w, h)
            _write_state(frame=[nx, ny, w, h])
            panel.setFrame_display_(NSMakeRect(nx, ny, w, h), False)
            place_cap()
        except Exception as e:
            _log(f"共用位置出错:{e}")

    def save_frame():
        f = panel.frame()
        big = [f.origin.x, f.origin.y, f.size.width, f.size.height]
        # 🔴 10-31:变形动画中途的大小不是用户调的,别记(原来定时存位置把展开半路的 143 宽记成横屏宽,摆窗口读到它 → 卡在最小宽 150)
        morphing = bool(st.get("morph"))
        if not st.get("placed") or in_browser() or is_card() or morphing:
            # 🔴 悬浮窗还没摆过(一直收着)/ 现在是文字卡或浏览器画面:坐标不是镜像悬浮窗的,别覆盖用户拖好的位置
            big = _read_state().get("frame") or big
        c = cap.frame()
        brw = in_browser()
        capmode = ((not st["b_expanded"]) if brw else st["collapsed"]) or (st["alpha"] <= 0.05 and st["cap_alpha"] > 0.05)
        shown = ([c.origin.x, c.origin.y, c.size.width, c.size.height] if capmode else
                 ([f.origin.x, f.origin.y, f.size.width, f.size.height] if (brw or is_card()) else big))
        _write_state(frame=big, shown_frame=shown, updated=time.time(),
                     visible=(st["cap_alpha"] if capmode else st["alpha"]) > 0.05)
        if st.get("placed") and st.get("aspect") and not brw and not is_card() and not capmode and not morphing:
            remember_size(f.size.width, f.size.height, st["aspect"])

    class Delegate(NSObject):
        def windowDidMove_(self, n):
            if n.object() is panel and not st.get("morph"):
                # 用户拖了展开的窗口(不是程序按悬浮标摆的位置)→ 悬浮标跟着换到新位置(展开方式 C,10-30)
                f = panel.frame()
                if st.get("alpha", 0) > 0.05 and not st.get("placing_browser"):
                    cx, cy = get_cap()
                    px, py = panel_from_cap(cx, cy + CAP_H, f.size.width, f.size.height)
                    if abs(px - f.origin.x) > 1 or abs(py - f.origin.y) > 1:
                        set_cap(*cap_from_panel(f.origin.x, f.origin.y, f.size.width, f.size.height))
                save_frame()

        def windowDidResize_(self, n):
            if n.object() is panel and not st.get("morph"):
                save_frame()
                view.setNeedsDisplay_(True)

        def windowWillStartLiveResize_(self, n):
            st["rs_corner"] = False

        def windowDidEndLiveResize_(self, n):
            st["rs_corner"] = False

        @objc.signature(b"{CGSize=dd}@:@{CGSize=dd}")
        def windowWillResize_toSize_(self, win, size):
            """拉边缩放:按宽算高,画面保持比例(SeeU C-0.3 起整窗不是画面比例,不能用 setContentAspectRatio)。"""
            a = st.get("aspect")
            if win is panel and a and not st.get("morph") and not is_card():
                # 10-24:原来只看宽算高 → 拉上/下边(只有高在变)完全没反应,窄到最小宽附近也很难变形。
                # 现在看哪个方向变得多(相对当前大小),就以哪个为准;高变得多就由高反推宽。
                cur = win.frame().size
                dw = abs(size.width - cur.width) / max(cur.width, 1.0)
                dh = abs(size.height - cur.height) / max(cur.height, 1.0)
                w_by_h = (size.height - TB_H - BORDER) * a + 2 * BORDER
                if abs(size.width - cur.width) > 0.5 and abs(size.height - cur.height) > 0.5:
                    st["rs_corner"] = True
                if st.get("rs_corner"):
                    # 10-31 用户报斜拉画面抖:宽高变得差不多时上面这条每帧在两边来回跳 → 斜拉取两种算法里大的,跟着鼠标走。
                    # 一次拉动里出现过宽高同时变就一直按斜拉算(鼠标偶尔只横/竖挪 1 像素时不退回老算法,不然还是会跳)
                    w_in = max(size.width, w_by_h)
                else:
                    w_in = w_by_h if dh > dw else size.width
                w = fit_w(w_in, a)
                return NSMakeSize(w, win_h(w, a))
            return size
        def themeChanged_(self, n):
            # 系统切深浅色:等外观生效再换字色(玻璃自己会跟着变)
            self.performSelector_withObject_afterDelay_("lookRefresh:", None, 0.3)

        def lookRefresh_(self, _):
            apply_look()
    delegate = Delegate.alloc().init()
    panel.setDelegate_(delegate)
    NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        delegate, "themeChanged:", "AppleInterfaceThemeChangedNotification", None)

    def set_pass(until):
        """借用系统鼠标那几秒:悬浮窗、悬浮标不接鼠标(点击穿到下面的镜像);until=0 恢复。用户自己用电脑时不受影响(只跟着 real 走)。"""
        on = until > 0
        if on == bool(st.get("pass_until")) and (not on or until - (st.get("pass_until") or 0) < 1.0):
            return                              # 状态没变(real 连着来时 1 秒内不重复写文件)
        st["pass_until"] = until
        for w in (panel, cap):
            w.setIgnoresMouseEvents_(on)
        isl.set_ignore_mouse(on)
        if on:
            st["hover"] = False
            set_live(pass_until=until, pass_wids=[int(panel.windowNumber()), int(cap.windowNumber())]
                     + ([isl.window_number()] if isl.window_number() else []))
        else:
            set_live(pass_until=0, pass_wids=[])
        _log("借用系统鼠标:悬浮窗不接鼠标" if on else "恢复接鼠标")

    def apply_look():
        nonlocal txt_rgb
        t = look_txt()
        if t == txt_rgb:
            return
        txt_rgb = t
        _log("外观切到" + ("暗黑" if t == LIGHT_TXT else "浅色"))
        cap_build()                      # 缓存键带字色,会重建
        pnl["key"] = None
        cap_view.setNeedsDisplay_(True)
        view.setNeedsDisplay_(True)

    # ---- 悬浮窗大小(SeeU C-0.4 用户定):竖屏画面(iPhone 镜像)、横屏画面(BlueStacks、模拟器、电脑窗口)各记一份。
    # 竖屏记窗高、横屏记窗宽(= 长边),同一类 App 共用;没记过用默认宽 DEFAULT_W。老版本只有一份 frame,当竖屏那份接着用。
    def orient(aspect):
        return "port" if aspect < 0.95 else "land"          # 接近正方形归横屏

    def max_w(aspect):
        vf = NSScreen.mainScreen().visibleFrame()
        by_h = (FIT_SCREEN * vf.size.height - TB_H - BORDER) * aspect + 2 * BORDER   # 宽到这么多,高就顶到屏幕 90%
        return max(MIN_W, min(MAX_W, FIT_SCREEN * vf.size.width, by_h))

    def fit_w(w, aspect):
        return max(MIN_W, min(max_w(aspect), w))

    def remembered_w(aspect):
        s = _read_state()
        if orient(aspect) == "port":
            h = s.get("size_port_h") or ((s.get("frame") or [0, 0, 0, None])[3] if "size_port_h" not in s else None)
            w = (h - TB_H - BORDER) * aspect + 2 * BORDER if h else DEFAULT_W
        else:
            w = s.get("size_land_w") or DEFAULT_W
        return fit_w(w, aspect)

    def remember_size(w, h, aspect):
        if orient(aspect) == "port":
            _write_state(size_port_h=round(h, 1))
        else:
            _write_state(size_land_w=round(w, 1))

    def place(aspect):
        """按目标窗口比例放好悬浮窗:大小按横竖那份记录,位置沿用记过的右上角(跟悬浮标、文字卡对齐),没有就右上角默认。"""
        saved = _read_state().get("frame")
        w = remembered_w(aspect)
        nh = win_h(w, aspect)
        vf = NSScreen.mainScreen().visibleFrame()
        if saved:
            fx, fy = refit(w, nh)                             # 10-30:按悬浮标位置摆(展开方式 C)
            fx = max(vf.origin.x, min(fx, vf.origin.x + vf.size.width - w))       # 别出屏幕
            fy = max(vf.origin.y, min(fy, vf.origin.y + vf.size.height - nh))
            fr = (fx, fy, w, nh)
        else:
            fr = default_frame(aspect)
            fr = (fr[0] + fr[2] - w, fr[1] + fr[3] - nh, w, nh)
        # SeeU C-0.3:画面外多了按钮栏和玻璃边,整窗不再是画面比例 → 不用 setContentAspectRatio,改在 windowWillResize 里按宽算高
        panel.setContentResizeIncrements_(NSMakeSize(1, 1))
        # 🔴 只限最小宽不够:保持比例缩放时系统按高度算,宽会被压到最小宽以下(10-15 用户:按钮叠在一起)
        panel.setMinSize_(NSMakeSize(MIN_W, win_h(MIN_W, aspect)))
        panel.setMaxSize_(NSMakeSize(max_w(aspect), win_h(max_w(aspect), aspect)))
        if st.get("morph") and st["morph"]["opening"]:
            # 10-31:变形中途比例才定下来 → 从当前位置重新弹到新终点(不跳),内容淡入照旧
            f = panel.frame()
            st["morph"].update(to=list(fr), re_from=[f.origin.x, f.origin.y, f.size.width, f.size.height],
                               re_t0=time.time())
        else:
            panel.setFrame_display_(NSMakeRect(*fr), True)
        st["placed"] = True

    def place_card():
        """文字卡(浏览器卡片 / 镜像「看操作」):固定大小,右上角跟记住的悬浮窗对齐(不改记住的悬浮窗大小)。"""
        x, y, w, h = big_frame()
        sk = card_info().get("stuck")
        if sk:
            bh = TB_H + 10 + text_h(tr("card.stuck_why", "卡住了: {why}", why=sk["why"]), 15, BROWSER_W - 28, 3) + \
                text_h(tr("card.todo", "怎么办: {todo}", todo=sk["todo"]), 11.5, BROWSER_W - 28, 3) + 14
        else:
            bh = BROWSER_H + (BROWSER_H_ISEE - BROWSER_H) * len(card_notes())     # 小字说明(借鼠标 / I See / 隐身)每条多一行
            wt = card_why()
            if wt:                                  # 10-30:原因占几行就加几行高
                bh += text_h(wt, WHY_SIZE, BROWSER_W - 28, 2) + 2
            st["why_sig"] = (wt, borrowing())
        panel.setContentResizeIncrements_(NSMakeSize(1, 1))    # 去掉画面比例锁(place() 换回画面时会再设)
        panel.setMinSize_(NSMakeSize(BROWSER_W, bh))
        panel.setMaxSize_(NSMakeSize(BROWSER_W, bh))
        st["placing_browser"] = True
        panel.setFrame_display_(NSMakeRect(*refit(BROWSER_W, bh), BROWSER_W, bh), True)
        st["placing_browser"] = False
        img_layer.setContents_(None)
        pnl["key"] = None
        view.setNeedsDisplay_(True)
    place_browser = place_card

    def close_stream():
        if st["stream"] is not None:
            sck._close_stream(st["stream"])
        st.update(stream=None, out=None, n=-1, stream_wid=None)

    def set_title(wid):
        """标题行写被看的 App 名(SeeU C-0.3)。"""
        try:
            info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
            st["title"] = str(info[0].get("kCGWindowOwnerName") or "") if info else ""
        except Exception:
            st["title"] = ""

    def stream_target(wid):
        """画面流该取多宽(像素)= 悬浮窗画面区的实际像素宽(点 × 屏幕倍率),夹在 STREAM_MIN_W~STREAM_MAX_W。
        展开动画中按动画终点算;还没摆成这个比例时按记住的大小算。"""
        try:
            info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
            b = info[0]["kCGWindowBounds"]
            aspect = float(b["Width"]) / float(b["Height"])
        except Exception:
            return 600
        m = st.get("morph")
        if m and m.get("opening") and m.get("to"):
            w = m["to"][2]
        elif not st["collapsed"] and st["aspect"] is not None and abs(aspect - st["aspect"]) < 0.02:
            w = panel.frame().size.width
        else:
            w = remembered_w(aspect)
        scr = panel.screen() or NSScreen.mainScreen()
        scale = scr.backingScaleFactor() if scr else 2.0
        return int(max(STREAM_MIN_W, min(STREAM_MAX_W, (w - 2 * BORDER) * scale)))

    def stream_stale(wid):
        """窗口被拉大/缩小得够多 → 要按新大小重开流(拖动中不算,松手后下一次 show 再开)。"""
        req = st.get("stream_req")
        if not req or panel.inLiveResize() or st.get("morph"):
            return False
        t = stream_target(wid)
        return t > req * STREAM_REOPEN or t < req / 1.6

    def open_stream(wid):
        close_stream()
        req = stream_target(wid)
        r = sck._open_stream(wid, fps=FPS, max_w=req, background=False, out_cls=WatchOutput)
        if r is None:
            _log(f"开画面流失败 wid={wid}")
            return False
        stream, out, (pw, ph) = r
        st.update(px=sck._window_px(wid), stream=stream, out=out, n=-1, stream_wid=wid, stream_req=req)
        _log(f"开画面流 wid={wid} 取 {pw}×{ph}(要 {req} 宽)")
        set_title(wid)
        aspect = pw / float(ph) if ph else 0.5
        if st["aspect"] is None or abs(aspect - st["aspect"]) > 0.01:
            st["aspect"] = aspect
            place(aspect)
        return True

    def touch():
        """用户碰过悬浮窗/悬浮标(移上去、点、拖):从这一刻起再保留 HIDE_AFTER_S 秒。
        10-15 用户报"收起之后找不到了":一轮刚结束时收起,悬浮标出来不到 1 秒就到点消失。"""
        st["last_touch"] = time.time()

    def alive_t():
        return max(st["last_show"], st["last_touch"])

    # ---- 灵动岛式展开/收起(10-20 用户定):悬浮窗从悬浮标的位置弹簧变形长出来,内容后半段淡入;收起反过来缩回悬浮标
    def _spring(t):
        import math
        z, w = 1 - MORPH_BOUNCE, 2 * math.pi / MORPH_T
        if z >= 1:
            return 1 - (1 + w * t) * math.exp(-w * t)
        wd = w * math.sqrt(1 - z * z)
        return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + z * w / wd * math.sin(wd * t))

    def _cap_rect():
        c = cap.frame()
        return [c.origin.x, c.origin.y, c.size.width, c.size.height]

    def _morph_apply(k, kq=None, a=None):
        """k = 外框进度;kq = 内容淡入用的进度(默认同 k);a = 起点(默认悬浮标)。"""
        a, b = a or st["morph"]["from"], st["morph"]["to"]
        x, y, w, h = [a[i] + (b[i] - a[i]) * k for i in range(4)]
        w, h = max(24.0, w), max(20.0, h)
        # 10-30 展开方式 C:找悬浮标和窗口横向"对齐的那个点"(右上角 u=1、左上角 u=0、正中 u=0.5),
        # 让它跟着插值、两边按比例长 —— 一个公式管三种;窗口被屏幕边挤偏时 u 落在中间,照样顺。
        u = 0.5 if abs(b[2] - a[2]) < 1 else min(1.0, max(0.0, (a[0] - b[0]) / (b[2] - a[2])))
        px = a[0] + u * a[2] + ((b[0] + u * b[2]) - (a[0] + u * a[2])) * k
        top = a[1] + a[3] + (b[1] + b[3] - a[1] - a[3]) * k
        panel.setFrame_display_(NSMakeRect(px - u * w, top - h, w, h), True)     # 顶边跟着走,不抖
        kq = k if kq is None else kq
        q = 0.0 if st["morph"]["open"] is None else min(1.0, max(0.0, (kq - 0.35) / 0.45))
        # 10-31 用户报「点开浮标时左侧有字被挡住,后来自己消失」:只按时间淡入,窗口还窄时标题已显出来、被边切掉半截
        # → 再按大小卡一道:长到终点的 55% 才开始显,85% 显全(收起时反过来,一缩就先淡掉)
        frac = min(w / max(b[2], 1.0), h / max(b[3], 1.0))
        q = min(q, max(0.0, min(1.0, (frac - 0.55) / 0.3)))
        view.setAlphaValue_(q)
        img_layer.setOpacity_(q)
        ttl_layer.setOpacity_(q)
        set_panel_radius(min(h / 2.0, PANEL_R))

    class Morpher(NSObject):
        def step_(self, _t):
            m = st.get("morph")
            if not m:
                return
            t = time.time() - m["t0"]
            # 悬浮标(玻璃)和深色窗口交叉淡化,不出现"深色胶囊停半拍再换成玻璃"(10-20 连拍看到)
            if m["opening"]:
                done = t >= MORPH_T * 2.2
                xf = min(1.0, t / XFADE_S)
                cap.setAlphaValue_(1.0 - xf)
                panel.setAlphaValue_(xf)
            else:
                t_end = MORPH_T * 0.75 + XFADE_S          # 缩到悬浮标大小就收尾,不等弹簧尾巴
                done = t >= t_end
                xf = min(1.0, max(0.0, (t - MORPH_T * 0.75) / XFADE_S))
                if xf > 0 and not cap.isVisible():
                    place_cap()
                    cap.orderFrontRegardless()
                cap.setAlphaValue_(xf)
                panel.setAlphaValue_(1.0 - xf)
            if m["opening"] and m.get("re_t0"):
                t2 = time.time() - m["re_t0"]
                done = done and t2 >= MORPH_T * 2.2
            k = 1.0 if done else _spring(t)
            if not m["opening"]:
                k = 1.0 - k
            try:
                if m["opening"] and m.get("re_t0") and not done:
                    _morph_apply(_spring(t2), kq=k, a=m["re_from"])     # 换了终点:外框从换的那一刻重新弹
                else:
                    _morph_apply(k)
            except Exception as e:
                _log(f"变形出错:{e!r}")
                done = True
            if done:
                m["timer"].invalidate()
                st["morph"] = None
                view.setAlphaValue_(1.0)
                img_layer.setOpacity_(1.0)
                ttl_layer.setOpacity_(1.0)
                set_panel_radius(PANEL_R if pglass is not None else 12)
                if m["opening"]:
                    panel.setFrame_display_(NSMakeRect(*m["to"]), True)
                    panel.setAlphaValue_(1.0)
                    cap.setAlphaValue_(0.0)
                    cap.orderOut_(None)
                    save_frame()
                else:
                    st["alpha"] = 0.0
                    panel.setAlphaValue_(0.0)
                    panel.orderOut_(None)
                    # 放回记住的悬浮窗大小(不是动画开始时的大小:浏览器卡片 300 宽会漏进镜像悬浮窗,10-20 实测)
                    panel.setFrame_display_(NSMakeRect(*big_frame()), False)
                    st["cap_alpha"] = 1.0
                    place_cap()
                    cap.setAlphaValue_(1.0)
                    cap.orderFrontRegardless()
                    save_frame()
                if m.get("after"):
                    m["after"]()
    morpher = Morpher.alloc().init()

    def morph(opening, after=None):
        """opening=True:从悬浮标长成悬浮窗/卡片(panel 已摆到目标位置);False:缩回悬浮标。"""
        old = st.get("morph")
        if old:
            old["timer"].invalidate()
            st["morph"] = None
        if opening:
            # 10-31:点浮标展开时鼠标多半就在窗口要长到的范围里 → 一开始就按「鼠标在上面」画(按钮栏,不画标题),免得跟「灯光」叠字
            try:
                from AppKit import NSEvent
                mp, pf = NSEvent.mouseLocation(), panel.frame()
                if pf.origin.x <= mp.x <= pf.origin.x + pf.size.width and pf.origin.y <= mp.y <= pf.origin.y + pf.size.height:
                    st["hover"] = True
            except Exception:
                pass
            panel_build()                  # 10-31:变形期间不重建标题图层,先按目标大小建好,才能跟着淡入
        f = panel.frame()
        target = [f.origin.x, f.origin.y, f.size.width, f.size.height]
        capr = _cap_rect()
        m = dict(t0=time.time(), opening=opening, open=True, after=after, big=target,
                 **{"from": capr if opening else capr, "to": target})
        st["morph"] = m
        if opening:
            st["cap_alpha"] = 0.0          # 悬浮标在动画里淡出(交叉淡化),不在这里直接藏
        st["alpha"] = 1.0
        panel.setAlphaValue_(0.0 if opening else 1.0)
        _morph_apply(0.0 if opening else 1.0)
        panel.orderFrontRegardless()
        m["timer"] = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1.0 / MORPH_FPS, morpher, "step:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(m["timer"], NSRunLoopCommonModes)

    def on_button(name):
        touch()
        if name in ("halo_real", "halo_bg"):          # 老按钮名(命令行/测试还能用)
            lv = live()
            set_live(**{name: not bool(lv.get(name))})
            st["live"], st["live_t"] = live(), time.time()
            _log(f"按钮 {name} → {st['live'].get(name)}")
            view.setNeedsDisplay_(True)
        elif name == "light":                        # 灯光:原地往右弹出 关 / 抢占 / 被控
            st["light"] = dict(open=True, t0=time.time())
            view.setNeedsDisplay_(True)
        elif name.startswith("light_") and name[6:] in LIGHTS:
            lvl = name[6:]
            # 被控包含抢占(用户 10-21:被控 = 只要在操作就亮;抢占 = 只在借用真鼠标时亮)
            set_live(halo_real=lvl in ("real", "bg"), halo_bg=lvl == "bg")
            st["live"], st["live_t"] = live(), time.time()
            st["light"] = dict(open=False, t0=time.time())
            _log(f"按钮 灯光 → {lvl}")
            view.setNeedsDisplay_(True)
        elif name == "why":                          # 10-30:原因开关(只在 AI 任务出现)
            set_live(why_off=why_shown())
            st["live"], st["live_t"] = live(), time.time()
            _log(f"按钮 原因 → {why_shown()}")
            pnl["key"] = None
            view.setNeedsDisplay_(True)
        elif name == "view":                         # 看画面 ↔ 看操作
            if not screen_ok():
                return
            toggle_view()
        elif name == "isee":
            st["isee"] = not st["isee"]
            st["isee_click_t"] = time.time()         # 命令写设置文件要一小会,这几秒先不拿文件里的旧值盖回来(见主循环)
            # 交给 seeu 的命令去改(开的时候顺带体检浏览器开关,可能等系统授权框;放子进程,不卡住显示)
            old = st.get("isee_proc")                  # 11-07 复查:上一条还没跑完就结束它(连点两下时「开」比「关」慢,会后写、停在开)
            if old is not None and old.poll() is None:
                try:
                    old.terminate()
                except Exception:
                    pass
            st["isee_proc"] = subprocess.Popen([sys.executable, "-m", "seeu", "isee", "on" if st["isee"] else "off"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            _log(f"按钮 I See → {st['isee']}")
            if is_card() and (in_browser() and st["b_expanded"] or not in_browser()):
                place_card()
            view.setNeedsDisplay_(True)
            cap_view.setNeedsDisplay_(True)
        elif name == "collapse" and in_browser():
            st["solo"] = None                         # 单看一个任务时点收起 = 回到多任务岛(C-0.8)
            st["b_expanded"] = False                  # 浏览器卡片收起:只这一轮,不改记住的展开/收起
            st["hover"] = False
            st["light"] = None
            place_cap()
            morph(False, after=close_stream)          # 在看浏览器画面的话顺手关流;下次展开回到文字卡
        elif name == "expand" and in_browser():
            st["b_expanded"] = True
            st["cap_alpha"] = 0.0
            place_browser()
            morph(True)
        elif name == "collapse":
            st["solo"] = None
            st["collapsed"] = True
            set_live(collapsed=True)
            st["hover"] = False
            st["light"] = None
            place_cap()
            morph(False, after=close_stream)
            _log("收起成悬浮标")
        elif name == "expand":
            st["collapsed"] = False
            set_live(collapsed=False)
            if st["mview"] == "steps":
                place_card()
                morph(True)
            elif st["wid"] is not None:
                # 10-31 用户报「没过渡、直接出画面」:原来先开画面流再变形,开流要等系统约 0.4 秒,这段一动不动。
                # 改成先变形、再开流 —— 开流时 sck 在等待里照样转事件循环,动画照播;画面到了跟着淡入(用户在小样里选 B)。
                set_title(st["wid"])                 # 标题先定,不然变形期间不重建标题,收尾才蹦出来
                img_layer.setContents_(None)         # 不留上一轮的旧画面
                morph(True)
                open_stream(st["wid"])               # 比例变了 place() 会改动画终点,不直接跳
            else:
                morph(True)
            _log("展开悬浮窗")
        save_frame()

    def toggle_view():
        """看画面 ↔ 看操作(用户 10-21 定)。浏览器默认文字卡,点了播操作的那个窗口;镜像默认画面,点了换成文字卡。"""
        if in_browser():
            if st["stream"] is None:
                st["wid"], st["aspect"] = st["browser"].get("wid"), None
                if not st["wid"] or not open_stream(st["wid"]):
                    st["wid"] = None
                    place_card()
                    _log("浏览器看画面:开画面流失败,留在文字卡")
            else:
                close_stream()
                st["wid"], st["aspect"] = None, None
                place_card()
        elif st["mview"] == "screen":
            st["mview"] = "steps"
            close_stream()
            place_card()
        else:
            st["mview"] = "screen"
            st["aspect"] = None                     # 文字卡大小 → 让 open_stream 按画面比例重新摆
            if st["wid"] is not None:
                open_stream(st["wid"])
        pnl["key"] = None
        view.setNeedsDisplay_(True)
        _log(f"切到{'文字卡' if is_card() else '画面'}")

    def fade(win, key, target):
        if abs(st[key] - target) <= 0.01:
            return False
        step = (1 / 30.0) / 0.25
        st[key] = min(target, st[key] + step) if target > st[key] else max(target, st[key] - step)
        if st[key] > 0 and not win.isVisible():
            win.orderFrontRegardless()
        win.setAlphaValue_(st[key])
        if st[key] <= 0.01:
            win.orderOut_(None)
        return True

    # ---- 多任务(SeeU C-0.8,10-24 用户定):按「任务名」(项目名,没有就按窗口/App)分开记,≥2 个同时在跑就换成灵动岛;只有 1 个照旧。
    tasks = {}            # 任务名 -> 状态
    pending = []          # 待重放的原始消息(切回单任务 / 单看某任务时,把那个任务最后一条消息再走一遍,让原悬浮窗接上)
    owner_cache = {}

    def owner_name(wid):
        c = owner_cache.get(wid)
        if c and time.time() - c[0] < 30:
            return c[1]
        try:
            info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(wid)) or []
            nm = str(info[0].get("kCGWindowOwnerName") or "") if info else ""
        except Exception:
            nm = ""
        owner_cache[wid] = (time.time(), nm)
        return nm

    def named_key(wid):
        """同一个窗口已有带项目名的任务 → 返回它的任务名(最近动过的那个);没有返回 None。
        10-27:有程序停手后手动调点击时没带项目名,被记成「w窗口号」第二个任务,岛来回跳。"""
        best = None
        for k, t in tasks.items():
            if wid and t.get("wid") == wid and t.get("who") and (best is None or t["last"] > best[1]):
                best = (k, t["last"])
        return best[0] if best else None

    def classify(raw):
        """一条消息 → (类型, 任务名, 项目名, App 名, 窗口号, 附加);认不出返回 None。"""
        try:
            if raw.startswith("stuck "):
                arr = json.loads(raw[6:])
                who = str(arr[5]) if len(arr) > 5 else ""
                return "stuck", who or str(arr[0]), who, str(arr[0]), None, arr
            if raw.startswith("browser "):
                arr = json.loads(raw[8:])
                who = str(arr[3]) if len(arr) > 3 else ""
                wid = int(arr[2]) if len(arr) > 2 and arr[2] else None
                return "browser", who or named_key(wid) or str(arr[0]), who, str(arr[0]), wid, arr
            msg = raw.split()
            if len(msg) in (2, 3, 4) and msg[0] == "show":
                who = msg[3] if len(msg) == 4 else ""
                wid = int(msg[1])
                app_ = owner_name(wid) or "App"
                return "show", who or named_key(wid) or f"w{wid}", who, app_, wid, msg
            if len(msg) in (4, 5) and msg[0] == "mark":
                who = msg[4] if len(msg) == 5 else ""
                return "mark", who or st.get("cur_key") or "", who, "", None, msg
        except Exception:
            pass
        return None

    near = dict(busy=False, want=None)

    def near_req(key, wid, fx, fy, t):
        """点击后在后台线程认点击处的字(10-27 自动推)。忙着就只留最新一次,不排队、不拖慢显示。"""
        near["want"] = (key, wid, fx, fy, t)
        if near["busy"]:
            return
        near["busy"] = True
        import threading

        def run():
            try:
                while near["want"]:
                    key_, wid_, fx_, fy_, t_ = near["want"]
                    near["want"] = None
                    try:
                        x, on = near_text(wid_, fx_, fy_)
                    except Exception as e:
                        x, on = "", False
                        _log(f"点击处认字出错:{e!r}")
                    st["near"] = (x, t_, on)
                    tk = tasks.get(key_)
                    if tk is not None and tk.get("mark_t", 0) <= t_ + 0.05:      # 岛上那行也换成「点『X』附近」
                        tk["step"] = near_step(x, on) if x else tr_step("点击")
            finally:
                near["busy"] = False
        threading.Thread(target=run, name="seeu-near-text", daemon=True).start()

    def note_task(raw, c, now):
        """把一条消息记进任务表(重放的不算)。"""
        kind, key, who, app_, wid, extra = c
        if not key:
            return
        t = tasks.get(key)
        if t is None:
            t = tasks[key] = dict(key=key, who=who, app=app_ or key, kind="app", step="", steps=[], born=now, last=now,
                                  borrow=False, real_until=0.0, stuck=None, hidden=False, wid=None, raw=None)
        step = None
        if kind == "show":
            t.update(kind="mirror", app=app_, wid=wid, stuck=None, hidden=False, raw=raw)
            t["real_until"] = now + PASS_S if (len(extra) >= 3 and extra[2] == "real") else 0.0
            # 10-27:不再写「操作 BlueStacks」;没在点就是等下一步(岛那边按 mark_t 判断)
        elif kind == "browser":
            t.update(kind="browser", app=app_, wid=wid, stuck=None, hidden=browser_hidden(app_), raw=raw, real_until=0.0)
            step = doing_plain(str(extra[1])) if str(extra[1]).strip() else tr("island.operating", "操作 {app}", app=app_)
        elif kind == "stuck":
            t.update(kind="browser", app=app_, stuck=dict(why=str(extra[2]), todo=str(extra[3])), raw=raw, real_until=0.0)
            step = str(extra[1])
        elif kind == "mark":
            t["mark_t"] = now
            step = tr_step("点击")
            w_ = t.get("wid") or st.get("wid")
            if w_ and len(extra) >= 4:
                try:
                    near_req(key, w_, float(extra[2]), float(extra[3]), now)
                except (TypeError, ValueError):
                    pass
        if who:
            t["who"] = who
        if step and step != t["step"]:
            t["step"] = step
            t["steps"] = ([step] + [x for x in t["steps"] if x != step])[:4]
        t["last"] = now
        st["cur_key"] = key

    def doing_plain(stp):
        stp = (stp or "").strip()
        return tr_step(stp[2:] if stp.startswith("正在") else stp)

    def alive_tasks(now):
        out = []
        for k, t in list(tasks.items()):
            idle = now - t["last"]
            if idle > IDLE_EXIT_S:
                del tasks[k]
            elif idle < HIDE_AFTER_S or t["stuck"]:     # 卡住的留着(等人处理),最多 IDLE_EXIT_S
                t["borrow"] = now < t["real_until"]
                out.append(t)
        return out

    def set_solo(key):
        """从岛上点「看画面」:只看这个任务(原悬浮窗接手);之后在悬浮窗上点收起 = 回到岛。"""
        t = tasks.get(key)
        st["solo"] = key
        if t and t.get("raw"):
            pending.append(t["raw"])
        _log(f"单看任务 {key}")

    def isee_toggle():
        st["isee"] = not st["isee"]
        st["isee_click_t"] = time.time()
        old = st.get("isee_proc")                  # 11-07 复查:上一条还没跑完就结束它(连点两下时「开」比「关」慢,会后写、停在开)
        if old is not None and old.poll() is None:
            try:
                old.terminate()
            except Exception:
                pass
        st["isee_proc"] = subprocess.Popen([sys.executable, "-m", "seeu", "isee", "on" if st["isee"] else "off"], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        _log(f"岛上按钮 I See → {st['isee']}")

    def light_set(lvl):
        set_live(halo_real=lvl in ("real", "bg"), halo_bg=lvl == "bg")
        st["live"], st["live_t"] = live(), time.time()
        _log(f"岛上按钮 灯光 → {lvl}")

    isl.init(dict(tr=tr, isee_get=lambda: st["isee"], isee_toggle=isee_toggle, light_get=light_level, light_set=light_set,
                  solo=set_solo, log=_log))

    class Ticker(NSObject):
        def tick_(self, _t):
            with objc.autorelease_pool():
                if st.get("pass_until") and time.time() > st["pass_until"]:
                    set_pass(0)                 # 借用结束(超时没再收到 real):恢复接鼠标
                try:
                    self._tick()
                except Exception as e:      # 某一步出错也不能卡住"该收起就收起"
                    _log(f"tick 出错:{e!r}")
                try:
                    idle = time.time() - alive_t()
                    if idle > HIDE_AFTER_S + 3:
                        for win, key in ((panel, "alpha"), (cap, "cap_alpha")):
                            if key == "cap_alpha" and idle <= HIDE_AFTER_S + LINGER_S + 3:
                                continue                # 悬浮标还在多留的那几分钟里
                            if win.isVisible() and not st.get("morph"):
                                _log("兜底收起(超时没收到 show,正常淡出没走完)")
                                st[key] = 0.0
                                win.setAlphaValue_(0.0)
                                win.orderOut_(None)
                        if st["stream"] is not None:
                            close_stream()
                            _write_state(visible=False, updated=time.time())
                except Exception as e:
                    _log(f"兜底收起出错:{e!r}")

        def _tick(self):
            now = time.time()
            for _ in range(50):                      # 读积压消息,有上限
                replay = bool(pending)
                if replay:
                    raw = pending.pop(0)
                else:
                    try:
                        raw = sock.recv(4096).decode()
                    except BlockingIOError:
                        break
                    st["last_msg"] = now
                    c = classify(raw)
                    if c:
                        note_task(raw, c, now)
                        if st.get("solo") and c[1] and c[1] != st["solo"]:
                            continue                # 单看某个任务期间,别的任务只记表,不动原悬浮窗
                        if st.get("multi"):         # 岛在显示:原悬浮窗/悬浮标不动(不开画面流),只管借鼠标穿透
                            if c[0] == "show":
                                set_pass(now + PASS_S if (len(c[5]) >= 3 and c[5][2] == "real") else 0)
                            elif c[0] in ("browser", "stuck"):
                                set_pass(0)
                            continue
                if raw.startswith("why "):          # 10-30:AI 这一步的原因(MCP why)
                    try:
                        arr = json.loads(raw[4:])
                        st["why"] = dict(app=str(arr[0]), text=str(arr[1]).strip(), t=now,
                                         act=str(arr[3]) if len(arr) > 3 else "")
                    except Exception:
                        pass
                    pnl["key"] = None
                    view.setNeedsDisplay_(True)
                    continue
                if raw.startswith("stuck "):
                    try:
                        arr = json.loads(raw[6:])
                        sapp, sstep, why, todo, helps = arr[:5]     # 10-27:带项目名是 6 段,原来按 5 段拆会报错、整条丢掉
                        st["who"] = str(arr[5]) if len(arr) > 5 else ""
                    except Exception:
                        continue
                    if st["stream"] is not None:
                        close_stream()                  # 卡住强制切回文字卡(用户 10-21 定)
                    st["light"] = None
                    st["browser"] = dict(app=sapp, step=sstep, wid=(st.get("browser") or {}).get("wid"),
                                         stuck=dict(why=why, todo=todo, helps=bool(helps), t=now))
                    st["wid"], st["aspect"], st["mode"] = None, None, "bg"
                    set_pass(0)
                    st["last_show"] = st["last_act"] = now
                    was_cap = st["cap_alpha"] > 0.05 and not st["b_expanded"]
                    st["b_expanded"] = True
                    place_browser()
                    pnl["key"] = None
                    panel_build()                       # 先把字换好再弹开
                    if was_cap:
                        morph(True)                     # 从悬浮标弹开(灵动岛)
                    else:
                        st["cap_alpha"] = 0.0
                        cap.setAlphaValue_(0.0)
                        cap.orderOut_(None)
                    _log(f"卡住了:{sapp} {sstep}")
                    continue
                if raw.startswith("browser "):
                    try:
                        arr = json.loads(raw[8:])
                        bapp, bstep = arr[0], arr[1]
                        bwid = int(arr[2]) if len(arr) > 2 and arr[2] else None     # SeeU C-0.3 起:操作的浏览器窗口号
                        st["who"] = str(arr[3]) if len(arr) > 3 else ""             # SeeU C-0.4 起:项目名
                    except Exception:
                        bapp, bstep, bwid = "浏览器", "", None
                    from_mirror = st.get("browser") is None
                    first = from_mirror or now - alive_t() > HIDE_AFTER_S
                    # 正在看这个浏览器窗口的画面就接着看;换了窗口 / 不知道窗口 / 从镜像换过来 → 关流回文字卡
                    keep = (not first) and st["stream"] is not None and bwid and bwid == st.get("stream_wid")
                    if st["stream"] is not None and not keep:
                        close_stream()
                        st["wid"], st["aspect"] = None, None
                        if from_mirror:
                            st["alpha"] = 0.0
                            panel.setAlphaValue_(0.0)
                            panel.orderOut_(None)
                        elif st["b_expanded"]:
                            st["browser"] = dict(app=bapp, step=bstep, wid=bwid)
                            place_card()
                    was_stuck = bool((st.get("browser") or {}).get("stuck"))
                    was_hid = bool((st.get("browser") or {}).get("hidden"))
                    hid = browser_hidden(bapp)
                    st["browser"] = dict(app=bapp, step=bstep, wid=bwid, hidden=hid)
                    if (was_stuck or was_hid != hid) and st["b_expanded"]:
                        place_card()                    # 卡住那张高卡片缩回正常高度 / 隐身提醒那行加上或去掉
                    if not keep:
                        st["wid"], st["aspect"] = None, None
                    if st.get("mode") != "bg":
                        st["mode"] = "bg"
                    set_pass(0)
                    st["last_show"] = st["last_act"] = now
                    if first:
                        st["b_expanded"] = False
                        place_cap()
                    view.setNeedsDisplay_(True)
                    cap_view.setNeedsDisplay_(True)
                    continue
                msg = raw.split()
                if len(msg) in (2, 3, 4) and msg[0] == "show":
                    wid = int(msg[1])
                    mode = msg[2] if len(msg) >= 3 else "bg"
                    st["who"] = msg[3] if len(msg) == 4 else ""
                    set_pass(now + PASS_S if mode == "real" else 0)
                    if mode == "real":                     # 10-27:借鼠标时自动弹开卡片写清楚;借完自动收回(只收自己弹开的)
                        st["borrow_until"] = now + BORROW_HOLD_S
                        # 10-30 用户报:橙色光圈亮了悬浮窗没弹 —— 展开过一次后闲置自己缩回悬浮标(不改 collapsed),只看 collapsed 就不弹;
                        # 改成悬浮窗当时没显示出来(收着 / 缩回悬浮标)就弹
                        hidden_ = st["collapsed"] or st["alpha"] <= 0.05
                        if not st.get("borrow_auto") and hidden_ and st.get("browser") is None and not st.get("morph"):
                            st["borrow_auto"] = True
                            place_card()
                            pnl["key"] = None
                            panel_build()               # 先把字换好再弹开(10-27 实测:弹开动画里还是上一张卡片的字)
                            if st["cap_alpha"] > 0.05:
                                morph(True)
                    if mode != st.get("mode"):
                        st["mode"] = mode
                        cap_view.setNeedsDisplay_(True)
                        view.setNeedsDisplay_(True)
                    st["last_show"] = st["last_act"] = now
                    if st.get("browser") is not None:     # 从浏览器换回有画面的窗口
                        st["browser"], st["b_expanded"] = None, False
                        if st["stream"] is not None:      # 刚才在看浏览器画面
                            close_stream()
                        st["wid"] = None
                    changed = wid != st["wid"]
                    st["wid"] = wid
                    if changed:
                        set_title(wid)
                    if st.get("borrow_auto"):
                        pass                             # 借鼠标弹开的卡片照旧(不开画面流)
                    elif st["collapsed"]:
                        if st["cap_alpha"] <= 0.01:
                            place_cap()
                    elif st["mview"] == "steps":       # 镜像在「看操作」:不开画面流,摆成文字卡
                        if changed or abs(panel.frame().size.width - BROWSER_W) > 0.5:
                            place_card()
                    elif changed or st["stream"] is None or sck._window_px(wid) != st["px"] or stream_stale(wid):
                        open_stream(wid)             # 换窗口 / 窗口被缩放 / 收起后再开 / 悬浮窗拉大缩小够多(10-31)
                elif len(msg) in (4, 5) and msg[0] == "mark":   # 10-27:带项目名是 5 段(C-0.8 起),以前 == 4 全被丢,卡片一直「等下一步」、画面上也没点击圈
                    fx, fy = float(msg[2]), float(msg[3])
                    if 0 <= fx <= 1 and 0 <= fy <= 1:
                        st["last_act"] = now
                        st["marks"] = [m for m in st["marks"] if now - m[3] < RING_S] + [(msg[1], fx, fy, now)]
                        st["dot"] = (fx, fy, now)
                        st["last_mark"] = (msg[1], now)      # 镜像「看操作」文字卡用
                elif msg and msg[0] == "hide":
                    st["last_show"] = st["last_touch"] = 0.0
                    tasks.clear()
                    st["solo"] = None
                elif len(msg) == 2 and msg[0] == "island":   # 测试用:island open / close / hover / unhover / more
                    isl.test(msg[1])
                elif len(msg) == 2 and msg[0] == "hover":   # 测试用:不动鼠标也能看按钮栏
                    st["hover"] = msg[1] == "1"
                    view.setNeedsDisplay_(True)
                elif msg and msg[0] in ("expand", "collapse"):
                    on_button(msg[0])
                elif len(msg) == 2 and msg[0] == "btn":       # 测试用:不动鼠标按按钮(light / light_bg / view / collapse …)
                    if msg[1] == "collapse":
                        st["close_anim"] = st.get("close_anim") or now     # 跟真点一样先播合拢
                    elif msg[1] == "isee" and not st["isee"]:
                        # 11-07 复查:发这条消息就能把 I See 打开(命令是本进程拉起的,seeu.isee.from_overlay 分不出真点还是消息)。
                        # 开 I See 只认真鼠标点;关可以(AI 本来就能关)。
                        _log("btn isee(开)不接受:I See 只能用户亲手点开")
                    else:
                        on_button(msg[1])
                elif msg and msg[0] == "reset":
                    _write_state(frame=None, cap=None, size_port_h=None, size_land_w=None)
                    if st["aspect"]:
                        place(st["aspect"])
                    place_cap()
                elif msg and msg[0] == "quit":
                    close_stream()
                    _write_state(visible=False, updated=now)
                    NSApplication.sharedApplication().terminate_(None)
            if now - st["live_t"] > 1.0:             # 项目开跑时可能改了开关初始值;I See 可能在别处开关
                st["live"], st["live_t"] = live(), now
                ise = isee_on()
                if ise != st["isee"] and now - st.get("isee_click_t", 0) > 3.0:   # 刚点过按钮的 3 秒内不盖(11-06:命令还没写完文件会闪一下)
                    st["isee"] = ise
                    cap_view.setNeedsDisplay_(True)
                    view.setNeedsDisplay_(True)
                    if in_browser() and st["stream"] is None and st["b_expanded"]:
                        place_card()                   # 卡片高度跟着 I See 那行变
            alive = alive_tasks(now)
            if st.get("solo") and not any(t["key"] == st["solo"] for t in alive):
                st["solo"] = None
            multi = st.get("solo") is None and len(alive) >= 2
            if multi != bool(st.get("multi")):
                st["multi"] = multi
                _log(f"多任务岛 {'出现' if multi else '收起'}({len(alive)} 个任务:{'、'.join(t['key'] for t in alive) or '无'})")
                share_pos(multi)                     # 10-27:悬浮标和岛共用一个位置,切换时不再跳
                if not multi and alive:                # 掉回单任务:把剩下那个最后一条消息再走一遍,原悬浮窗接上
                    last = max(alive, key=lambda t: t["last"])
                    if last.get("raw"):
                        pending.append(last["raw"])
            if multi:
                isl.sync([dict(t) for t in alive], now)
                if now - _read_state().get("updated", 0) > 1:
                    _write_state(shown_frame=list(isl.frame() or []) or None, updated=now, visible=isl.is_visible())
                st["last_show"] = max(st["last_show"], max(t["last"] for t in alive))
            else:
                isl.hide()
            if st.get("borrow_auto") and now > st.get("borrow_until", 0) and not st.get("morph"):
                st["borrow_auto"] = False              # 借完自动收回(10-27)
                place_cap()
                morph(False)
            brw = in_browser()
            idle = now - alive_t()
            has = st["wid"] is not None or brw
            active = has and idle < HIDE_AFTER_S and not multi
            linger = has and HIDE_AFTER_S <= idle < HIDE_AFTER_S + LINGER_S and not multi   # 到点先缩成悬浮标多留一会儿(不改记住的展开/收起)
            if linger and st["cap_alpha"] <= 0.01 and not st.get("morph"):
                place_cap()                          # 悬浮标摆回悬浮窗右上角再淡入
            if st.get("morph"):      # 变形动画进行中:窗口透明度/显隐由动画管
                ch1 = ch2 = False
            else:
                # 浏览器:默认悬浮标,点开才是卡片(10-20 用户定"浏览器操作时弹出悬浮标");镜像:没收起且有画面/文字卡才是悬浮窗
                show_p = active and (st.get("borrow_auto") or (st["b_expanded"] if brw else
                                     (not st["collapsed"] and (st["stream"] is not None or st["mview"] == "steps"))))
                # 🔴 悬浮窗出不来时一律显示悬浮标(SeeU C-0.4 用户报"一会出现一会消失":多留期间鼠标移上悬浮标 = 又算"在用",
                # 画面已关、悬浮窗出不来,原来按"在用且没收起"把悬浮标也藏了,60 秒后再冒出来)
                ch1 = fade(panel, "alpha", 1.0 if show_p else 0.0)
                ch2 = fade(cap, "cap_alpha", 1.0 if (active or linger) and not show_p else 0.0)
            if brw and not active and not linger and st["alpha"] <= 0.01 and st["cap_alpha"] <= 0.01:
                st["browser"], st["b_expanded"] = None, False
                close_stream()
            if not active and not linger and not st["collapsed"] and st["alpha"] <= 0.01 and st["cap_alpha"] <= 0.01:
                st["collapsed"] = True                 # 10-27 用户定:不记,这一轮完了下次从悬浮标开始
                set_live(collapsed=True)
            if (ch1 and st["alpha"] <= 0.01) and st["stream"] is not None:
                close_stream()                       # 淡出完就关流,省 CPU,菜单栏录屏图标也会消失
            if ch1 or ch2:
                save_frame()
            elif (active or linger) and now - _read_state().get("updated", 0) > 3:
                save_frame()                         # 显示期间定时续一下,给提示条判断"在不在显示"
            shim_update(now)
            if st["alpha"] > 0.01 and not st.get("morph") and is_card() and (card_why(), borrowing()) != st.get("why_sig"):
                place_card()                         # 10-30:原因出现 / 换了 / 没了、借鼠标开始 / 结束,卡片高度跟着变
            if st["hover"] and st["alpha"] > 0.01:
                # 10-31:点开时是程序认定「鼠标在上面」的(没收到进入事件),移出去时未必有离开事件 → 每帧核一下,出去了就当离开
                from AppKit import NSEvent
                mp, pf = NSEvent.mouseLocation(), panel.frame()
                if not (pf.origin.x <= mp.x <= pf.origin.x + pf.size.width and pf.origin.y <= mp.y <= pf.origin.y + pf.size.height):
                    st["hover"] = False
                    view.setNeedsDisplay_(True)
            if st["alpha"] > 0 or st.get("morph"):
                panel_build()
            out = st["out"]
            if out is not None and out.n != st["n"] and out.pb is not None and st["alpha"] > 0:
                st["n"] = out.n
                surf = Quartz.CVPixelBufferGetIOSurface(out.pb)
                Quartz.CATransaction.begin()
                Quartz.CATransaction.setDisableActions_(True)
                img_layer.setContents_(None)       # 同一块缓冲被复用时也要刷新
                img_layer.setContents_(surf)
                Quartz.CATransaction.commit()
            sk = (st.get("browser") or {}).get("stuck")
            if sk and sk.get("helps") and now - sk["t"] < PULSE_S + 0.2 and st["alpha"] > 0:
                view.setNeedsDisplay_(True)          # I See 按钮在闪
            ca = st.get("close_anim")
            if ca:
                if now - ca >= CLOSE_ANIM_S + 0.05:
                    st["close_anim"] = None
                    on_button("collapse")
                else:
                    view.setNeedsDisplay_(True)
            L = st.get("light")
            if L and now - L["t0"] < MORPH_T * 2.2 + 0.1 and st["alpha"] > 0:
                view.setNeedsDisplay_(True)          # 灯光选项条在伸缩
            if st["marks"] or (st["dot"] and now - st["dot"][2] < DOT_S + 0.1):
                st["marks"] = [m for m in st["marks"] if now - m[3] < RING_S]
                view.setNeedsDisplay_(True)
            if now - st["last_msg"] > IDLE_EXIT_S and st["alpha"] <= 0.01 and st["cap_alpha"] <= 0.01:
                close_stream()
                NSApplication.sharedApplication().terminate_(None)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    try:   # 后台程序默认不能换鼠标样式;开这个连接属性才行(私有接口,只当加速层,失败就是箭头不变)
        import ctypes
        import ctypes.util
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        sl = ctypes.cdll.LoadLibrary("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight")
        sl.SLSMainConnectionID.restype = ctypes.c_int
        sl.SLSSetConnectionProperty.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        sl.SLSSetConnectionProperty.restype = ctypes.c_int
        cid = sl.SLSMainConnectionID()
        key = cf.CFStringCreateWithCString(None, b"SetsCursorInBackground", 0x08000100)   # UTF-8
        true_ptr = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        err = sl.SLSSetConnectionProperty(cid, cid, key, true_ptr)
        if err:
            _log(f"开后台换鼠标样式返回 {err}(箭头可能不变)")
    except Exception as e:
        _log(f"开后台换鼠标样式失败(箭头可能不变):{e!r}")
    ticker = Ticker.alloc().init()
    timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / 30.0, ticker, "tick:", None, True)
    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)   # 拖动/缩放时也照跑
    _write_state(visible=False, updated=time.time())
    print(f"watch_window 已启动,监听 127.0.0.1:{PORT},空闲 {IDLE_EXIT_S}s 自动退出")
    app.run()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "serve":
        serve()
    elif cmd == "show" and len(argv) >= 2:
        show(int(argv[1]), argv[2] if len(argv) >= 3 else "bg")
    elif cmd == "demo":
        # 手动试用:python3 -m seeu_lib.watch_window demo ["iPhone Mirroring"] [秒数]  —— 按应用名找窗口,连续显示一阵
        owner = argv[1] if len(argv) >= 2 else "iPhone Mirroring"
        secs = min(float(argv[2]) if len(argv) >= 3 else 60, 600)     # 硬上限 10 分钟
        from seeu_lib import mac_input as mi
        g = mi.win_geo(owner, all_spaces=True)
        if not g:
            print(f"找不到「{owner}」的窗口")
            return 2
        print(f"悬浮窗会连续显示 {secs:.0f} 秒(窗口 {g['id']}),随便试:拖、拉边、移上去点按钮、收起再展开。按 Ctrl+C 提前结束。")
        t0 = time.time()
        try:
            while time.time() - t0 < secs:
                show(g["id"])
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        print(f"结束,{HIDE_AFTER_S} 秒后自己收起。")
    elif cmd == "browser":
        browser(argv[1] if len(argv) >= 2 else "Safari", " ".join(argv[2:]))
    elif cmd == "mark" and len(argv) >= 4:
        mark(argv[1], argv[2], argv[3])
    elif cmd in ("hide", "quit", "reset", "expand", "collapse"):
        if _running():
            send(cmd)
        elif cmd == "reset":
            _write_state(frame=None, cap=None, size_port_h=None, size_land_w=None)
        elif cmd in ("expand", "collapse"):
            set_live(collapsed=cmd == "collapse")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
