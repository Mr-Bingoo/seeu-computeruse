"""SeeU 用到的通用模块(悬浮窗、代理光标、截图、认字、让路等)。"""
import os


def home(*parts):
    """SeeU 的状态/日志目录:先看环境变量 SEEU_HOME,没设就是 ~/.seeu。传参就拼成子路径;不自动建目录。"""
    base = os.environ.get("SEEU_HOME") or os.path.expanduser("~/.seeu")
    return os.path.join(base, *parts)
