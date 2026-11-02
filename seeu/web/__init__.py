"""SeeU · 浏览器模块(C-1.4 起,SeeU C-0.1 10-20 改成「本地优先」)

四块之一(Mac 原生 App / **Mac 浏览器** / iPhone 镜像 / 以上都不是)。不用登录、SeeU 不联网;四条路(10-20 用户定,C-1.0 加调试端口):
  调试端口(SeeU 专用那份)   隐身 Chrome、cdp.launch 拉起的网页壳 App(VS Code…)在跑就排第一,全程藏着读写(见 seeu/cdp.py);
                            用户自己开着的那份接不上、不碰。浏览器照样守允许名单(I See 下不查)
  插件(Chrome 内核,可选)   装了就优先;没允许的网站 → refused 提示去允许(🔴 不退回)
                            C-0.5 起名单跟开关合成一份(allow.json),插件 = Chrome 授权 且 在名单里才碰
                            ——I See 模式下改成换下一条路;Chrome 不许插件碰的页面(应用商店等)→ 换下一条路并带 note
  开关(Safari / Chrome 内核) 浏览器的「允许来自 Apple 事件的 JavaScript」开着就用,见 aejs.py;
                            开关没有网站范围,SeeU 自守允许名单(没允许的网站这条路不用,I See 下不查)
  辅助功能(所有浏览器打底)  只能看/点/打当前显示的标签页;选下拉框、后台标签页做不了
不再主动建议装插件/换浏览器:只有这一步真做不了时,reason 的「怎么办」和结果里的 unlock 说开什么能做。
失败的 reason 一律三段:「卡在:哪一步。原因:为什么。怎么办:……」,给调用 SeeU 的 AI 照着转述。
密码框/银行卡框不碰、不替调用方提交表单(两条网页脚本路一样);C-0.5 起验证码框、新密码框也不碰(三条路一样)。插件隐私说明见 extension/privacy.html。

用法(seeu.see / seeu.tap 等遇到浏览器会自动转到这里,也可以直接用):
    from seeu import web
    r = web.see("Safari")                     # 当前标签页:编号清单 + 整页文字
    print(web.describe(r["items"]))
    web.type("Safari", 3, "张三")              # 按编号打字(也可以写控件名字)
    web.tap("Google Chrome", "Medium")         # 按名字点
    web.tabs("Safari"); web.open("Safari", "https://example.com")   # 后台开标签页
    web.see("Safari", tab="1234:2")            # 不切过去读后台标签页(插件 / 开关才行;编号从 tabs() 拿)
每个动作返回 dict(outcome=delivered|unverified|ineffective|refused|failed, route=调试端口|插件|开关|辅助功能, reason=…,
    做不到时还有 unlock=开什么能做)。I See 模式见 seeu/isee.py。
"""
import builtins
import json
import os
import socket
import time

from seeu import isee
from seeu.web import aejs

DIR = os.path.expanduser("~/.seeu/seeu_web")   # 不跟 SEEU_HOME:中转程序是浏览器拉起的,读不到用户的环境变量,三处要对得上就都写死(11-01)
CHROMIUM = {"Google Chrome": "chrome", "Chrome": "chrome", "Microsoft Edge": "edge", "Brave Browser": "brave",
            "Arc": "arc", "Chromium": "chromium", "Vivaldi": "vivaldi"}
OTHERS = {"Safari", "Safari Technology Preview", "Firefox", "Orion"}
APP_NAME = {"Chrome": "Google Chrome"}
PRIVACY = "插件不联网,只和本机 SeeU 通信,只碰你允许过的网站,代码公开"
SUGGEST = "辅助功能做不到这一步。"      # 老名字留着(外面可能引用);怎么办见 unlock()
PLUGIN_GAIN = "能读后台标签页、选网页下拉框、填新式网页表单"
BLOCKED_NOTE = "这一页 Chrome 不许任何插件碰(应用商店、Chrome 设置页等),已换别的路继续"
FREE_NOTE = "I See:插件没允许这个网站,已换别的路继续"
STEP = {"see": "读网页", "read": "读网页", "tap": "点击", "type": "打字", "check": "勾选", "select": "选下拉框",
        "scroll": "滚动", "open": "开标签页", "tabs": "列标签页"}
_last = {}          # app -> {"route", "items", "tab"}
_step = {}          # app -> 正在做的动作(悬浮标卡片上显示)


class WebError(RuntimeError):
    def __init__(self, msg, code="error"):
        super().__init__(msg)
        self.code = code


def _name(app):
    return APP_NAME.get(app, app)


def is_browser(app):
    return _name(app) in CHROMIUM or _name(app) in OTHERS


def _cdp(app):
    """SeeU 专用那份(调试端口)在跑 → cdp.Handle,否则 None。"""
    try:
        from seeu import cdp
        return cdp.running(_name(app))
    except Exception:
        return None


def is_cdp(app):
    """这个 App 有 SeeU 专用那份在跑(网页壳 App 也算):seeu.act 遇到就转到这里。"""
    return _cdp(app) is not None


def _cd_tab(tab):
    return tab is None or (isinstance(tab, str) and ":" not in tab)


