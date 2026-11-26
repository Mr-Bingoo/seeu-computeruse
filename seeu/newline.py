"""打字遇到换行按什么(默认「按推荐」)。

换行改按 Shift+回车(微信 / Slack 这类「回车就发送」的框里,多行字原来第一行就发出去了)。
但下面这几类程序里 Shift+回车另有意思,照旧按单独的回车:
- VS Code 及同一家底子的编辑器(Cursor、Trae、VSCodium、Windsurf):装了 Python 扩展时 Shift+回车 = 把这行送去终端运行;
- Jupyter(桌面版、笔记本):Shift+回车 = 运行这一格;
- 表格(Excel、Numbers、LibreOffice、WPS):Shift+回车 = 往上走一格,多行字会倒着盖掉上面的格子。
三个系统共用:Mac 传包名 + 显示名,Windows 传 exe,Linux 传 comm / wm_class / app_id。纯计算,不碰系统。"""

PLAIN_ENTER = (
    # 包名(Mac)
    "com.microsoft.vscode", "com.vscodium", "com.todesktop.230313mzl4w4u92", "com.trae.app", "com.exafunction.windsurf",
    "org.jupyter.jupyterlab-desktop", "com.microsoft.excel", "com.apple.iwork.numbers", "org.libreoffice.script",
    "com.kingsoft.wpsoffice.mac",
    # 程序名 / 显示名(三个系统)
    "visual studio code", "code", "code.exe", "code-oss", "codium", "vscodium", "vscodium.exe", "cursor", "cursor.exe",
    "trae", "trae.exe", "windsurf", "windsurf.exe", "jupyterlab", "jupyterlab.exe", "jupyter",
    "microsoft excel", "excel", "excel.exe", "numbers", "libreoffice", "soffice", "soffice.bin", "soffice.exe",
    "scalc", "scalc.exe", "libreoffice-calc", "et", "et.exe", "wps", "wps.exe", "wpsoffice",
)


def plain_enter(*names):
    """names 里有一个对上名单就返回 True(换行按单独的回车);都对不上返回 False(按 Shift+回车)。"""
    for n in names:
        t = str(n or "").strip().lower()
        if not t:
            continue
        if t in PLAIN_ENTER or t.rsplit("/", 1)[-1] in PLAIN_ENTER or t.rsplit("\\", 1)[-1] in PLAIN_ENTER:
            return True
    return False


def mods(*names):
    """换行该带的修饰键:() 或 ("shift",)。"""
    return () if plain_enter(*names) else ("shift",)
