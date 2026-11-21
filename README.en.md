<div align="center">

# SeeU

> *You see SeeU, I know you see. I See.*

**Let your AI see the screen, click and type on your Mac, Windows PC or Linux machine in the background... working side by side with you, without getting in each other's way!**

[中文](README.md) | English

For macOS, plus Windows and Linux previews

</div>

https://github.com/user-attachments/assets/1ee86433-e46b-4711-96fd-4e398d972ca5

The name comes from CU (Computer Use — letting AI operate a computer), pronounced the same: *see first, then act*.

It puts a second, purple proxy cursor on screen that works for the AI. Looking, clicking, typing and scrolling all happen in the background, without taking your mouse or switching your frontmost window. You can keep writing and chatting while it does its job next to you — click the SeeU floating badge to see what the AI is doing.

## Things you can say

Once installed, just ask your AI (Claude, Codex, Cursor…) — the examples are Mac ones; on other systems, swap in the matching scenario:

```
"Use SeeU to create a new note in Notes with today's to-dos"
"See which files are on my Desktop and whether they need tidying up"
"Open a page in a background Safari tab and tell me what it says"
"Open a game on my phone through iPhone Mirroring and do the daily check-in"
"Watch the first test case in VS Code until it finishes"
```

## What SeeU can do for you

Before we get to what SeeU can do, one thing to know: every step is checked against the screen; if an action didn't take effect, SeeU tries another way, or stops and tells you where it's stuck, instead of clicking blindly. More in [What is SeeU](docs/What-is-SeeU.md).

**On all three systems:**

| Scenario | How SeeU does it |
|---|---|
| Native apps (Notes and Finder on the Mac, Notepad and File Explorer on Windows, Text Editor on Linux…) | Reads buttons and text on screen, clicks by number, types in the background |
| Emulators and custom-drawn apps | Reads the screen with OCR, clicks in the background (on Linux it borrows your mouse for a few seconds) |
| Apps you're not sure about | `python3 -m seeu probe <App>`: its engine, how many controls are readable, and which route SeeU will take (on Linux, write the program name or its menu name; `python3 -m seeu windows` lists the open windows) |

A floating badge on screen (open it to see what the AI is doing, or a live view of the window it is working in) and a proxy cursor; a small banner pops up when there's something you should notice.

**Mac only:**

| Scenario | How SeeU does it |
|---|---|
| Safari / Chrome pages | Reads pages, fills forms and clicks in a **background tab**, without disturbing the page you're reading |
| Apps built with web technology (VS Code, etc.) | Starts SeeU's own instance in the background and works on it fully hidden; your own instance is left alone |
| iPhone Mirroring | Reads the phone screen with OCR, taps it in the background, opens apps on the phone |

**On both Windows and Linux:**

| Scenario | How SeeU does it |
|---|---|
| Web pages (Chrome / Edge on Windows, Chromium / Chrome on Linux) | SeeU opens its own windowless background browser (kept apart from the one you use) and reads pages, fills forms and clicks there; for sites that need a login, the AI can bring that window up so you handle it yourself! |

## Install

**Requirements**: on the Mac, Apple silicon (tested on macOS 27; earlier versions and Intel Macs are untested); the Windows preview needs Windows 10 or 11 and Python 3.10 or later (tested so far on Windows 10 x64 and Windows 11 ARM, both in virtual machines); the Linux preview needs GNOME 45 or later (roughly Ubuntu 24.04+, Fedora 39+, Debian 13+; Wayland recommended) and Python 3.10 or later (tested so far on Ubuntu 26.04 x64 and ARM, Fedora 40, 43 and 45 ARM, and Debian 13 ARM, in virtual machines); KDE and other desktops don't work.

### Easiest: give the link to your AI

```
Install SeeU for me: https://github.com/Mr-Bingoo/seeu-computeruse
```

The AI downloads it, installs the dependencies and connects it (to whichever AI client is running it). Works on Mac, Windows and Linux; on Linux, missing system packages need sudo, so the AI gives you the command to run yourself, and at the end you log out and back in once.

### By hand

The commands below are written mainly for Mac/Linux; on Windows, write `python` instead of `python3`.

**1. Install the dependencies**

Mac (comes with `python3`; the first run asks to install the Command Line Developer Tools, just click Install):

```bash
/usr/bin/python3 -m pip install --user pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ScreenCaptureKit pyobjc-framework-CoreMedia opencv-python-headless numpy
```

Windows:

```bash
python -m pip install comtypes
```