def _cd_see(app, h, tab, max_items, free):
    from seeu import cdp
    p = cdp.find_page(h, tab)
    if _name(app) in CHROMIUM and not (free or aejs.is_allowed(p.get("url"))):
        raise WebError(f"这个网站({aejs.origin(p.get('url')) or p.get('url')})不在 SeeU 允许名单里,调试端口那条路不碰",
                       "not_allowed_ae")
    r = cdp.page_fn(h, "pageSnapshot", [max_items, 20000], p["id"])
    return dict(route="调试端口", items=_items(r), text=r["text"], url=r["url"], title=r["title"],
                tab=dict(id=p["id"], title=p.get("title", ""), url=p.get("url", ""), active=tab is None))


def _page(app, route, fn, args, tid):
    """开关 / 调试端口两条路跑网页函数(同一份 pageSnapshot/pageAct/pageRead)。"""
    if route == "调试端口":
        from seeu import cdp
        h = _cdp(app)
        if not h:
            raise WebError("SeeU 专用那份已经关了", "no_app")
        return cdp.page_fn(h, fn, args, tid)
    return aejs.page(_name(app), fn, args, tid)


def _loaded(app, route, tid, timeout=10.0):
    if route == "调试端口":
        from seeu import cdp
        h = _cdp(app)
        return bool(h) and cdp.wait_loaded(h, tid, timeout)
    return aejs.wait_loaded(_name(app), tid, timeout)


def plugin_ready(app):
    """插件 + 中转程序都在线就返回状态 dict,否则 None。"""
    key = CHROMIUM.get(_name(app))
    if not key:
        return None
    sock, st = os.path.join(DIR, key + ".sock"), os.path.join(DIR, key + ".json")
    if not os.path.exists(sock):
        return None
    try:
        info = json.load(builtins.open(st))   # 本模块有自己的 open(开标签页),这里要内置的
        os.kill(int(info["pid"]), 0)
    except Exception:
        return None
    return info


