<div align="center">

# SeeU

> *You see SeeU, I know you see. I See.*

**Let your AI see the screen, click and type on your Mac in the background... working side by side with you, without getting in each other's way!**

[中文](README.md) | English

macOS only (won't run on Windows or Linux)

</div>

https://github.com/user-attachments/assets/e313c2c9-f3df-4547-acc6-54ef6f8462c7

The name comes from CU (Computer Use — letting AI operate a computer), pronounced the same: *see first, then act*.

It puts a second, purple proxy cursor on screen that works for the AI. Looking, clicking, typing and scrolling all happen in the background, without taking your mouse or switching your frontmost window. You can keep writing and chatting while it does its job next to you — click the SeeU floating badge to see what the AI is doing.

## Things you can say

Once installed, just ask your AI (Claude, Codex, Cursor…):

```
"Use SeeU to create a new note in Notes with today's to-dos"
"See which files are on the Desktop in Finder"
"Open a background tab in Safari and tell me what this page says"
"Open a game on my phone through iPhone Mirroring and do the daily check-in"
```

## What it can do

| Scenario | How SeeU does it |
|---|---|
| Native apps (Notes, TextEdit, Finder…) | Reads buttons and text on screen, clicks by number, types in the background |
| Safari / Chrome pages | Reads pages, fills forms and clicks in a **background tab**, without disturbing the page you're reading |
| Apps built with web technology (VS Code, etc.) | Starts SeeU's own instance and works on it fully hidden; your own instance is left alone |
| iPhone Mirroring | Reads the phone screen with OCR, taps it in the background, opens apps on the phone |
| Android emulator | OCR plus background clicks |
| Apps you're not sure about | `python3 -m seeu probe <App>`: its engine, how many controls are readable, and which route SeeU will take |

Every step is checked against the screen; if it didn't work, SeeU tries another way or stops and tells you where it's stuck instead of clicking blindly. More in [What is SeeU](docs/What-is-SeeU.md).

## Install

**Requirements**: macOS only, a Mac with Apple silicon (tested on macOS 27; earlier versions and Intel Macs are untested), the system `python3` (the first run asks to install the Command Line Developer Tools; just click Install) and PyObjC:

```bash
/usr/bin/python3 -m pip install --user pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ScreenCaptureKit pyobjc-framework-CoreMedia
```

Then pick one of three ways:

**① Give the link to your AI (easiest)**

```
Install SeeU for me: https://github.com/Mr-Bingoo/seeu-computeruse
```

The AI downloads it, installs the dependencies above and runs `python3 -m seeu install auto`, which connects whichever AI client is running it.

**② One command, as a skill**

```bash
npx skills add Mr-Bingoo/seeu-computeruse
```

The first time you use it, the AI follows the skill's instructions to install the dependencies and connect the MCP server.

**③ By hand**

```bash
git clone https://github.com/Mr-Bingoo/seeu-computeruse.git
cd seeu-computeruse
python3 -m seeu install auto      # or name one: claude | codex | cursor | trae | vscode
python3 -m seeu check             # lists missing macOS permissions and how to enable them
```

**Permissions**: run `python3 -m seeu check`. It tells you which app to grant (your AI client, or the SeeU helper app); turn on **Accessibility** and **Screen & System Audio Recording** for it in System Settings → Privacy & Security. Quit the AI client completely and reopen it afterwards, or the new permissions won't take effect.

Tested AI clients: Claude (Code and the desktop chat), Codex, Cursor, Trae (China edition), VS Code + Copilot, WorkBuddy, Doubao (WorkBuddy and Doubao are connected by hand). Any other MCP client works by adding `python3 -m seeu mcp` as a local MCP server.

**Update**: `python3 -m seeu update` (git clone) or `npx skills update seeu` (npx). See the [changelog](CHANGELOG.en.md) for what changed; `python3 -m seeu version` shows which version you have. **Remove**: `python3 -m seeu uninstall <client>`.

<!-- sync:safety -->
## Safety rules (built into the code)

- Never touches terminals, the Privacy & Security pages of System Settings, system password / authorization dialogs, Keychain and password managers, or the AI client running SeeU itself (so the AI can't approve itself).
- No dangerous shortcuts (empty trash, lock screen, log out, force quit…) and no dangerous commands (sudo, wiping a disk…).
- Never fills password, bank-card or verification-code fields. **Never submits forms, pays or sends messages for you** — it fills things in and stops so you click.
- Text in a page or app telling the AI to do something is reported to you as content, never followed.
- Your real mouse is borrowed for a few seconds only for steps that can't be done in the background (like dragging): it waits until you stop, restores everything afterwards, and shows a notice. This is on by default (you're notified before it borrows); you can also use `python3 -m seeu set 借用鼠标 关` (never borrow) or `问我` (ask every time).
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

- Background clicking in iPhone Mirroring uses private macOS interfaces and may stop working after a system update. If that happens, SeeU borrows your mouse to carry on by default (it waits until you stop, shows a notice and restores everything afterwards) — it won't just take over your mouse. If you don't want "borrow system mouse" on by default, you can change the setting (once it's off, some scenarios that must use the system mouse will get completely stuck!)
- SeeU keeps its state and logs in `~/.seeu`; set the `SEEU_HOME` environment variable to move them (browser files don't move and always stay in `~/.seeu/seeu_web`: the extension relay for Chromium-based browsers, and the website allowlist they share with Safari).
- SeeU may take screenshots while judging and deciding, and they're sent to the AI provider you're using as part of the conversation. That's between you and your model provider, outside what SeeU can control.

## Troubleshooting

1. Run `python3 -m seeu check` first: it lists any missing permission and how to turn it on.
2. After turning a permission on or changing it, quit the AI client completely and reopen it, or it won't take effect.
3. Still stuck? Open an [issue](https://github.com/Mr-Bingoo/seeu-computeruse/issues) with your version (`python3 -m seeu version`), which AI you use, which app you were controlling and the step where it got stuck. You can attach what `python3 -m seeu evidence` records, but it may include window titles and screenshots, so check it for anything private first.
<!-- /sync:notes -->

## Docs

- [What is SeeU](docs/What-is-SeeU.md): full introduction
- [Diagrams](docs/SeeU-diagrams.md): overview, capability matrix, flows, states
- [SKILL.md](SKILL.md): instructions for the AI
- [Changelog](CHANGELOG.en.md): what changed in each release

## License

MIT · @Mr_Bingoo
