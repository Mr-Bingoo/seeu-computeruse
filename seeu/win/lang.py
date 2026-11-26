# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 命令行提示的英文。

代码里的提示照旧写中文(测试、别的调用方按中文字判断),只在打印给人看的出口过一遍 tx():
语言是英文时,先按各模块自己的片段表换(长的先换),再过 Mac 版的 reason_en.to_en(结果原因 + 中文标点)。
语言跟 Mac 一样:seeu/设置.json「语言」,环境变量 SEEU_LANG=zh|en 优先。没收录的片段原样留中文,不报错。
不依赖 Windows,任何平台都能导入(离线测试用)。
"""


def is_en():
    try:
        from seeu.i18n import lang
        return lang() == "en"
    except Exception:   # noqa: BLE001
        return False


def tx(text, table=(), force=None):
    """force=True / False:不看设置,强制转 / 不转(测试用)。"""
    if not (is_en() if force is None else force) or not isinstance(text, str):
        return text
    for zh, en in sorted(table, key=lambda p: -len(p[0])):
        if zh in text:
            text = text.replace(zh, en)
    try:
        from seeu.reason_en import to_en
        return to_en(text)
    except Exception:   # noqa: BLE001
        return text


def L(zh, en):
    return en if is_en() else zh
