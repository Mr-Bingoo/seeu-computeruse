# SeeU diagrams

> Written by @Mr_Bingoo x Claude · "the author" below = @Mr_Bingoo
>
> The diagrams show "what's there and how it flows"; the docs explain "why, and which pitfalls we hit". The diagrams are written in Mermaid: change a line of text and the diagram follows, and GitHub renders them directly.
> Five kinds: ① overview (what it's made of) ② capability matrix (how far each scenario goes) ③ swimlane diagrams (for one step: who does what, how it decides, how it returns; one per action)
> ④ state diagrams (which states it can be in and how it switches) ⑤ mind map (all features at a glance).
> The diagrams only show SeeU's general approach; where a step was added because the author hit a problem in a real scenario, a short "Example:" paragraph under the diagram explains it.

> 💡 Diagrams marked "Windows preview" or "Linux preview" are for those systems (one overview and one capability matrix each; swimlanes 3.6 and 3.7 are Windows, 3.8 and 3.9 are Linux); all the others show the Mac version. For how Windows and Linux differ, see the [README](../README.en.md).

## ① Overview

**Mac**

```mermaid
block-beta
  columns 6
  H1["① Who calls it"]:6
  U1["Your Python programs<br/>scheduled tasks, automation"]:2
  U2["AI (Claude, Codex, Qwen…)<br/>MCP tools + Skill instructions<br/>one-step setup · npx launcher"]:2
  U3["Command line<br/>permission check, evidence, I See"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["Decisions<br/>entry: pick route · switch route · verify · report<br/>safety rules · stepping aside · mouse queue<br/>I See"]:2
  R["Routes<br/>browser: extension/switch/Accessibility<br/>stealth browser · debugging port<br/>Accessibility · background click · real mouse"]:2
  FB["Seeing and feedback<br/>screenshots + text recognition<br/>floating window · island · agent cursor<br/>glow · toast · permission check · evidence"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ System abilities it relies on"]:6
  P1["Accessibility permission<br/>Screen Recording permission"]:2
  P3["Private background-click interface<br/>falls back to the real mouse"]:2
  P4["AppleScript, granted per app<br/>debugging port (Chromium)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ Six scenarios"]:6
  A1["Safari"] A2["Chrome etc."] A3["Electron apps"] A4["Native apps"] A5["Emulators"] A6["iPhone Mirroring"]
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

**Windows preview**

```mermaid
block-beta
  columns 6
  H1["① Who calls it"]:6
  U1["Your Python programs<br/>scheduled tasks, automation"]:2
  U2["AI (Claude, Codex, Qwen…)<br/>MCP tools + Skill instructions<br/>one-step setup · npx launcher"]:2
  U3["Command line<br/>check, evidence, settings"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["Decisions<br/>entry: pick route · switch · verify · report<br/>safety rules · step aside · no clicks by an untrustworthy picture<br/>I See"]:2
  R["Routes<br/>background browser (debugging port)<br/>read controls · post window messages<br/>borrow the front · borrow the real mouse"]:2
  FB["Seeing and feedback<br/>window capture + OCR<br/>floating window · island · agent cursor<br/>toast · check · evidence"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ System abilities it relies on (no permissions to grant)"]:6
  P1["Control interface<br/>(UI Automation)"]:2
  P3["Mouse / keyboard messages to the window<br/>then borrow the front / real mouse"]:2
  P4["Window capture · built-in Windows OCR<br/>debugging port (Chrome / Edge)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ Three kinds of scenario"]:6
  A1["Native apps"]:2 A2["Chrome / Edge pages"]:2 A3["Emulators · custom-drawn apps"]:2
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

**Linux preview**

```mermaid
block-beta
  columns 6
  H1["① Who calls it"]:6
  U1["Your Python programs<br/>scheduled tasks, automation"]:2
  U2["AI (Claude Code, Codex, Cursor…)<br/>MCP tools + Skill instructions<br/>one-step setup"]:2
  U3["Command line<br/>check (can fix things itself), settings, update"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["Decisions<br/>entry: pick route · switch · verify · report<br/>safety rules (incl. lock screen, system dialogs) · step aside · queue<br/>I See"]:2
  R["Routes<br/>background browser (debugging port)<br/>act on controls · menu bars<br/>borrow the real mouse and keyboard"]:2
  FB["Seeing and feedback<br/>screenshot + OCR<br/>floating badge · island · agent cursor<br/>glow · toast · check"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ System abilities it relies on"]:6
  P1["Accessibility interface (AT-SPI)<br/>accessibility master switch"]:2
  P3["System screenshot permission<br/>system remote-control permission"]:2
  P4["SeeU's GNOME extension<br/>debugging port (Chromium / Chrome)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ Three kinds of scenario"]:6
  A1["Native apps (GTK / Qt)"]:2 A2["Chromium / Chrome pages"]:2 A3["Emulators · custom-drawn apps"]:2
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

## ② Capability matrix

Legend: ✅ background, no disturbance · ⚡ briefly borrows the front window or your mouse · ⚠️ with conditions · ❌ not possible

**Mac**

| Scenario | Read content | Click | Type | Scroll | Works while hidden | Permissions needed |
|---|---|---|---|---|---|---|
| Safari | ✅ | ✅ | ✅ | ✅ | ✅ stealth Safari | Accessibility, the Safari switch (asks for your password), control of Safari |
| Chrome etc. | ✅ | ✅ | ✅ | ✅ | ✅ stealth Chrome (flashes 0.2–0.4 s at startup) | Accessibility, extension or switch; stealth Chrome uses the debugging port and needs nothing turned on |
| Electron apps (desktop software built with web tech; Electron, CEF and the like all count; e.g. VS Code) | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ❌ your own copy | None for SeeU's copy; yours needs Accessibility and Screen Recording |
| Native apps (Notes…) | ✅ | ✅ | ✅ | ✅ | ✅ (opening a specific note flashes briefly) | Accessibility; control of that app when AppleScript is used |
| Emulators (e.g. BlueStacks) | ✅ text recognition | ✅ background click (private interface) | ✅ | ✅ | ❌ (window must be there) | Accessibility, Screen Recording |
| iPhone Mirroring | ✅ text recognition | ✅ background click (private interface) | ✅ | ✅ (adds a small drag when stuck) | ❌ (window must be there, any size) | Accessibility, Screen Recording |
| Dragging (any scenario) | — | ⚡ borrows the real mouse | — | — | — | Same as above |

Every scenario goes through the safety rules first: Terminal, system permission prompts, the Privacy & Security part of System Settings, password apps (Keychain, Passwords, 1Password and so on), the AI client running SeeU itself (such as Claude or Codex), SeeU's own floating window buttons (so the AI can't turn on I See for itself), and dangerous shortcuts / commands / menu items are all blocked; password, verification-code and bank card fields are never touched. When opening apps in the background for Qwen, terminals, script apps, password apps, System Settings, browsers, other AI clients and remote-access apps are never opened.

"Background click (private interface)" = posting the click straight to the window through an interface macOS hasn't made public. It may stop working after a system update, and then SeeU automatically falls back to the real mouse (see 3.3).

For emulators we suggest ADB first (Android's official debugging tool, a public interface that doesn't go through SeeU): clicks, swipes and screenshots are fully in the background with accurate coordinates. SeeU fills in with background clicks, for example typing Chinese (ADB's built-in input only handles English letters and numbers) or when ADB isn't enabled in the emulator.

**Windows preview**

| Scenario | Read content | Click | Type | Scroll | Works while hidden | Permissions needed |
|---|---|---|---|---|---|---|
| Native apps (Notepad, File Explorer…) | ✅ reads controls | ✅ background click; ⚡ newer UI (e.g. the new Notepad's dialogs) briefly borrows the front | ✅ | ✅ | ⚠️ fine when covered by other windows; minimized windows can't be seen | None |
| Chrome / Edge pages (background browser) | ✅ | ✅ | ✅ | ✅ | ✅ never shows a window; shown only when you need to sign in yourself | None; only sites on the allow list |
| Your own Chrome or Electron apps (e.g. VS Code) | ✅ reads controls | ✅ background click | ✅ the input field must be named first | ✅ | ❌ when the window is covered, clicks don't reach the page (use the background browser for web pages) | None |
| Emulators, custom-drawn apps | ✅ text recognition | ✅ background click | ✅ | ✅ | ❌ (window must be there, not minimized) | None; OCR needs a Windows text-recognition language pack |
| Dragging (any scenario) | — | ✅ background first; ⚡ borrows the real mouse if that fails | — | — | — | — |

Three more things on Windows: windows running as administrator can't be touched (a Windows rule); when a window is on another virtual desktop, SeeU won't borrow your mouse or switch you over; when the picture can't be trusted (window covered, machine busy, another desktop), it won't click by a position on the screenshot, but clicks the control instead or asks the AI to look again.

**Linux preview**

| Scenario | Read content | Click | Type | Scroll | Works while hidden | Permissions needed |
|---|---|---|---|---|---|---|
| Native apps (Text Editor, FeatherPad…) | ✅ reads controls | ✅ acts on the control; ⚡ clicking by screen position borrows the real mouse | ✅ | ✅ where there's a scroll bar; ⚡ otherwise borrows the mouse | ⚠️ covered, minimized or on another workspace: clicking by number still works, but its picture can't be captured | Screenshot permission; Qt apps also need the accessibility master switch; clicking by screen position needs remote-control permission |
| Chromium / Chrome pages (background browser) | ✅ | ✅ | ✅ | ✅ | ✅ never shows a window; shown only when you need to sign in yourself | No permission, but install Chromium or Chrome first; only sites on the allow list |
| VS Code and other web-technology apps | ✅ reads controls (start VS Code with the accessibility flag) | ✅ acts on the control | ⚡ borrows the keyboard for a few seconds | ⚡ borrows the mouse | ❌ to borrow the keyboard or mouse the window must be on the current workspace, not minimized | Accessibility master switch, started with ACCESSIBILITY_ENABLED=1, remote-control permission |
| Your own browser (Firefox, Chrome…) | ✅ look only | ❌ | ❌ | ❌ | — | Not touched: it would bypass the allow list and carries your logins; web pages go through the background browser |
| Emulators, custom-drawn apps | ✅ text recognition (needs Tesseract) | ⚡ borrows the real mouse | ⚡ borrows the keyboard | ⚡ borrows the mouse | ❌ (window must be visible) | Screenshot and remote-control permissions |
| Long-press, dragging (any scenario) | — | ⚡ borrows the real mouse | — | — | — | Remote-control permission |

More things on Linux: only GNOME 45 or later is supported (Wayland recommended), and after SeeU's GNOME extension is installed or updated you need to log out and back in once; nothing happens while the screen is locked, and SeeU won't borrow your mouse or keyboard while a system dialog (password, authorization) is open; when clicking by screen position, it won't click if that point is covered by another window.

## ③ Swimlane diagrams

Each diagram has one column per module, with time running top to bottom. `alt` = a choice between branches, `opt` = only happens when the condition holds, `loop` = repeats (always with a limit).
The "Desktop feedback" column is what you see on screen; the glow depends on the floating window's "Light" setting: off / takeover (orange only while borrowing the mouse, default) / controlled (purple whenever it's operating).
The badge just says "SeeU", or "I See" while I See is on (a breathing dot = working); borrowing the mouse and getting stuck aren't shown by color: the floating window expands and says so.

### 3.1 Click a button (native app)

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant S as Safety · step aside
  participant R as Route
  participant A as Target app
  participant F as Desktop feedback
  AI->>E: Click a button
  E->>F: Badge "SeeU" breathes,<br/>card says "Clicking 'OK'"<br/>(with only coordinates, it reads the text at the click point:<br/>on the text it says so,<br/>next to it, "Clicking near 'OK'")
  opt The AI gave a reason
    E->>F: Reason in grey under "Now…",<br/>at the bottom of the picture in live view,<br/>fades after 3 s
  end
  E->>S: Safety rules check
  alt Blocked (Terminal, system prompts,<br/>the AI client running SeeU…)
    S-->>E: Refuse
    E-->>AI: refused "please do this step yourself"
    AI-->>U: Passes it on
  else Allowed
    E->>E: Pick routes by app type<br/>(Accessibility → background click → real mouse)
    E->>R: Route 1: Accessibility, by control
    R->>A: Press (no front-window change, mouse untouched)
    opt Light = controlled
      F-->>U: Purple glow around the screen
    end
    F-->>U: Purple agent cursor "SeeU" moves onto the button
    E->>E: Verify by reading back / comparing screenshots
    alt Took effect
      E-->>AI: delivered
    else No effect
      E->>R: Route 2: background click<br/>(compare screenshots after the click,<br/>no change = record the scene, next route)
      E->>R: Route 3: borrow the real mouse
      R->>S: May I borrow it?
      loop You're typing,<br/>or kept using the mouse/keyboard<br/>for more than about 1.5 s (with a limit)
        S->>S: Wait until you've stopped for about 3 s
      end
      S->>S: Mouse queue<br/>(only one task borrows the real mouse at a time,<br/>others wait, with a limit)
      F-->>U: Floating window expands:<br/>"Using your mouse<br/>(clicking 'OK') / don't move it,<br/>back in a few seconds"<br/>(top of the island when multitasking)
      F-->>U: Bright orange agent cursor,<br/>name tag shows your name
      opt Light = takeover or controlled
        F-->>U: Orange glow around the screen
      end
      F->>F: The badge gets out of the way<br/>(ignores the mouse for these seconds)
      S->>S: Refuse if SeeU's own badge is still underneath
      Note over S,F: So the AI can't click SeeU's own buttons and turn on I See for itself
      S->>A: Bring to front, click with the real mouse
      Note over U,S: If you keep using the mouse/keyboard for more than about 1.5 s = pause,<br/>resumes about 3 s after you stop. No click while the target app shows a dialog
      S->>A: Restore the previous front app and mouse position
      F-->>U: 2.5 s after borrowing,<br/>the expanded window collapses itself
      E->>E: Verify
      alt Success
        E-->>AI: delivered
      else Still no luck
        F-->>U: Floating window expands: "Stuck:<br/>reason / what to do: …",<br/>stays open until you deal with it (1 hour at most)
        E-->>AI: Failed (where · why · what to do)
      end
    end
  end
```

Whoever opens it closes it: a window that opened itself to say the mouse is being borrowed collapses by itself 2.5 s afterwards; a window you opened stays open until you collapse it, and while the mouse is borrowed it only shows the notice and then switches back. Getting stuck also opens the window by itself; it waits for you to collapse it, or goes back to normal when the AI carries on.
Fallback: after 60 s idle it shrinks to the badge, then fades after another 60 s; on Windows and Linux it simply disappears after 120 s idle. Stuck is the exception: the window stays open for up to 1 hour, and only then goes away like this.

**Several tasks at once**

- What SeeU does:
  - Only one task acts on the same app at a time (on Windows, the same window); after a step it keeps the app for a few seconds for its next step. The others queue for up to 30 seconds; if their turn doesn't come, the AI is told "busy, try again shortly" — nobody barges in. Several conversations in one AI client and different clients such as Claude and Codex all queue the same way.
  - Slow work such as typing a long passage keeps reporting "still working", so nobody cuts in; a step that was stopped because another task had just touched the app, so nothing was done, gives the app up right away.
  - If a click by position had to queue for more than 3 seconds and meanwhile the window moved or the picture near the click point changed, SeeU doesn't click and asks the AI to look again; if another task moved the focus in the same app, typing or a key press without a target field is skipped this time and the AI is asked to name the field (tapping the field and typing then happen in one go, with nobody in between).
  - Only one task borrows the real mouse at a time; the others queue. If a borrow had to wait, SeeU takes a fresh "before" picture after the wait, so a screen that changed by itself while waiting isn't mistaken for a successful click.
  - If a task exits unexpectedly without letting go, its claim expires after a while instead of blocking forever.
  - Each task has its own cursor, labeled with its conversation name (Claude, Claude2…) in its own color; a queued one dozes off (Zz) and fades. The island splits into two parts, with queued tasks below.
- Suggestions:
  - Stagger scheduled tasks, especially ones that borrow the mouse (dragging, clicks that don't land in the background);
  - Run mouse-heavy tasks when you're not using the computer;
  - Give SeeU a desktop of its own and work on another one, so you don't get in each other's way;
  - Use background routes wherever possible (ADB first for emulators, SeeU's own copy for Electron apps); the fewer mouse borrows the better.

Example: the author runs several automation projects at once (a phone app, an Android emulator, web form filling) and wrote a set of cross-project rules for them: who's using the mouse, who should give way, how scheduled tasks are staggered, how a crashed program's claim is taken over. The queue above is the smallest piece taken from those rules.

### 3.2 Typing

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant S as Safety · step aside
  participant R as Route
  participant A as Target app
  participant F as Desktop feedback
  AI->>E: Type some text into a field<br/>(optionally with Return)
  E->>S: Is the Mac locked ·<br/>is a system password being entered ·<br/>does the text contain a dangerous command ·<br/>may the target be touched
  alt Any yes
    E-->>AI: refused "please do this step yourself"<br/>(never types while locked,<br/>clicks still work)
  else All clear
    E->>F: Card says "Typing into 'Search'"<br/>(the field's name in quotes,<br/>the AI's reason in grey below if given)
    E->>R: Route 1: background typing
    R->>A: Focus without bringing to front,<br/>send characters straight to the target process<br/>(Chinese and English both work)
    E->>E: Verify: read the field,<br/>or recognize text in a screenshot if unreadable,<br/>look for the last few characters
    alt It went in
      opt Return needed
        E->>R: Press Return separately<br/>(so half a sentence doesn't get sent)
      end
      E-->>AI: delivered
    else It didn't go in<br/>(emulators skip this and report no effect)
      E->>R: Route 2: foreground typing
      R->>S: Step-aside check + mouse queue
      S->>A: Bring to front and type
      S->>A: Restore the front app
      E-->>AI: Success / no effect<br/>(the caller decides what's next)
    end
  end
```

Example: when the author tested in BlueStacks (an Android emulator), text that wouldn't go in was caused by Android's input connection breaking, so even a real keyboard couldn't type; and with the window on another desktop, switching to the front just grabbed the front window for nothing. So emulators skip foreground typing and report no effect straight away.

### 3.3 iPhone Mirroring: background clicks and scrolling (private interface)

> **Highlight**: clicks and scrolling in Mirroring use macOS's unpublished SkyLight interface (`SLEventPostToPid`) to post events straight to the mirroring window: **your mouse doesn't move and the front window doesn't change**. This is what lets SeeU work truly in the background in iPhone Mirroring and emulators.
> **⚠️ Good to know up front**: ① a system update may change it → SeeU checks every time whether the interface is still there and goes straight to the real mouse if not; ② posted events come with no receipt, so there's no telling whether a click landed → it verifies by comparing screenshots, and if nothing changed it records the scene and falls back to the real mouse;
> ③ buttons are found by recognizing text in screenshots, which doesn't depend on this interface and keeps working if it breaks; ④ the approach was learned from the public code of the open-source project Cua; no closed-source program was reverse-engineered.

```mermaid
sequenceDiagram
  autonumber
  participant AI as AI / project
  participant E as SeeU entry
  participant R as Background click
  participant M as iPhone Mirroring
  participant S as Safety · step aside
  participant F as Desktop feedback
  AI->>E: Click "OK" / scroll down somewhere<br/>(can give a blank spot)
  E->>E: Capture only the mirroring window and recognize text<br/>to find where "OK" is<br/>(public interface, not a phone screenshot)
  E->>R: Is the private interface still there?
  alt No (changed by a system update)
    R-->>E: Unavailable
    E->>S: Go straight to the real mouse<br/>(step aside + mouse queue,<br/>see 3.1)
  else Yes
    E->>F: Card says "Clicking 'OK'"<br/>("…near" when next to the text)<br/>/ "Scrolling down"
    opt You have Apps<br/>or Spotlight open<br/>(a background click would close them)
      E->>E: Wait up to 15 s for you to finish,<br/>on timeout click anyway and save a screenshot of the panel
    end
    R->>M: First send "mouse moving in from outside the window"<br/>so the window knows where the pointer is
    R->>M: Post the click / scroll events straight to the mirroring process<br/>(mouse untouched, front window unchanged)
    Note over R,M: No receipt for posted events, only the screen shows whether they arrived
    E->>E: Compare screenshots
    alt Screen changed
      E-->>AI: Success
    else No change · click
      E->>E: Record the scene (before/after screenshots,<br/>which window is at that point)
      E->>S: Fall back to the real mouse and click again<br/>(step aside + mouse queue)
      E-->>AI: Success / failed (where · why ·<br/>what to do)
    else No change · first scroll right after a click
      R->>M: Add a small drag on a blank spot to unstick it<br/>(won't hit a list row)
      R->>M: Scroll again
      E-->>AI: Scrolled / didn't move<br/>(the caller decides)
    end
  end
```

There's no background way to drag; it always borrows the real mouse (see 3.1).

Example: when the author used iPhone Mirroring on mini program pages inside an app (web pages embedded in the app), they found that after one background click, pop-up panels stopped scrolling; the "small drag" above was added for that, landing on blank space in the list so nothing gets clicked by mistake.
The author's own automation also needs the mirroring window fixed at 391×859, so it turns on the "fixed size" switch (`SEEU_BASELINE=1`); SeeU doesn't pin the size by default, and any window size works.

### 3.4 Stealth browser at work, then called out

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant ST as Stealth browser
  participant W as Watchdog
  participant B as Browser
  participant F as Desktop feedback
  AI->>ST: Launch Safari / Chrome in stealth and open a page
  alt You already have this browser open
    ST-->>AI: Leave it alone (stealth is for SeeU only)
  else Not open
    ST->>B: Hide it right after launch<br/>(Safari shows no window,<br/>Chrome shows for 0.2–0.4 s)
    ST->>W: Start the watchdog,<br/>checking every 0.3 s whether a window shows
    loop Working
      AI->>B: Read pages / click / fill in<br/>(Safari via the Apple Events switch,<br/>Chrome via the debugging port)
      F-->>U: Badge just says SeeU,<br/>card says "Safari is working hidden in the background,<br/>don't open it", live view greyed out
    end
    opt You click the Dock icon or "live view"
      B-->>W: A window is showing
      W->>W: Noticed within about 0.24 s,<br/>notes "was called out"
      W->>F: Floating window expands "Stuck:<br/>called onto the desktop / what to do:<br/>reopen with one command" + toast
      W->>W: Records evidence once in the background
      AI->>B: Click / type again
      W-->>AI: Always refused (even if hidden again)
      U->>ST: After looking, runs the one-command reopen
      ST->>B: Close → reopen in stealth → tabs restored as they were
      ST->>W: New watchdog
    end
    AI->>ST: Quit when done
  end
```

### 3.5 Electron app through the debugging port (VS Code as the example)

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant C as Debugging port
  participant A as Electron app
  participant F as Desktop feedback
  AI->>E: Change some text in VS Code and save
  alt It's the copy you have open yourself
    E->>A: Can't connect to the debugging port, use the old way<br/>(Accessibility → background typing)
    E->>A: Things like saving briefly borrow the front window<br/>(see stepping aside in 3.1)
    E-->>AI: Success,<br/>noting "this step borrowed the front window"
  else Left to SeeU on its own
    alt SeeU's own copy is already running
      E->>C: Connect directly
    else Not open yet
      E->>C: Open SeeU's own copy<br/>(separate profile, random port,<br/>local machine only)
      C->>A: Hide it as soon as a window appears,<br/>hand the front back to you (may flash)
    end
    F-->>U: Floating window says "Working in VS Code"
    C->>A: Make the page think it has focus
    alt Focus is in VS Code's built-in terminal / a dangerous command is about to be typed
      C-->>E: Refuse (safety rules)
      E-->>AI: refused "please do this step yourself"
    else Normal
      C->>A: Read the whole file / type / send ⌘S to save
      C->>C: Read back to verify<br/>(any unsaved changes?)
      C-->>E: Success
      E-->>AI: delivered
    end
    opt You call it out from the Dock
      F-->>U: Stops within 0.2 s,<br/>floating window expands with an explanation + toast
      U->>E: After looking, runs the one-command reopen<br/>(same files)
    end
    E->>C: Close it when done, the port closes with it
  end
```

### 3.6 Windows preview: click a button

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant S as Safety · step aside
  participant R as Routes
  participant A as Target window
  participant F as Desktop feedback
  AI->>E: Click a button<br/>(number / name / screen position)
  E->>F: "SeeU" badge breathes,<br/>card says "Clicking 'OK'"
  E->>S: Safety rules check
  alt Hit (admin window, command-line window,<br/>password app, the AI client running SeeU…)
    S-->>E: Refuse
    E-->>AI: refused "please do this step yourself"
    AI-->>U: Passes it on
  else Passed
    E->>E: Find the target: a number is checked first<br/>(gone = don't click, ask the AI to look again),<br/>a name is looked up in controls, then in OCR results
    opt Only a screen position (or an OCR result)
      E->>E: Can the picture be trusted?<br/>(window covered, machine busy, another virtual desktop)
      alt Can't
        E-->>AI: Don't click, use a number or look again
      end
    end
    F-->>U: Purple agent cursor moves to the button
    E->>R: Step 1: background click
    R->>A: Mouse messages to the child window under that point<br/>(no front switch, mouse untouched)
    E->>E: Verify (picture, window title,<br/>control contents, text read back,<br/>any change counts)
    alt Took effect
      E-->>AI: delivered
    else No effect
      E->>S: May it borrow?
      alt Window on another virtual desktop
        S-->>E: No borrowing, no switching you over
        E-->>AI: refused "please switch over, or move the window here"
      else Borrow mouse = off
        E-->>AI: Stops and says where it's stuck
      else Borrow mouse = ask
        F-->>U: Orange toast: needs to borrow
        E-->>AI: ask_user (the AI retries once you agree)
      else Borrow mouse = on (default)
        opt The control can be "pressed"
          E->>R: Step 2: borrow the front and press
          R->>A: Front for about 0.03–0.2 s,<br/>then handed straight back
        end
        E->>R: Step 3: borrow the real mouse
        R->>S: Are you using the computer?
        loop Mouse or keyboard used in the last second (waits up to 6 s)
          S->>S: Wait until you stop
        end
        alt Still in use
          E-->>AI: refused "you're using the computer, not borrowing now"
        else You stopped
          F-->>U: Bright orange agent cursor
          R->>A: Bring to front, check nothing covers the point,<br/>real mouse click (about 0.2 s)
          R->>A: Mouse back where it was, front back to the previous app
          E->>E: Verify
          E-->>AI: delivered, or failed (where · why · what to do)
        end
      end
    end
  end
```

Main differences from the Mac (3.1): Windows has no private-interface step, background clicks are window messages; there's an extra "borrow the front and press" step, faster than the real mouse and without moving it; no system permissions to grant.

### 3.7 Windows preview: web pages through the background browser

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant N as Allow list
  participant B as Background browser
  participant F as Desktop feedback
  AI->>E: Open a page
  E->>N: Is this site on the list?<br/>(no limit while I See is on)
  alt Not on it
    E-->>AI: refused "not on the allow list"
    AI-->>U: Asks whether to add it
    opt You agree
      AI->>N: Add it, open again
    end
  else On it
    alt Background browser already running
      E->>B: Attach
    else Not started
      E->>B: Start SeeU's own Chrome or Edge<br/>(windowless, separate profile, random port,<br/>local only, your own browser untouched)
    end
    loop Work
      AI->>E: Read the page / click by number / fill in
      E->>B: Through the debugging port
      alt Cursor in a password, verification-code or bank-card field
        B-->>E: No typing, no keys that change the contents
        E-->>AI: refused "please do this step yourself"
      else Normal
        B-->>E: Read back and verify
        E-->>AI: delivered
      end
      F-->>U: Floating window says it's working on a page,<br/>live view greyed out (no window to show)
    end
    opt The site needs a login
      AI-->>U: Please sign in yourself
      U->>E: Agree to show it
      E->>B: Close, reopen as a normal window
      U->>B: Sign in yourself
      E->>B: Close the window, reopen windowless<br/>(the login stays in this profile)
    end
  end
```

No long-press or dragging in browsers (both act by screen position and would bypass the allow list); things on a page are clicked by number only.

### 3.8 Linux preview: click a button, type into a field

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant S as Safety · step aside
  participant R as Routes
  participant A as Target window
  participant F as Desktop feedback
  AI->>E: Click a button / type into a field<br/>(number / name / screen position)
  E->>F: "SeeU" badge breathes,<br/>card says "Clicking 'OK'"
  E->>S: Safety rules check
  alt Hit (terminal, password field, dangerous menu such as "Run",<br/>the AI client running SeeU, screen locked…)
    S-->>E: Refuse
    E-->>AI: refused "please do this step yourself"
    AI-->>U: Passes it on
  else Passed
    E->>E: Find the target: back to the window it last looked at<br/>(several same-named windows don't get mixed up),<br/>a number is checked first
    alt By number / name, the control can act or the field accepts text
      F-->>U: Purple agent cursor glides to the target
      E->>R: Step 1: act on the control
      R->>A: The control's own action / insert text into the field<br/>(mouse and keyboard untouched, no front switch, works when covered)
      E->>E: Verify (control or window title changed,<br/>or the text read back matches)
      E-->>AI: delivered
    else Only a screen position, or the background can't do it<br/>(VS Code input fields, emulators)
      opt Only a screen position
        E->>E: Is that point covered by another window?
        alt Covered
          E-->>AI: Don't click, use a number or look again
        end
      end
      E->>S: May it borrow?
      alt Screen locked, a system dialog open,<br/>window minimized or on another workspace
        S-->>E: No borrowing
        E-->>AI: refused (with the reason)
      else Borrow mouse = off
        E-->>AI: Stops and says where it's stuck
      else Borrow mouse = ask
        F-->>U: Orange toast: needs to borrow
        E-->>AI: ask_user (the AI retries once you agree)
      else Borrow mouse = on (default)
        E->>S: Queue with other SeeU tasks, one at a time
        R->>S: System remote-control permission<br/>(asks you the first time, not after that)
        loop Mouse or keyboard used in the last second (waits up to 6 s)
          S->>S: Wait until you stop
        end
        alt Still in use
          E-->>AI: refused "you're using the computer, not borrowing now"
        else You stopped
          F-->>U: Orange named cursor + orange glow around the screen,<br/>the window opens by itself: "Using your mouse",<br/>collapses 2.5 s afterwards
          R->>A: Bring to front, move the pointer, click / press / type<br/>(Chinese is pasted via the clipboard, then restored)
          R->>A: Pointer back where it was, front back to the previous app
          E->>E: Verify
          E-->>AI: delivered, or failed (where · why · what to do)
        end
      end
    end
  end
```

Main differences from Windows (3.6): on Linux the background has only one step, "act on the control" (no mouse messages to windows), so when that can't do it SeeU borrows the real mouse and keyboard; borrowing needs the system's remote-control permission; nothing is borrowed while the screen is locked or a system dialog is open.

### 3.9 Linux preview: web pages through the background browser

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant AI as AI / project
  participant E as SeeU entry
  participant N as Allow list
  participant B as Background browser
  participant F as Desktop feedback
  AI->>E: Open a page
  E->>N: Is this site on the list?<br/>(no limit while I See is on)
  alt Not on it
    E-->>AI: refused "not on the allow list"
    AI-->>U: Asks whether to add it
    opt You agree
      AI->>N: Add it, open again
    end
  else On it
    alt Background browser already running
      E->>B: Attach
    else Not started
      E->>B: Start SeeU's own Chromium or Chrome<br/>(windowless, separate profile, random port,<br/>local only, your own browser untouched)
    end
    loop Work
      AI->>E: Read the page / click by number / fill in
      E->>B: Through the debugging port
      alt Cursor in a password, verification-code or bank-card field
        B-->>E: No typing, no keys that change the contents
        E-->>AI: refused "please do this step yourself"
      else Normal
        B-->>E: Read back and verify
        E-->>AI: delivered
      end
      F-->>U: Floating window says it's working on a page,<br/>live view greyed out (no window to show)
    end
    opt The site needs a login
      AI-->>U: Please sign in yourself
      U->>E: Agree to show it
      E->>B: Close, reopen as a normal window
      U->>B: Sign in yourself
      E->>B: Close the window, reopen windowless<br/>(the login stays in this profile)
    end
  end
```

Same as Windows (3.7); only the browser differs: Linux uses Chromium or Chrome (the snap Chromium on Ubuntu works too). Your own browser is look-only for SeeU (tapping, typing, pressing keys and scrolling are refused), so web pages always go to this background browser.

## ④ State diagrams

### 4.1 Stealth browser

```mermaid
stateDiagram-v2
  NotOpen: Not open
  Hidden: Working hidden
  Out: Called out
  Stopped: Stopped
  [*] --> NotOpen
  NotOpen --> Hidden: Launch in stealth (left alone if you have it open)
  Hidden --> Hidden: Read / click / type
  Hidden --> Out: You click the Dock icon or live view
  Out --> Stopped: Noticed within about 0.24 s; window expands + toast + evidence
  Stopped --> Stopped: Any further action refused (even if hidden again)
  Stopped --> Hidden: You run the one-command reopen (tabs as they were)
  Hidden --> NotOpen: Quit when done
```

### 4.2 Floating window

```mermaid
stateDiagram-v2
  None: Not shown
  Badge: Badge
  Win: Floating window
  Borrow: Borrowing notice (opened by itself)
  WinBorrow: The window you opened shows the borrowing notice
  Stuck: Stuck notice
  Island: Island
  [*] --> None
  None --> Badge: SeeU starts acting (always starts as the badge, no memory of last time)
  Badge --> Win: You open it
  Win --> Badge: You collapse it, or 60 s idle
  Badge --> None: Auto · another 60 s idle, fades out
  Badge --> Borrow: Auto · borrows the real mouse
  Borrow --> Badge: Auto · collapses 2.5 s after handing back
  Win --> WinBorrow: Auto · borrows the real mouse
  WinBorrow --> Win: Auto · switches back, stays open
  Badge --> Stuck: Auto · a step gets stuck
  Win --> Stuck: Auto · a step gets stuck
  Stuck --> Win: Auto · the AI carries on, stays open
  Stuck --> Badge: You collapse it, or 1 hour unattended
  state Win {
    Live: Live view
    Steps: Steps
    [*] --> Live
    Live --> Steps: Click "Steps" (the only option for stealth browsers)
    Steps --> Live: Click "Live view"
  }
  Badge --> Island: Two or more tasks running (shares the badge's position)
  Island --> Badge: Only one left
  note right of Badge
    Says "SeeU", or "I See" while I See is on
    Dot color = current mode (purple = background, orange = borrowing the mouse, changeable in settings), breathing = working
  end note
  note left of Win
    While an AI is using it: reason in grey under "Now…"
    The button bar gets a "Reason" switch (on by default)
  end note
  note right of Island
    Opened: one row per task
    Order: borrowing the mouse > stuck > most recent activity
  end note
```

### 4.3 I See (I know the risks: authorized to act first)

```mermaid
stateDiagram-v2
  Off: Off
  On: On
  [*] --> Off
  Off --> On: You click the floating window button yourself (SeeU never clicks its own; the AI won't turn it on for you) / you turn it on from the command line
  On --> Off: You turn it off
  On --> Off: Turns off automatically after 24 h by default (reminds you if the browser's extra permission is still on)
  state On {
    Work: Working
    Try: Trying another way
    Skip: Skipped
    Halt: Stuck
    [*] --> Work
    Work --> Try: Hits a problem, doesn't stop to ask
    Try --> Work: Found a way (at most 3 routes / 60 s per spot)
    Try --> Skip: Can't do it, nothing later depends on it (noted, reported at the end)
    Skip --> Work
    Try --> Halt: Everything later depends on it (stops and reports at once)
  }
  note right of Off
    When off, anything it can't do is reported straight away:
    where it's stuck, why, what to do
    Web pages only; stepping aside, password fields and safety rules still apply when on
  end note
```

## ⑤ Mind map

Everything SeeU can do, in one picture.

```mermaid
mindmap
  root((SeeU))
    See
      Screenshots + text recognition
      Read controls via Accessibility
      List of page elements
    Act
      Click · long-press
      Type · keys · menus
      Scroll · unstick with a drag
      Dragging borrows the mouse
    Six scenarios
      Safari
      Chrome and others
      Electron apps
      Native apps
      Emulators
      iPhone Mirroring
    Stays out of your way
      Background clicks · front window untouched
      Steps aside · mouse queue
      Several AIs at once · same app takes turns
      Stealth browsers
      Debugging port
    Lets you see
      Floating window · badge
      Island · multitasking
      Agent cursor · glow
      Toasts
      The AI's reasons
      Always tells you before borrowing the mouse
    Safety rules
      Hard-coded safety rules
      Never touches password apps
      Never clicks its own badge
      AI rule: never submits or pays for you
      I See, I know the risks
    Evidence when things go wrong
      Permission check
      One-command evidence
      Stops when called out
    Who uses it
      Python programs
      AI · MCP plus Skill
      One-step setup for Claude, Codex and more · add Qwen and others by hand
      Command line
```
