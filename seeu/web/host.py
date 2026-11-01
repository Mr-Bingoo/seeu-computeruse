"""SeeU 浏览器助手 · 本机中转程序(C-1.4,10-20)

Chrome(及同内核浏览器)在插件连上来时自动启动本程序:标准输入/输出走 Chrome「本机消息」格式
(4 字节长度 + JSON),同时在 ~/.seeu/seeu_web/<浏览器>.sock 开一个本机 socket 给 SeeU(seeu/web.py)用。
SeeU 发一行 JSON 请求 → 转给插件 → 插件回包 → 按 id 回给 SeeU。不联网;只用标准库(Chrome 用 -I 启动)。
浏览器关了 / 插件断开 → 标准输入读到头 → 删 socket 退出。
C-0.5(SeeU,10-22):网站允许名单合成一份 = ~/.seeu/seeu_web/allow.json(开关那条路 aejs.py 用的同一个文件)。
  转给插件的每个请求都带上当前名单(allow 字段),插件「Chrome 授权了 且 在名单里」才碰;
  插件发来 {list: get|add|remove, origin, qid} → 改/读名单,回 {qid, list}。
"""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time

DIR = os.path.expanduser("~/.seeu/seeu_web")   # 不跟 SEEU_HOME:中转程序是浏览器拉起的,读不到用户的环境变量,三处要对得上就都写死(11-01)
BROWSERS = {"Google Chrome": "chrome", "Microsoft Edge": "edge", "Brave Browser": "brave", "Arc": "arc",
            "Chromium": "chromium", "Vivaldi": "vivaldi"}
TIMEOUT_MAX = 120

_out_lock = threading.Lock()
_waiting = {}            # id -> [Event, 回包]
_next = [0]
_info = {}
ALLOW_FILE = os.path.join(DIR, "allow.json")   # 🔴 跟 aejs.ALLOW_FILE 同一个文件、同一个格式(网站 = 协议://域名[:端口])
_list_lock = threading.Lock()


def load_allow():
    try:
        with open(ALLOW_FILE, encoding="utf-8") as f:
            lst = json.load(f)
        return [x for x in lst if isinstance(x, str)]
    except Exception:
        return []


def _norm_origin(o):
    """插件给的是 https://a.com/* 或 https://a.com,统一成 https://a.com;不是 http/https 的不收。"""
    o = (o or "").strip()
    if o.endswith("/*"):
        o = o[:-2]
    o = o.rstrip("/")
    if not (o.startswith("http://") or o.startswith("https://")) or "/" in o.split("://", 1)[1]:
        return None
    return o


def edit_allow(op, origin):
    """op = get / add / remove。返回改完的名单。"""
    with _list_lock:
        lst = load_allow()
        o = _norm_origin(origin)
        if op in ("add", "remove") and o:
            lst = [x for x in lst if x != o]
            if op == "add":
                lst.append(o)
            tmp = ALLOW_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lst, f, ensure_ascii=False, indent=1)
            os.replace(tmp, ALLOW_FILE)
        return lst


def browser_key():
    """看是谁启动了我(父进程),分出是哪个浏览器;认不出就叫 chromium。"""
    try:
        comm = subprocess.run(["ps", "-o", "comm=", "-p", str(os.getppid())], capture_output=True, text=True,
                              timeout=3).stdout.strip()
    except Exception:
        comm = ""
    for name, key in BROWSERS.items():
        if f"/{name}.app/" in comm or comm.endswith("/" + name):
            return key
    return "chromium"


def send(msg):
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    with _out_lock:
        sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
        sys.stdout.buffer.flush()


def read_loop(sock_path, status_path):
    """读插件发来的消息;读到头 = 浏览器那边断了,收拾退出。"""
    inp = sys.stdin.buffer
    while True:
        head = inp.read(4)
        if len(head) < 4:
            break
        n = struct.unpack("<I", head)[0]
        body = inp.read(n)
        try:
            msg = json.loads(body.decode("utf-8"))
        except Exception:
            continue
        if msg.get("list"):
            try:
                send({"qid": msg.get("qid"), "list": edit_allow(msg["list"], msg.get("origin"))})
            except Exception as e:
                send({"qid": msg.get("qid"), "error": str(e)})
            continue
        if msg.get("hello"):
            _info.update(version=msg.get("version"), ua=msg.get("ua"), hello_at=time.time())
            _write_status(status_path)
            continue
        w = _waiting.get(msg.get("id"))
        if w:
            w[1] = msg
            w[0].set()
    for p in (sock_path, status_path):
        try:
            os.remove(p)
        except OSError:
            pass
    os._exit(0)


def _write_status(path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(_info, pid=os.getpid()), f, ensure_ascii=False)
    os.replace(tmp, path)


def serve_client(conn):
    """一个 SeeU 连接:一行一个请求 {cmd, args, timeout},回一行。"""
    f = conn.makefile("rwb")
    try:
        for line in f:
            try:
                req = json.loads(line.decode("utf-8"))
            except Exception:
                f.write(b'{"ok":false,"error":"\\u8bf7\\u6c42\\u4e0d\\u662f JSON","code":"bad_req"}\n')
                f.flush()
                continue
            _next[0] += 1
            rid = _next[0]
            ev = threading.Event()
            _waiting[rid] = [ev, None]
            send({"id": rid, "cmd": req.get("cmd"), "args": req.get("args") or {}, "allow": load_allow()})
            tmo = min(float(req.get("timeout") or 30), TIMEOUT_MAX)
            if ev.wait(tmo):
                rep = _waiting.pop(rid)[1]
            else:
                _waiting.pop(rid, None)
                rep = {"ok": False, "error": f"插件 {tmo:.0f} 秒没回话", "code": "timeout"}
            rep.pop("id", None)
            f.write((json.dumps(rep, ensure_ascii=False) + "\n").encode("utf-8"))
            f.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    os.makedirs(DIR, exist_ok=True)
    key = browser_key()
    sock_path = os.path.join(DIR, key + ".sock")
    status_path = os.path.join(DIR, key + ".json")
    _info.update(browser=key, started_at=time.time())
    try:
        os.remove(sock_path)
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o600)          # 只有本用户能连
    srv.listen(8)
    _write_status(status_path)
    threading.Thread(target=read_loop, args=(sock_path, status_path), daemon=True).start()
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=serve_client, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
