"""SeeU · I See 模式(我知风险)(SeeU C-0.1,10-20 用户定)

看过 README「I See 模式」一节 = 知道风险;开了以后 SeeU 中途不提示、不停,自动换路直到做成,最后出报告。
放开的:SeeU 自己的允许名单不查(开关这条路)、插件没允许的网站自动换开关/辅助功能、失败自动换下一条路。
拿不掉的:用户亲手在用键鼠时让路;密码框/新密码框/验证码框/银行卡框不碰(代码层);付款、转账这类(调用方 AI 自己的规矩)——
  这些不中途停,记成「跳过」,报告里统一列。

开法(只让用户自己开,AI 只能关;11-02 用户定):
  悬浮窗 / 灵动岛上的 I See 按钮;或用户自己在终端里敲:python3 -m seeu isee on [小时]   /  off  /  status  /  report
  底层存在 seeu/设置.json 的 "I See",🔴 11-16 起还要带上 on() 写的「I See 凭证」才算开:手改设置文件写「开」不算
  (防 AI 绕开按钮直接改文件);环境变量 SEEU_ISEE=0 强制关(这一个进程),=1 不再能开(11-16 起,原来给定时任务用,没人用)。
默认 24 小时后自动失效(设置文件里 "I See 到期")。到期后第一次用 SeeU 会弹提示条提醒关浏览器开关。
日志:~/.seeu/seeu_isee.log(只在本机;7 天前的自动清;打的字只记长度,不记内容)。

10-24 C-0.7 用户定(卡片说明「我已知风险，授权 AI 执行 · 卡住时请立即报告！」):
  某一项做不了、不影响别的 → skip():记一笔、悬浮标上记数,不弹提示条,做完报告里列;
  真卡住、后面都靠它 → stuck():立刻停,卡片展开写卡在哪/为什么/怎么办 + 提示条,不加声音。
  跳过还是停由调用方判断(SeeU 不知道后面的步骤靠不靠这一步)。
  怎么办只从固定清单 FIXES 里给(插件、开关、辅助功能、屏幕录制、自动化);清单外的(哪怕网页上写着要装)只报告不推荐,
  防网页里的恶意文字借 I See 让 AI 推荐装东西。尽力有上限:每个卡点最多 MAX_TRIES 条路 / MAX_SECS 秒,到顶算卡住。
  授权不含对外动作:发消息、提交、付款,以及最后勾权限、点「添加插件」那一下,都要用户亲手。
"""
import json
import os
import sys
import time
from seeu_lib import home   # 11-01:状态/日志目录统一取法(SEEU_HOME,没设 = ~/.seeu;开源包里默认 ~/.seeu)

HERE = os.path.dirname(os.path.abspath(__file__))
# 11-13:环境变量 SEEU_SETTINGS_FILE 可以把 I See 的开关换到别的文件(只给开发测试用:虚拟机里的代码是共享目录,
# 不换的话在虚拟机里点 I See 会改到这台 Mac 上真的 设置.json)。平时不设。
SETTINGS = os.environ.get("SEEU_SETTINGS_FILE") or os.path.join(HERE, "设置.json")
LOG = home("seeu_isee.log")
KEY, KEY_UNTIL, KEY_PROOF = "I See", "I See 到期", "I See 凭证"
# 11-16:凭证用的本机密钥(只本用户可读);删了 = 现有的开着作废,关 / 到期时就删(旧凭证抄回去也不算)。
# 🔴 不跟 SEEU_HOME 走(同 seeu_web):各家 MCP 配置可能各设各的 SEEU_HOME,跟着走会找不到同一把、把用户开的当成伪造
SECRET = os.path.expanduser("~/.seeu/seeu_isee.key")
DEFAULT_HOURS = 24
KEEP_DAYS = 7
FMT = "%Y-%m-%d %H:%M"
LIVE = home("seeu_isee_live.json")     # 本轮跳过/卡住计数,给悬浮标读
MAX_TRIES, MAX_SECS = 3, 60          # 每个卡点最多换几条路、最多花多少秒(到顶算卡住)
_PANE = "x-apple.systempreferences:com.apple.preference.security?"
# 卡住时「怎么办」只能从这里给:SeeU 自己要用的东西。(名字, 怎么做, 能直接打开的设置页 或 None)
FIXES = {
    "plugin": ("装 SeeU 浏览器插件", "跟 AI 说一声它来装(也可以终端 python3 -m seeu.web.install),装完在网页上点浏览器右上角的 SeeU 图标「允许这个网站」", None),
    "aejs_safari": ("打开 Safari 开关", "Safari 菜单 → 设置 → 高级 → 勾「显示网页开发者功能」;再到 开发 菜单 → 勾「允许来自 Apple 事件的 JavaScript」", None),
    "aejs_chrome": ("打开 Chrome 开关", "Chrome 菜单 查看 → 开发者 → 勾「允许 Apple 事件中的 JavaScript」", None),
    "accessibility": ("给辅助功能授权", "系统设置 → 隐私与安全性 → 辅助功能(新版 macOS 英文界面里叫 Device Control and Data Access) → 打开运行 SeeU 的程序(终端 / Claude)", _PANE + "Privacy_Accessibility"),
    "screen": ("给屏幕录制授权", "系统设置 → 隐私与安全性 → 屏幕与系统录音 → 打开运行 SeeU 的程序", _PANE + "Privacy_ScreenCapture"),
    "automation": ("允许控制这个 App", "系统设置 → 隐私与安全性 → 自动化 → 在运行 SeeU 的程序下面勾上要控制的 App(Safari / Chrome / 备忘录…,每个 App 单独一项)", _PANE + "Privacy_Automation"),
}


