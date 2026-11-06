# Changelog

[中文](CHANGELOG.md) | English

A few plain sentences per release: what's new, what changed, and whether you need to do anything. To update, just tell the AI to "update SeeU" (or run `python3 -m seeu update`); ask the AI which version you have (or run `python3 -m seeu version`).

## v1.1.3 (2026-11-06)

After v1.1.2 went out we reviewed everything once more. This release closes the safety gaps that review found, and corrects a few places where the docs promised too much.

- **Web tools no longer read other apps**: "read page" and "list tabs" didn't check their target, so they would also read the AI client running SeeU, or a password app built with web technology. They now accept browsers only, and go through the safety rules like every other action.
- **A browser under another name still follows the web rules**: writing Chrome with a window title, a bundle id or a process id used to bypass the allow list and the typing limits. It is now recognised as the browser first.
- **The Empty Trash menu item is blocked in more languages**: Simplified Chinese macOS uses a different wording from the one SeeU blocked, so it slipped through. Traditional Chinese and British English ("Empty Bin") are covered too.
- **Half an emoji no longer stops the service**: a truncated emoji in a page title or text made the SeeU service exit, after which every tool failed. It is now replaced with � and the reply goes through.
- **Scrolling in web pages goes the right way**: the tool description says negative means down, but pages scrolled up. Without the Apple-events switch or the extension, page scrolling used to simply fail; it now falls back to the background scroll wheel.
- **Long-press has a limit**: at most 10 seconds. A very large value used to hang the whole service.
- **OpenCV and numpy added to the install instructions**: screenshots and result checks need them, and they were missing. `python3 -m seeu check` now checks for both.
- **Docs made accurate**: the safety rules now separate what is hard-coded from the rules written for the AI. Not submitting, paying or sending messages for you belongs to the second kind; the code doesn't block it. In iPhone Mirroring and emulators SeeU can't recognise password fields, so that also relies on the AI there. The retry described in v1.1.1 ("taps the search box first") passed the wrong coordinates; that is fixed here, but it still hasn't been exercised on a real device.
- **What you need to do**: fully quit your AI client and open it again after updating. Run `python3 -m seeu check` once; if it says the image libraries are missing, install them with the command it shows.

## v1.1.2 (2026-11-06)

This release mostly closes safety gaps, and fixes a few things that could go wrong.

- **Sites not on the allow list: ask first, then open**: SeeU used to open the page and then ask whether to add the site, by which time the page had already been visited with your login. It now asks first and opens only after you agree. With I See mode on it still opens directly.
- **Stricter allow list in the hidden Chrome**: in SeeU's own Chrome, pages that aren't on the list are not read, and no keys or text are sent to them. Your own browser is unchanged.
- **Dangerous shortcuts are blocked under any name**: shortcuts like Empty Trash used to slip through when delete was written as backspace or alt as option. They are all blocked now.
- **"Don't look, don't touch" filled in**: terminals, password apps and the privacy pages of System Settings are no longer even looked at; System Settings is blocked on another desktop too; nothing is typed while the cursor is in a verification-code field.
- **"Open a web page" only opens web pages**: browsers only, http / https URLs only. Local files (file://) can no longer be added to the allow list.
- **Return is pressed only after the text is verified**: if SeeU can't confirm the text went in, it doesn't press Return and tells the AI to look first.
- **More robust**: a text-recognition failure no longer takes the whole SeeU server down; a misspelled modifier key no longer leaves ⌘ held; typing more than 200 characters on a web page no longer falsely reports no effect; after starting a hidden browser the frontmost app is handed back to you; quitting the hidden Chrome only quits SeeU's own copy, not your Chrome or other apps.
- **Command line**: when an AI adds a site or changes borrow-mouse from the command line it must pass your reply (`--user-said`); typing the commands yourself is unaffected.
- **What you need to do**: after updating, quit your AI client completely and reopen it. If you used local files (file://) as test pages, serve them from a local address instead (e.g. `http://127.0.0.1:8000`).

## v1.1.1 (2026-11-06)

- **Less mouse-borrowing in iPhone Mirroring**: when tapping a text field only adds a cursor to the screen, SeeU used to treat it as a miss and borrow your mouse to tap again. It now looks for small changes around the tap, so it no longer borrows the mouse for nothing.
- **No more false "only partly typed" on long text**: text recognition sometimes misreads, adds or drops a letter. SeeU only compared the last few characters, so one mistake reported a partial result and skipped Return. It now tolerates a few recognition errors, but the ending must still match, so Return isn't pressed if typing really stopped short.
- **Opening an app in iPhone Mirroring no longer falsely succeeds**: when the search box wasn't focused, the text didn't go in but SeeU still reported success. It now reports a failure when the text doesn't go in. A retry that taps the search box first was also added, but that step hasn't been exercised on a real device yet.
- **Known issue**: ⌘A in iPhone Mirroring was once reported as having no effect even though everything was selected. We couldn't reproduce it; if you see it, have the AI look at the screen again.
- **What you need to do**: after updating, quit your AI client completely and reopen it for the new version to take effect.

## v1.1.0 (2026-11-02)

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
- **Safety rules**: terminals, passwords and privacy settings are hard-coded as off limits; not submitting, paying or sending messages for you is a rule written for the AI.
- **Mouse borrowing, three modes**: on (default, with a notice) / ask me / off.
- **macOS only**: Windows and Linux versions are being researched.
