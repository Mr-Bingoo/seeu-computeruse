"""更新 SeeU:python3 -m seeu 更新 [--check]   (英文别名 update)

只管用 git clone 装的那份(开源仓库 seeu-computeruse):拉 GitHub 上的新版,只快进、不合并、不覆盖用户改过的文件。
  --check  只看有没有新版,不动文件。
更新后:SeeU 小程序(seeu/launcher)源码变了、而且本机生成过小程序 → 重新生成并提醒用户重开授权(自签名,签名一变系统当新程序);
没变就不碰,省得用户白白重开授权(11-01 定)。最后提醒重开 AI 客户端,再跑一遍检查授权。
每个 git 调用都有超时,出错就停手说原因,不重试。
"""
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


class _Stop(Exception):
    pass


def _git(*args, timeout=GIT_TIMEOUT_S):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=timeout,
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
        if dirty:
            print(T("upd.dirty", files="\n".join("  " + l.split(None, 1)[-1] for l in dirty.splitlines())))
            return 1
        changed = _git("diff", "--name-only", "HEAD", "@{u}").splitlines()
        try:
            _git("merge", "--ff-only", "--quiet", "@{u}")
        except (_Stop, subprocess.TimeoutExpired) as e:
            print(T("upd.pull_fail", err=e))
            return 1
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