def call(app, cmd, timeout=30, **args):
    key = CHROMIUM.get(_name(app))
    if not key:
        raise WebError(f"{app} 不支持插件", "no_plugin")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout + 5)
    try:
        s.connect(os.path.join(DIR, key + ".sock"))
    except OSError:
        raise WebError("插件没连上(浏览器没开,或插件/中转程序没装)", "no_plugin")
    try:
        s.sendall((json.dumps({"cmd": cmd, "args": args, "timeout": timeout}, ensure_ascii=False) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    rep = json.loads(buf.decode() or "{}")
    if not rep.get("ok"):
        raise WebError(rep.get("error") or "插件没回话", rep.get("code") or "error")
    return rep.get("result")


# ---------------------------------------------------------------- 建议装插件(一天一次;用户说不装就只在真做不了时提)

def _sugg_state():
    try:
        return json.load(builtins.open(os.path.join(DIR, "suggest.json")))
    except Exception:
        return {}


def _sugg_save(st):
    os.makedirs(DIR, exist_ok=True)
    with builtins.open(os.path.join(DIR, "suggest.json"), "w") as f:
        json.dump(st, f, ensure_ascii=False)


def decline_plugin(app, on=True):
    """用户说「不装插件」:以后不再主动推荐,只在后台模式真做不了时提。on=False 撤销。"""
    st = _sugg_state()
    st.setdefault(_name(app), {})["declined"] = bool(on)
    _sugg_save(st)


def suggestion(app, hard=False):
    """老接口(10-20 前一天一次建议装插件)。现在不主动建议:hard=False 恒为 None;hard=True = unlock(app)。"""
    return unlock(app) if hard else None


def allow_how(o):
    """不在允许名单时怎么办(11-02 用户定:先让 AI 在聊天里问、答应了 AI 自己加;终端命令放后面当后备)。
    MCP 按里面的「seeu allow 网址」认出网站,提示 AI 去问用户。"""
    return f"把这个网站加进 SeeU 允许名单(AI 问你时答应就行;也可以终端 python3 -m seeu allow {o or '网址'})"


def unlock(app, url=None):
    """这一步辅助功能做不到时,开什么能做。返回一句话;Firefox 这类没有增强路的照实说。"""
    n = _name(app)
    if n in aejs.SAFARI:
        st = aejs.state(n)
        if st == "on":
            if url and not aejs.is_allowed(url) and not isee.active():
                return allow_how(aejs.origin(url)) + ",或开 I See 模式"
            return None
        if st == "denied":
            return "系统设置 → 隐私与安全性 → 自动化 里允许控制 Safari"
        return "打开 Safari 开关:" + aejs.howto(n)
    if n in CHROMIUM:
        parts = []
        if not plugin_ready(app):
            parts.append(f"装 SeeU 插件({PRIVACY};跟 AI 说一声它来装,也可以终端 python3 -m seeu.web.install)")
        if aejs.supported(n) and aejs.state(n) != "on":
            parts.append("或打开 Chrome 开关:" + aejs.howto(n))
        elif aejs.supported(n) and url and not aejs.is_allowed(url) and not isee.active():
            parts.append("或" + allow_how(aejs.origin(url)))
        return ";".join(parts) or None
    return f"{n} 只能走辅助功能;换 Safari 或 Chrome 打开这个网页能做"


def _explain(ex, step, app):
    """失败说清三件事:卡在哪一步、为什么、怎么办。"""
    code = getattr(ex, "code", "error")
    todo = {
        "not_allowed": f"在这个网页上点浏览器右上角的 SeeU 图标,选「允许这个网站」({PRIVACY}),或开 I See 模式"
                       "(用命令加进名单的网站,Chrome 也要在这里点一次才放行)",
        "blocked_page": "把这个标签页切到前面,SeeU 会改用辅助功能读",
        "not_found": "先 see 看看页面上现在有什么,换个名字或编号",
        "stale": "页面变了,重新 see 一次再按新编号操作",
        "refused": "这一步请你自己来",
        "timeout": "等页面加载完再试,或者网速慢多等一会",
        "no_app": "先打开这个浏览器",
        "busy": "等那个任务做完再来,或者你自己点",
    }.get(code)
    if todo is None and code == "not_allowed_ae" and _cdp(app):     # SeeU 专用那份(调试端口):只差名单
        import re as _re
        o = _re.search(r"((?:https?|file)://[^)\s)]*)", str(ex))
        todo = allow_how(o.group(1) if o else None) + ",或开 I See 模式"
    if todo is None:     # 读不到 / 做不到 / 不支持:说开什么能做;都不行就只能人来
        u = unlock(app, ((_last.get(app) or {}).get("url")))
        if u:
            todo = u + "。都不开的话,这一步只能你自己来。"
        elif (_last.get(app) or {}).get("note"):
            todo = "Chrome 不许插件碰这一页,别的路也做不到,这一步只能你自己点。"
        else:
            todo = "这一步 SeeU 做不了,只能你自己点。"
    why = {"not_allowed": "这个网站还没在 SeeU 插件的允许名单里"}.get(code) or str(ex).split("。建议换成")[0].rstrip("。")
    return f"卡在:{step}。原因:{why}。怎么办:{todo}"


# ---------------------------------------------------------------- 看

def _items(r):
    items = []
    for it in r["items"]:
        d = dict(id=it["i"] + 1, role=it["role"], text=it.get("name", ""), rect=it["rect"], inView=it["inView"])
        for k in ("value", "checked", "disabled", "href", "options", "secret", "hint"):
            if k in it:
                d[k] = it[k]
        items.append(d)
    return items


def _ae_tab(tab):
    return isinstance(tab, str) and ":" in tab


def _ae_on(app):
    n = _name(app)
    return aejs.supported(n) and aejs.state(n) == "on"


def see(app, tab=None, max_items=400):
    """读网页:返回 {route, items, text, url, title, tab}。items 每项:id、role、text(名字)、value、checked…
    挑路:插件 → 开关 → 辅助功能(见模块说明)。tab:插件给整数 id,开关给 "窗口id:标签"(都从 tabs() 拿)。"""
    free = isee.active()
    if not _step.get(app):
        _watch(app, "读网页")
    out, note = None, None
    h = _cdp(app)
    if h and _cd_tab(tab):
        try:
            out = _cd_see(app, h, tab, max_items, free)
        except WebError as ex:
            if tab is not None or ex.code in ("refused", "called_out"):
                raise WebError(str(ex) if str(ex).startswith("卡在:") else _explain(ex, "读网页", app), ex.code)
            note = (f"{ex},改用别的路" if ex.code == "not_allowed_ae" else f"调试端口那条路没走通({ex}),改用别的路")
    if out is None and plugin_ready(app) and not _ae_tab(tab) and not (h and tab is not None):
        try:
            r = call(app, "snapshot", tab=tab, max=max_items)
            out = dict(route="插件", items=_items(r), text=r["text"], url=r["url"], title=r["title"], tab=r["tab"])
        except WebError as ex:
            # Chrome 不许任何插件碰的页面(应用商店、chrome:// 设置页等,10-20 实测应用商店)→ 换下一条路
            blocked = "cannot be scripted" in str(ex) or "Cannot access" in str(ex)
            if not blocked and not (free and ex.code == "not_allowed"):
                raise WebError(_explain(ex, "读网页", app), ex.code)
            if tab is not None and not _is_active(app, tab):
                raise WebError("这一页插件碰不了,后台标签页别的路又读不了(插件的标签编号换不过去)。"
                               "先用 tabs() 拿开关那条路的编号再读", "blocked_page")
            note = BLOCKED_NOTE if blocked else FREE_NOTE
            tab = None
    n = _name(app)
    if out is None and (tab is None or _ae_tab(tab)) and _ae_on(app):
        try:
            t = aejs.find_tab(n, tab)
            if free or aejs.is_allowed(t["url"]):
                r = aejs.page(n, "pageSnapshot", [max_items, 20000], t["id"])
                out = dict(route="开关", items=_items(r), text=r["text"], url=r["url"], title=r["title"],
                           tab=dict(id=t["id"], title=t["title"], url=t["url"], active=t["active"]))
            elif tab is None:
                o = aejs.origin(t["url"])
                note = (note + ";" if note else "") + (
                    f"这个网站({o})不在 SeeU 允许名单里,开关那条路没用,改用辅助功能(要用开关:{allow_how(o)})"
                    if o else f"当前标签是浏览器自己的页面({t['url']},如起始页),开关那条路不读")
            else:
                ex = WebError(f"这个网站({aejs.origin(t['url'])})不在 SeeU 允许名单里,开关那条路不碰", "not_allowed_ae")
                raise WebError(_explain(ex, "读网页", app), ex.code)
        except aejs.AEError as ex:
            if tab is not None:
                raise WebError(_explain(WebError(str(ex), ex.code), "读网页", app), ex.code)
            note = (note + ";" if note else "") + f"开关那条路没走通({ex}),改用辅助功能"
    if out is None:
        if tab is not None:
            raise WebError(_explain(WebError("辅助功能只能读当前显示的标签页", "unsupported"), "读网页", app), "unsupported")
        try:
            out = _ax_see(app)
        except WebError as ex:
            # 10-30:前面几条路为什么没走通也带上(实测 open 开在后台标签、当前页是起始页 → 只报"读不到网页结构",看不出原因)
            msg = _explain(ex, "读网页", app) + (f"(前面:{note})" if note else "")
            raise WebError(msg + "。要读后台标签:see(App, tab=open() 返回的 id)", ex.code)
    if note:
        out["note"] = note
    _last[app] = out
    return out


def _is_active(app, tab):
    try:
        return any(t["id"] == tab and t["active"] for t in call(app, "tabs")["tabs"])
    except WebError:
        return False


def _secret_name(it):
    """secret 老版本是 True(只有密码框/银行卡框),C-0.5 起是框的种类(密码框/新密码框/验证码框/银行卡框)。"""
    k = it.get("secret")
    return k if isinstance(k, str) else "密码框/银行卡框"


def describe(items):
    lines = []
    for it in items:
        extra = ""
        if it.get("secret"):
            extra = f" [{_secret_name(it)},不碰]"
        elif it.get("checked") is not None:
            extra = " [✓]" if it["checked"] else " [ ]"
        elif it.get("value"):
            extra = f" = {it['value'][:30]!r}"
        elif it.get("hint"):
            extra = f" (提示:{it['hint'][:20]})"
        lines.append(f"{it['id']:>3}. {it['role']:<14} {it['text'][:50]}{extra}")
    return "\n".join(lines)


def read(app, tab=None):
    """整页文字(比价、看文案用)。tab 是开关那条路的编号("窗口:序号")就不走插件(C-0.5 实测修)。"""
    if _cdp(app):
        return {k: v for k, v in see(app, tab=tab).items() if k in ("text", "url", "title")}
    if plugin_ready(app) and not _ae_tab(tab):
        try:
            return call(app, "read", tab=tab)
        except WebError as ex:
            if "cannot be scripted" not in str(ex) and "Cannot access" not in str(ex):
                raise
    return {k: v for k, v in see(app, tab=tab).items() if k in ("text", "url", "title")}


def _pick(app, target, tab):
    """target(编号 / 名字)→ 清单里的那一项。名字先全等再包含。"""
    cur = _last.get(app)
    if cur is None or (tab is not None and (cur.get("tab") or {}).get("id") != tab) or not isinstance(target, int):
        cur = see(app, tab=tab)
    items = cur["items"]
    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
        it = next((i for i in items if i["id"] == int(target)), None)
        if not it:
            raise WebError(f"没有编号 {target},先 see 一次", "not_found")
        return cur, it
    t = str(target)
    hits = ([i for i in items if i["text"] == t] or [i for i in items if t in i["text"]] or
            [i for i in items if t in (i.get("hint") or "")])          # 输入框里的灰色提示字也能找
    if not hits:
        raise WebError(f"页面上没找到「{t}」", "not_found")
    return cur, hits[0]


def _result(route, outcome, reason=None, **kw):
    d = dict(outcome=outcome, route=route)
    if reason:
        d["reason"] = reason
    d.update(kw)
    return d


def _watch(app, step):
    """浏览器操作时弹监看悬浮标(10-20 用户定;后台标签页没画面,只写这一步)。规矩同 act._watch:
    设置.json「监看小窗」= 关 / SEEU_NO_WATCH=1 就不弹。异常吞掉,不影响操作。"""
    if os.environ.get("SEEU_NO_WATCH"):
        return
    try:
        cfg = json.load(builtins.open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "设置.json"), encoding="utf-8"))
        if str(cfg.get("监看小窗", "开")).strip() in ("关", "off"):
            return
        from seeu_lib import watch_window as ww
        fn = getattr(ww, "browser", None)          # 长进程里可能是旧版 watch_window
        if fn:
            fn(_name(app), step)
        from seeu import act                        # 10-21:屏幕光圈(被控提示开着才亮,规则同 act)
        act._halo("bg")
    except Exception:
        pass