def _load(strict=False):
    """读 设置.json。strict=True(要改完写回去的地方用):文件在但读不出来就报错。
    11-06 体检:原来读坏了返回 {},on / off 接着把只剩一个键的内容整份写回,署名、颜色、借用鼠标等全丢。"""
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:       # 11-14:认记事本存的带 BOM 的(Windows)
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as ex:
        if strict:
            raise RuntimeError(f"设置.json 读不出来(格式坏了:{ex}),没改;先把这个文件修好")
        return {}


LOCK = os.path.expanduser("~/.seeu/seeu_isee.lock")    # 11-16:改 I See 那几项时的文件锁(同密钥,不跟 SEEU_HOME)
LOCK_WAIT_S = 5


try:                     # 按「有哪个用哪个」选,不看 sys.platform(测试会把它换掉)
    import fcntl as _fcntl
except ImportError:      # Windows
    _fcntl = None


class _Locked:
    """改设置里 I See 那几项(开 / 关 / 到期关)时拿的锁:几个进程同时改不会互相冲掉(到期自动关跟用户刚点开撞上,
    复查提的)。最多等 LOCK_WAIT_S 秒,拿不到抛 RuntimeError(不无限等)。有 fcntl 用 flock(Mac),没有用 msvcrt.locking(Windows)。"""
    def __enter__(self):
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        self.f = open(LOCK, "a+b")
        t0 = time.time()
        while True:
            try:
                if _fcntl:
                    _fcntl.flock(self.f.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                else:
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                return self
            except OSError:
                if time.time() - t0 > LOCK_WAIT_S:
                    self.f.close()
                    raise RuntimeError(_L("I See 的设置正被别的程序改着,等了几秒还没好,没改;过一会儿再试",
                                          "Another program is changing the I See setting; gave up after a few seconds, try again shortly"))
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            if _fcntl:
                _fcntl.flock(self.f.fileno(), _fcntl.LOCK_UN)
            else:
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self.f.close()
        return False


def _save(d):
    tmp = SETTINGS + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def _L(zh, en):
    try:
        from seeu.i18n import lang
        return en if lang() == "en" else zh
    except Exception:
        return zh


def _secret(create=False):
    """凭证密钥(32 字节随机,文件只本用户可读)。没有且 create=False → None。"""
    try:
        with open(SECRET, "rb") as f:
            k = f.read()
        if len(k) >= 32:
            return k
    except OSError:
        pass
    if not create:
        return None
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    for _ in range(3):
        # 先写满临时文件再 link 到正式位置:正式文件要么没有、要么是完整的一把(写到一半被结束也不会留空文件);
        # 两个 on() 同时第一次跑,link 失败的那个读先建好的那把(11-16 复查两轮)
        k = os.urandom(32)
        tmp = SECRET + f".{os.getpid()}.{os.urandom(4).hex()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
        try:
            os.link(tmp, SECRET)
            return k
        except FileExistsError:
            got = _secret()
            if got:
                return got
            try:              # 老版本留下的坏文件(长度不够):删掉重建
                os.remove(SECRET)
            except OSError:
                pass
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    raise RuntimeError(_L("I See 的密钥文件建不起来(~/.seeu/seeu_isee.key),没开", "Couldn't create the I See key file (~/.seeu/seeu_isee.key); not turned on"))


def _drop_secret():
    """关 / 到期 / 认出伪造时作废密钥:之前写过的凭证全部对不上(防 AI 记下凭证、关了以后原样抄回去)。"""
    try:
        os.remove(SECRET)
    except OSError:
        pass


def _proof(until, nonce, key):
    import hashlib
    import hmac
    return hmac.new(key, f"I See|{until or ''}|{nonce}".encode(), hashlib.sha256).hexdigest()


def proof_ok(d):
    """设置里的「开」是不是 on() 写的(凭证对得上)。只读,不改文件。
    🔴 挡的是「AI 绕开按钮直接把设置文件改成开」;同一个账号下的程序真要伪造也拦不住,这只是让绕路变成明摆着的伪造。"""
    pf = d.get(KEY_PROOF)
    if not isinstance(pf, str) or "." not in pf:
        return False
    key = _secret()
    if not key:
        return False
    import hmac
    nonce, sig = pf.split(".", 1)
    return hmac.compare_digest(sig, _proof(d.get(KEY_UNTIL), nonce, key))


def file_on(d):
    """只看设置文件(不看环境变量、不改文件):写着开 + 凭证对 + 没过期。悬浮窗、取证这种不能改东西的地方用。"""
    if str(d.get(KEY, "关")) not in ("开", "on", "1", "true") or not proof_ok(d):
        return False
    until = d.get(KEY_UNTIL)
    try:
        return not (until and time.time() > time.mktime(time.strptime(until, FMT)))
    except ValueError:
        return False


_FORGED_LOGGED = False


def status(_again=False):
    """{on, source(环境变量/设置文件), until(到期时间文字或 None)}。过期的顺手关掉并提醒一次。"""
    env = os.environ.get("SEEU_ISEE", "").strip().lower()
    if env in ("0", "off", "关", "false"):
        return dict(on=False, source="环境变量", until=None)
    d = _load()
    if str(d.get(KEY, "关")) not in ("开", "on", "1", "true"):
        return dict(on=False, source="设置文件", until=None)
    if not proof_ok(d):
        # 11-16:写着开、凭证对不上 = 不是 on() 开的(手改 / 别的程序改的 / 升级前开的)→ 当关,不改文件(复查:改了会把
        # 读不到密钥的进程误判的那份也关掉),每个进程只记一次
        global _FORGED_LOGGED
        if not _FORGED_LOGGED:
            _FORGED_LOGGED = True
            log("forged")
        return dict(on=False, source="设置文件", until=None, forged=True)
    until = d.get(KEY_UNTIL)
    try:
        expired = until and time.time() > time.mktime(time.strptime(until, FMT))
    except ValueError:
        expired = True          # 11-16:到期时间写坏了按已过期(原来当没过期 = 一直开着)
    if expired:
        try:
            with _Locked():
                d2 = _load()
                if d2.get(KEY_PROOF) != d.get(KEY_PROOF):
                    # 读到之后有人刚开 / 关过(锁外读的是旧的)→ 不动它,按现在的内容重新算一次
                    changed = True
                else:
                    changed = False
                    d2[KEY] = "关"
                    d2.pop(KEY_UNTIL, None)
                    d2.pop(KEY_PROOF, None)
                    _drop_secret()
                    _save(d2)
        except RuntimeError:
            return dict(on=False, source="设置文件", until=until, expired=True)     # 拿不到锁:按到期算关,不写
        if changed:            # 只重算一次,别来回转
            return status(True) if not _again else dict(on=False, source="设置文件", until=until)
        _expired_notice()
        return dict(on=False, source="设置文件", until=until, expired=True)
    return dict(on=True, source="设置文件", until=until)


def active():
    try:
        return status()["on"]
    except Exception:
        return False


def hours_ok(hours):
    """0 = 不自动关;否则 1 分钟 ~ 一年(11-16:负数原来开出一个已经过期的,NaN / 无穷大会崩)。"""
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return False
    return h == 0 or 1 / 60 <= h <= 24 * 365


def _tty_confirm(secs=60):
    """Mac 终端里开的现场确认(11-16 复查,照 Windows):随机一个字母,要人在这个终端的键盘上按。读的是控制终端 /dev/tty,
    AI 的命令行没有控制终端(打不开就算没确认);进程脱离父进程链(后台、launchd)也答不上来。最多等 secs 秒。"""
    import random
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return False
    ch = random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        os.close(fd)
        return False
    try:
        os.write(fd, _L(f"要打开 I See(我知风险),请在键盘上按字母 {ch} 确认,按别的键取消({secs} 秒内):",
                        f"To turn on I See (I know the risks), press the letter {ch} to confirm, any other key cancels "
                        f"(within {secs} s): ").encode())
        tty.setcbreak(fd)
        termios.tcflush(fd, termios.TCIFLUSH)        # 先清掉之前积着的键
        r, _, _ = select.select([fd], [], [], secs)
        k = os.read(fd, 4).decode(errors="ignore")[:1] if r else ""
        os.write(fd, (k + "\n").encode())
        return k.upper() == ch
    except Exception:
        return False
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        os.close(fd)


def _win_console_ok():
    """Windows 命令行那条:on() 自己再查一遍(不信调用方传的 by):真控制台、不是编辑器 / AI 终端、现场按对字母。"""
    try:
        from seeu import __main__ as m
        from seeu.win import lang as lg
    except Exception:
        return False
    return m._win_by_person() and not m._win_isee_ai() and m._win_key_confirm(lg)


def _win_overlay_ok():
    """Windows 悬浮窗那条:本进程就是浮标,而且它刚认出一次手按(GetCurrentInputMessageSource = 硬件)按下。"""
    cands = [sys.modules.get("seeu.win.floatwin")]
    m = sys.modules.get("__main__")          # 用 -m 拉起时浮标代码叫 __main__(floatwin 顶上也登记了别名,这里双保险)
    if m is not None and getattr(getattr(m, "__spec__", None), "name", "") == "seeu.win.floatwin":
        cands.append(m)
    now = time.time()
    return any(fw is not None and getattr(fw, "SERVING", False) and 0 <= now - getattr(fw, "HAND_T", 0) < 5 for fw in cands)


def _linux_overlay_ok():
    """Linux 悬浮标那条(11-18 C-3.0):本进程就是浮标显示进程,而且小插件刚报过一次来自硬件(/dev/input)的按下。"""
    cands = [sys.modules.get("seeu.linux.floatwin")]
    m = sys.modules.get("__main__")
    if m is not None and getattr(getattr(m, "__spec__", None), "name", "") == "seeu.linux.floatwin":
        cands.append(m)
    now = time.time()
    return any(fw is not None and getattr(fw, "SERVING", False) and 0 <= now - getattr(fw, "HAND_T", 0) < 5 for fw in cands)


def person_ok(by=None):
    """这次「开」是不是用户亲手(11-16 复查后:都在这里自己查,不信调用方的话)。
    Mac:悬浮窗亲自拉起的(from_overlay),或父进程链里没有 AI 客户端 + 终端里现场按对字母;
    Windows:by="console" 真控制台 + 不是 AI + 现场按键;by="overlay" 浮标进程里刚有一次手按。"""
    if sys.platform == "win32":
        if by == "console":
            return _win_console_ok()
        if by == "overlay":
            return _win_overlay_ok()
        return False
    if sys.platform.startswith("linux") and by == "overlay":
        return _linux_overlay_ok()
    if from_overlay():
        return True
    return not from_ai() and _tty_confirm()


def on(hours=DEFAULT_HOURS, by=None):
    """开 I See,hours 小时后自动失效(0 = 不失效)。顺带做一次体检,返回体检结果。
    11-16:「只让用户自己开」原来只在命令行入口查,`python -c "isee.on()"` 能绕 → 查在这里;不是用户亲手抛 PermissionError。"""
    if not hours_ok(hours):
        raise ValueError(_L("小时数不对:0 = 不自动关,其余 1 分钟到一年", "Bad hours: 0 = never turns off by itself, otherwise 1 minute to 1 year"))
    if not person_ok(by):
        log("on_refused", by=by)
        raise PermissionError(_L("I See 只能你自己开(悬浮窗上的 I See 按钮,或自己在终端里敲命令),AI 不能替你开",
                                 "Only you can turn on I See (the I See button on the overlay, or typing the command in a terminal yourself)"))
    hours = float(hours)
    with _Locked():
        d = _load(strict=True)
        d[KEY] = "开"
        d[KEY_UNTIL] = time.strftime(FMT, time.localtime(time.time() + hours * 3600)) if hours else None
        nonce = os.urandom(8).hex()
        d[KEY_PROOF] = nonce + "." + _proof(d[KEY_UNTIL], nonce, _secret(create=True))
        _save(d)
    log("on", hours=hours)
    try:
        os.remove(LIVE)          # 新一轮从 0 计
    except OSError:
        pass
    return checkup()


def off():
    with _Locked():
        d = _load(strict=True)
        d[KEY] = "关"
        d.pop(KEY_UNTIL, None)
        d.pop(KEY_PROOF, None)
        _save(d)
        _drop_secret()
    log("off")


def checkup():
    """开启时体检:开着的浏览器逐个试一下开关(第一次会弹系统授权框,集中在这时弹掉,跑起来就不再弹)。
    没开的浏览器不碰(不会替你打开)。返回 {浏览器: 状态说明}。"""
    if sys.platform != "darwin":      # 11-13:Windows 版没有浏览器开关 / 插件这几条路,没什么可体检的
        return {}
    from seeu.web import aejs, plugin_ready
    out = {}
    for app in sorted(aejs.SAFARI | aejs.CHROME_LIKE):
        if not aejs.running(app):
            continue
        st = aejs.state(app)
        txt = {"on": "开关开着 ✅", "switch_off": "开关没开(" + aejs.howto(app) + ")",
               "denied": "系统没授权控制它(系统设置 → 隐私与安全性 → 自动化)",
               "timeout": "卡在系统授权弹窗上,去点「允许」", "no_tab": "没有窗口,判断不了"}.get(st, st)
        if app in aejs.CHROME_LIKE and plugin_ready(app):
            txt += ";插件在线 ✅"
        out[app] = txt
    return out


# ---------------------------------------------------------------- 日志 + 报告

def log(event, **kw):
    """记一条(只在本机)。打的字只记长度。"""
    if "text" in kw:
        kw["text_len"] = len(str(kw.pop("text")))
    rec = dict(t=time.strftime("%Y-%m-%d %H:%M:%S"), ts=time.time(), event=event, **kw)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        _prune()
    except OSError:
        pass


def _prune():
    try:
        if os.path.getsize(LOG) < 512 * 1024:
            return
        cut = time.time() - KEEP_DAYS * 86400
        keep = [ln for ln in open(LOG, encoding="utf-8") if json.loads(ln).get("ts", 0) >= cut]
        with open(LOG, "w", encoding="utf-8") as f:
            f.writelines(keep)
    except Exception:
        pass


def _live(**inc):
    """本轮计数(开 I See 时清零):skips / stucks。悬浮标读这个显示「跳过 N 项」。"""
    try:
        with open(LIVE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    for k, v in inc.items():
        d[k] = d.get(k, 0) + v
    d["t"] = time.time()
    try:
        os.makedirs(os.path.dirname(LIVE), exist_ok=True)
        tmp = LIVE + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, LIVE)
    except OSError:
        pass
    return d


def fix_plan(key):
    """固定清单里的一项 → {name, how, open}。不在清单里 → None(只报告,不推荐)。"""
    f = FIXES.get(key)
    return dict(key=key, name=f[0], how=f[1], open=f[2]) if f else None


def skip(app, step, why):
    """某一项做不了、不影响后面的:记一笔 + 计数,不打扰(用户定不弹提示条)。返回本轮已跳过几项。"""
    log("skip", app=app, step=step, reason=str(why)[:200])
    return _live(skips=1).get("skips", 0)


def stuck(app, step, why, fix=None, todo=None, open_page=False):
    """真卡住、后面都靠它:立刻报告。卡片展开写卡在哪/为什么/怎么办 + 提示条(不加声音)。
    fix = FIXES 里的键(给能照做的方案);清单外的东西只写 todo(默认「这一步你自己来」),不推荐装/开别的。
    open_page=True 且这项有设置页:顺手打开系统设置对应那页(只打开,勾选要用户亲手)。返回给调用方转述的一句话。"""
    plan = fix_plan(fix) if fix else None
    todo_txt = f"{plan['name']}:{plan['how']}" if plan else (todo or "这一步你自己来")
    log("stuck", app=app, step=step, reason=str(why)[:200], fix=fix if plan else None, todo=todo_txt[:200])
    _live(stucks=1)
    msg = f"卡在:{app} {step} 原因:{why} 怎么办:{todo_txt}"
    if os.environ.get("SEEU_NO_WATCH"):
        return msg
    try:
        from seeu_lib import watch_window as ww
        if getattr(ww, "stuck", None):
            ww.stuck(app, step, str(why)[:120], todo_txt[:160], False)
    except Exception:
        pass
    try:
        import subprocess
        subprocess.Popen([sys.executable, "-m", "seeu_lib.cursor_overlay", "toast", f"SeeU 卡住了 · {app}",
                          f"{step}:{str(why)[:60]}", "8"],
                         cwd=os.path.dirname(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if open_page and plan and plan["open"]:
            subprocess.Popen(["open", plan["open"]])
    except Exception:
        pass
    return msg


def record(app, step, result):
    """浏览器动作做完记一笔(I See 开着才记)。result = SeeU 的结果 dict。"""
    if not active():
        return
    log("act", app=app, step=step, outcome=result.get("outcome"), route=result.get("route"),
        reason=(result.get("reason") or "")[:200], unlock=result.get("unlock"))


def report(since=None):
    """结束报告三栏:做成了 / 跳过了(原因)/ 开什么能多做。since = 时间戳,默认最近一次开启以来。"""
    recs = []
    try:
        recs = [json.loads(ln) for ln in open(LOG, encoding="utf-8")]
    except Exception:
        pass
    if since is None:
        since = max([r["ts"] for r in recs if r.get("event") == "on"] or [0])
    acts = [r for r in recs if r.get("event") == "act" and r.get("ts", 0) >= since]
    skips = [r for r in recs if r.get("event") == "skip" and r.get("ts", 0) >= since]
    stucks = [r for r in recs if r.get("event") == "stuck" and r.get("ts", 0) >= since]
    done = [r for r in acts if r.get("outcome") in ("delivered", "unverified")]
    skipped = [r for r in acts if r.get("outcome") not in ("delivered", "unverified")]
    unlock = sorted({r["unlock"] for r in skipped if r.get("unlock")})
    lines = [_L(f"做成了 {len(done)} 步", f"Done: {len(done)} step(s)")]
    lines += [f"  - {r['app']} {r['step']}({r.get('route')})" for r in done[-20:]]
    lines.append(_L(f"跳过了 {len(skipped) + len(skips)} 步", f"Skipped: {len(skipped) + len(skips)} step(s)"))
    lines += [f"  - {r['app']} {r['step']}" + _L(":", ": ") + f"{r.get('reason') or r.get('outcome')}" for r in skipped + skips]
    if stucks:
        lines.append(_L(f"卡住停下 {len(stucks)} 次", f"Stopped when stuck: {len(stucks)} time(s)"))
        lines += [f"  - {r['app']} {r['step']}" + _L(f":{r.get('reason')};怎么办:{r.get('todo')}",
                                                     f": {r.get('reason')}; what to do: {r.get('todo')}") for r in stucks]
    if unlock:
        lines.append(_L("开这些能多做:", "Turn these on to do more:"))
        lines += [f"  - {u}" for u in unlock]
    return "\n".join(lines)


def _expired_notice():
    log("expired")
    if sys.platform == "win32":          # 11-14:Windows 上 seeu_lib.cursor_overlay 用不了,用 SeeU 自己的提示条
        try:
            from seeu.win import cursor
            from seeu.i18n import lang
            en = lang() == "en"
            cursor.toast("SeeU · I See expired and turned off" if en else "SeeU · I See 已到期关闭",
                         "I See mode is off again; SeeU will ask before switching routes." if en else
                         "I See 已关,SeeU 遇到卡点会先停下问你", 8)
        except Exception:
            pass
        return
    try:
        import subprocess
        subprocess.Popen([sys.executable, "-m", "seeu_lib.cursor_overlay", "toast", "SeeU · I See 已到期关闭",
                          "Safari / Chrome 的「允许来自 Apple 事件的 JavaScript」还开着的话,不用了记得关", "8"],
                         cwd=os.path.dirname(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


AI_PROCS = ("claude", "codex", "cursor", "trae", "windsurf", "gemini", "workbuddy", "doubao", "copilot", "aider", "opencode")


def from_ai():
    """11-02:这条命令是不是 AI 客户端在跑(父进程链里有 AI 客户端,或 Claude Code 的环境变量)。"""
    if os.environ.get("CLAUDECODE") or os.environ.get("CODEX_SANDBOX") or os.environ.get("CURSOR_TRACE_ID"):
        return True
    import subprocess
    pid = os.getppid()
    for _ in range(20):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception:
            return False
        if not out:
            return False
        ppid, comm = out.split(None, 1)
        name = comm.lower()
        if any(k in os.path.basename(name) or f"/{k}" in name for k in AI_PROCS) or "visual studio code" in name:
            return True
        if ppid in ("0", "1"):
            return False
        pid = int(ppid)
    return False


def from_overlay(port=None):
    """11-06 C-1.1.3:这条命令是不是悬浮窗进程亲自拉起的(= 用户点了悬浮窗 / 岛上的 I See 按钮)。
    认法:**直接**父进程是 watch_window serve,而且正占着悬浮窗的端口;隔一层(祖父进程)不算。
    原因:悬浮窗常由 AI 客户端里的 SeeU 服务拉起,父进程链上有客户端 → from_ai() 为真 → 按钮一直开不了
    (v1.1.0 加 from_ai 后没测过按钮,11-06 用真实进程链核对出来)。读不到、超时一律当「不是」。"""
    import subprocess
    if port is None:
        try:
            from seeu_lib import watch_window as ww
            port = ww.PORT
        except Exception:
            port = 47833
    ppid = os.getppid()
    if ppid <= 1:
        return False
    try:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(ppid)], capture_output=True, text=True, timeout=3).stdout
        if "watch_window" not in cmd or "serve" not in cmd.split():
            return False
        r = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(ppid), f"-iUDP:{int(port)}"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and f":{int(port)}" in r.stdout
    except Exception:
        return False


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "on" and not from_overlay() and from_ai():
        from seeu.i18n import lang
        print("Only you can turn on I See: click the I See button on the SeeU overlay (or run this in the macOS Terminal app). "
              "The AI can't turn it on for you." if lang() == "en" else
              "I See 只能你自己开:点 SeeU 悬浮窗上的「I See」按钮(或在系统自带的「终端」里运行这条命令)。AI 不能替你开。")
        sys.exit(3)
    if cmd == "on":
        hours = argv[1] if len(argv) > 1 else DEFAULT_HOURS
        if not hours_ok(hours):        # 11-16:原来 `isee on abc` 直接崩、负数开出已过期的
            print(_L("用法:python3 -m seeu isee on [小时](0 = 不自动关;最短 1 分钟,最长一年)",
                     "Usage: python3 -m seeu isee on [hours] (0 = never turns off by itself; 1 minute to 1 year)"), file=sys.stderr)
            sys.exit(2)
        try:
            res = on(hours)
        except (PermissionError, RuntimeError) as ex:
            print(str(ex), file=sys.stderr)
            sys.exit(3 if isinstance(ex, PermissionError) else 1)
        st = status()
        print(_L("I See 开了", "I See is on") + (_L(f",到 {st['until']} 自动关", f", turns off at {st['until']}") if st.get("until")
                                               else _L("(不自动关)", " (won't turn off by itself)")))
        for k, v in res.items():
            print(f"  {k}" + _L(":", ": ") + f"{v}")
    elif cmd == "off":
        try:
            off()
        except RuntimeError as ex:
            print(str(ex), file=sys.stderr)
            sys.exit(1)
        print(_L("I See 关了", "I See is off"))
    elif cmd == "report":
        print(report())
    elif cmd == "status":
        st = status()
        src = _L("环境变量 SEEU_ISEE", "the SEEU_ISEE environment variable") if st["source"] == "环境变量" else _L("设置文件", "settings file")
        print(_L("开着" if st["on"] else "关着", "on" if st["on"] else "off")
              + (_L(f",到 {st['until']}", f", until {st['until']}") if st["on"] and st.get("until") else "")
              + _L(f"(来源:{src})", f" (from {src})")
              + (_L(";设置里写着开,但不是你用按钮 / 终端开的(或是升级前开的),按关算;要用请重新开一次",
                    "; the settings file says on, but it wasn't turned on with the button / terminal (or was turned on before an "
                    "update), so it counts as off; turn it on again if you need it")
                 if st.get("forged") else ""))
    else:
        print(_L("用法:python3 -m seeu isee on [小时] | off | status | report",
                 "Usage: python3 -m seeu isee on [hours] | off | status | report"), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
