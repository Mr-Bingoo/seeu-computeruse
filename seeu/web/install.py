"""SeeU 浏览器助手 · 安装 / 卸载本机中转程序(C-1.4,10-20)

  python3 -m seeu.web.install            找出本机装了的 Chrome 同内核浏览器,逐个登记中转程序,再教怎么加载插件
  python3 -m seeu.web.install uninstall  撤销登记

登记 = 往浏览器自己的 NativeMessagingHosts 目录放一个 com.seeu.bridge.json,写明中转程序在哪、只许我们这个插件连。
"""
import json
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOST_NAME = "com.seeu.bridge"
EXT_ID = "lbofonjjcompipempkdfpdbbfjanmgff"     # 由 extension/manifest.json 里的 key 算出,固定不变
SUPPORT = os.path.expanduser("~/Library/Application Support")
BROWSER_DIRS = {
    "Google Chrome": "Google/Chrome",
    "Microsoft Edge": "Microsoft Edge",
    "Brave": "BraveSoftware/Brave-Browser",
    "Arc": "Arc/User Data",
    "Chromium": "Chromium",
    "Vivaldi": "Vivaldi",
}


def _wrapper():
    """Chrome 要一个能直接执行的文件:写个小 sh 包一下(用系统 Python,-I 不读用户环境)。"""
    p = os.path.join(HERE, "host.sh")
    with open(p, "w") as f:
        f.write('#!/bin/sh\nexec /usr/bin/python3 -I "$(dirname "$0")/host.py" "$@"\n')
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def found():
    return {name: os.path.join(SUPPORT, d) for name, d in BROWSER_DIRS.items() if os.path.isdir(os.path.join(SUPPORT, d))}


def install():
    path = _wrapper()
    manifest = {"name": HOST_NAME, "description": "SeeU 浏览器助手本机中转", "path": path, "type": "stdio",
                "allowed_origins": [f"chrome-extension://{EXT_ID}/"]}
    done = []
    for name, d in found().items():
        nd = os.path.join(d, "NativeMessagingHosts")
        os.makedirs(nd, exist_ok=True)
        with open(os.path.join(nd, HOST_NAME + ".json"), "w") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        done.append(name)
    if not done:
        print("没找到 Chrome 同内核浏览器(Chrome / Edge / Brave / Arc / Chromium / Vivaldi),先装一个再来。")
        return 1
    print("✅ 已登记中转程序:" + "、".join(done))
    print("\n接下来在浏览器里加载插件(每个浏览器做一次):")
    print("  1. 地址栏打开 chrome://extensions(Edge 是 edge://extensions)")
    print("  2. 右上角打开「开发者模式」")
    print("  3. 点「加载已解压的扩展程序」,选这个文件夹:")
    print("     " + os.path.join(HERE, "extension"))
    print("  4. 插件编号应该是 " + EXT_ID + "(不是的话中转程序会拒绝连接,告诉 SeeU 维护者)")
    print("  5. 打开要让 SeeU 操作的网站,点右上角拼图图标里的 SeeU,选「允许这个网站」")
    return 0


def uninstall():
    n = 0
    for d in found().values():
        p = os.path.join(d, "NativeMessagingHosts", HOST_NAME + ".json")
        if os.path.exists(p):
            os.remove(p)
            n += 1
    print(f"已撤销 {n} 个浏览器的登记;插件本身请在扩展程序页面里移除。")
    return 0


if __name__ == "__main__":
    sys.exit(uninstall() if sys.argv[1:2] == ["uninstall"] else install())
