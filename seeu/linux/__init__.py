"""SeeU Linux 版(预览,只支持 GNOME + Wayland)。"""
import os
import sys

# 桌面会话的环境变量:辅助功能接口、截图、小插件都靠会话总线和 Wayland。
SESSION_KEYS = ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY", "XDG_SESSION_TYPE",
                "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION", "XAUTHORITY")


def _shell_env(uid):
    """同一个用户的 gnome-shell 进程的环境变量(读不到返回 {})。"""
    try:
        pids = [d for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        return {}
    for d in pids:
        try:
            if os.stat(f"/proc/{d}").st_uid != uid:
                continue
            with open(f"/proc/{d}/comm", encoding="utf-8") as f:
                if f.read().strip() != "gnome-shell":
                    continue
            with open(f"/proc/{d}/environ", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        env = {}
        for item in raw.split(b"\0"):
            k, sep, v = item.decode("utf-8", "replace").partition("=")
            if sep:
                env[k] = v
        if env.get("DBUS_SESSION_BUS_ADDRESS") or env.get("WAYLAND_DISPLAY"):
            return env
    return {}


def fix_session_env(environ=None, uid=None, shell_env=None):
    """补上缺的桌面会话变量(Codex 实测:它拉起 MCP 服务时只给 HOME、PATH、LANG 等 8 个变量,
    缺了会话总线,AT-SPI 一连就整个进程退出)。只补缺的、不改已有的;先照搬本用户 gnome-shell 的,
    再退回 /run/user/<uid> 下的默认位置。返回补了哪些。"""
    env = os.environ if environ is None else environ
    if environ is None and not sys.platform.startswith("linux"):
        return []
    if env.get("DBUS_SESSION_BUS_ADDRESS") and env.get("XDG_RUNTIME_DIR") and (env.get("WAYLAND_DISPLAY") or env.get("DISPLAY")):
        return []
    uid = os.getuid() if uid is None else uid
    src = _shell_env(uid) if shell_env is None else shell_env
    added = []
    for k in SESSION_KEYS:
        if not env.get(k) and src.get(k):
            env[k] = src[k]
            added.append(k)
    run = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    if not env.get("XDG_RUNTIME_DIR") and os.path.isdir(run):
        env["XDG_RUNTIME_DIR"] = run
        added.append("XDG_RUNTIME_DIR")
    if not env.get("DBUS_SESSION_BUS_ADDRESS") and os.path.exists(os.path.join(run, "bus")):
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + os.path.join(run, "bus")
        added.append("DBUS_SESSION_BUS_ADDRESS")
    if not env.get("WAYLAND_DISPLAY") and os.path.exists(os.path.join(run, "wayland-0")):
        env["WAYLAND_DISPLAY"] = "wayland-0"
        added.append("WAYLAND_DISPLAY")
    return added


try:
    fix_session_env()
except Exception:   # noqa: BLE001   补不上就照旧,后面检查会说缺什么
    pass