def _stuck(app, step, r):
    """普通模式卡住:悬浮卡片自动展开说清楚(10-20 用户定)。I See 能解决的(允许名单 / 插件没允许)提示开 I See、按钮闪;
    解决不了的照实写该开什么。密码框这类底线不算卡住,不弹。"""
    reason = r.get("reason") or ""
    if "SeeU 不碰" in reason or os.environ.get("SEEU_NO_WATCH"):
        return
    why = reason.split("原因:", 1)[-1].split("。怎么办:")[0] if "原因:" in reason else reason
    todo = reason.split("怎么办:", 1)[-1] if "怎么办:" in reason else (r.get("unlock") or "这一步你自己来")
    helps = r.get("code") in ("not_allowed", "not_allowed_ae") or "I See" in (r.get("unlock") or "")
    if r.get("code") == "not_allowed_ae":     # 11-02:加名单比开 I See 安全,先说这个
        todo = "回对话里答应 AI 把这个网站加进名单;或点上面的「I See」"
    elif r.get("code") == "not_allowed":
        todo = "在网页上点 SeeU 图标「允许这个网站」;或点上面的「I See」"
    elif helps:
        todo = "点上面的「I See」,开了会自动换别的路再试"
    try:
        from seeu_lib import watch_window as ww
        fn = getattr(ww, "stuck", None)
        if fn:
            fn(_name(app), step, why[:120], todo[:160], helps)
    except Exception:
        pass


