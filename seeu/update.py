"""更新 SeeU:python3 -m seeu 更新 [--check]   (英文别名 update)

只管用 git clone 装的那份(开源仓库 seeu-computeruse):拉 GitHub 上的新版,只快进、不合并、不覆盖用户改过的文件。
  例外:只改过 seeu/设置.json(改设置、点 I See 都会改它)不算挡路 —— 先收起用户那份,更新完把用户改过的项放回新版的设置里(11-07)。
  --check  只看有没有新版,不动文件。
更新后:SeeU 小程序(seeu/launcher)源码变了、而且本机生成过小程序 → 重新生成并提醒用户重开授权(自签名,签名一变系统当新程序);
没变就不碰,省得用户白白重开授权(11-01 定)。最后提醒重开 AI 客户端,再跑一遍检查授权。
每个 git 调用都有超时,出错就停手说原因,不重试。
"""
import json
import os
import shutil
import subprocess
import sys

from seeu import version
from seeu.i18n import T, lang

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO_URL = "https://github.com/Mr-Bingoo/seeu-computeruse"
GIT_TIMEOUT_S = 60
BUILD_TIMEOUT_S = 180
SETTINGS_REL = "seeu/设置.json"
KEEP_SKIP = ("说明",)            # 说明文字跟新版走,不算用户的设置
SIDE_SUFFIX = ".updating"        # 收起设置期间放在设置文件旁边的备份(写回成功就删;进程中途被杀,下次运行更新时靠它恢复)


class _Stop(Exception):
    pass


