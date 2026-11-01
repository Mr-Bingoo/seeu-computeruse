"""借鼠标排队(开源版):同一时间只让一个 SeeU 借用系统鼠标键盘。

规则只留三条:一次一个;拿不到立刻返回(要等由调用方自己控制次数,有上限);持有方意外退出 / 超过 12 小时自动作废。
锁文件 ~/.seeu/locks/mouse.lock(JSON:pid、project、label、ts、epoch);测试时设 SEEU_LOCK_DIR=<临时目录>。
本模块不打印,返回结构化结果。
"""
import contextlib
import json
import os
import subprocess
import time

MAX_HOLD_HOURS = 12


def lock_dir():
    return os.environ.get("SEEU_LOCK_DIR") or os.path.expanduser("~/.seeu/locks")


def lock_file():
    return os.path.join(lock_dir(), "mouse.lock")


@contextlib.contextmanager
def _mutex():
    """读-判断-写包在一把 flock 里(锁旁边的空文件,锁文件本身会被替换)。"""
    import fcntl
    os.makedirs(lock_dir(), exist_ok=True)
    fd = os.open(os.path.join(lock_dir(), ".mouse.flock"), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def _start_time(pid):
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True,
                             timeout=3, env={**os.environ, "LC_ALL": "C"}).stdout.strip()
        return time.mktime(time.strptime(" ".join(out.split()), "%a %b %d %H:%M:%S %Y")) if out else None
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return None


def _stale_reason(d):
    """作废原因;还有效返回 None。"""
    if d.get("_corrupt") or not isinstance(d.get("epoch"), (int, float)):
        return "锁文件读不出来"
    if not _alive(d.get("pid")):
        return "持有的进程已退出"
    st = _start_time(d.get("pid"))
    if st is not None and st > d["epoch"] + 1:
        return "进程号被系统复用"
    if (time.time() - d["epoch"]) / 3600 > MAX_HOLD_HOURS:
        return f"持有超过 {MAX_HOLD_HOURS} 小时"
    return None


def _read():
    try:
        with open(lock_file()) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"_corrupt": True}


def status():
    """当前锁(带 stale / stale_reason),没有返回 None。"""
    d = _read()
    if d is None:
        return None
    d = dict(d)
    why = _stale_reason(d)
    d.update(stale=why is not None, stale_reason=why)
    return d


def acquire(project, label, pid=None, attended=True):
    """拿锁:ok=True 拿到(本进程已持有也算);ok=False 别人占着,held=持有者。attended 只为跟调用方写法一致。"""
    pid = os.getpid() if pid is None else int(pid)
    with _mutex():
        cur = status()
        if cur and not cur["stale"] and cur.get("pid") != pid:
            return {"ok": False, "held": cur}
        tmp = f"{lock_file()}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"pid": pid, "project": project, "label": label,
                       "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "epoch": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, lock_file())
        return {"ok": True, "held": None}


def release(pid=None):
    """放锁:只放本进程的。"""
    pid = os.getpid() if pid is None else int(pid)
    with _mutex():
        cur = _read()
        if not cur:
            return {"released": False, "none": True}
        if cur.get("pid") != pid:
            return {"released": False, "none": False, "held": cur}
        try:
            os.remove(lock_file())
        except FileNotFoundError:
            pass
        return {"released": True, "none": False}


def describe(d):
    if not d:
        return "(没人在借)"
    if d.get("_corrupt"):
        return "(锁文件坏了)"
    return f"「{d.get('project', '?')}」pid={d.get('pid')}「{d.get('label', '')}」起于 {d.get('ts', '?')}"
