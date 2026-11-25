# Changelog

[中文](CHANGELOG.md) | English

Plain talk about each release, no scapegoats to sacrifice here! What's new, what changed, and whether you need to do anything. To update or check your version, just tell the AI "update SeeU" or "check SeeU's version", or run it yourself (`python3` on the Mac and Linux, `python` on Windows): update with `python3 -m seeu update`, check the version with `python3 -m seeu version`.

## v1.6.1 (2026-11-26)

Small fixes: key presses are no longer misreported as "no effect", SeeU tells you what to do when it needs your mouse and keyboard, touching a stuck floating window restarts its timer, the Linux helper can be turned back on after being disabled, and several hints are more accurate.

- **Key presses aren't misreported** (Mac): pressing one letter or Return in a large window changes too little of the picture, so SeeU reported no effect and the AI might press again (typing it twice, sending twice). SeeU now also compares the text, cursor and window: a change means success; when it can't tell, it says so and the AI looks first.
- **Keys don't land in another window** (Mac): with several windows of one app open, a key meant for one window could go to another. SeeU now checks that the focus is in that window and otherwise doesn't press, asking the AI to tap there first (typing already had this check). Browsers too, so ⌘W doesn't close the wrong window. It also doesn't press when the app is frozen and its windows can't be read; when two windows have exactly the same size and position, it tells them apart by title.
- **More careful Return after typing** (Mac): before pressing Return after typing, SeeU checks that the cursor hasn't jumped to a password field and, when a window was specified, that it's still in that window; otherwise it only types, doesn't press Return, and tells the AI so.
- **Clear words when it can't borrow the mouse and keyboard**: when the window is on another desktop or you're using the computer, the AI used to get only "refused". Now it gets a sentence it can pass on to you: move the window or let go first, then reply "ready".
- **Touching a stuck window restarts the hour**: hovering, moving, clicking or dragging on the expanded floating window restarts the 1-hour countdown on all three systems; a mouse left still on it doesn't count.
- **Safari setting directions fixed** (Mac): "Allow JavaScript from Apple Events" is under Settings → Developer in newer Safari, not the Develop menu.
- **The Linux helper can be turned back on**: if the helper had been turned off in Extensions, reinstalling didn't enable it, and SeeU wrongly said the screen was locked. Now check --fix turns it back on without logging in again. Right after a first install, it says you need to log in again instead of saying the screen is locked.
- **More accurate hints on Linux**: in the Activities overview it now says to press Esc, separate from password prompts; the English hints about the helper no longer mix in Chinese.
- **BlueStacks isn't mistaken** (Mac): with only its disk cleanup helper running, that used to be taken for BlueStacks.
- **Tested devices**: the docs now say how far a physical Intel Mac and a physical Windows 11 x64 PC have been tested.
- **What you need to do**: quit the AI app completely and reopen it after updating. No need to reinstall the Linux helper.

## v1.6.0 (2026-11-24)

SeeU can now be installed as a plugin: one command in Claude Code or Codex, and it fetches what it needs the first time you use it. We also went through the code for all three systems and fixed a batch of places where it could click or type in the wrong spot or click twice, and filled a few gaps in the safety rules.

