"""SeeU Windows 版(预览)。

Mac 版代码一行不动,Windows 的实现全在这个目录:api(系统接口)、window(找窗口、截窗口)、inputs(后台点击打字滚动、借前台)、
uia(控件清单、读文字、密码框)、safety(安全底线)、act(动作层,用法和返回格式跟 Mac 版一样)。
在 Windows 上 `import seeu; seeu.tap(...)` 自动走这里(见 seeu/__init__.py)。
"""
