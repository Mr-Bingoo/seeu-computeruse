"""MCP 工具标注:三个系统的 tools/list 都从这张表给工具加 annotations。

告诉客户端哪个工具只看、哪个会动东西(Anthropic 目录政策要求 readOnlyHint / destructiveHint / title)。
点、长按、打字、按键、点菜单、管理命令照实标「可能有破坏性」。
openWorldHint 一律 True:操作的是用户电脑上真实的 App / 网页。加新工具时在这里补一行;没写的工具不加标注。
"""

_RO = {"readOnlyHint": True, "openWorldHint": True}


def _act(destructive, idempotent=False):
    return {"readOnlyHint": False, "destructiveHint": destructive, "idempotentHint": idempotent, "openWorldHint": True}


import sys

HINTS = {
    # 只看、不动东西(Mac 上 seeu_check 缺权限时会打开系统设置那一页 → Mac 不标只读;Windows / Linux 的检查只看)
    "seeu_check": ("Check SeeU's setup", _act(False, True) if sys.platform == "darwin" else _RO),
    "seeu_probe": ("Probe an app", _RO),
    "seeu_see": ("Look at an app's screen", _RO),
    "seeu_windows": ("List open windows", _RO),
    "seeu_web_tabs": ("List browser tabs", _RO),
    "seeu_web_read": ("Read a web page", _RO),
    # 会动,但不会改坏东西
    "seeu_scroll": ("Scroll", _act(False)),
    "seeu_web_open": ("Open a background browser tab", _act(False)),
    "seeu_mirror_home": ("Go to the iPhone home screen", _act(False, True)),
    "seeu_mirror_open": ("Open an app on the iPhone", _act(False)),
    "seeu_open_app": ("Open an app in the background", _act(False)),
    "seeu_allow_site": ("Add a site to SeeU's allow list", _act(False, True)),
    # 会动,可能改坏东西
    "seeu_tap": ("Click", _act(True)),
    "seeu_long_press": ("Long-press", _act(True)),
    "seeu_type": ("Type text", _act(True)),
    "seeu_press": ("Press a key", _act(True)),
    "seeu_menu": ("Click a menu item", _act(True)),
    "seeu_manage": ("Manage SeeU settings", _act(True)),
}


def annotate(tools):
    """给工具列表加 title + annotations,返回新列表(不改原来的 TOOLS)。"""
    out = []
    for t in tools:
        h = HINTS.get(t.get("name"))
        if h:
            t = dict(t, title=h[0], annotations=dict(h[1], title=h[0]))
        out.append(t)
    return out