- **Plugin**: in Claude Code type `/plugin install seeu --marketplace Mr-Bingoo/seeu-computeruse`; in Codex add the marketplace and install from a terminal (commands under "Install" in the README). Start a new conversation and it works — no download or connect step. The first time you use it, SeeU installs its Python libraries in the background (Mac / Windows); during those minute or two the tools answer "getting ready". Settings now live in your own user folder, so plugin updates won't wipe them; settings from an older git install are carried over automatically.
- **Finds apps on a Mac set to Chinese**: with the system language set to Chinese, names like 「文本编辑」「Safari浏览器」「iPhone镜像」weren't recognized, and the English names didn't work either; now both are recognized.
- **Steadier library install on the Mac**: the system's Python 3.9 picked a newer pyobjc that won't install; the install now pins versions that do and only uses prebuilt packages (no compiling on your Mac), and the check no longer says "all set" when libraries are missing. If you have another Python (Homebrew, pyenv, conda…), connecting now uses the system one automatically, and the check tells you if you ran it with the wrong one.
- **Typing no longer crashes SeeU on Mac**: on an Intel Mac virtual machine running macOS 14, the first background typing made SeeU quit unexpectedly and the AI lost all its tools. The cause is found and fixed, and it works on that virtual machine now.
- **I See only turns on with your own click** (Mac): a simulated click from another program could turn on I See on the floating badge; now only a real mouse click counts (Windows and Linux already worked this way; one gap there is closed too).
- **Multi-line text isn't sent early**: line breaks in the text were typed as Return, so in chat boxes where Return sends (WeChat, Slack…) the first line went out on its own. Line breaks are now Shift+Return, which still starts a new line in editors; in VS Code, Jupyter and spreadsheets (Excel, Numbers…), where Shift+Return means something else (run code, move up a cell), they stay Return.
- **No more double clicks**: for radio buttons and checkboxes, where the screen barely changes, SeeU couldn't tell the click worked and clicked again with the real mouse (a checkbox ended up checked and unchecked). It now reads whether the control is selected. And when the action went through but checking it afterwards failed, it no longer does it again (Windows).
- **Won't click into another window of the same program** (Windows): with two windows of one program open, if the AI looked at one and you then clicked the other, clicking by number went into yours. Now it asks to look again first.
- **Correct screenshots with display scaling on Linux**: at 125%, 200% and similar scaling, the window screenshot given to the AI only covered a corner and mixed in other windows, and clicking by screenshot position was off. It now captures the whole window, and sharper.
- **A few wrong clicks and keys fixed on Linux**: clicking by number after the window moved now follows the new position; before pressing Return with the real keyboard after typing, SeeU checks the cursor is still in that field; clicking by screenshot position no longer drifts when part of the window is off screen.
- **Safety rules filled in**: buttons and menu items named "Empty Trash / Recycle Bin", "Shut Down" or "Log Out" aren't clicked (before, only the shortcuts and the menu bar were blocked); on Windows the Start menu and taskbar search box are off-limits, only the path of an existing folder is typed into the File Explorer address bar, and nothing happens while the screen is locked; on Linux an extra modifier key no longer slips a dangerous shortcut through; no dragging in browsers; text from a web page's error isn't passed to the AI as if SeeU said it; and if the page moved to a site outside the allow list after the AI looked at it, clicking or typing by number checks again first.
- **The floating window no longer closes by itself when SeeU is stuck**: when SeeU gets stuck on a web page, the window opens and says why. It used to go away after a minute or two, so you missed it if you weren't at the computer. Now it stays open until you collapse it or the AI carries on, for up to 1 hour.
- **The floating badge no longer gets stuck on screen** (Linux): if the program drawing it quit unexpectedly, its last frame stayed on screen; it now hides itself within ten seconds.
- **The floating window starts on older macOS too**: it used the Liquid Glass look that only exists from macOS 26, so on older systems it didn't start at all; without it, it now uses a dark background.
- **What you need to do**: for the plugin, follow "Install" in the README. If you installed with git, fully quit your AI client after updating and reopen it. On Linux the update installs a new GNOME extension, so log out and back in once.

## v1.5.1 (2026-11-22)

The Linux preview has now been tested on Fedora and Debian, the floating badge works on the newest GNOME again, and the docs spell out what Linux needs and which AI clients it supports.

- **Tested on Fedora and Debian**: a fresh install and the full test run on Fedora 40, 43 and 45 and Debian 13 (GNOME 46, 49, 51 and 48). The minimum is now stated: GNOME 45 or later (roughly Ubuntu 24.04+, Fedora 39+, Debian 13+).
- **Works on the newest GNOME (51, used by Fedora 45)**: SeeU's GNOME extension didn't work there — no floating badge or glow, and after borrowing the mouse the pointer wasn't put back. It now works on both older and newer GNOME.
- **The screenshot permission sticks on the first check**: the check used to wait only 6 seconds, so if you didn't click "Allow" in time the dialog stayed open, the click didn't count, and it popped up again next time; now the first check tells you first and waits for you (up to 2 minutes).
- **The light icon matches the Mac** (Windows, Linux): the four corners of the light icon on the floating badge used to be square; they're now rounded, as on the Mac.
- **The floating badge follows light / dark mode on older GNOME (45, 46)**: on these versions it was always dark, even with the system in light mode; it now matches the system setting.
- **Install hints match your system**: the install commands shown by the check, text recognition and the "no browser found" message used to be Ubuntu's; Fedora now gets dnf and Debian gets apt.
- **The check also looks for the Pillow image library**: Debian doesn't install it by default, and without it the AI gets no screenshot when it looks at a window; the check now tells you it's missing and how to install it.
- **App names in your system's language**: some app names used to show up in another language (on Fedora, Text Editor appeared in Kabyle).
- **Clean removal on Linux**: once every AI client connected with the one-step install is removed, the GNOME extension is removed too (if you connected another client by hand, run check --fix to put it back).
- **Docs**: they now say which AI clients Linux supports (Claude Code, Codex, Cursor, VS Code; the others have no Linux version), which system packages to install (apt on Ubuntu / Debian, dnf on Fedora), and that web pages need Chromium or Chrome first.
- **What you need to do**: on the Mac and Windows, as before, quit the AI client completely and reopen it after updating. On Linux the new extension is installed for you during the update; log out and back in once. On Debian without Pillow, install it with the command the check gives you.

