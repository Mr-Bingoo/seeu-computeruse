# -*- coding: utf-8 -*-
"""SeeU Windows 版 · 认字(第 2 段,11-11):读不到控件的程序(模拟器、游戏、自绘界面)靠截图认字出清单。

用 Windows 自带的文字识别(Windows.Media.Ocr,经同目录 ocr.ps1 调,不用装 Python 包)。
⚠️ 要装了对应语言的「识别语言包」才能用(11-11 虚拟机里一个都没有)。没有就返回 available=False 和怎么装,不报错、不瞎猜。
装法(要管理员,用户自己做):设置 → 时间和语言 → 语言和区域 → 中文(简体)→ 语言选项 → 装「光学字符识别」;
或管理员 PowerShell:Add-WindowsCapability -Online -Name "Language.OCR~~~zh-CN~0.0.1.0"
"""
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "ocr.ps1")
HOWTO = ("Windows 没装文字识别语言包,认不了字。装法(要管理员,请用户自己做):设置 → 时间和语言 → 语言和区域 → 中文(简体)"
         "→ 语言选项 → 装「光学字符识别」;或管理员 PowerShell 运行 "
         "Add-WindowsCapability -Online -Name \"Language.OCR~~~zh-CN~0.0.1.0\"(英文用 en-US)")
_LANGS = []


def _run(args, timeout=30):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1] + args,
                       capture_output=True, timeout=timeout, creationflags=0x08000000)
    out = r.stdout.decode("utf-8", "replace").strip().splitlines()
    return json.loads(out[-1]) if out else {}


def langs():
    """能用的识别语言(只问一次)。"""
    if not _LANGS:
        try:
            _LANGS.append(list(_run(["-List"]).get("langs") or []))
        except Exception:
            _LANGS.append([])
    return _LANGS[0]


def available():
    return bool(langs())


def recognize(png_bytes_or_path):
    """认一张图。返回 dict(available, lang, lines=[{text, x, y, w, h}], note)。坐标是图片像素。"""
    if not available():
        return dict(available=False, lines=[], note=HOWTO)
    path, tmp = png_bytes_or_path, None
    if isinstance(png_bytes_or_path, (bytes, bytearray)):
        fd, tmp = tempfile.mkstemp(prefix="seeu_ocr_", suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(png_bytes_or_path)
        path = tmp
    try:
        ls = langs()
        lang = next((x for x in ls if x.lower().startswith("zh")), ls[0])   # 有中文先用中文(中文引擎也认英文字母和数字)
        d = _run([os.path.abspath(path), lang])
    except Exception as ex:
        return dict(available=True, lines=[], note=f"认字出错:{ex}")
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    if d.get("error"):
        return dict(available=False, lines=[], note=HOWTO)
    lines = d.get("lines") or []
    for ln in lines:
        ln["text"] = tidy(ln.get("text", ""))
    return dict(available=True, lang=d.get("lang"), lines=lines)


_CJK = r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]"


def tidy(text):
    """Windows 中文识别把每个汉字当一个词、用空格连(「画 笔」「6 个 字 符 , 共 6 个」,11-12 虚拟机实测),按名字点就对不上。
    去掉挨着汉字 / 中文标点那一侧的空格;英文单词之间的空格照留。"""
    import re
    t = re.sub(rf"(?<={_CJK}) +| +(?={_CJK})", "", str(text))
    return t.strip()
