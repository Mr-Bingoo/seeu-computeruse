"""SeeU 版本号和更新说明(11-01)。

对外版本从 v1.0.0 起(公开那天),每发一版:改 seeu/VERSION,并在 CHANGELOG.md / CHANGELOG.en.md 顶上加一段「## vX.Y.Z(日期)」。
内部测完去掉 Beta 后跟会话版本号同步(用户 11-01 定):C-1.0 = v1.0.0,C-1.1 = v1.1.0,补丁 C-1.1.1 = v1.1.1。更新命令用 notes() 挑出比用户手上新的那几段给人看。
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
_HEAD = re.compile(r"^## v(\d+(?:\.\d+)*)", re.M)


def current():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def _key(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()


def notes(text, since=None):
    """CHANGELOG 全文 → 比 since 新的各段(原样拼起来);since 为空只给最新一段;找不到段落给空串。"""
    heads = list(_HEAD.finditer(text or ""))
    out = []
    for i, m in enumerate(heads):
        if since and _key(m.group(1)) <= _key(since):
            break
        out.append(text[m.start():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip())
        if not since:
            break
    return "\n\n".join(out)
