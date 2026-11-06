"""SeeU · I See 模式(我知风险)(SeeU C-0.1,10-20 用户定)

看过 README「I See 模式」一节 = 知道风险;开了以后 SeeU 中途不提示、不停,自动换路直到做成,最后出报告。
放开的:SeeU 自己的允许名单不查(开关这条路)、插件没允许的网站自动换开关/辅助功能、失败自动换下一条路。
拿不掉的:用户亲手在用键鼠时让路;密码框/新密码框/验证码框/银行卡框不碰(代码层);付款、转账这类(调用方 AI 自己的规矩)——
  这些不中途停,记成「跳过」,报告里统一列。

开法(三种,任选):
  设置文件 seeu/设置.json 里 "I See" 写 "开"(底层存储;11-02 起只让用户自己开(悬浮窗 I See 按钮),AI 只能关)
  命令:python3 -m seeu isee on [小时]   /  off  /  status  /  report
  定时任务:环境变量 SEEU_ISEE=1(只管这一个进程,优先于设置文件;=0 强制关)
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
SETTINGS = os.path.join(HERE, "设置.json")
LOG = home("seeu_isee.log")
KEY, KEY_UNTIL = "I See", "I See 到期"
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
    "accessibility": ("给辅助功能授权", "系统设置 → 隐私与安全性 → 辅助功能 → 打开运行 SeeU 的程序(终端 / Claude)", _PANE + "Privacy_Accessibility"),
    "screen": ("给屏幕录制授权", "系统设置 → 隐私与安全性 → 屏幕与系统录音 → 打开运行 SeeU 的程序", _PANE + "Privacy_ScreenCapture"),
    "automation": ("允许控制这个 App", "系统设置 → 隐私与安全性 → 自动化 → 在运行 SeeU 的程序下面勾上要控制的 App(Safari / Chrome / 备忘录…,每个 App 单独一项)", _PANE + "Privacy_Automation"),
}


def _load(strict=False):
    """读 设置.json。strict=True(要改完写回去的地方用):文件在但读不出来就报错。
    11-06 体检:原来读坏了返回 {},on / off 接着把只剩一个键的内容整份写回,署名、颜色、借用鼠标等全丢。"""
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as ex:
        if strict:
            raise RuntimeError(f"设置.json 读不出来(格式坏了:{ex}),没改;先把这个文件修好")
        return {}


def _save(d):
    tmp = SETTINGS + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def status():
    """{on, source(环境变量/设置文件), until(到期时间文字或 None)}。过期的顺手关掉并提醒一次。"""
    env = os.environ.get("SEEU_ISEE", "").strip().lower()
    if env in ("1", "on", "开", "true"):
        return dict(on=True, source="环境变量", until=None)
    if env in ("0", "off", "关", "false"):
        return dict(on=False, source="环境变量", until=None)
    d = _load()
    if str(d.get(KEY, "关")) not in ("开", "on", "1", "true"):
        return dict(on=False, source="设置文件", until=None)
    until = d.get(KEY_UNTIL)
    try:
        expired = until and time.time() > time.mktime(time.strptime(until, FMT))
    except ValueError:
        expired = False
    if expired:
        d[KEY] = "关"
        _save(d)
        _expired_notice()
        return dict(on=False, source="设置文件", until=until, expired=True)
    return dict(on=True, source="设置文件", until=until)


def active():
    try:
        return status()["on"]
    except Exception:
        return False


def on(hours=DEFAULT_HOURS):
    """开 I See,hours 小时后自动失效(0 = 不失效)。顺带做一次体检,返回体检结果。"""
    d = _load(strict=True)
    d[KEY] = "开"
    d[KEY_UNTIL] = time.strftime(FMT, time.localtime(time.time() + hours * 3600)) if hours else None
    _save(d)
    log("on", hours=hours)
    try:
        os.remove(LIVE)          # 新一轮从 0 计
    except OSError:
        pass
    return checkup()


def off():
    d = _load(strict=True)
    d[KEY] = "关"
    d.pop(KEY_UNTIL, None)
    _save(d)
    log("off")


def checkup():
    """开启时体检:开着的浏览器逐个试一下开关(第一次会弹系统授权框,集中在这时弹掉,跑起来就不再弹)。
    没开的浏览器不碰(不会替你打开)。返回 {浏览器: 状态说明}。"""
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
    lines = [f"做成了 {len(done)} 步"]
    lines += [f"  - {r['app']} {r['step']}({r.get('route')})" for r in done[-20:]]
    lines.append(f"跳过了 {len(skipped) + len(skips)} 步")
    lines += [f"  - {r['app']} {r['step']}:{r.get('reason') or r.get('outcome')}" for r in skipped + skips]
    if stucks:
        lines.append(f"卡住停下 {len(stucks)} 次")
        lines += [f"  - {r['app']} {r['step']}:{r.get('reason')};怎么办:{r.get('todo')}" for r in stucks]
    if unlock:
        lines.append("开这些能多做:")
        lines += [f"  - {u}" for u in unlock]
    return "\n".join(lines)


def _expired_notice():
    log("expired")
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
        hours = float(argv[1]) if len(argv) > 1 else DEFAULT_HOURS
        res = on(hours)
        st = status()
        print(f"I See 开了" + (f",到 {st['until']} 自动关" if st.get("until") else "(不自动关)"))
        for k, v in res.items():
            print(f"  {k}:{v}")
    elif cmd == "off":
        off()
        print("I See 关了")
    elif cmd == "report":
        print(report())
    else:
        st = status()
        print(("开着" if st["on"] else "关着") + f"(来源:{st['source']}" + (f",到 {st['until']}" if st.get("until") else "") + ")")


if __name__ == "__main__":
    main(sys.argv[1:])
