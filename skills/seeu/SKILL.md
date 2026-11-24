---
name: seeu
description: Use SeeU to see and operate apps on the user's computer (Mac, Windows or Linux) in the background — look at a window, click, type, scroll — without taking the mouse or switching the frontmost app. Use it when the user asks you to operate a desktop app (TextEdit, Notes, Notepad, VS Code…), a web page, iPhone Mirroring or an emulator, or says "use SeeU" / "click / fill in / check something in X for me". Don't use SeeU for things that have their own tools, like writing files or running commands.
---

# SeeU (plugin): operate this computer in the background

This copy of SeeU was installed as a plugin, so **its MCP tools (seeu_check, seeu_see, seeu_tap…) are already connected**.
Reply to the user in the user's language; this file is in English only because it is written for you.

## Before the first task
1. Call `seeu_check`.
   - If it says SeeU is getting ready (installing its Python libraries on first use), tell the user in one short line,
     wait about 30 seconds and call `seeu_check` again. Nothing is needed from the user while it installs.
   - If a permission is missing, pass its message to the user word for word and wait for them to turn it on.
     Never open or click System Settings yourself.
2. **Do not run `python3 -m seeu install …` / `接入`**: the plugin already connected SeeU, and connecting it again would add a
   second copy of the same tools. To update SeeU, the user updates the plugin (Claude Code: `claude plugin update seeu`; Codex: `codex plugin marketplace upgrade seeu-computeruse`), then starts a new session.

## How to work
Read the guide for this system first, then follow it. The paths are relative to the plugin's own folder
(two levels up from this file); skip their "install / connect" steps, everything else applies as written:

| System | Guide |
|---|---|
| macOS | `seeu/skill/SKILL.md` |
| Windows | `seeu/win/skill/SKILL.md` |
| Linux (GNOME) | `seeu/linux/skill/SKILL.md` |

On Linux, SeeU also needs a few system packages and its small GNOME helper. If `seeu_check` reports either as missing:
give the user the package command it shows (it needs sudo, so the user runs it), then run
`python3 -m seeu check --fix` from the plugin's folder, and only at the end ask the user to log out and back in once
(that ends this conversation).

When the guides mention running `python3 -m seeu …` on the command line, run it from the plugin's folder
(on Windows write `python` instead of `python3`).
