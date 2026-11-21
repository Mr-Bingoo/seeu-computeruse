# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 认字(读不到控件的窗口:游戏、模拟器、自绘界面)。用开源的 Tesseract(要装:中文加 chi_sim 语言包)。
没装就抛 RuntimeError 说清怎么装,不偷偷降级。"""
import shutil
import subprocess


def langs():
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10).stdout
        return [x.strip() for x in out.splitlines()[1:] if x.strip()]
    except Exception:   # noqa: BLE001
        return []


def available():
    return bool(shutil.which("tesseract"))


def recognize(png):
    """返回 [{text, x, y, w, h}](相对图片左上角)。按行合并。"""
    if not available():
        from seeu.linux import distro
        raise RuntimeError(f"没装认字程序 Tesseract(装法:{distro.install_cmd('ocr')})")
    have = langs()
    lang = "+".join(x for x in ("chi_sim", "eng") if x in have) or "eng"
    out = subprocess.run(["tesseract", png, "-", "-l", lang, "--psm", "11", "tsv"], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError("认字出错:" + (out.stderr or "").strip()[:200])
    rows = [ln.split("\t") for ln in out.stdout.splitlines()[1:]]
    lines = {}
    for r in rows:
        if len(r) < 12 or not r[11].strip() or float(r[10] or -1) < 40:
            continue
        key = (r[2], r[3], r[4])               # 块、段、行
        x, y, w, h = int(r[6]), int(r[7]), int(r[8]), int(r[9])
        cur = lines.get(key)
        if cur is None:
            lines[key] = dict(text=r[11], x=x, y=y, w=w, h=h)
        else:
            sep = "" if (r[11][:1] > "⺀" and cur["text"][-1:] > "⺀") else " "     # 中文字之间不加空格
            x1 = max(cur["x"] + cur["w"], x + w)
            y1 = max(cur["y"] + cur["h"], y + h)
            cur.update(text=cur["text"] + sep + r[11], x=min(cur["x"], x), y=min(cur["y"], y))
            cur.update(w=x1 - cur["x"], h=y1 - cur["y"])
    return list(lines.values())