## v1.5.0 (2026-11-21)

The Linux preview is here: on GNOME desktops such as Ubuntu, the AI can now look at windows, press buttons and type into fields in the background, without getting in your way.

- **Linux preview**: for the GNOME desktop (Wayland, Ubuntu's default) with Python 3.10 or newer; tested on Ubuntu 26.04, both x64 and ARM. It can look at windows (screenshot + numbered list), press buttons by number in the background, type Chinese and English into fields, scroll, pick menu items, long-press, drag and read text from screenshots; web pages go through SeeU's own background browser (Chromium or Chrome). What can't be done in the background (clicking by screen position, input fields in VS Code, emulators) borrows your mouse and keyboard for a few seconds, under the same "borrow mouse" setting as on the Mac and Windows. If the computer doesn't meet these requirements, the connect step says so up front.
- **Visible on Linux too**: the proxy cursor, the floating badge (opens into a card and the island, with I See and the live view), the glow around the screen while borrowing, and toasts look the same as on the Mac; several conversations still queue, each with its own cursor.
- **Extra care on Linux**: nothing happens while the screen is locked; your mouse and keyboard aren't borrowed while a system dialog (password, authorization) is open; with several same-named windows of one app open, text never goes into a window the AI didn't look at; an editor's "Run" menu, which runs the file as a program, is never clicked; terminals embedded in apps aren't touched; your own browser is look-only (web pages always go through the background browser, so the allow list can't be bypassed).
- **Hand the link to an AI to install**: works on Linux too; tested with Codex in the ChatGPT desktop app, which downloaded, installed and connected SeeU by itself following the README. One-step setup covers Claude Code, Codex, Cursor and VS Code.
- **Understands a miscopied window name** (Windows, Linux): with several windows of one app open, an AI sometimes copied the instructions' "App「window title」" literally as "App" and the window wasn't found; now SeeU just matches the title, and the instructions use real names as examples.
- **Docs**: the README, "What is SeeU" and the diagrams now cover Linux; "What is SeeU" has a new "Splits itself · several tasks in parallel" section.
- **What you need to do**: on the Mac and Windows, after updating, quit the AI client completely and open it again. On Linux, install it the first time as the README's "Install" section says, then log out and back in once.

## v1.4.2 (2026-11-18)

On Windows, windows on another virtual desktop can now be read and typed into; the docs now fully explain how several sessions share SeeU.

- **Windows on another virtual desktop can be read and filled in**: once a window was on another virtual desktop, SeeU could only read its frame controls, not the text or the input fields, so the AI had to ask you to switch over. Now SeeU also asks the parts inside the window directly. Tested with the classic Notepad on Windows 10 and the new Notepad on Windows 11: the text can be read and typed into a field by its number, and you aren't switched over. If an app still can't be read fully, the AI is told, as before, to ask you to switch over or move the window here.
- **Docs cover several sessions**: "What is SeeU" has a new "Several conversations in parallel" section explaining how sessions take turns; the business diagram's "Several tasks at once" part is filled in too.
- **What you need to do**: after updating, quit the AI client completely and open it again.

## v1.4.1 (2026-11-17)

A few improvements: browsers work on another desktop too, and several sessions sharing SeeU take turns more smoothly and reliably.

- **Browsers can be read and filled in on another desktop** (Mac): without the browser switch or the extension, a Safari or Chrome window used to vanish from SeeU's view once it was on another desktop, and if another window of the same browser was open on the current desktop, SeeU could read that one instead. Now it goes straight to the window you're using, so it can read and fill in pages on another desktop too. (A minimized window can be read, but typing doesn't go in.)
- **A blocked step lets go right away** (Mac and Windows): when SeeU blocks a session's step and nothing was done, that session no longer keeps the app, so the next session in line doesn't wait a few seconds for nothing.
- **Long typing isn't cut into** (Mac and Windows): a step that took more than two minutes used to be treated as stuck, and another session could cut in; now it keeps reporting "still working" while it works (up to 10 minutes).
- **SeeU's own browser on Windows queues typing and keys too**: as on the Mac, only one session at a time types or presses Enter in the same browser.
- **Waiting before borrowing the mouse no longer fakes a success** (Mac and Windows): if the step that borrows your mouse first waited for another session or for you to stop, it used to compare against the picture from before the wait, so a screen that changed by itself counted as a successful click; now it takes a fresh picture after the wait.
- **What you need to do**: after updating, quit the AI client completely and open it again.

## v1.4.0 (2026-11-17)

Several sessions in the same AI client can now use SeeU at the same time: one at a time per app, the others wait in line; each session gets its own cursor, and text no longer lands in the wrong window. (Different AI clients open at once queue the same way, tested with Claude + Codex; sub-agents inside one session count as one and don't queue against each other.)

- **Several sessions at once take turns** (Mac and Windows): only one session's AI acts in an app at a time (on Windows, in a window), and it keeps the app for a few seconds for its next step; other sessions wait in line for up to 30 seconds, and if their turn doesn't come they're told "busy, try again shortly" instead of cutting in. Borrowing your mouse and keyboard also takes turns between sessions.
- **One cursor per session**: each cursor shows which session it is (Claude, Claude2…) in its own color; one that's waiting dozes off (Zz) and fades. Open the badge and the island shows who's waiting too.
- **Text no longer lands in the wrong window** (Mac): with two windows of the same app and two sessions typing, text could end up in the other window; now SeeU checks the field is in the target window first and doesn't type if it isn't.
- **No cutting in**: if another session clicked in the same app after an AI's last step and that AI then types or presses keys without naming a field, SeeU skips it and asks the AI to name the field (SeeU then clicks the field and types in one go, with no one cutting in). After waiting several seconds in line, it also won't click at the old position if the window moved or changed.
- **What you need to do**: after updating, quit your AI client completely and reopen it so the new rules take effect. To turn queueing off, set the environment variable `SEEU_NO_SCHED=1`.

## v1.3.0 (2026-11-16)

Only you can turn on I See, and now it's much harder to get around; and when the AI points inside a dialog, SeeU can borrow your mouse to click there.

- **Borrowing the mouse inside a dialog** (Mac): before, whenever the target app showed a dialog or sheet, SeeU never borrowed your mouse to click. Now it does when the AI is pointing inside that dialog and the dialog was already there when the AI last looked at the screen; a popup that appears afterwards, or a click outside the dialog, is still refused.
- **Only you can turn on I See, for real this time** (Mac and Windows):
  - Editing the settings file to say "on" no longer counts; after I See is turned off or expires, copying the old "on" record back doesn't count either.
  - Turning it on from the Mac terminal now also asks you to press the letter shown on screen (same as Windows); the AI's command line can't answer it.
  - On Windows, the I See button on the floating window only accepts a click from your own mouse; simulated clicks from a program can't turn it on.
  - The environment variable `SEEU_ISEE=1` no longer turns it on (`=0` still forces it off).
- **Small fixes**: a mistyped number of hours after `isee on` no longer crashes, and a negative one no longer turns on something already expired; the `isee` commands on the Mac now speak English too; on Windows, adding sites to the allow list or changing settings from a terminal inside an editor or AI app now also needs your own words.
- **What you need to do**: after updating, quit your AI app completely and reopen it; if I See was on, turn it on again.

## v1.2.1 (2026-11-16)

Two small fixes after v1.2.0, plus a few plainer wordings in the README.

- **The floating badge sometimes didn't show** (Mac): after several AIs had used SeeU at once, the badge could stay hidden. Now when it should be showing but isn't on screen, SeeU puts it back and notes what happened, so the cause can be tracked down later.
- **The AI's instructions now say what to do on Windows**: the instructions file at the top of the repository only talked about the Mac, so an AI given the link on Windows might think SeeU can't be installed there. It now says up front that there is a Windows preview and which instructions to follow.
- **What you need to do**: nothing, just update.

## v1.2.0 (2026-11-16)

The Windows preview is here, and the Mac version is steadier too: when SeeU isn't confident about what's on screen it doesn't click blindly, it doesn't pull windows to the front lightly, and it doesn't casually switch you to another desktop.

- **Windows preview**: SeeU now runs on Windows 10 / 11 with the everyday things in place: look at windows, click, type, press keys, scroll, long-press and drag in the background; web pages go through SeeU's background browser (Chrome or Edge); a floating badge, a proxy cursor and small banners show what the AI is doing. One-step setup for Claude, Codex, Cursor, Trae and VS Code (WorkBuddy and Doubao can be added by hand), with the interface in Chinese or English. It has a few things fewer than the Mac version; see the [README](README.en.md) for setup and what's missing.
- **More careful on Windows when the picture can't be trusted** (Windows): when the machine is busy, the window is covered or it sits on another virtual desktop, the screenshot SeeU gets may be out of date. SeeU then won't tap by a position on that screenshot; it taps the control instead, or asks the AI to look again. After pressing an arrow key it checks the cursor really moved; if the text reads back unchanged after typing, it doesn't report success and doesn't press Enter for you; and for apps whose controls can't be read (Trae, Doubao) it falls back to reading text from the screenshot.
- **No more tapping on an old picture on the Mac either** (Mac): for apps like VS Code, when the window is covered, on another desktop, or the Mac is locked, the screenshot is out of date. SeeU then won't tap by a position on that screenshot; it uses another way instead, or asks you to uncover the window.
- **Won't switch you to another desktop** (Mac): when SeeU needs to borrow your mouse but the window is on another desktop, it doesn't borrow it; it asks you to switch there or move the window here.
- **Before tapping by number, SeeU checks the control is still there** (Mac and Windows): after the AI looked at the screen once, tapping by number used the position recorded at that moment, so if a list scrolled or a dialog appeared in between, the tap landed on something else. Now SeeU asks first: if the control is still there it is tapped at its current position; if it is gone nothing is tapped and the AI is told "the screen changed, look again". Picture-only targets with no controls (iPhone Mirroring, emulators) work as before for now.
- **Checkboxes are no longer clicked twice**: with the window in the background, SeeU sometimes couldn't see the screen change after clicking a checkbox or switch, tried another way and clicked again, which unticked it. It now reads the control's own state after the click and counts a change as success.
- **No more pulling a window to the front for nothing when a dialog is open** (Mac): when the target app has a dialog or sheet open, SeeU won't borrow your mouse to click in it. It used to bring that app to the front first and only then find it shouldn't click; now it checks first and leaves your windows alone.
- **Qwen works now, and Chinese app names are understood** (Mac and Windows): add Qwen by hand as the README's "Qwen" paragraph describes; in Qwen, SeeU can also open apps for it in the background, so you no longer click "Allow" each time. The Windows preview works with Qwen too (update Qwen until it has the "Work" page). When the AI writes a Chinese app name such as 「备忘录」 (Notes) or 「访达」 (Finder), SeeU finds the app on an English system too (and English names work on a Chinese system). Newer macOS renamed Accessibility to "Device Control and Data Access" in English; the permission hints now give both names.
- **I See on the command line on Windows too** (Windows): `python -m seeu isee on|off|status|report`. Only you can turn it on, by running it in a Windows cmd / PowerShell window and pressing the letter it shows; it refuses when an AI runs it, or when it runs in a terminal inside an editor or AI app.
- **What you need to do**: after updating, fully quit your AI client and open it again.

## v1.1.5 (2026-11-07)

Updating no longer stops because you changed a setting, and a few leftover edge cases from the last review are closed.

- **You can update after changing settings**: the settings file lives next to the code, so once you changed a setting (or clicked the I See button on the overlay), update stopped with "you have changed these files". When the settings file is the only change, update now goes ahead: your changed settings are kept, and options added by the new version get their defaults. If the update is interrupted (terminal closed, power lost), your settings aren't lost either — they are put back the next time you run update.
- **⚠️ This one update may still need a manual step**: the updater that runs is the old one already on your Mac. If it still says "You have changed these SeeU files" and the only file listed is the settings file (the old updater shows `seeu/设置.json` as `"seeu/\350\256\276\347\275\256.json"`), run `git stash`, `python3 -m seeu update`, `git stash pop` in the SeeU folder, in that order. After this release it's no longer needed.
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
