"""SeeU —— 我们自己的 Computer Use(名字取「CU」的谐音,别处一律只叫 SeeU)。说明见同目录 README.md。"""

import sys

# 11-01 用户定:只支持 macOS。别的系统一进来就说清楚,别等到缺 pyobjc 报一大段英文。
# 还没加载设置、认不了语言,中英文一起写。python3 -m seeu 直接退出;被别的程序 import 就抛 ImportError 带这段话。
MAC_ONLY = ("SeeU 目前只支持 macOS，其能力主要来自macOS自带的辅助功能、截屏和文字识别，当前设备（{os}）暂时用不了，其他系统的版本正在调研中，欢迎关注！\n"
            "SeeU only supports macOS for now. Its abilities mainly come from macOS's built-in Accessibility, screen capture and "
            "text recognition, so it can't run on this device ({os}) yet. Versions for other systems are being researched, stay tuned!")
if sys.platform != "darwin":
    import platform as _pf
    _msg = MAC_ONLY.format(os=_pf.system() or sys.platform)
    if sys.argv[:1] == ["-m"]:
        print(_msg, file=sys.stderr)
        sys.exit(1)
    raise ImportError(_msg)

# 10-14 用户反馈"每次点击小火箭都跳一次":bgclick.focus_without_raise(SLPSPostEventRecordTo)会把调用它的
# Python 登记成前台应用,Dock 冒图标。凡是 import seeu 的进程先标成后台程序(lsappinfo listen 实测出生即 BackgroundOnly,
# 聚焦照常成功)。要在任何 AppKit/SkyLight 调用之前设,所以放包入口。
try:
    from Foundation import NSBundle
    NSBundle.mainBundle().infoDictionary()["LSBackgroundOnly"] = "1"
except Exception:
    pass


# 10-29:动作统一挂在包上(import seeu; seeu.tap(...)),实现在 seeu/act.py。
# 用到才加载:bgclick 等子模块 import seeu 时不连带拉起 act(act 反过来要 import 它们,提前拉会循环导入)。
ACTIONS = ("see", "tap", "type", "scroll", "press", "menu", "drag", "long_press", "describe",
           "mirror_home", "mirror_open_app", "mirror_baseline")


SUBMODULES = ("web", "stealth", "cdp", "isee", "safety", "act")   # 10-30:Skill 里写 seeu.web.type(...),用到再加载


def __getattr__(name):
    if name in ACTIONS:
        from seeu import act
        return getattr(act, name)
    if name in SUBMODULES:
        import importlib
        return importlib.import_module(f"seeu.{name}")
    raise AttributeError(f"module 'seeu' has no attribute {name!r}")
