# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 命令行和提示条的英文(11-18 C-3.0,照 Windows 版 win/lang.py)。

代码里的提示照旧写中文(测试、别的调用方按中文字判断),只在打印给人看的出口过一遍 tx():
语言是英文时,先换这里的片段(命令行独有的)+ 给 AI 的原因那套(mcp_server.LINUX_PHRASES)+ Windows 网页那套,
最后过 Mac 版的 reason_en.to_en(通用结果原因 + 中文标点)。没收录的片段原样留中文,不报错。
语言跟 Mac / Windows 一样:seeu/设置.json「语言」,环境变量 SEEU_LANG=zh|en 优先。
"""

CLI = [
    # 结果
    ("路线=", "route="), ("试过=", "tried="), ("截图=", "screenshot="), ("截图:", "Screenshot:"), ("窗口: ", "Window: "),
    ("这个程序开着好几个窗口:", "This program has several windows:"), ("   (别的工作区)", "   (other workspace)"),
    ("按控件", "through the control"), ("借真鼠标", "with the real mouse"), ("借真键盘", "with the real keyboard"),
    ("屏幕位置", "screen position"), ("没有能按的动作", "no action to press"),
    # 检查
    ("SeeU 检查(Linux 版预览)", "SeeU check (Linux preview)"), ("会话", "Session"), ("辅助功能接口", "Accessibility API"),
    ("辅助功能总开关", "Accessibility switch"), ("GNOME 小插件", "GNOME helper"), ("截图授权", "Screenshot permission"),
    ("认字(可选)", "Text recognition (optional)"),
    ("一键接入的 AI 客户端都移除了,同时删掉了 SeeU 的 GNOME 小插件(注销重新登录一次后彻底停下)。",
     "All AI clients connected with the one-step install are removed, so SeeU's GNOME helper was removed too (it fully stops after you log out and back in once). "),
    ("要是你还手动接了别的 AI 客户端,运行 python3 -m seeu 检查 --fix 再注销重新登录一次就能装回。",
     "If you also connected another AI client by hand, run python3 -m seeu check --fix and log out and back in once to reinstall the helper."),
    ("没装认字程序 Tesseract(装法:", "Tesseract (text recognition) isn't installed (install: "),
    ("认字出错:", "Text recognition failed: "),
    ("SeeU 的 GNOME 小插件没删掉(", "Couldn't remove SeeU's GNOME helper ("), ("),可以到「扩展」App 里手动删", "); you can remove it in the Extensions app"), ("图片处理库", "Image library"), ("Pillow 在", "Pillow is installed"),
    ("没装 Pillow,看画面拿不到截图、按位置点不了;装:", "Pillow isn't installed, so seeing a window gives no screenshot and tapping by position won't work; install: "), ("借真鼠标键盘", "Real mouse/keyboard"),
    (";第一版只在 GNOME + Wayland 上测过", "; the first version is only tested on GNOME + Wayland"),
    # 11-21 C-3.3 接入前的环境提醒 + Python 那行
    (";要 3.10 以上,先升级 Python", "; SeeU needs 3.10 or later, please upgrade Python"),
    ("⚠️ 先说一声:这台电脑不完全满足 SeeU Linux 预览版的要求", "⚠️ Heads-up: this computer doesn't fully meet the SeeU Linux preview's requirements"),
    ("   接入照常做;运行 python3 -m seeu 检查 能看全哪些没齐。", "   Connecting goes ahead anyway; run python3 -m seeu check to see everything that's missing."),
    (",SeeU 要 3.10 以上,先升级 Python 再用", "; SeeU needs 3.10 or later, please upgrade Python first"),
    ("Python 是 ", "Python is "),
    (",不是 GNOME;SeeU Linux 预览版只支持 GNOME(Ubuntu 默认桌面),在这个桌面上接好了也看不了窗口、点不了按钮",
     ", not GNOME; the SeeU Linux preview supports GNOME only (Ubuntu's default desktop), so even once connected it can't see windows or click buttons here"),
    ("现在的桌面是 ", "The current desktop is "),
    (",SeeU Linux 预览版只在 GNOME + Wayland 上测过,可能有用不了的地方(Ubuntu 登录界面右下角的齿轮里能选 Wayland)",
     "; the SeeU Linux preview is only tested on GNOME + Wayland, so some things may not work (on Ubuntu, pick Wayland from the gear at the bottom right of the login screen)"),
    ("现在的显示方式是 ", "The current display session is "),
    ("AT-SPI 正常,读到 ", "AT-SPI works, sees "), (" 个程序", " programs"), ("AT-SPI 读不到任何程序", "AT-SPI sees no programs"),
    ("用不了(", "not usable ("), (");装:", "); install: "),
    ("已打开系统的辅助功能总开关;已经开着的 Qt / Electron / Chrome 程序要重开一次才读得到控件",
     "Turned on the system accessibility switch; Qt / Electron / Chrome programs that are already open need a restart to expose their controls"),
    ("开着(Qt、Electron、Chrome 的控件也读得到)", "on (Qt, Electron and Chrome controls are readable too)"),
    ("关着:Qt、Electron(VS Code 这类)、Chrome 的控件读不到;运行 python3 -m seeu 检查 --fix 打开",
     "off: Qt, Electron (VS Code and the like) and Chrome controls can't be read; run python3 -m seeu check --fix to turn it on"),
    ("读不到", "can't read it"), ("现在不是 GNOME 桌面,第一版只支持 GNOME", "this isn't a GNOME desktop; the first version supports GNOME only"),
    ("已装好 SeeU 的 GNOME 小插件", "Installed SeeU's GNOME helper"), (";🔴 要注销重新登录一次才生效", "; 🔴 log out and back in once for it to take effect"),
    ("在跑(GNOME ", "running (GNOME "), (",小插件第 ", ", helper version "), (" 版)", ")"),
    (";是旧版,借鼠标和代理光标要新版:运行 python3 -m seeu 检查 --fix,再注销重新登录一次",
     "; it's an old version — mouse borrowing and the proxy cursor need the new one: run python3 -m seeu check --fix, then log out and back in once"),
    ("(运行 python3 -m seeu 检查 --fix)", " (run python3 -m seeu check --fix)"),
    ("SeeU 的 GNOME 小插件被关掉了:在「扩展」App 里把 SeeU 打开(或运行 python3 -m seeu 检查 --fix)",
     "SeeU's GNOME helper is turned off: turn SeeU on in the Extensions app (or run python3 -m seeu check --fix)"),
    ("SeeU 的 GNOME 小插件还没加载:装好后要注销重新登录一次;已经重新登录过的话,看「扩展」App 里它有没有报错",
     "SeeU's GNOME helper isn't loaded: after installing it, log out and back in once; if you already did, check the Extensions app for an error"),
    ("允许了", "allowed"), ("Tesseract,语言:", "Tesseract, languages: "),
    ("没装(读不到控件的窗口才用;", "not installed (only needed for windows without readable controls; "),
    ("设置是「关」:后台做不到时不借(python3 -m seeu 设置 借用鼠标 开)",
     "the setting is \"off\": SeeU won't borrow them when the background can't do it (python3 -m seeu settings borrow-mouse on)"),
    ("现在会弹出系统的「远程桌面」框:请打开「允许远程操作」,再点「共享」(SeeU 只在后台做不到时借一下,借的时候右上角会亮提示)",
     "The system \"Remote Desktop\" dialog will open now: turn on \"Allow remote control\", then click \"Share\" (SeeU only borrows "
     "the mouse when the background can't do it; the top-right corner lights up while it does)"),
    ("已允许,以后借鼠标不再弹框", "Allowed; no more dialogs when borrowing the mouse"), ("没拿到授权:", "Not granted: "),
    ("如果弹出系统的「允许应用截图吗?」框,请点「允许」(只要点一次,最多等 2 分钟)",
     "If the system \"Allow applications to take screenshots?\" dialog opens, click \"Allow\" (only once; waiting up to 2 minutes)"),
    ("已允许远程操作", "remote control allowed"),
    ("还没允许远程操作(要用时 SeeU 会说;运行 python3 -m seeu 检查 --fix 先允许)",
     "remote control not allowed yet (SeeU will say when it's needed; run python3 -m seeu check --fix to allow it now)"),
    (";设置「借用鼠标」= 开", "; setting \"borrow mouse\" = on"), (";设置「借用鼠标」= 问我", "; setting \"borrow mouse\" = ask"),
    ("都齐了", "All set"), ("有没齐的,按上面说的补", "Something is missing — fix it as described above"),
    # 设置
    ("借用鼠标: 开", "Borrow mouse: on"), ("借用鼠标: 问我", "Borrow mouse: ask"), ("借用鼠标: 关", "Borrow mouse: off"),
    ("  (开 = on / 问我 = ask / 关 = off)", ""), ("用法:python3 -m seeu 设置 借用鼠标 开|问我|关", "Usage: python3 -m seeu settings borrow-mouse on|ask|off"),
    ("没改:设置文件读不出来(", "Not changed: the settings file can't be read ("), ("已改:借用鼠标 = 开", "Changed: borrow mouse = on"),
    ("已改:借用鼠标 = 问我", "Changed: borrow mouse = ask"), ("已改:借用鼠标 = 关", "Changed: borrow mouse = off"),
    # 提示条
    ("SeeU 想借你的", "SeeU wants to borrow your "), ("一下,AI 会问你", " — the AI will ask you"),
    ("想借你的鼠标长按一下,AI 会问你", "wants to borrow your mouse for a long-press — the AI will ask you"),
    ("想借你的鼠标拖一下,AI 会问你", "wants to borrow your mouse for a drag — the AI will ask you"),
    ("鼠标长按一下", "mouse for a long-press"), ("鼠标拖一下", "mouse for a drag"), ("鼠标", "mouse"), ("键盘", "keyboard"),
    ("请先别动鼠标键盘,马上还给你", "Please don't touch the mouse/keyboard, back in a moment"),
    ("借用鼠标滚动", "Borrowing the mouse wheel"), ("借用鼠标", "Borrowing the mouse"), ("借用键盘", "Borrowing the keyboard"),
    # 后台打开
    (" 已经开着,没动它(没拉到前台)。用 seeu_see 看它的画面", " is already open; left as it is (not brought to the front). Look at it with seeu_see"),
    (" 打开时自己跳到了最前面,", " jumped to the front when it opened; "), ("已切回原来的窗口。", "switched back to the user's window. "),
    ("没能切回原来的窗口。", "couldn't switch back to the user's window. "), ("已在后台打开 ", "Opened in the background: "),
    ("(没拉到前台)。接下来用 seeu_see 看它的画面", " (not brought to the front). Next, look at it with seeu_see"),
    (" 开起来了,但还没看到它的窗口。等一两秒再 seeu_see 看看", " started, but its window hasn't shown up yet. Wait a second or two, then seeu_see"),
    ("找不到叫「", "No app called \""), ("」的 App(「活动」里搜得到的才找得到),请用户确认 App 名",
                                      "\" (only apps you can find in Activities); ask the user for the app's name"),
    (",SeeU 不替你打开", "; SeeU won't open it for you"), ("是命令行程序或系统工具", "is a command-line program or system tool"),
    ("是命令行程序,能直接运行任何命令", "is a command-line program that can run any command"),
    ("是系统设置或系统管理相关的界面", "is system settings or an admin tool"), ("是存密码的程序", "is a password app"),
    ("是 AI 客户端或远程协助程序", "is an AI client or remote-desktop tool"),
    ("是虚拟机 / 容器 / 兼容层,能在里面运行任何程序", "is a virtual machine / container / compatibility layer that can run any program"),
    ("是浏览器,开网页请用 seeu_web_open(网址要过允许名单)", "is a browser; for web pages use seeu_web_open (the site must be on the allow list)"),
    ("没写要打开哪个 App", "no app name given"),
]

# 清单里的控件类别(see 列表):英文时按 AT-SPI 原来的叫法写
ROLE_EN = {"按钮": "button", "开关按钮": "toggle", "勾选框": "checkbox", "单选": "radio", "输入框": "field", "密码框": "password",
           "文字": "text", "链接": "link", "菜单项": "menu item", "菜单": "menu", "标签页": "tab", "下拉框": "dropdown",
           "列表项": "list item", "格子": "cell", "标题": "heading", "段落": "paragraph", "数字框": "number", "滑块": "slider",
           "图片": "image", "网页": "web page", "窗口": "window", "对话框": "dialog", "终端": "terminal", "文档": "document"}
FLAG_EN = {"  [密码框]": "  [password]", "  [可写]": "  [writable]", "  [输入框,后台写不进]": "  [field, can't write in background]"}

USAGE_EN = """SeeU for Linux (preview)
  python3 -m seeu windows                          list windows
  python3 -m seeu see <App>                        screenshot + numbered list
  python3 -m seeu tap <App> <number|name>          press a control
  python3 -m seeu type <App> <text> [--at number|name] [--enter]
  python3 -m seeu press <App> <key> [mods…] [--at number]
  python3 -m seeu scroll <App> [dy] [dx]          negative dy = scroll down
  python3 -m seeu long_press <App> <number|name|x y> [--ms ms]   long-press (borrows the real mouse, default 1000)
  python3 -m seeu drag <App> x1 y1 x2 y2 [x3 y3 …]               drag (borrows the real mouse, screen coordinates)
  python3 -m seeu menu <App> <menu> <item> […]                   click a menu-bar item (background), e.g. menu featherpad File New
  python3 -m seeu probe <App>                                     read-only check: can SeeU automate it, which route
  python3 -m seeu open <App>                                      open an app in the background (not terminals, settings, browsers…)
  python3 -m seeu check [--fix]                    check / install the GNOME helper, screenshot and remote-control permissions, accessibility API
  python3 -m seeu settings [borrow-mouse on|ask|off]   whether SeeU may borrow your real mouse/keyboard when the background can't do it
  python3 -m seeu update [--check]                 update to the new version on GitHub (git clone installs only)"""


def is_en():
    try:
        from seeu.i18n import lang
        return lang() == "en"
    except Exception:   # noqa: BLE001
        return False


def _table():
    t = list(CLI)
    try:
        from seeu.linux.mcp_server import LINUX_PHRASES
        t += LINUX_PHRASES
    except Exception:   # noqa: BLE001
        pass
    try:
        from seeu.win.mcp_server import WIN_PHRASES
        t += WIN_PHRASES
    except Exception:   # noqa: BLE001
        pass
    return t


def tx(text, force=None):
    """force=True / False:不看设置,强制转 / 不转(测试用)。"""
    if not (is_en() if force is None else force) or not isinstance(text, str):
        return text
    from seeu.win import lang as WL
    return WL.tx(text, _table(), force=True)


def say(*a, **k):
    print(*[tx(x) if isinstance(x, str) else x for x in a], **k)


def L(zh, en):
    return en if is_en() else zh
