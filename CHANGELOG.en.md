# Changelog

[中文](CHANGELOG.md) | English

A few plain sentences per release: what's new, what changed, and whether you need to do anything. To update, just tell the AI to "update SeeU" (or run `python3 -m seeu update`); ask the AI which version you have (or run `python3 -m seeu version`).

## v1.1.5 (2026-11-07)

Updating no longer stops because you changed a setting, and a few leftover edge cases from the last review are closed.

- **You can update after changing settings**: the settings file lives next to the code, so once you changed a setting (or clicked the I See button on the overlay), update stopped with "you have changed these files". When the settings file is the only change, update now goes ahead: your changed settings are kept, and options added by the new version get their defaults. If the update is interrupted (terminal closed, power lost), your settings aren't lost either — they are put back the next time you run update.
- **⚠️ This one update may still need a manual step**: the updater that runs is the old one already on your Mac. If it still says "You have changed these SeeU files" and the only file listed is `seeu/设置.json`, run `git stash`, `python3 -m seeu update`, `git stash pop` in the SeeU folder, in that order. After this release it's no longer needed.
- **Clicking "Paste" counts as pasting**: with the cursor in a password or verification-code field, only ⌘V and Paste in the menu bar were blocked; clicking an on-screen button named "Paste", or Paste / Cut / Undo in a context menu (by click, long-press or drag), got around it. Those are now refused too.
- **In browsers, no Return or Space while the focus is outside the page**: when the keyboard focus is on a toolbar button, an extension's popup, a browser settings page or a dialog the browser itself shows, those two keys would click the button for you (for example "Allow this site"). They are now refused; Esc and Tab still work. Inside pages and in the address bar nothing changes.
- **Password fields inside embedded frames are recognised**: in SeeU's own hidden Chrome, nothing was checked while the cursor was inside a frame embedded in the page. A frame from the same site is now looked into; one embedded from another site (common for payments and third-party sign-in, and its contents can't be inspected) is judged by its name and address — if it looks like sign-in, payment or verification, SeeU won't type or press keys into it. A frame with a plain name still isn't recognised, so there the rule relies on the AI.
- **Removing the Claude entry is more precise**: with no install record, both the "all projects" and the "this project" entries named seeu used to be deleted. Now only entries confirmed to point at this copy of SeeU are removed (both, if both do); if removal fails you're told so instead of seeing "removed".
- **Small fixes**: the downsized screenshot sent to the AI is no longer left in the system temp folder; Chinese file names in "you have changed these files" are no longer shown as escape sequences.
- **What you need to do**: fully quit your AI client and open it again after updating.

## v1.1.4 (2026-11-07)

Continuing the review from the last release: the remaining safety gaps are closed, and one long-standing problem is fixed — the I See button on the overlay didn't actually work.

- **The I See button works now**: since v1.1.0, to stop the AI from turning on I See for you, SeeU refuses an "on" command that looks like it came from an AI. But the overlay itself is often started by the SeeU inside your AI client, so your own click on the button was refused too — it lit up and went dark again. Now the one command sent by the overlay itself is accepted; the AI still can't turn it on from the command line.
- **No key presses or paste in password and verification-code fields**: only "type" was blocked before, so pressing keys one at a time, ⌘V, or Paste from the menu got around it. While the cursor is in such a field, character keys, Space, Return, Delete, cut, undo and paste are now refused; Tab, Esc, arrows and other shortcuts still work, so the field can be left. SeeU's own hidden Chrome used to refuse even Tab inside a password field; it now behaves the same way. In iPhone Mirroring and emulators SeeU can't tell what kind of field it is, so there this still relies on the AI.
- **Password fields on Chrome pages are really recognised now**: with your own Chrome in the background, SeeU couldn't read which field the cursor was in, so "never types into password or verification-code fields" didn't actually hold on Chrome pages. SeeU now asks Chrome to expose the page structure before checking; the first check takes about 2 seconds (same for Edge, Brave and other browsers on that engine). Inside apps built with Electron it still can't tell, so there the rule relies on the AI.
- **No long-press in browsers**: a long-press clicks by screen position, so it could act on pages outside the allow list and reach the extension icon in the toolbar. Things on a page are clicked by number anyway; long-press is now refused in browsers. iPhone Mirroring, emulators and ordinary apps are unaffected.
- **Script Editor, Automator and Shortcuts are off limits**: they can run scripts directly, same reasoning as terminals.
- **Uninstall only removes the entry SeeU added**: `python3 -m seeu remove <client>` used to delete any entry named seeu, which could be one you configured by hand or one added by another copy of SeeU. An entry with no install record that doesn't point at this copy is now left alone, and you're told how to remove it yourself.
- **What you need to do**: fully quit your AI client and open it again after updating.

## v1.1.3 (2026-11-06)

After v1.1.2 went out we reviewed everything once more. This release closes the safety gaps that review found, and corrects a few places where the docs promised too much.

- **Web tools no longer read other apps**: "read page" and "list tabs" didn't check their target, so they would also read the AI client running SeeU, or a password app built with web technology. They now accept browsers only, and go through the safety rules like every other action.
- **A browser under another name still follows the web rules**: writing Chrome with a window title, a bundle id or a process id used to bypass the allow list and the typing limits. It is now recognised as the browser first.
- **The Empty Trash menu item is blocked in more languages**: Simplified Chinese macOS uses a different wording from the one SeeU blocked, so it slipped through. Traditional Chinese and British English ("Empty Bin") are covered too.
- **Half an emoji no longer stops the service**: a truncated emoji in a page title or text made the SeeU service exit, after which every tool failed. It is now replaced with � and the reply goes through.
- **Scrolling in web pages goes the right way**: the tool description says negative means down, but pages scrolled up. Without the Apple-events switch or the extension, page scrolling used to simply fail; it now falls back to the background scroll wheel.
- **Long-press has a limit**: at most 10 seconds. A very large value used to hang the whole service.
- **OpenCV and numpy added to the install instructions**: screenshots and result checks need them, and they were missing. `python3 -m seeu check` now checks for both.
- **Docs made accurate**: the safety rules now separate what is hard-coded from the rules written for the AI. Not submitting, paying or sending messages for you belongs to the second kind; the code doesn't block it. In iPhone Mirroring and emulators SeeU can't recognise password fields, so that also relies on the AI there. The retry described in v1.1.1 ("taps the search box first") passed the wrong coordinates; that is fixed here and has been verified on a real device.
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
