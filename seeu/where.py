"""SeeU 装在哪、设置文件放哪(11-22 C-3.7,做插件版)。只用标准库:Mac / Windows / Linux、哪个进程都能 import。

插件版 = 用户在 Claude Code / Codex 里从插件市场装的那份:代码被拷进客户端自己的插件文件夹
(~/.claude/plugins/cache/…、~/.codex/plugins/cache/…),**插件一更新整个文件夹就换掉**。
所以插件版的设置(借用鼠标、语言、I See…)不能跟代码放一起,改存到用户自己的 ~/.seeu/设置.json
(开源包里是 ~/.seeu/设置.json);第一次用时从老地方抄一份(以前用 git 装过的,设置原样带过来)。
用 git clone 装的、本机开发用的这份:设置照旧在代码旁边的 seeu/设置.json,什么都不变。
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(HERE, "设置.json")                 # 跟代码一起发的那份(git 版就用它;插件版只当初始值)
MINE = os.path.expanduser("~/.seeu/设置.json")           # 插件版用的那份。不跟 SEEU_HOME 走(同 isee 的密钥):各家客户端可能各设各的
try:                                                        # 「SeeU 装在这儿」的纸条(install.write_pointer 写,跟 SEEU_HOME 走)
    from seeu_lib import home as _home
    POINTER = os.path.normpath(_home("seeu_server.json"))
except Exception:   # noqa: BLE001
    POINTER = os.path.expanduser("~/.seeu/seeu_server.json")
_MARKS = ("/plugins/cache/",)   # Claude Code ~/.claude/plugins/cache/…(设了 CLAUDE_CONFIG_DIR 也是 …/plugins/cache/)、Codex ~/.codex/plugins/cache/…


def as_plugin(path=HERE):
    """这份 SeeU 是不是从插件市场装的(按所在文件夹认)。环境变量 SEEU_AS_PLUGIN=1/0 可以硬指定(只给测试用)。"""
    v = os.environ.get("SEEU_AS_PLUGIN")
    if v in ("0", "1"):
        return v == "1"
    p = os.path.realpath(path).replace("\\", "/").lower() + "/"
    return any(m in p for m in _MARKS)


def _old_settings():
    """以前装过的那份(git 版)的 设置.json:看纸条上记的服务位置;纸条记的也是插件版、或文件不在,就没有。"""
    try:
        with open(POINTER, encoding="utf-8") as f:
            server = json.load(f).get("server") or ""
    except Exception:   # noqa: BLE001
        return None
    d = os.path.dirname(os.path.abspath(server))
    if os.path.basename(d).lower() in ("win", "linux"):     # Windows / Linux 的服务在 seeu/win、seeu/linux 下面
        d = os.path.dirname(d)
    p = os.path.join(d, "设置.json")
    return p if os.path.isfile(p) and not as_plugin(d) else None


def settings_file():
    """设置文件的路径。环境变量 SEEU_SETTINGS_FILE 优先(开发测试用);git 版 = 代码旁边那份;
    插件版 = ~/.seeu/设置.json,没有就先抄一份(老 git 版的 → 跟插件一起发的),抄不成就退回用代码旁边那份(只读也能跑)。"""
    env = os.environ.get("SEEU_SETTINGS_FILE")
    if env:
        return env
    if not as_plugin():
        return SHIPPED
    if os.path.isfile(MINE):
        return MINE
    src = _old_settings() or SHIPPED
    try:
        os.makedirs(os.path.dirname(MINE), exist_ok=True)
        tmp = f"{MINE}.{os.getpid()}.tmp"
        shutil.copyfile(src, tmp)
        if os.path.isfile(MINE):                            # 两个服务同时第一次启动:别人先抄好了就用别人的
            os.remove(tmp)
        else:
            os.replace(tmp, MINE)
        return MINE
    except OSError:
        return SHIPPED