def _git(*args, timeout=GIT_TIMEOUT_S):
    # core.quotepath=false:中文文件名(设置.json)原样给,不转成 \350\256… 这种写法
    r = subprocess.run(["git", "-C", ROOT, "-c", "core.quotepath=false", *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    if r.returncode != 0:
        raise _Stop((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"git {args[0]} 退出码 {r.returncode}")
    return r.stdout.strip()


def _show(path):
    """GitHub 上新版里的某个文件(没有就空串,不算出错)。"""
    try:
        return _git("show", "@{u}:" + path)
    except (_Stop, subprocess.TimeoutExpired):
        return ""


def _is_clone():
    try:
        return os.path.realpath(_git("rev-parse", "--show-toplevel")) == os.path.realpath(ROOT) and bool(_git("rev-parse", "--abbrev-ref", "@{u}"))
    except (_Stop, subprocess.TimeoutExpired):
        return False


def _settings_path():
    return os.path.join(ROOT, *SETTINGS_REL.split("/"))


def _write(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        _rm(tmp)                         # 写不成(磁盘满等)别留半个临时文件
        raise


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _dirty_paths(dirty):
    """改过的文件(跟 HEAD 比)。不从 status 那几行里切:_git 会去掉整段开头的空格,第一行切出来少一个字。
    工作区和暂存区各问一次再合起来(11-07 复查:文件 git add 过、工作区又改回原样时,只问工作区看不到它)。
    万一都给不出来(少见状态),退回 status 每行最后一段。"""
    paths = []
    for extra in ((), ("--cached",)):
        for l in _git("diff", "--name-only", *extra, "HEAD").splitlines():
            if l.strip() and l not in paths:
                paths.append(l)
    return paths or [l.split(None, 1)[-1].strip('"') for l in dirty.splitlines() if l.strip()]


def _settings_keep(paths):
    """改过的只有设置文件、而且两边都读得出来 → (用户那份原文 bytes, 用户改过的项);否则 None(照老规矩停手)。
    用户改过的项 = 跟装着的这一版原样不同的键(说明文字除外)。"""
    if paths != [SETTINGS_REL]:
        return None
    try:
        with open(_settings_path(), "rb") as f:
            raw = f.read()
        user = json.loads(raw.decode("utf-8"), object_pairs_hook=dict)
        base = json.loads(_git("show", "HEAD:" + SETTINGS_REL))
        if not isinstance(user, dict) or not isinstance(base, dict):
            return None
    except (OSError, ValueError, _Stop, subprocess.TimeoutExpired):
        return None
    mine = {k: v for k, v in user.items() if k not in KEEP_SKIP and (k not in base or base[k] != v)}
    return raw, mine


def _settings_restore(raw, mine):
    """更新完:把用户改过的项写进新版的设置文件。合不了(新版没这个文件、读不出来…)就把用户原来那份整份放回。
    返回 True = 合进去了;False = 整份放回;None = 两样都没写成(磁盘满、只读…),旁路备份留着下次再试。"""
    path = _settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            new = json.load(f)
        if not isinstance(new, dict):
            raise ValueError("not a dict")
        if mine:
            new.update(mine)
            _write(path, (json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return True
    except (OSError, ValueError):
        try:
            _write(path, raw)
            return False
        except OSError:
            return None


def _recover_side():
    """上次更新在「收起设置 → 写回」中间被杀(关终端窗口、被上层超时杀掉、断电,这些接不到异常):旁路备份还在。
    设置文件现在跟装着的这版原样一样(= 还没写回)→ 按旁路备份写回;已经不一样(用户后来又改过)→ 以现在的为准。然后删掉旁路备份。"""
    side = _settings_path() + SIDE_SUFFIX
    if not os.path.exists(side):
        return
    try:
        with open(side, encoding="utf-8") as f:
            d = json.load(f)
        clean = not _git("status", "--porcelain", "--untracked-files=no", "--", SETTINGS_REL)
    except (_Stop, subprocess.TimeoutExpired):
        return                          # 这次看不清,旁路备份留着
    except (OSError, ValueError):
        d, clean = None, False          # 旁路备份本身读不出来:没法用,删掉
    if clean and isinstance(d, dict) and isinstance(d.get("raw"), str) and isinstance(d.get("mine"), dict):
        if _settings_restore(d["raw"].encode("utf-8"), d["mine"]) is None:
            return
        if d["mine"]:
            print(T("upd.recovered", items="、".join(f"{k} = {v}" for k, v in d["mine"].items())))
    _rm(side)


def _rebuild_launcher():
    build = os.path.join(HERE, "launcher", "build.sh")
    try:
        r = subprocess.run(["sh", build], capture_output=True, text=True, timeout=BUILD_TIMEOUT_S)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"exit {r.returncode}")
        print(T("upd.launcher"))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(T("upd.launcher_fail", err=e, path=build))


def main(args=()):
    check_only = "--check" in args
    if not shutil.which("git"):
        print(T("upd.no_git"))
        return 1
    if not _is_clone():
        # 11-01 实测:npx skills add 把整个仓库(不带 .git)拷进 ~/.claude/skills/seeu 这类技能目录,更新要走 npx skills update
        in_skills = os.sep + "skills" + os.sep in ROOT + os.sep
        print(T("upd.npx") if in_skills else T("upd.not_git", url=REPO_URL))
        return 1
    try:
        if not check_only:
            _recover_side()
        old = _git("rev-parse", "--short", "HEAD")
        old_ver = version.current()
        try:
            _git("fetch", "--quiet")
        except (_Stop, subprocess.TimeoutExpired) as e:
            print(T("upd.fetch_fail", err=e))
            return 1
        behind = int(_git("rev-list", "--count", "HEAD..@{u}"))
        ahead = int(_git("rev-list", "--count", "@{u}..HEAD"))
        if behind == 0:
            print(T("upd.latest", ver=old_ver, rev=old))
            return 0
        new_ver = _show("seeu/VERSION").strip() or old_ver
        text = _show("CHANGELOG.en.md" if lang() == "en" else "CHANGELOG.md")
        notes = version.notes(text, since=old_ver) if new_ver != old_ver else ""
        if notes:                                           # 11-01:有更新说明就给说明,没有(没改版本号的小修)才列提交
            print(T("upd.notes", new=new_ver, old=old_ver, notes=notes))
        else:
            log = _git("log", "--oneline", "--no-decorate", "-n", "10", "HEAD..@{u}")
            print(T("upd.new", n=behind, log="\n".join("  · " + l for l in log.splitlines())))
        if check_only:
            return 0
        if ahead:
            print(T("upd.diverged"))
            return 1
        dirty = _git("status", "--porcelain", "--untracked-files=no")
        keep = None
        if dirty:
            paths = _dirty_paths(dirty)
            keep = _settings_keep(paths)
            if keep is None:
                print(T("upd.dirty", files="\n".join("  " + p for p in paths)))
                return 1
        # --no-renames:新版要是给设置文件改了名,默认只列新名字,会被当成「没动设置文件」→ 不收起 → 快进被 git 拒,而且每次都这样
        changed = _git("diff", "--name-only", "--no-renames", "HEAD", "@{u}").splitlines()
        if keep and SETTINGS_REL not in changed:
            keep = None                                     # 新版没动设置文件(多数更新如此):不用收起,带着你的改动直接快进,设置文件全程不碰
        side = _settings_path() + SIDE_SUFFIX
        try:
            if keep:                                        # 先留一份旁路备份,再把设置文件摆回原样(暂存区一起),快进才过得去
                _write(side, json.dumps({"raw": keep[0].decode("utf-8"), "mine": keep[1]}, ensure_ascii=False).encode("utf-8"))
                _git("checkout", "HEAD", "--", SETTINGS_REL)
            _git("merge", "--ff-only", "--quiet", "@{u}")
        except BaseException as e:                          # 没更新成(含 Ctrl-C):用户的设置原样放回
            if keep:
                try:
                    _write(_settings_path(), keep[0])
                    _rm(side)
                except OSError:
                    pass                                    # 放不回(磁盘满):旁路备份留着,下次运行时恢复
            if not isinstance(e, (_Stop, subprocess.TimeoutExpired, OSError)):
                raise
            print(T("upd.pull_fail", err=e))
            return 1
        if keep:
            try:
                merged = _settings_restore(*keep)
            except BaseException:                           # 写回途中被打断:尽力把原来那份整份放回;放不回也还有旁路备份,下次运行更新时恢复
                try:
                    _write(_settings_path(), keep[0])
                    _rm(side)
                except OSError:
                    pass
                raise
            if merged is None:
                print(T("upd.keep_fail", path=side))
            else:
                _rm(side)
                if not merged:
                    print(T("upd.kept_whole"))
                elif keep[1]:
                    print(T("upd.kept", items="、".join(f"{k} = {v}" for k, v in keep[1].items())))
        print(T("upd.done", oldv=old_ver, newv=version.current(), old=old, new=_git("rev-parse", "--short", "HEAD")))
    except (_Stop, subprocess.TimeoutExpired, ValueError) as e:
        print(T("upd.pull_fail", err=e))
        return 1
    if any(p.startswith("seeu/launcher/") for p in changed) and os.path.isdir(os.path.join(HERE, "launcher", "SeeU.app")):
        _rebuild_launcher()
    print(T("upd.restart"))
    print("\n" + T("upd.check"))
    from seeu import doctor
    try:
        doctor.main([])
    except SystemExit:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
