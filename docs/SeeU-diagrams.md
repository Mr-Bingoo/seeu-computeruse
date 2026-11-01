# SeeU diagrams

> Written by @Mr_Bingoo x Claude · "the author" below = @Mr_Bingoo
>
> The diagrams show "what's there and how it flows"; the docs explain "why, and which pitfalls we hit". The diagrams are written in Mermaid: change a line of text and the diagram follows, and GitHub renders them directly.
> Five kinds: ① overview (what it's made of) ② capability matrix (how far each scenario goes) ③ swimlane diagrams (for one step: who does what, how it decides, how it returns; one per action)
> ④ state diagrams (which states it can be in and how it switches) ⑤ mind map (all features at a glance).
> The diagrams only show SeeU's general approach; where a step was added because the author hit a problem in a real scenario, a short "Example:" paragraph under the diagram explains it.

## ① Overview

```mermaid
block-beta
  columns 6
  H1["① Who calls it"]:6
  U1["Your Python programs<br/>scheduled tasks, automation"]:2
  U2["AI (Claude, Codex…)<br/>MCP tools + Skill instructions<br/>one-step setup"]:2
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

## ② Capability matrix

Legend: ✅ background, no disturbance · ⚡ briefly borrows the front window or your mouse · ⚠️ with conditions · ❌ not possible

| Scenario | Read content | Click | Type | Scroll | Works while hidden | Permissions needed |
|---|---|---|---|---|---|---|
| Safari | ✅ | ✅ | ✅ | ✅ | ✅ stealth Safari | Accessibility, the Safari switch (asks for your password), control of Safari |
| Chrome etc. | ✅ | ✅ | ✅ | ✅ | ✅ stealth Chrome (flashes 0.2–0.4 s at startup) | Accessibility, extension or switch; stealth Chrome uses the debugging port and needs nothing turned on |
| Electron apps (desktop software built with web tech; Electron, CEF and the like all count; e.g. VS Code) | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ⚠️ yours needs the window visible | ✅ SeeU's own copy; ❌ your own copy | None for SeeU's copy; yours needs Accessibility and Screen Recording |
| Native apps (Notes…) | ✅ | ✅ | ✅ | ✅ | ✅ (opening a specific note flashes briefly) | Accessibility; control of that app when AppleScript is used |
| Emulators (e.g. BlueStacks) | ✅ text recognition | ✅ background click (private interface) | ✅ | ✅ | ❌ (window must be there) | Accessibility, Screen Recording |
| iPhone Mirroring | ✅ text recognition | ✅ background click (private interface) | ✅ | ✅ (adds a small drag when stuck) | ❌ (window must be there, any size) | Accessibility, Screen Recording |
| Dragging (any scenario) | — | ⚡ borrows the real mouse | — | — | — | Same as above |

Every scenario goes through the safety rules first: Terminal, system permission prompts, the Privacy & Security part of System Settings, password apps (Keychain, Passwords, 1Password and so on), the AI client running SeeU itself (such as Claude or Codex), SeeU's own floating window buttons (so the AI can't turn on I See for itself), and dangerous shortcuts / commands / menu items are all blocked; password, CAPTCHA and bank card fields are never touched.

"Background click (private interface)" = posting the click straight to the window through an interface macOS hasn't made public. It may stop working after a system update, and then SeeU automatically falls back to the real mouse (see 3.3).

For emulators we suggest ADB first (Android's official debugging tool, a public interface that doesn't go through SeeU): clicks, swipes and screenshots are fully in the background with accurate coordinates. SeeU fills in with background clicks, for example typing Chinese (ADB's built-in input only handles English letters and numbers) or when ADB isn't enabled in the emulator.

## ③ Swimlane diagrams

Each diagram has one column per module, with time running top to bottom. `alt` = a choice between branches, `opt` = only happens when the condition holds, `loop` = repeats (always with a limit).
The "Desktop feedback" column is what you see on screen; the glow depends on the floating window's "Light" setting: off / takeover (orange only while borrowing the mouse, default) / controlled (purple whenever it's operating).
The badge always just says "SeeU" (a breathing dot = working); borrowing the mouse and getting stuck aren't shown by color: the floating window expands and says so.

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
        F-->>U: Floating window expands: "Stuck:<br/>reason / what to do: …",<br/>stays open until you deal with it
        E-->>AI: Failed (where · why · what to do)
      end
    end
  end
  Note over E,F: A window you opened stays open until you collapse it,<br/>as a fallback it shrinks to the badge after 60 s idle, then fades after another 60 s
```

**Several tasks at once**

- What SeeU does: only one task borrows the real mouse at a time; the others queue. The wait has a limit, and if it runs out the task reports "stuck" rather than grabbing the mouse. If a task exits unexpectedly without letting go, its claim expires after a while instead of blocking forever.
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
  Note over AI,M: There's no background way to drag, it always borrows the real mouse (see 3.1)
```

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
  Borrow: Expanded (borrowing the mouse)
  Stuck: Expanded (stuck)
  Island: Island
  [*] --> None
  None --> Badge: SeeU starts acting (always starts as the badge, no memory of last time)
  Badge --> Win: You open it
  Win --> Badge: You collapse it, or 60 s idle
  Badge --> None: Another 60 s idle, fades out
  Badge --> Borrow: Borrows the real mouse
  Borrow --> Badge: Collapses itself 2.5 s after handing back
  Badge --> Stuck: A step gets stuck
  Stuck --> Badge: You collapse it (it won't on its own)
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
    Always just says "SeeU"
    Dot color = your chosen color, breathing = working
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
  Off --> On: You click the floating window button yourself (SeeU never clicks its own) / tell the AI "turn on I See" / turn it on from the command line
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
      Never submits or pays for you
      I See, I know the risks
    Evidence when things go wrong
      Permission check
      One-command evidence
      Stops when called out
    Who uses it
      Python programs
      AI · MCP plus Skill
      One-step setup for Claude, Codex and more
      Command line
```