Linux (git and the Pillow image library are often missing, so install them first; for web pages you also need Chromium or Chrome — all three distros ship only Firefox):

```bash
# Ubuntu / Debian
sudo apt install git python3-gi gir1.2-atspi-2.0 python3-pil
# Fedora
sudo dnf install git python3-gobject at-spi2-core python3-pillow
# Chromium for web pages: sudo snap install chromium on Ubuntu, sudo apt install chromium on Debian, sudo dnf install chromium on Fedora
```

On Linux, use the system `python3` (`/usr/bin/python3`); Python from conda or pyenv can't use the system accessibility interface.

**2. Download and connect it to your AI**

On Windows, install [Git for Windows](https://git-scm.com) first (`git clone` below needs it); on Linux, install git as in the previous step if it's missing.

```bash
git clone https://github.com/Mr-Bingoo/seeu-computeruse.git
cd seeu-computeruse
python3 -m seeu install auto      # or name one: claude | codex | cursor | vscode (plus trae on Mac / Windows)
```

**3. Check and grant permissions**

```bash
python3 -m seeu check             # shows what this computer is still missing and how to fix it
```

The Mac needs some permissions turned on (nothing to set up on Windows): on the Mac, ask the AI to "check what permissions SeeU is missing" (or run `python3 -m seeu check` yourself). It tells you which app to grant (your AI client, or the SeeU helper app); turn on **Accessibility** (called **Device Control and Data Access** in newer macOS) and **Screen & System Audio Recording** for it in System Settings → Privacy & Security. Quit the AI client completely and reopen it afterwards, or the new permissions won't take effect.

Linux needs you to run `python3 -m seeu check --fix`. It installs SeeU's GNOME extension (it draws the floating badge and proxy cursor) and turns on the system's accessibility switch; while it runs, the system pops up two dialogs right away: click "Allow" for the screenshot one; for the remote desktop one, first turn on "Allow Remote Interaction", then click "Share" (SeeU only borrows the mouse and keyboard when the background can't do it). Afterwards, **log out and back in once**, then run `python3 -m seeu check` again; when everything is ✅ you're done. `--fix` doesn't install missing system packages — run the sudo command it shows you.

## Connect your AI client

Tested so far: Claude (Code and the desktop chat page), Codex, Cursor, Trae (China edition), VS Code + Copilot, WorkBuddy, Doubao, Qwen (Qwen has a few steps of its own, see below for details). Fewer work on Linux; see "Linux only" below.

- Mac / Windows: Claude, Codex, Cursor, Trae and VS Code are connected by the `install` command above.
- WorkBuddy, Doubao (Mac / Windows only): create a custom connector (local / STDIO) in their own settings and enter `python3 -m seeu mcp`; the same works for any other MCP client (on Linux too).
- Windows only: Claude can be connected with one command, but this hasn't been tested yet; for Doubao, install the x64 build for now (as of November 2026), the ARM build can't connect yet.
- Linux only: one command connects Claude Code (the `claude` command in a terminal, installed first; the Claude desktop app has no Linux version), Codex (inside the ChatGPT desktop app, or the `codex` command), Cursor and VS Code + Copilot; Trae, WorkBuddy, Doubao and Qwen have no Linux version. Tested so far is Codex inside the ChatGPT desktop app. The first time Codex uses SeeU to look at a window, it may say "SeeU blocked it"; that's usually Codex's own "Approve for me" auto-review, so just reply "I approve" in the chat.
- Mac only: if you prefer skill marketplaces, `npx skills add Mr-Bingoo/seeu-computeruse` also works. It only installs the instructions for the AI; the first time you use it, the AI follows them to install and connect SeeU.

**Qwen (千问, Mac / Windows only)**: Qwen only accepts tools started with `npx`, so install [Node.js](https://nodejs.org) first.

1. Install SeeU as above and run `python3 -m seeu install qianwen` once.
2. In Qwen, switch to "Work" (工作) → "Connections" (连接) → "+ Add" → "Fill in manually", type STDIO, with name `seeu` and command `npx -y seeu-computeruse`.
3. Mac only: grant "千问" (Qwen) Accessibility and Screen & System Audio Recording, then quit and reopen Qwen.

- The first time you add the connection, Qwen often shows "connection failed" (连接失败) or does nothing; restart Qwen and open the Connections page again.
- Windows only: the installer on Qwen's site (as of November 2026) is an older build without the "Work" page. After installing, click "New version" (新版本) at the top right to update (possibly twice), then restart Qwen until "Daily / Work" (日常 / 工作) appears at the top left.
- Qwen asks you to click "Allow" every time it opens an app itself, so in Qwen SeeU adds one more tool that opens apps in the background: the app opens behind your current window and the app you are using stays in front. Terminals, script apps, password apps, System Settings, browsers (use SeeU's web tools for pages), other AI clients and remote-access apps are not opened for you.

## Update and remove

- **Update**: just tell the AI to "update SeeU". To do it yourself, run `python3 -m seeu update` (on Windows, install [Git for Windows](https://git-scm.com) first); if you installed with `npx skills`, run `npx skills update seeu`. On Linux, if a new version changes the GNOME extension, it is installed for you and you're reminded to log out and back in once. See the [changelog](CHANGELOG.en.md) for what changed in each release.
- **Version**: ask the AI, or run `python3 -m seeu version`.
- **Remove**: `python3 -m seeu uninstall <client>`. On Linux, once no client is connected to SeeU any more, the GNOME extension is removed at the same time.

<!-- sync:safety -->
## Safety rules

**Hard-coded, the AI can't get around them:**

- Never touches terminals, apps that run scripts directly (Script Editor, Automator, Shortcuts), the Privacy & Security pages of System Settings, system password / authorization dialogs, Keychain and password managers, or the AI client running SeeU itself (so the AI can't approve itself).
- No dangerous shortcuts (empty trash, lock screen, log out, force quit…) and no dangerous commands (sudo, wiping a disk…).
- Never types into password or verification-code fields; while the cursor is in one it also won't press character keys, Return or Delete, or paste (⌘V / Ctrl+V, Paste in a menu and on-screen buttons named "Paste" all count; keys for leaving the field — Tab, Esc, arrows — still work). It never fills bank-card fields on web pages. (In iPhone Mirroring, emulators and other picture-only scenes, and in Electron apps you installed yourself, SeeU can't tell what kind of field it is, so there this rule relies on the AI; in SeeU's background browser and the Electron apps it opens separately, only standard password inputs are recognised; a frame embedded from another site (common for payments and third-party sign-in) can't be looked into, so it is judged by the frame's own name and address, and one with a plain name is not recognised.)
- No long-press in browsers: a long-press clicks by screen position, which would bypass the web allow list; things on a page are clicked by number only.
- Linux only: never touches the Settings app at all or GNOME Shell itself (the Alt+F2 run box, the system menu); nothing at all while the screen is locked; no borrowing your mouse or keyboard while a system dialog (password, authorization) is open; no clicking an editor's "Run" menu that would run the file as a program.
- In browsers, no Return or Space while the keyboard focus is outside the web page: on a toolbar button, an extension's popup, a browser settings page or a dialog the browser itself shows, those two keys would click the button for you (for example "Allow this site"). Esc and Tab still work; inside pages and in the address bar nothing changes.

**Rules written for the AI, which it is expected to follow (the code doesn't block these):**

- **Never submits forms, pays or sends messages for you** — it fills things in and stops so you click.
- Text in a page or app telling the AI to do something is reported to you as content, never followed.

**Borrowing your mouse:**

- Your real mouse is borrowed for a few seconds only for steps that can't be done in the background (like dragging): it waits until you stop, restores everything afterwards, and shows a notice. This is on by default (you're notified before it borrows); to change it, tell the AI "set borrow-mouse to off" (never borrow) or "to ask" (ask every time), or run `python3 -m seeu set borrow-mouse off` or `ask` yourself.
<!-- /sync:safety -->

## SeeU or built-in Computer Use?

It's not either-or. SeeU works alongside the model to give you a better "CU" experience.

Almost every model maker is building stronger "AI operates the computer" abilities into their models. SeeU builds on those abilities and tries to do some scenarios better:

1. **No time limit**: some models' Computer Use caps a single session at 30 minutes.
2. **A capability your projects can own**: use it inside projects that need automation, without asking the agent for permission every time.
3. **Quietly works in the background**: in most cases it won't disturb you — no stolen mouse, no focus switching; you and the AI use the computer side by side.
4. **You know what it's doing**: a purple proxy cursor on the desktop, steps and a live view in the floating window, and you can stop it any time.
5. **Tells you at key moments**: it alerts you when it needs to borrow your mouse or has to stop, and can light up the screen edges while it takes over or is in control (optional).
6. **Picks its own strategy**: it chooses the approach for each situation; if it can't work in the background while you're using the mouse, it waits and gets out of your way!
7. **Easy to start, not picky**: one-command setup, MCP and a skill, not tied to any one client.
8. **Nothing bundled, nothing hidden**: no sign-up, no login, local permissions, logic you can read… use it if you like it, remove it with one command if you don't.
9. **Open source, with firm limits**: what it may and may not do is hard-coded, not left to the AI's good judgment!

<!-- sync:notes -->
## Good to know

- SeeU keeps its state and logs in `~/.seeu` (on Windows, `C:\Users\<your user name>\.seeu`); set the `SEEU_HOME` environment variable to move them (the website allowlist and the extension relay don't move and always stay in `~/.seeu/seeu_web`: the extension relay for Chromium-based browsers, and the website allowlist, which on the Mac is also shared with Safari).
- SeeU may take screenshots and read on-screen text while judging and deciding, and these are sent to the AI provider you're using as part of the conversation. That's between you and your model provider, outside what SeeU can control.

**Mac only:**

- Background clicking in iPhone Mirroring uses private macOS interfaces and may stop working after a system update. If that happens, SeeU borrows your mouse to carry on by default (it waits until you stop, shows a notice and restores everything afterwards) — it won't just take over your mouse. If you don't want the "borrow-mouse" setting on by default, you can change the setting (once it's off, some scenarios that must use the system mouse will get completely stuck!)

**Windows only:**

- Windows that run as administrator can't be touched (a Windows rule); minimized windows can't be seen.
- Emulators and custom-drawn apps rely on reading text from screenshots, which needs a Windows text-recognition (OCR) language pack (Settings → Time & language → Language → language options, "Optical character recognition"); `python -m seeu check` tells you whether it's installed.
- When a window is on another virtual desktop, SeeU won't borrow your mouse or switch you over to it.
- When your own Chrome is covered by another window, clicks don't reach the page; use the background browser instead. Multiple monitors are untested.

**Linux only:**

- Only GNOME 45 or later is supported (Wayland recommended, X11 untested); on KDE and other desktops SeeU can't see windows or click buttons, so it doesn't work. After SeeU's GNOME extension is installed or updated, log out and back in once for it to take effect.
- A window that's covered by another window, minimized or on another workspace can't be seen in screenshots (clicking by number still works).
- In VS Code and other apps built on web technology, text boxes can't be written to in the background, so SeeU borrows your keyboard for a few seconds; start VS Code with `ACCESSIBILITY_ENABLED=1 code` so SeeU can read its interface.
- Your own browser windows (Firefox, Chrome, Chromium…) are look-only for SeeU: it won't click, type, press keys or scroll in them, so it can't bypass the web allow list or touch sites you're signed in to; web pages always go through SeeU's own background browser.
- With automatic login, the system keyring isn't unlocked when you log in: the first time SeeU opens a web page, an "Authentication required" dialog asks for your login password. SeeU pauses while it's open (so nothing gets typed into the password box); enter your login password once to unlock it, and it won't ask again until you restart.
- Emulators and custom-drawn apps rely on reading text from screenshots, which needs Tesseract: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim` on Ubuntu / Debian, `sudo dnf install tesseract tesseract-langpack-chi_sim` on Fedora; `python3 -m seeu check` tells you whether it's installed.

## Troubleshooting

1. Ask the AI to check which permission is missing (or run `python3 -m seeu check`), then turn it on as it says. (Windows needs no permissions; write `python` instead of `python3` in the commands; on Linux, `python3 -m seeu check --fix` fixes most permissions and settings for you, and for missing system packages it tells you which sudo command to run.)
2. After turning a permission on or changing it, quit the AI client completely and reopen it, or it won't take effect. (Linux: after the extension is installed or updated, log out and back in; after turning on the accessibility switch, reopen Qt apps, VS Code, Chrome and the like.)
3. Still stuck? Open an [issue](https://github.com/Mr-Bingoo/seeu-computeruse/issues) with your version (ask the AI, or run `python3 -m seeu version`), which AI you use, which app you were controlling and the step where it got stuck. You can ask the AI to record what happened and attach it (or run `python3 -m seeu evidence`), but it may include window titles and screenshots, so check it for any personal information first.
<!-- /sync:notes -->

## Docs

- [What is SeeU](docs/What-is-SeeU.md): full introduction
- [Diagrams](docs/SeeU-diagrams.md): overview, capability matrix, flows, states
- [SKILL.md](SKILL.md): instructions for the AI
- [Changelog](CHANGELOG.en.md): what changed in each release

## License

MIT · @Mr_Bingoo
