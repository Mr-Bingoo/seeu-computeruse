# -*- coding: utf-8 -*-
"""SeeU Linux 版 · 认发行版,给提示里的装软件命令(11-21 C-3.4,为 Fedora / Debian 补测加)。

Ubuntu / Debian 一家用 apt,Fedora 一家用 dnf;认不出来按 apt(第一版只测过 Ubuntu)。
提示里只换命令那一段,前后的中文照旧(英文对照表按片段换,不受影响)。
"""

# 每样东西在两家的包名:(apt, dnf)
PKGS = {
    "ocr": ("tesseract-ocr tesseract-ocr-chi-sim", "tesseract tesseract-langpack-chi_sim"),
    "atspi": ("python3-gi gir1.2-atspi-2.0", "python3-gobject at-spi2-core"),
    "git": ("git", "git"),
    "pil": ("python3-pil", "python3-pillow"),     # 截图裁剪要用;Debian 的 GNOME 默认没装(11-21 C-3.4 实测)
}


def _os_release(path="/etc/os-release"):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                k, _, v = ln.strip().partition("=")
                if k:
                    out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def manager(path="/etc/os-release"):
    """'dnf'(Fedora / RHEL 一家)或 'apt'(其余,含 Ubuntu / Debian)。"""
    r = _os_release(path)
    ids = (r.get("ID", "") + " " + r.get("ID_LIKE", "")).lower().split()
    return "dnf" if any(x in ("fedora", "rhel", "centos") for x in ids) else "apt"


def browser_cmd(path="/etc/os-release"):
    """装 Chromium 的命令:Ubuntu 只有 snap 版(apt 的 chromium-browser 只是跳去 snap);Debian 用 apt;Fedora 用 dnf。"""
    if manager(path) == "dnf":
        return "sudo dnf install chromium"
    r = _os_release(path)
    return "sudo snap install chromium" if r.get("ID", "").lower() == "ubuntu" else "sudo apt install chromium"


def install_cmd(what, path="/etc/os-release"):
    """如 install_cmd('ocr') → 'sudo dnf install tesseract tesseract-langpack-chi_sim'。"""
    m = manager(path)
    return f"sudo {m} install {PKGS[what][1 if m == 'dnf' else 0]}"