def _guard(fn):
    """把 WebError / AEError 变成 SeeU 统一的结果(refused / failed),不往外抛。
    I See 开着:页面变了(编号失效)自动重看一次再做;每步记日志(打的字只记长度),供 isee.report() 出报告。"""
    def wrap(app, *a, **kw):
        step = STEP.get(fn.__name__, fn.__name__)
        _watch(app, step)
        _step[app] = step                   # 动作里顺带读页面时,悬浮标上别被「读网页」盖掉(10-20 用户实测看到)
        tries = isee.MAX_TRIES if isee.active() else 1      # I See:页面变了最多重看几次(10-24 定上限 3)
        for k in range(tries):
            try:
                r = fn(app, *a, **kw)
            except (WebError, aejs.AEError) as ex:
                if k + 1 < tries and getattr(ex, "code", "") in ("stale", "script"):
                    _last.pop(app, None)
                    time.sleep(0.5)
                    continue
                cur = _last.get(app) or {}
                route = cur.get("route") or ("插件" if plugin_ready(app) else "辅助功能")
                code = getattr(ex, "code", "error")
                out = "refused" if code in ("refused", "not_allowed", "not_allowed_ae", "called_out") else "failed"
                reason = str(ex) if str(ex).startswith("卡在:") else _explain(WebError(str(ex), code), step, app)
                r = _result(route, out, reason, code=code)
            break
        _step.pop(app, None)
        if r.get("outcome") == "ineffective" and r.get("route") == "辅助功能":
            r["reason"] = _explain(WebError(r.get("reason") or "操作没生效", "ineffective"), step, app)
        if r.get("outcome") not in ("delivered", "unverified") and "unlock" not in r:
            try:
                u = unlock(app, (_last.get(app) or {}).get("url"))
            except Exception:
                u = None
            if u:
                r["unlock"] = u
        note = (_last.get(app) or {}).get("note")
        if note and "note" not in r:
            r["note"] = note
        isee.record(_name(app), step, r)
        if r.get("outcome") in ("failed", "refused", "ineffective") and not isee.active():
            _stuck(app, step, r)
        return r
    wrap.__name__, wrap.__doc__ = fn.__name__, fn.__doc__
    return wrap


def _ae_act(app, cur, it, action, value=None, mode="replace"):
    """开关 / 调试端口两条路的 pageAct(按这一页实际走的路)。"""
    return _page(app, cur["route"], "pageAct", [it["id"] - 1 if it else -1, action, value, mode], cur["tab"]["id"])


# ---------------------------------------------------------------- 动作

@_guard
def tap(app, target, tab=None):
    cur, it = _pick(app, target, tab)
    if cur["route"] == "插件":
        tid = cur["tab"]["id"]
        before = call(app, "read", tab=tid, max=20000)
        st = call(app, "act", tab=tid, i=it["id"] - 1, action="click")
        if it.get("checked") is not None:
            ok = st.get("checked") != it["checked"] or it["role"] == "input:radio" and st.get("checked")
            return _result("插件", "delivered" if ok else "ineffective", None if ok else "点了但勾选状态没变", state=st)
        time.sleep(0.6)
        try:
            after = call(app, "read", tab=tid, max=20000)
        except WebError:
            after = {}
        changed = after.get("url") != before.get("url") or after.get("text") != before.get("text")
        return _result("插件", "delivered" if changed else "unverified",
                       None if changed else "点了,页面文字没变化(有的按钮本来就不变,没法核实)", state=st)
    if cur["route"] in ("开关", "调试端口"):
        rt, tid = cur["route"], cur["tab"]["id"]
        before = _page(app, rt, "pageRead", [20000], tid)
        st = _ae_act(app, cur, it, "click")
        _last.pop(app, None)
        if it.get("checked") is not None:
            ok = st.get("checked") != it["checked"] or it["role"] == "input:radio" and st.get("checked")
            return _result(rt, "delivered" if ok else "ineffective", None if ok else "点了但勾选状态没变", state=st)
        time.sleep(0.6)
        _loaded(app, rt, tid)               # 点完可能跳页:等加载完(有上限)
        try:
            after = _page(app, rt, "pageRead", [20000], tid)
        except (aejs.AEError, WebError):
            after = {}
        changed = after.get("url") != before.get("url") or after.get("text") != before.get("text")
        return _result(rt, "delivered" if changed else "unverified",
                       None if changed else "点了,页面文字没变化(有的按钮本来就不变,没法核实)", state=st)
    return _ax_tap(app, it)


