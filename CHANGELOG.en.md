# Changelog

[中文](CHANGELOG.md) | English

A few plain sentences per release: what's new, what changed, and whether you need to do anything. To update, just tell the AI to "update SeeU" (or run `python3 -m seeu update`); ask the AI which version you have (or run `python3 -m seeu version`).

## v1.1.0 (unreleased)

- **Less Terminal**: when a site isn't on the allow list, the AI asks you in the chat and adds it once you agree. Restarting a hidden browser that got brought to the front, changing borrow-mouse, setting up the Chrome extension, checking permissions and updating can all be done by just telling the AI. The Terminal commands still work as a fallback.
- **The badge tells you when it's waiting for you**: while the AI asks in the chat whether to add a site, the floating window opens a card saying "say yes in the chat"; it goes away once you agree.
- **Safari stays out of the way**: if Safari isn't open, SeeU starts it hidden and works in the background, so its window doesn't cover the one you're using.
- **See what the AI changed for you**: when the AI adds a site, changes a setting or restarts a browser for you, a notice pops up at the top right of the screen.
- **Only you can turn on I See**: only with the I See button on the floating window; the AI can't turn it on for you (it can turn it off).
- **English setting command**: `python3 -m seeu set borrow-mouse on|ask|off`.
- Wording fixes in the privacy note and README.
- **What you need to do**: after updating, quit your AI client completely and reopen it so the new tools show up.

## v1.0.0 (2026-11-01)

First public release.

- **Background control**: native apps, Safari / Chrome pages, apps built with web tech, iPhone Mirroring and Android emulators: see the screen, click, type and scroll in the background without taking your mouse or switching your front window.
- **Visible**: a purple agent cursor plus a floating badge; open it to see the steps and a live view, and stop it any time.
- **Setup**: MCP and Skill support; `python3 -m seeu install auto` connects Claude, Codex, Cursor, Trae and VS Code in one step.
- **Hard-coded safety rules**: never touches terminals, passwords or privacy settings, and never submits, pays or sends messages for you.
- **Mouse borrowing, three modes**: on (default, with a notice) / ask me / off.
- **macOS only**: Windows and Linux versions are being researched.
