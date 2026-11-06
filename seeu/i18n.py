# -*- coding: utf-8 -*-
"""SeeU 中英文对照表(10-21 用户定:开源做中文 + 英文两版,按钮、提示、悬浮标都要两套)。

用法:
    from seeu.i18n import T, step
    T("btn.collapse")                  # 收起 / Hide
    T("overlay.wait", what="Siri", secs=15)
    step("打字")                        # 步骤名(代码里流转的是中文名)→ 当前语言
语言:seeu/设置.json「语言」= 自动(跟系统)| 中文 | English;环境变量 SEEU_LANG=zh|en 优先。
新写给用户看的文字都加到 TEXT 里,别再写死;没收录的 key 原样返回(不会报错)。
"""
import json
import os
import time

TEXT = {
    # 悬浮标 / 卡片按钮(英文要短:卡片 300 宽一排四个)
    "btn.isee": ("I See", "I See"),
    "btn.why": ("原因", "Why"),          # 10-30:AI 每一步的原因开关(只在 AI 任务出现)
    "btn.halo_real": ("抢占", "Takeover"),
    "btn.halo_bg": ("被控", "Controlled"),
    "btn.light": ("灯光", "Glow"),          # 10-21 用户定:光圈开关叫「灯光」,关着时显示「灭灯泡 + 灯光」
    "btn.light_off": ("关", "Off"),
    "btn.collapse": ("收起", "Hide"),
    "btn.view_screen": ("看画面", "Screen"),
    "btn.view_steps": ("看操作", "Steps"),
    "card.doing": ("正在{step}", "{step}…"),
    "card.idle": ("等下一步", "Waiting"),
    "card.no_screen": ("后台标签页没有画面可看", "Background tab, nothing to show"),
    "card.isee_note": ("我已知风险，授权 AI 执行 · 卡住时请立即报告！", "I accept the risks and authorize AI to act · report if stuck right away!"),
    "island.cap": ("SeeU · {n} 个任务", "SeeU · {n} tasks"),
    "island.cap_borrow": (" · 借鼠标中", " · using mouse"),
    "island.cap_stuck": (" · 有卡住", " · stuck"),
    "island.cap_skip": (" · 跳过 {n} 项", " · {n} skipped"),
    "island.borrow": ("借用鼠标 · ", "Using mouse · "),
    "island.stuck": ("卡住了 · ", "Stuck · "),
    "island.now": ("刚刚", "just now"),
    "island.sec": ("{n} 秒前", "{n}s ago"),
    "island.min": ("{n} 分钟前", "{n}m ago"),
    "island.note_borrow": ("正在用你的鼠标,别动它,马上还你", "Using your mouse, hands off for a moment"),
    "island.skipped": ("已跳过 {n} 项,做完一起告诉你", "{n} skipped, will report at the end"),
    "island.doing": ("正在", "Now: "),
    "island.fold": ("折叠 ⌃", "Fold ⌃"),
    "island.operating": ("操作 {app}", "Working in {app}"),
    "card.screen_hidden": ("隐身中,看不了画面", "Working hidden, no screen to show"),
    "card.hidden_note": ("{app} 在后台隐身干活,别点开它", "{app} is working hidden, don't open it"),
    "card.stuck_at": ("卡在: {step}", "Stuck at: {step}"),
    "card.stuck": ("卡住了 · {step}", "Stuck · {step}"),
    "card.screen_off": ("网页模块操作的可能是后台标签页,不放画面", "May be a background tab, no live view"),
    "card.why": ("原因: {why}", "Why: {why}"),
    "card.todo": ("怎么办: {todo}", "What to do: {todo}"),
    # 10-27 用户定:自动推「在做什么」、借鼠标 / 卡住自动展开写清楚
    "card.near": ("点「{x}」附近", "Clicking near “{x}”"),
    "card.on": ("点「{x}」", "Clicking “{x}”"),               # 10-28:点在字上不写「附近」
    "card.borrow": ("正在用你的鼠标", "Using your mouse"),
    "card.borrow_at": ("正在用你的鼠标(点「{x}」附近)", "Using your mouse (near “{x}”)"),
    "card.borrow_on": ("正在用你的鼠标(点「{x}」)", "Using your mouse (on “{x}”)"),
    "card.borrow_note": ("别动鼠标,几秒后还你", "Don't move the mouse, back in a few seconds"),
    "card.stuck_why": ("卡住了: {why}", "Stuck: {why}"),
    # 步骤名(代码里用中文名流转,显示时再翻)
    "step.点击": ("点击", "Clicking"),
    "step.打字": ("打字", "Typing"),
    "step.按键": ("按键", "Pressing keys"),
    "step.读网页": ("读网页", "Reading page"),
    "step.勾选": ("勾选", "Checking"),
    "step.选下拉框": ("选下拉框", "Choosing option"),
    "step.滚动": ("滚动", "Scrolling"),
    "step.长按": ("长按", "Long-pressing"),           # 10-30:MCP 告诉悬浮窗这一步是什么动作
    "step.点菜单": ("点菜单", "Using menu"),
    "step.回主屏": ("回主屏", "Going home"),
    "step.打开 App": ("打开 App", "Opening app"),
    "step.开标签页": ("开标签页", "Opening tab"),
    "step.列标签页": ("列标签页", "Listing tabs"),
    # 后台点击给系统浮层让路(bgclick.wait_overlays)
    "overlay.wait": ("⏸ SeeU 等你关掉 {what} 再点(最多 {secs} 秒)", "⏸ SeeU waits for you to close {what} (up to {secs}s)"),
    "overlay.timeout": ("⚠️ SeeU 等了 {secs} 秒浮层还开着,照点了(可能把它收起): {what}",
                        "⚠️ {what} still open after {secs}s, clicking anyway (it may close)"),
    # 11-01 借用鼠标「问我」档的提示条
    "ask.title": ("SeeU 要借你的鼠标", "SeeU needs your mouse"),
    "ask.body": ("{what}:请回到 AI 对话里选「仅此一次 / 自动使用 / 拒绝」", "{what}: go back to the AI chat and choose \"just this once / allow for this session / refuse\""),
    "ask.tap": ("点一下", "A click"), "ask.type": ("打字", "Typing"), "ask.drag": ("拖动", "A drag"),
    # 11-01 更新命令(python3 -m seeu 更新 / update)
    "upd.not_git": ("这份 SeeU 不是用 git clone 装的(或者是开发用的本机版),没法自动更新。到 {url} 下载新版覆盖,或重新 git clone。",
                    "This copy of SeeU wasn't installed with git clone (or it's a development copy), so it can't update itself. Download the new version from {url}, or git clone it again."),
    "upd.npx": ("这份 SeeU 是用 npx skills 装的,更新请运行:npx skills update seeu(装完把 AI 客户端退出再打开)。",
                "This copy of SeeU was installed with npx skills; to update run: npx skills update seeu (then quit and reopen your AI client)."),
    "upd.no_git": ("没找到 git 命令:先装 Xcode 命令行工具(xcode-select --install),再运行一次。",
                   "git not found: install the Xcode Command Line Tools (xcode-select --install), then run this again."),
    "upd.fetch_fail": ("连不上 GitHub,这次没更新(原因:{err})。等网络好了再运行一次。",
                       "Couldn't reach GitHub, nothing was updated ({err}). Run this again when the network is back."),
    "upd.latest": ("已经是最新版(v{ver},{rev}),不用更新。", "Already up to date (v{ver}, {rev})."),
    "upd.notes": ("有新版 v{new}(你现在是 v{old}),更新说明:\n\n{notes}", "New version v{new} available (you have v{old}). What's new:\n\n{notes}"),
    "ver.line": ("版本 v{v}", "Version v{v}"),
    "upd.dirty": ("你改过 SeeU 的这些文件,为了不覆盖你的改动,这次没更新:\n{files}\n要更新:先把改动挪走(或 git stash),再运行一次。",
                  "You have changed these SeeU files; to avoid overwriting them, nothing was updated:\n{files}\nTo update: move your changes away (or git stash), then run this again."),
    "upd.kept": ("你改过的设置已经放回新版里:{items}", "Your settings were carried over to the new version: {items}"),
    "upd.keep_fail": ("⚠️ 新版装好了,但你的设置没能写回去(磁盘满或文件只读?)。备份在 {path},腾出空间后再运行一次更新就会自动放回。",
                      "⚠️ The new version is installed, but your settings could not be written back (disk full or read-only?). A backup is at {path}; free some space and run update again to restore them."),
    "upd.recovered": ("上次更新中途被打断,你的设置现在已经放回:{items}", "The last update was interrupted; your settings have now been restored: {items}"),
    "upd.kept_whole": ("新版的设置文件没能合并,已把你原来那份设置文件整份放回(设置照旧;新版要是加了新设置项,先用默认值)。",
                       "Could not merge the new settings file, so your old settings file was put back as it was (your settings are unchanged; any new options use their defaults)."),
    "upd.diverged": ("你本地有自己的提交,跟 GitHub 上的新版对不上,这次没更新。请手动 git pull 处理。",
                     "Your copy has its own commits that don't match the new version on GitHub, so nothing was updated. Please run git pull yourself."),
    "upd.new": ("有新版:{n} 个更新\n{log}", "New version available: {n} change(s)\n{log}"),
    "upd.done": ("✅ 更新好了:v{oldv} → v{newv}({old} → {new})", "✅ Updated: v{oldv} → v{newv} ({old} → {new})"),
    "upd.pull_fail": ("拉取新版失败,这次没更新(原因:{err})。", "Pulling the new version failed, nothing was updated ({err})."),
    "upd.launcher": ("SeeU 小程序有改动,已经重新生成。⚠️ 系统会把它当成新程序:请到「系统设置 → 隐私与安全性」的「辅助功能」和「屏幕与系统录音」里,把 SeeU 关掉再打开一次。",
                     "The SeeU helper app changed and was rebuilt. ⚠️ macOS treats it as a new app: in System Settings → Privacy & Security, turn SeeU off and on again under Accessibility and Screen & System Audio Recording."),
    "upd.launcher_fail": ("SeeU 小程序有改动,但重新生成失败(原因:{err})。可以手动运行:sh {path}",
                          "The SeeU helper app changed but rebuilding it failed ({err}). You can run it yourself: sh {path}"),
    "upd.restart": ("已经开着的 AI 客户端还在用旧版:把 Claude / Codex / Cursor 这些退出再打开,新版才生效。",
                    "AI clients that are already open still use the old version: quit and reopen Claude / Codex / Cursor etc. to use the new one."),
    "upd.check": ("顺便检查一下授权:", "Checking permissions:"),
}

_C = {"t": 0.0, "lang": "zh"}
_SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "设置.json")


def lang():
    """当前语言 'zh' | 'en'。设置文件每 2 秒最多读一次。"""
    env = (os.environ.get("SEEU_LANG") or "").strip().lower()
    if env in ("zh", "en"):
        return env
    now = time.time()
    if now - _C["t"] > 2.0:
        _C["t"] = now
        try:
            with open(_SETTINGS, encoding="utf-8") as f:
                v = str(json.load(f).get("语言", "中文")).strip().lower()
        except Exception:
            v = "中文"
        if v in ("english", "en", "英文"):
            _C["lang"] = "en"
        elif v in ("自动", "auto"):
            try:
                from Foundation import NSLocale
                first = str(NSLocale.preferredLanguages()[0])
            except Exception:
                first = "zh"
            _C["lang"] = "zh" if first.startswith("zh") else "en"
        else:
            _C["lang"] = "zh"
    return _C["lang"]


def T(key, **kw):
    pair = TEXT.get(key)
    if not pair:
        return key
    s = pair[1 if lang() == "en" else 0]
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def step(name):
    """步骤中文名 → 当前语言;没收录的原样返回。"""
    return T("step." + name) if ("step." + name) in TEXT else name
