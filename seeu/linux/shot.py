# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 截图:走系统截图授权(xdg-desktop-portal Screenshot,不弹选择框)截整屏,再按窗口位置裁。

- 第一次会弹系统框「允许应用截图吗?」,用户点允许后一直不弹(GNOME 50 实测,约 0.5 秒一张)。
- 🔴 不在 GNOME 小插件里截图:GNOME 50 在 Shell 里截图会让整个会话崩掉(见小插件开头)。
- 系统每截一张都存进用户的「图片」文件夹 → 拿到就立刻挪进 SeeU 自己的临时目录,不在用户文件夹里留东西。
- 只能截到屏幕上看得见的:窗口被别的窗口挡住、在别的工作区、最小化时,裁出来的不是它(调用方要看 visible())。
"""
import os
import shutil
import tempfile
import time
import urllib.parse

TIMEOUT = 12          # 等系统回话的上限(秒);第一次要用户点允许,超时就当「等用户授权」


class NeedGrant(RuntimeError):
    """系统还没允许截图(弹着框等用户点 / 用户点了拒绝)。"""


def _tmpdir():
    """SeeU 放截图的临时目录。先用 XDG_RUNTIME_DIR(只有本人能进);退回 /tmp 时核对目录是自己的、不是软链接、权限 700,
    原来目录已经存在就直接用 —— 别人先建好一个大家都能读的同名目录,就能看到截图。"""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base) and os.stat(base).st_uid == os.getuid():
        d = os.path.join(base, "seeu")
    else:
        d = os.path.join(tempfile.gettempdir(), f"seeu_linux_{os.getuid()}")
    os.makedirs(d, mode=0o700, exist_ok=True)
    st = os.lstat(d)
    import stat as _st
    if _st.S_ISLNK(st.st_mode) or not _st.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise RuntimeError(f"SeeU 的临时目录 {d} 不是你自己的(可能被别人抢先建了),为了不让截图被别人看到,先不截;删掉它再试")
    if st.st_mode & 0o077:
        os.chmod(d, 0o700)
    return d


LOCK_WAIT = 15         # 别的 SeeU 进程正在截图时最多等这么久(一张约 0.5 秒)


def full(timeout=TIMEOUT):
    """截整屏,返回 PNG 路径(在 SeeU 的临时目录里)。
    🔴 两个 SeeU 进程(两个 AI 会话)同时截图,后到的那个系统不回话、干等 12 秒,还误报「等你允许截图」
    → 全机一次只截一张(文件锁,最多等 LOCK_WAIT 秒;拿不到锁照样去截,不比原来差)。"""
    import fcntl
    fd = os.open(os.path.join(_tmpdir(), "shot.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        t0 = time.time()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() - t0 > LOCK_WAIT:
                    break
                time.sleep(0.05)
        # 🔴 x86:系统的截图服务闲一阵会自己退出;下一张请求把它拉起来,可这一张请求本身就丢了(等 90 秒也不回),
        # 原来干等 12 秒后报「等你允许截图」/「点了拒绝」,其实早就允许过。
        # → 系统记着「允许过」:每次只等 TRY_TIMEOUT 秒,不回就重发一张新的请求,最多 TRIES 次;没允许过:照旧等用户点(timeout)
        if _granted() is True:
            for i in range(TRIES):
                try:
                    return _full(min(timeout, TRY_TIMEOUT))
                except NeedGrant:
                    continue
            raise RuntimeError("系统的截图服务一直没给出截图(截图早就允许过了;可能正在启动或卡住),等几秒再试")
        return _full(timeout)
    finally:
        os.close(fd)        # 关掉就放锁


TRY_TIMEOUT, TRIES = 6, 6      # 合计最多约 36 秒(x86:新窗口刚出来时截图服务卡过 ~25 秒,没显卡加速的机器)


def _granted():
    """系统授权记录里,普通程序(非沙盒)的截图是不是允许过:True / False / None(查不到)。"""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        r = bus.call_sync("org.freedesktop.impl.portal.PermissionStore", "/org/freedesktop/impl/portal/PermissionStore",
                          "org.freedesktop.impl.portal.PermissionStore", "Lookup", GLib.Variant("(ss)", ("screenshot", "screenshot")),
                          None, Gio.DBusCallFlags.NONE, 3000, None)
        perms = r.unpack()[0]
        v = perms.get("")
        if v is None:
            return None
        return "yes" in v
    except Exception:   # noqa: BLE001
        return None


def _full(timeout=TIMEOUT):
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    token = f"seeu{int(time.time() * 1000)}{os.getpid()}"
    handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop, res = GLib.MainLoop(), {}

    def on_resp(conn, snd, path, iface, sig, params):
        code, results = params.unpack()
        res["code"], res["uri"] = code, results.get("uri")
        loop.quit()

    sid = bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                               handle, None, Gio.DBusSignalFlags.NO_MATCH_RULE, on_resp)
    try:
        bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Screenshot",
                      "Screenshot", GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", token),
                                                                   "interactive": GLib.Variant("b", False)})),
                      None, Gio.DBusCallFlags.NONE, 5000, None)
        GLib.timeout_add(int(timeout * 1000), loop.quit)
        loop.run()
    finally:
        bus.signal_unsubscribe(sid)
    if "code" not in res:
        raise NeedGrant("系统在等你允许截图:屏幕上应该弹着「允许应用截图吗?」,请点「允许」(只要点一次)")
    if res["code"] != 0 or not res.get("uri"):
        raise NeedGrant("系统没允许截图(点了拒绝,或在设置里关了):在「设置 → 隐私 → 截图」里允许后再试")
    src = urllib.parse.unquote(urllib.parse.urlparse(res["uri"]).path)
    dst = os.path.join(_tmpdir(), f"full_{int(time.time() * 1000)}.png")
    shutil.move(src, dst)            # 跨分区用 move(/tmp 和家目录常不在一个分区)
    _prune()
    return dst


_LOGICAL = [0.0, None]


def logical_size():
    """桌面(所有显示器拼起来)的逻辑尺寸 (宽, 高),跟窗口坐标、控件坐标同一套;问不到返回 None。记 3 秒。
    虚拟机实测:显示缩放 200% 时整屏截图是实际像素(宽是逻辑的 2 倍),窗口坐标却是逻辑的 →
    原来直接拿窗口坐标裁,裁到的只是窗口左上角那一块、还混着别的窗口(给 AI 的截图错了,按截图位置点也跟着偏)。"""
    now = time.time()
    if now - _LOGICAL[0] < 3:
        return _LOGICAL[1]
    out = None
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        _s, monitors, logical, props = bus.call_sync(
            "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig",
            "GetCurrentState", None, None, Gio.DBusCallFlags.NONE, 2000, None).unpack()
        size = {}
        for (conn, *_), modes, _mp in monitors:
            for m in modes:
                if m[6].get("is-current"):
                    size[conn] = (m[1], m[2])
        phys = int(props.get("layout-mode", 1)) == 2          # 2 = 按实际像素排(X11 式);1 = 按逻辑尺寸排(Wayland 默认)
        x1 = y1 = 0.0
        for lx, ly, scale, transform, _p, mons, _lp in logical:
            pw, ph = size.get(mons[0][0], (0, 0))
            if transform in (1, 3, 5, 7):                     # 竖屏:宽高对调
                pw, ph = ph, pw
            k = 1.0 if phys else float(scale or 1)
            x1, y1 = max(x1, lx + pw / k), max(y1, ly + ph / k)
        out = (x1, y1) if x1 > 0 and y1 > 0 else None
    except Exception:   # noqa: BLE001
        out = None
    _LOGICAL[:] = [now, out]
    return out


def crop(png, x, y, w, h, out=None, mask=()):
    """从整屏图里裁出一块(超出屏幕的部分截掉)。返回 (路径, 实际的 x, y, w, h)。
    mask:屏幕坐标的 (x, y, w, h) 列表,裁之前涂黑(盖在目标窗口上面的终端、密码程序那块不发给 AI)。
    传进来的、返回的坐标都是逻辑坐标(跟窗口、控件一套);整屏图是实际像素时按倍数换算再裁,
    裁出来的图保持实际像素(更清楚),调用方按「返回的范围 ↔ 图的尺寸」换算(mcp_server._px_to_screen、认字清单)。"""
    from PIL import Image, ImageDraw
    im = Image.open(png)
    ls = logical_size()
    k = im.width / float(ls[0]) if ls and ls[0] > 0 else 1.0
    if abs(k - 1.0) < 0.02:
        k = 1.0
    if mask:
        im = im.convert("RGB")
        d = ImageDraw.Draw(im)
        for mx, my, mw, mh in mask:
            d.rectangle((int(mx * k), int(my * k), int((mx + mw) * k) - 1, int((my + mh) * k) - 1), fill=(0, 0, 0))
    x0, y0 = max(0, int(round(x * k))), max(0, int(round(y * k)))
    x1, y1 = min(im.width, int(round((x + w) * k))), min(im.height, int(round((y + h) * k)))
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError("窗口不在屏幕范围里")
    out = out or os.path.join(_tmpdir(), f"win_{int(time.time() * 1000)}.png")
    im.crop((x0, y0, x1, y1)).save(out)
    return out, (x0 / k, y0 / k, (x1 - x0) / k, (y1 - y0) / k)


def diff(a, b, box=None):
    """两张图差多少(百分比,0~100)。box=(x, y, w, h) 只比这一块(两张图坐标一致时用)。"""
    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert("L"), Image.open(b).convert("L")
    if box:
        x, y, w, h = [int(v) for v in box]
        ia, ib = ia.crop((x, y, x + w, y + h)), ib.crop((x, y, x + w, y + h))
    if ia.size != ib.size:
        return 100.0
    d = ImageChops.difference(ia, ib).point(lambda v: 255 if v > 24 else 0)
    hist = d.histogram()
    return 100.0 * hist[255] / max(1, ia.width * ia.height)


def _prune(keep=200):
    d = _tmpdir()
    fs = sorted((os.path.join(d, n) for n in os.listdir(d) if n.endswith(".png")), key=os.path.getmtime)
    for p in fs[:-keep]:
        try:
            os.remove(p)
        except OSError:
            pass