@_guard
def check(app, target, on=True, tab=None):
    cur, it = _pick(app, target, tab)
    if cur["route"] == "插件":
        st = call(app, "act", tab=cur["tab"]["id"], i=it["id"] - 1, action="check", value=bool(on))
        ok = st.get("checked") == bool(on)
        return _result("插件", "delivered" if ok else "ineffective", None if ok else "勾选状态没变成想要的", state=st)
    if cur["route"] in ("开关", "调试端口"):
        st = _ae_act(app, cur, it, "check", bool(on))
        _last.pop(app, None)
        ok = st.get("checked") == bool(on)
        return _result(cur["route"], "delivered" if ok else "ineffective", None if ok else "勾选状态没变成想要的", state=st)
    if it.get("checked") == bool(on):
        return _result("辅助功能", "delivered", state={"checked": on})
    return _ax_tap(app, it)


@_guard
def type(app, target, text, mode="replace", tab=None):
    """往输入框打字。mode=replace 清空再写 / append 接在后面。不按回车、不提交。"""
    from seeu import safety
    try:
        safety.check_text(text)
    except safety.Refused as ex:
        return _result(None, "refused", str(ex))
    cur, it = _pick(app, target, tab)
    if it.get("secret"):
        return _result(cur["route"], "refused", f"{_secret_name(it)},SeeU 不碰")
    if cur["route"] == "插件":
        st = call(app, "act", tab=cur["tab"]["id"], i=it["id"] - 1, action="type", value=str(text), mode=mode)
        ok = str(text) in (st.get("value") or "")
        return _result("插件", "delivered" if ok else "ineffective",
                       None if ok else "写完读回没看到这段字", state=st)
    if cur["route"] in ("开关", "调试端口"):
        st = _ae_act(app, cur, it, "type", str(text), mode)
        ok = str(text) in (st.get("value") or "")
        return _result(cur["route"], "delivered" if ok else "ineffective",
                       None if ok else "写完读回没看到这段字", state=st)
    return _ax_type(app, it, str(text), mode)


@_guard
def select(app, target, option, tab=None):
    cur, it = _pick(app, target, tab)
    if cur["route"] in ("开关", "调试端口"):
        st = _ae_act(app, cur, it, "select", str(option))
        return _result(cur["route"], "delivered", state=st)
    if cur["route"] != "插件":
        raise WebError("辅助功能选不了网页下拉框(会弹出菜单抢前台)", "unsupported")
    st = call(app, "act", tab=cur["tab"]["id"], i=it["id"] - 1, action="select", value=str(option))
    return _result("插件", "delivered", state=st)


@_guard
def scroll(app, dy=None, tab=None):
    cur = _last.get(app) or see(app, tab=tab)
    if cur["route"] == "插件":           # 按这一页实际走的路,不按插件在不在(开关编号时 see 走的是开关,C-0.5 实测修)
        st = call(app, "act", tab=(cur.get("tab") or {}).get("id"), i=-1, action="scroll", value=dy)
        _last.pop(app, None)
        return _result("插件", "delivered", state=st)
    if cur["route"] in ("开关", "调试端口"):
        st = _ae_act(app, cur, None, "scroll", dy)
        _last.pop(app, None)
        return _result(cur["route"], "delivered", state=st)
    raise WebError("网页滚动先走 seeu.scroll(后台滚轮)", "unsupported")


# ---------------------------------------------------------------- 标签页

def tabs(app):
    """插件:所有已允许网站的标签页(没允许的只给个数)。开关:所有窗口的标签页(没进 SeeU 允许名单的只给个数,
    I See 下全给)。辅助功能:当前窗口标签栏上的名字。调试端口:这份 App 里的页面(浏览器同样守名单)。"""
    h = _cdp(app)
    if h:
        from seeu import cdp
        allt = [dict(id=p["id"], title=p.get("title", ""), url=p.get("url", ""), active=i == 0)
                for i, p in enumerate(cdp.pages(h))]
        shown = allt if isee.active() or _name(app) not in CHROMIUM else [t for t in allt if aejs.is_allowed(t["url"])]
        return dict(route="调试端口", tabs=shown, hidden=len(allt) - len(shown))
    if plugin_ready(app):
        return dict(route="插件", **call(app, "tabs"))
    if _ae_on(app):
        allt = aejs.tabs(_name(app))
        shown = allt if isee.active() else [t for t in allt if aejs.is_allowed(t["url"])]
        return dict(route="开关", tabs=shown, hidden=len(allt) - len(shown))
    return dict(route="辅助功能", tabs=_ax_tabs(app), hidden=0)


def _wait_screen_free(timeout=60):
    """要抢前台之前:别的自动化任务登记占着画面(桌面锁)/ 用户正在用键鼠 → 等(有上限)。返回 None 或卡住的原因。"""
    t0 = time.time()
    while True:
        why = None
        try:
            from seeu_lib import desktop_lock as dl
            d = dl.status()
            if d and not d.get("stale") and d.get("pid") != os.getpid():
                why = "别的自动化任务正占着画面:" + dl.describe(d)
        except Exception:
            pass
        if not why:
            try:
                from seeu_lib import input_guard as ig
                busy, msg = ig.user_active(2.0)
                if busy:
                    why = "你正在用键盘鼠标(" + msg + ")"
            except Exception:
                pass
        if not why or time.time() - t0 > timeout:
            return why
        time.sleep(1)


