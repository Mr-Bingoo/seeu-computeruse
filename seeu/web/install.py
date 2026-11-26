"""SeeU 浏览器助手 · 安装 / 卸载本机中转程序

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


# 插件版的代码文件夹每次更新都会换位置 → 中转程序和插件文件抄一份到固定的地方再登记,
# 不然更新后浏览器找不到中转程序、「加载已解压的扩展程序」选的那个文件夹也没了。host.py 只用标准库,单拿出来能跑。
STABLE = os.path.expanduser("~/.seeu/seeu_web/app")     # 同 host.py 的 DIR,不跟 SEEU_HOME


def _plugin():
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
        from seeu.where import as_plugin
        return as_plugin(HERE)
    except Exception:   # noqa: BLE001
        return False


def _sync(src, dst):
    """把 src(文件或文件夹)抄到 dst,只抄内容不一样的;dst 里多出来的文件删掉。"""
    import filecmp
    import shutil
    if os.path.isfile(src):
        if not (os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False)):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst + ".tmp")
            os.replace(dst + ".tmp", dst)
        return
    os.makedirs(dst, exist_ok=True)
    names = set(os.listdir(src))
    for n in names:
        if not n.startswith("."):
            _sync(os.path.join(src, n), os.path.join(dst, n))
    for n in set(os.listdir(dst)) - names:
        p = os.path.join(dst, n)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def base():
    """中转程序和插件文件所在的文件夹:git 版 = 代码旁边;插件版 = 抄到 STABLE。"""
    if not _plugin():
        return HERE
    _sync(os.path.join(HERE, "host.py"), os.path.join(STABLE, "host.py"))
    _sync(os.path.join(HERE, "extension"), os.path.join(STABLE, "extension"))
    return STABLE


def refresh():
    """插件版服务启动时调:登记过(STABLE 在)就把新版的中转程序、插件文件抄过去。没登记过不动。"""
    if _plugin() and os.path.isdir(STABLE):
        base()


def _wrapper():
    """Chrome 要一个能直接执行的文件:写个小 sh 包一下(用系统 Python,-I 不读用户环境)。"""
    p = os.path.join(base(), "host.sh")
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
    print("     " + os.path.join(base(), "extension"))
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