def open(app, url, active=False, timeout=20):
    """后台开一个标签页(active=False 不切过去),等加载完。返回 {id, allowed, loaded}。
    11-02 用户定:网站不在名单、AI 要回对话里问用户时,悬浮窗展开卡片写「等你答应」(下一步动作会自动清掉)。"""
    r = _open(app, url, active, timeout)
    if r.get("allowed") is False and r.get("route") in ("开关", "调试端口"):
        try:
            from seeu_lib import watch_window as ww
            from seeu.i18n import lang
            o = aejs.origin(url) or url
            if lang() == "en":
                ww.stuck(_name(app), "Open tab", f"{o} isn't on SeeU's allow list", "Say yes in the chat to let the AI add it", False)
            else:
                ww.stuck(_name(app), "开标签页", f"{o} 不在 SeeU 允许名单里", "回对话里答应 AI 把它加进名单", False)
        except Exception:
            pass
    return r


def _open(app, url, active=False, timeout=20):
    h = _cdp(app)
    if h:                               # 调试端口:后台建标签,不露窗口
        from seeu import cdp
        tid = cdp.open_tab(h, url)
        loaded = cdp.wait_loaded(h, tid, timeout)
        _last.pop(app, None)
        return dict(id=tid, allowed=isee.active() or aejs.is_allowed(url), loaded=loaded, route="调试端口")
    if plugin_ready(app):
        r = call(app, "open", timeout=timeout + 5, url=url, active=active)
        _last.pop(app, None)
        if not r.get("allowed"):
            r["note"] = (r.get("note") or "") + " 这个网站还没允许 SeeU 操作,在网页上点 SeeU 图标选「允许这个网站」"
        return r
    n = _name(app)
    if _ae_on(app):
        if n not in aejs.SAFARI:        # Chrome 开新标签可能抢前台:先看画面空不空
            why = _wait_screen_free()
            if why:
                return dict(id=None, allowed=None, loaded=None, outcome="refused", reason=_explain(
                    WebError(why + ";Chrome 开新标签会抢前台", "busy"), "开标签页", app))
        tid = aejs.open_tab(n, url)
        loaded = aejs.wait_loaded(n, tid, timeout)
        _last.pop(app, None)
        return dict(id=tid, allowed=isee.active() or aejs.is_allowed(url), loaded=loaded, route="开关")
    aejs.open_bg(n, url)                # 浏览器没开着:冷启动会抢前台,抢了就切回去(11-02 用户实测)
    if n in aejs.SAFARI and _ae_on(app):   # 刚拉起来开关才查得到:接着按开关那条路给标签编号
        try:
            cur = aejs.current(n)
            loaded = aejs.wait_loaded(n, cur["id"], timeout)
            return dict(id=cur["id"], allowed=isee.active() or aejs.is_allowed(url), loaded=loaded, route="开关")
        except aejs.AEError:
            pass
    aejs.show(n)                        # 开关走不了:辅助功能要看得见窗口,放出来(不抢前台)
    return dict(id=None, allowed=None, loaded=None, note="没有插件和开关:用系统命令后台打开,读的时候要它在前面那个标签页")


def activate(app, tab):
    r = call(app, "activate", tab=tab)
    _last.pop(app, None)
    return r


# ---------------------------------------------------------------- 辅助功能这条路(没有插件 / 非 Chrome 内核)

AX_INTER = {"AXButton", "AXLink", "AXTextField", "AXTextArea", "AXCheckBox", "AXRadioButton", "AXPopUpButton",
            "AXComboBox", "AXMenuButton", "AXSlider", "AXSearchField", "AXDisclosureTriangle"}
ROLE_CN = {"AXButton": "button", "AXLink": "a", "AXTextField": "input:text", "AXTextArea": "textarea",
           "AXCheckBox": "input:checkbox", "AXRadioButton": "input:radio", "AXPopUpButton": "select",
           "AXComboBox": "combobox", "AXSearchField": "input:search", "AXMenuButton": "button", "AXSlider": "slider",
           "AXDisclosureTriangle": "summary"}


def _ax_app(app):
    from seeu import ax
    try:
        el, pid = ax.app_element(_name(app))
    except Exception:
        raise WebError(f"{_name(app)} 没在运行", "no_app")
    # 🔴 Chrome 要两个开关都写一遍(都会报"不支持",但会生效),约 2 秒后网页结构才出来(10-20 实测)
    for k in ("AXManualAccessibility", "AXEnhancedUserInterface"):
        try:
            ax.set_attr(el, k, True)
        except Exception:
            pass
    return ax, el


def _ax_webarea(ax, el, wait_s=5.0):
    t0 = time.time()
    while True:
        for w in ax.attr(el, "AXWindows") or []:
            stack = [(w, 0)]
            while stack:
                e, d = stack.pop()
                if ax.attr(e, "AXRole") == "AXWebArea" and (ax.attr(e, "AXChildren") or []):
                    return w, e
                if d < 25:
                    stack.extend((c, d + 1) for c in ax.attr(e, "AXChildren") or [])
        if time.time() - t0 > wait_s:
            raise WebError("读不到网页结构(浏览器没把网页交给系统辅助功能)。" + SUGGEST, "no_web")
        time.sleep(0.5)


def _ax_see(app):
    ax, el = _ax_app(app)
    win, area = _ax_webarea(ax, el)
    items, texts = [], []
    stack = [(area, 0)]
    t0 = time.time()
    while stack and time.time() - t0 < 10:
        e, d = stack.pop()
        role = ax.attr(e, "AXRole")
        if role in AX_INTER:
            name = str(ax.attr(e, "AXTitle") or ax.attr(e, "AXDescription") or "")
            sub = ax.attr(e, "AXSubrole")
            it = dict(id=0, role=ROLE_CN.get(role, role), text=name.strip(), el=e, ax_role=role, rect=ax.frame(e))
            kind = ax.secret_kind(role, sub, name, ax.attr(e, "AXPlaceholderValue"), ax.attr(e, "AXHelp"))
            if kind:
                it["secret"] = kind
            elif role in ("AXCheckBox", "AXRadioButton"):
                it["checked"] = bool(ax.attr(e, "AXValue"))
            elif role in ("AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"):
                it["value"] = str(ax.attr(e, "AXValue") or "")
            if role == "AXLink":
                u = ax.attr(e, "AXURL")
                if u:
                    it["href"] = str(u)
            items.append(it)
        elif role == "AXStaticText":
            v = str(ax.attr(e, "AXValue") or "").strip()
            if v:
                texts.append(v)
        elif role == "AXImage":
            # 图片的说明文字也算页面文字:评分这类常藏在图里(10-20 应用商店「Average rating 4.2 out of 5 stars.」)
            v = str(ax.attr(e, "AXDescription") or ax.attr(e, "AXTitle") or "").strip()
            if v:
                texts.append(f"[图:{v}]")
        if d < 80:
            stack.extend((c, d + 1) for c in reversed(ax.attr(e, "AXChildren") or []))
    for i, it in enumerate(items, 1):
        it["id"] = i
    title = str(ax.attr(win, "AXTitle") or "")
    url = str(ax.attr(area, "AXURL") or "")
    return dict(route="辅助功能", items=items, text="\n".join(texts), url=url, title=title, tab=None)


def _ax_tap(app, it):
    from seeu import ax
    before = it.get("checked")
    if it.get("ax_role") == "AXRadioButton" and before:
        return _result("辅助功能", "delivered", "本来就选着", state={"checked": True})
    acts = ax.action_names(it["el"]) or []
    if "AXPress" not in acts:
        raise WebError("这个控件辅助功能按不下去。", "ineffective")
    ax.perform(it["el"], "AXPress")
    time.sleep(0.3)
    if before is not None:
        now = bool(ax.attr(it["el"], "AXValue"))
        ok = now != before or (it["ax_role"] == "AXRadioButton" and now)
        _last.pop(app, None)
        return _result("辅助功能", "delivered" if ok else "ineffective", None if ok else "按了但勾选状态没变",
                       state={"checked": now})
    _last.pop(app, None)
    return _result("辅助功能", "unverified", "按下了(网页按钮没法直接核实,需要的话再 see 一次看页面)")


def _ax_type(app, it, text, mode):
    """先直接写值(读回核实),不行再聚焦 + 后台键盘(跟 seeu.type 同一条路)。10-20 实测两条都能进中文。"""
    from seeu import ax, bgkey as bk
    el = it["el"]
    old = str(ax.attr(el, "AXValue") or "")
    want = old + text if mode == "append" else text
    try:
        ax.set_attr(el, "AXValue", want)
        time.sleep(0.2)
        if str(ax.attr(el, "AXValue") or "") == want:
            _last.pop(app, None)
            return _result("辅助功能", "delivered", state={"value": want})
    except Exception:
        pass
    try:
        ax.set_attr(el, "AXFocused", True)
    except Exception:
        pass
    time.sleep(0.2)
    bk.type_to(_name(app), text, enter=False)
    time.sleep(0.5)
    got = str(ax.attr(el, "AXValue") or "")
    _last.pop(app, None)
    ok = text in got
    return _result("辅助功能", "delivered" if ok else "ineffective", None if ok else "打完读回没看到这段字",
                   state={"value": got})


def _ax_tabs(app):
    ax, el = _ax_app(app)
    out = []
    for w in (ax.attr(el, "AXWindows") or [])[:1]:
        stack = [(w, 0)]
        while stack:
            e, d = stack.pop()
            if ax.attr(e, "AXRole") == "AXRadioButton" and ax.attr(e, "AXSubrole") in (None, "AXTabButton") \
                    and ax.attr(e, "AXParent") is not None and ax.attr(ax.attr(e, "AXParent"), "AXRole") == "AXTabGroup":
                out.append(dict(title=str(ax.attr(e, "AXTitle") or ""), active=bool(ax.attr(e, "AXValue"))))
            if d < 12 and ax.attr(e, "AXRole") != "AXWebArea":
                stack.extend((c, d + 1) for c in ax.attr(e, "AXChildren") or [])
    return out
