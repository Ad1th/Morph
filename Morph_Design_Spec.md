# MORPH — Design Specification
## Designer Handoff Document
### Immersive, OS-Adaptive Environment Reproduction Interface

---

# 0. Purpose of This Document

This document is the design handoff for Morph.

It is intentionally written for the person responsible for the visual design, interaction design, motion, and frontend-facing design system.

Morph is not supposed to look like a normal developer dashboard.

The product's central visual idea is **Immersion**:

> When a developer chooses an environment to reproduce, Morph should make them feel like they have entered that environment.

If the target is Windows, the workspace should look and behave visually like Windows.

If the target is Linux, it should look and behave visually like Linux.

If the target is macOS, it should look and behave visually like macOS.

This visual layer is not claiming to virtualize an entire operating system. The actual reproduction is performed by Morph's runtime using controllable system conditions. The interface gives the developer an immersive representation of the environment being tested and provides the controls, evidence, experiment results, and application workspace around that execution.

The design should communicate sophisticated systems engineering without becoming a generic "AI developer tool" dashboard.

---

# 1. Product Design Goal

Morph should answer this question visually:

> "What if I could take the machine where my software failed and bring that environment onto my own machine?"

The interface should make that concept immediately understandable.

A developer should be able to:

1. Capture or define an environment.
2. See exactly what Morph is trying to reproduce.
3. Enter an immersive representation of that environment.
4. Run the application.
5. Observe the failure.
6. Experiment with individual conditions.
7. Identify the condition or combination responsible.
8. Fix the application.
9. Replay the same environment.
10. Turn the discovered failure into a permanent regression test.

The UI must make this journey obvious.

---

# 2. Core Design Principle: IMMERSIVE

## This is the most important design requirement.

Morph should NOT feel like:

- A Grafana dashboard.
- A generic cloud console.
- A Docker management UI.
- A standard CI dashboard.
- A collection of cards.
- An AI chat interface.
- A monitoring product.

It should feel like an environment laboratory.

The visual language should combine:

- Developer tooling
- Operating-system interfaces
- Hardware/system visualization
- Laboratory instrumentation
- Controlled experimentation
- High-end technical software

The product should feel serious enough for an experienced developer but visually exciting enough that a hackathon judge immediately wants to interact with it.

---

# 3. Signature Interaction

The signature interaction should be:

## "Enter Environment"

Example:

The developer selects:

WINDOWS 11

CPU:
4 cores
2.4 GHz

RAM:
8 GB

Locale:
en-IN

Network:
180 ms latency
2% packet loss

They press:

**ENTER ENVIRONMENT**

The interface transitions from the Morph control interface into an OS-adaptive workspace.

The environment changes visually.

For Windows:
- Windows-style desktop
- Windows-style taskbar
- Windows-style application windows
- Windows filesystem conventions
- Windows terminal representation

For Linux:
- Linux desktop representation
- Linux-style panels/window chrome
- Linux terminal
- `/home/...` filesystem conventions

For macOS:
- macOS-style menu bar
- macOS-style Dock
- macOS-style application windows
- Finder-like filesystem representation
- macOS terminal

The application being tested appears inside that workspace.

This transition should be one of the strongest moments in the demo.

---

# 4. Important Technical/Design Boundary

The OS-adaptive workspace is a visual and interaction representation of the target environment.

It should NOT be designed as if Morph is claiming to emulate every instruction, kernel subsystem, driver, or hardware component of an entire computer.

The underlying Morph runtime is responsible for applying reproducible conditions such as:

- CPU allocation/limits
- Memory limits
- Network latency
- Packet loss
- Jitter
- Bandwidth constraints where supported
- Locale/time configuration
- Filesystem isolation
- Environment variables
- Application dependencies
- Relevant runtime conditions

The interface represents those conditions clearly.

Therefore:

### Visual fidelity should be high.

### System virtualization claims should remain technically honest.

This distinction is important for the pitch and for technical judges.

---

# 5. Visual Identity

## Desired feeling

Morph should feel:

- Precise
- Technical
- Experimental
- Premium
- Minimal
- Fast
- Deep
- Slightly futuristic
- Developer-native

Avoid:

- Excessive gradients
- "AI purple" aesthetics
- Floating glass cards everywhere
- Generic SaaS dashboards
- Excessive rounded rectangles
- Stock illustrations
- Cartoonish icons
- Corporate enterprise styling
- Overly flashy cyberpunk effects

The visual sophistication should come from information architecture, typography, motion, system visualization, and detail.

---

# 6. Color System

Morph should have a restrained base palette.

Suggested direction:

### Base

Near-black / very dark neutral background.

### Primary surfaces

Dark charcoal / graphite.

### Secondary surfaces

Slightly lighter graphite.

### Borders

Low-contrast neutral borders.

### Primary accent

Use one recognizable Morph accent.

It should appear primarily for:

- Active controls
- Environment transitions
- Experiment state
- Important metrics
- Confirmed findings

Do not use the accent everywhere.

### Semantic colors

Green:
Confirmed success / reproduced / fixed

Yellow:
Warning / inconclusive / unstable

Red:
Failure / reproduced failure

Blue or neutral:
Informational state

The exact colors should be selected in Figma and formalized as design tokens.

---

# 7. Typography

Use a highly readable modern sans-serif.

Possible direction:

- Inter
- Geist
- SF Pro-like system typography

Use a monospace font for:

- Terminal
- Commands
- CPU/system values
- Logs
- Environment identifiers
- Technical output
- Reproduction commands

Typography should create hierarchy without relying on huge text.

---

# 8. LANDING PAGE

## Objective

The landing page should be immersive.

This is NOT supposed to be a normal SaaS landing page with:

Hero
→ Features
→ Pricing
→ Testimonials
→ Footer

The opening experience should communicate:

> "Morph can enter the machine."

---

# 9. Immersive Landing Page Concept

## Scene 1 — A Computer

Start with a highly detailed computer/laptop representation.

It should look like a real machine rather than an abstract illustration.

The screen displays a normal operating system.

The page starts relatively calm.

Headline:

MORPH

Supporting copy should be short.

The primary visual does the explanation.

---

# 10. Scroll Interaction: Enter the Computer

As the user scrolls:

The camera moves toward the computer.

Then into the screen.

Then deeper into the machine.

The viewer sees internal components.

Possible sequence:

Computer
↓
Motherboard
↓
CPU
↓
CPU package
↓
Transistors / internal structures
↓
Memory
↓
RAM modules
↓
Storage
↓
SSD/NAND
↓
Individual NAND cells/chips
↓
Zoom back out

This does NOT need to be physically accurate at semiconductor level.

It needs to visually communicate increasing levels of system detail.

The concept:

> A computer is not one thing. It is a collection of interacting layers and conditions.

---

# 11. Environment Morphing

After zooming into hardware, the visual should begin changing.

For example:

One CPU configuration becomes another.

One RAM configuration becomes another.

Storage changes.

Hardware layout changes.

Then the camera pulls back.

A different machine appears.

The operating system changes.

Windows → Linux → macOS.

This visually communicates the problem Morph solves:

Different machines create different execution realities.

---

# 12. Transition Into Product

After the immersive hardware sequence:

The user reaches the Morph product interface.

The landing page should introduce two product paths.

## Developer

Local, open-source, free.

Run Morph directly on your own machine.

## Cloud

For environments that cannot be reproduced locally or require more compute.

Cloud execution.

The exact final naming can remain aligned with the existing product positioning.

Do not invent new branding.

---

# 13. Landing Page Fallback

The fully immersive 3D sequence is desirable but NOT allowed to consume the entire hackathon.

If a proper live 3D implementation begins threatening the dashboard/product build, immediately switch to:

- Pre-rendered assets
- Image sequence
- Video sequence
- Scroll-triggered animation
- CSS transforms
- Lightweight canvas/WebGL only where necessary

The effect should still feel immersive.

The product functionality takes priority.

---

# 14. MAIN APPLICATION STRUCTURE

Recommended application structure:

```text
Morph
│
├── Environments
│
├── Reproduce
│
├── Experiments
│
├── Runs
│
├── Failures
│
├── Regression Tests
│
└── Settings
```

The exact navigation labels can be adjusted during implementation, but the conceptual hierarchy should remain.

---

# 15. HOME / OVERVIEW

The home screen should not be a generic analytics dashboard.

It should immediately answer:

- What environments exist?
- What was reproduced?
- What failed?
- What needs attention?
- What was recently discovered?

Suggested structure:

```text
MORPH

[ Environments ] [ Experiments ] [ Failures ]

Recent

Windows 11 / 8 GB / 180ms
FAILURE REPRODUCED

macOS / 16 GB / 0ms
PASS

Linux / 4 GB / 2% loss
INCONCLUSIVE
```

The main visual emphasis should be on environments and reproducibility, not charts.

---

# 16. ENVIRONMENT LIBRARY

This is one of the most important screens.

Each environment should feel like a machine profile.

Example:

```text
WINDOWS 11
Captured Environment

CPU
4 cores
2.4 GHz

MEMORY
8 GB

LOCALE
en-IN

NETWORK
180 ms
2% packet loss

FILESYSTEM
NTFS

Captured:
Sep 6, 2026
```

Include:

- OS
- OS version
- CPU architecture
- Core count
- Clock speed where available
- RAM
- GPU/hardware information where relevant
- Locale
- Timezone
- Filesystem characteristics
- Network characteristics
- Environment variables where relevant
- Application/runtime dependencies
- Capture metadata

Do not overload the initial view.

Use expandable sections.

---

# 17. ENVIRONMENT DETAIL

Clicking an environment opens a detailed environment page.

Recommended structure:

```text
WINDOWS 11
Captured Environment

[ ENTER ENVIRONMENT ]

Hardware
CPU
RAM
GPU
Storage

Operating System
Version
Architecture
Locale
Timezone

Network
Latency
Jitter
Packet Loss
Bandwidth

Runtime
Language
Runtime version
Dependencies

Filesystem
Type
Case sensitivity
Path behaviour
```

There should be a prominent:

**ENTER ENVIRONMENT**

button.

---

# 18. OS-ADAPTIVE WORKSPACE

This is the core visual feature.

When the user enters an environment, Morph should change its visual workspace according to the selected target OS.

The outer Morph controls should remain available, but the central execution area should feel like the target machine.

### Platform priority — this matches the PRD's MVP table exactly

Do not treat Windows, macOS, and Linux as equal-effort builds:

- **Windows — P0, full craft.** This is the primary demo target used in every example profile across the PRD and this spec (180ms/2% loss/4 cores/8GB). Build the full workspace: desktop, taskbar, window chrome, terminal, Explorer-like view.
- **macOS — P0, full craft.** Also must work live. Full workspace, same bar as Windows.
- **Linux — P2, recorded-fallback acceptable.** Per the PRD, Linux/Pi support can ship as a recorded fallback rather than a live P0. Design it as a **simplified/lower-fidelity representation** — recognizable panel + terminal + `/home/...` paths — not a full desktop+dock+window-manager build. If time is short, a static screen or short pre-rendered clip is acceptable; do not spend Priority-4 hours polishing it to the same level as Windows/macOS.

**If Priority 4 (this section) runs long:** protect Priority 5 and 6 (experiment interface, RCA view) at its expense, not the reverse. Those screens are where the PRD's judging-criteria mapping places Innovation and Technical Complexity; the OS skin mainly earns Immersion/UI-UX. A rougher OS transition with a sharp RCA screen beats a polished OS transition with a rushed one.

---

# 19. WINDOWS WORKSPACE

When reproducing Windows:

Visual direction:

- Windows-like desktop
- Taskbar
- Start button
- Windows-style window controls
- Windows-style application frame
- File Explorer-like view
- Windows Terminal representation
- `C:\Users\...` paths

The target OS label should remain subtly visible.

Example:

```text
┌─────────────────────────────────────────────┐
│  Morph  |  Windows 11                      │
├─────────────────────────────────────────────┤
│                                             │
│       ┌──────────────────────────────┐      │
│       │ Application                  │      │
│       │                              │      │
│       │       RUNNING                │      │
│       │                              │      │
│       └──────────────────────────────┘      │
│                                             │
├─────────────────────────────────────────────┤
│ Start     Terminal   Explorer       14:32   │
└─────────────────────────────────────────────┘
```

Do not simply use a Windows wallpaper.

The entire workspace should communicate Windows.

---

# 20. LINUX WORKSPACE (P2 — SIMPLIFIED, RECORDED-FALLBACK ACCEPTABLE)

Unlike Windows and macOS, this does not need full-fidelity live-demo craft. Build the minimum that reads as "recognizably Linux" and stop:

- Panel or terminal-first layout (skip building a full desktop+dock+window-manager)
- Terminal prominently available — this alone carries most of the "recognizable Linux" signal
- `/home/user/...` paths visible somewhere

Skip unless time genuinely allows:
- Full desktop representation
- GNOME/KDE-style window chrome
- Process/system information panel

Do not attempt to perfectly reproduce every Linux distribution — the goal is recognizable OS context, achieved as cheaply as possible. If the live build isn't ready in time, a short pre-rendered clip or static screen of this workspace is an acceptable substitute for the demo, same as the landing page's fallback policy (Section 13).

---

# 21. macOS WORKSPACE

When reproducing macOS:

Visual direction:

- Menu bar
- macOS-style window chrome
- Finder-like filesystem
- Dock
- Terminal
- `/Users/...`
- macOS-style application windows

The workspace should feel distinctly different from Windows and Linux.

---

# 22. OS SWITCHING

Switching environments should produce a noticeable transition.

Example:

```text
WINDOWS 11
        ↓
Loading environment
        ↓
Applying conditions
        ↓
Entering workspace
        ↓
LINUX
```

The transition can include:

- Window rearrangement
- Desktop transition
- Taskbar → Dock
- Filesystem path transformation
- Terminal transformation
- Environment metadata updating

This should be subtle, not theatrical.

---

# 23. APPLICATION EXECUTION

The application under test should appear inside the workspace.

The user should be able to:

- Launch it
- Interact with it where feasible
- See its output
- Trigger the known failure
- View logs
- Stop/restart it

The exact application used in the hackathon demo should be selected early.

---

# 24. DEMO APPLICATIONS

We should NOT attempt to test dozens of applications.

Build a small corpus of intentionally flawed applications.

Recommended:

### Demo 1 — Network-sensitive application

A client/server application where:

- Normal network → works
- Increased latency → degraded
- Latency + packet loss → reproducible failure

This should be the primary demo.

### Demo 2 — Resource-sensitive application

An application that behaves differently under constrained RAM/CPU.

### Demo 3 — Environment-specific application

A smaller compatibility failure involving:

- Locale
- Filesystem behaviour
- OS-specific path handling

Only one or two additional demos are necessary.

---

# 25. EXPERIMENT SCREEN

This is where Morph becomes more than an environment launcher.

The user should see:

```text
FAILURE REPRODUCED

Baseline
PASS

Current Environment
FAIL
```

Then the experiment matrix:

```text
Condition              Result

Normal Network         PASS
+ 100ms latency        PASS
+ 300ms latency        PASS
+ 500ms latency        FAIL
+ 500ms + 2% loss      FAIL
```

The interface should visually highlight the transition point.

---

# 26. VARIABLE ISOLATION

Morph should allow the user to change one condition while holding others constant.

Example:

```text
CPU
[ 4 cores ]

RAM
[ 8 GB ]

Latency
[ 0 ms ] → [ 100 ] → [ 200 ] → [ 400 ]

Packet Loss
[ 0% ]

Locale
[ en-IN ]
```

The important visual concept:

> Change one thing. Run again. Compare.

This should be extremely easy to understand.

---

# 27. BASELINE VS TREATMENT

The experiment UI should make control and treatment obvious.

Example:

```text
CONTROL
0ms latency
0% loss
8GB RAM
4 cores

Result:
PASS


TREATMENT
500ms latency
2% loss
8GB RAM
4 cores

Result:
FAIL
```

Then:

```text
CONFIDENCE
High

Network conditions strongly associated with failure.
```

Do not make the statistical analysis the primary visual.

Show the conclusion first.

Allow the technical evidence to expand below it.

---

# 28. ROOT CAUSE VIEW

The RCA screen should answer:

> What changed?

> What caused the failure?

> What evidence supports this?

Example:

```text
ROOT CAUSE

Network latency + packet loss

Confidence: High

The application passed under the baseline
environment and failed consistently when
latency and packet loss were introduced.

Evidence

Latency
0ms     PASS
100ms   PASS
300ms   PASS
500ms   FAIL

Packet loss
0%      PASS
1%      PASS
2%      FAIL

Combined condition
500ms + 2% → FAIL
```

Then:

**Create Regression Test**

---

# 29. "EXPOSED" VS "CAUSED"

This distinction is important.

Morph should not falsely claim:

"Network caused the bug."

Sometimes the network may simply expose an application bug.

The UI should support distinctions such as:

### CAUSED

The failure depends directly on the environment condition.

### EXPOSED

The environment makes an existing application bug reproducible.

### INCONCLUSIVE

Evidence is insufficient.

This will make the product feel much more technically credible.

---

# 30. FAILURE REPRODUCTION VIEW

When Morph successfully reproduces a failure:

Use a strong but restrained state change.

Example:

```text
FAILURE REPRODUCED

3 / 3 runs failed

Environment:
Windows 11
4 cores
8 GB RAM
500ms latency
2% packet loss

Original:
FAILED

Morph:
FAILED
```

The key point:

The original failure and reproduced failure should be visually connected.

---

# 31. ORIGINAL VS REPRODUCED

This could be a powerful visual.

```text
CAPTURED USER ENVIRONMENT
        │
        │ Environment profile
        ↓
MORPH REPRODUCTION
        │
        │ Same conditions
        ↓
MATCHED FAILURE
```

Show matching evidence:

- Error type
- Exit code
- Stack trace
- Request failure
- Timing
- Resource usage

Whatever is available from the demo.

---

# 32. POST-DEPLOYMENT FLOW

A developer should also be able to start from a user failure.

Flow:

```text
User Failure
     ↓
Environment data + error logs
     ↓
Environment profile
     ↓
Reproduce
     ↓
Experiment
     ↓
Root Cause
     ↓
Fix
     ↓
Regression Test
```

The UI should make this feel like one continuous workflow.

---

# 33. ERROR LOG / AGENT INPUT

The capture component should collect application-relevant environment information.

The UI should show what was captured and why.

Example:

```text
CAPTURED

OS                    Windows 11
Architecture          x86_64
CPU cores             4
CPU frequency         2.4 GHz
RAM                   8 GB
Locale                en-IN
Timezone              Asia/Kolkata
Filesystem            NTFS
Network latency       180ms
Packet loss           2%

Application
Runtime               Node 22
Dependencies          42
```

Avoid collecting irrelevant personal data.

The product should communicate that the environment profile contains technical reproduction information, not arbitrary user data.

---

# 34. REGRESSION TEST CREATION

Once a cause is confirmed:

Button:

**CREATE REGRESSION TEST**

The user sees:

```text
REGRESSION TEST CREATED

Trigger:
500ms latency
2% packet loss

Expected:
Application exits successfully

Observed before fix:
Timeout

Observed after fix:
PASS
```

This artifact should be reusable by CI.

---

# 35. REGRESSION TEST LIBRARY

The library should contain:

```text
Network timeout under high latency
Windows path compatibility
Low-memory startup
Locale date parsing
```

Each test should show:

- Environment
- Trigger
- Expected result
- Last result
- Created date
- Git/build association if available

---

# 36. CI EXPERIENCE

Morph should eventually integrate into CI.

For the hackathon:

Keep this simple.

Possible workflow:

```text
git push
   ↓
CI
   ↓
Morph regression tests
   ↓
PASS / FAIL
```

The UI should show:

```text
CI RUN

Build #142

Regression Tests
✓ Windows environment
✓ Network timeout
✓ Low-memory startup

3 / 3 passed
```

Do not build a full CI platform.

---

# 37. LIVE DEMO MODE

There should be a dedicated demo-friendly state.

The judge should not need to understand the entire product.

Recommended flow:

### Step 1

Select environment.

### Step 2

Enter environment.

### Step 3

Run application.

### Step 4

Show failure.

### Step 5

Run experiment.

### Step 6

Show root cause.

### Step 7

Fix application.

### Step 8

Replay.

### Step 9

Show PASS.

This should take minutes, not 20 minutes.

---

# 38. THE "WOW" MOMENT

The strongest moment should be:

A judge watches the application fail.

Then the developer selects the captured environment.

The interface transitions into the target OS workspace.

The same application is run.

The failure happens again.

Then Morph changes one environment variable/condition at a time and finds the trigger.

Finally:

```text
CAUSE CONFIRMED
```

Then after the fix:

```text
REPLAY

✓ PASS
```

That is the story.

---

# 39. HARDWARE VISUALIZATION

The product should visually explain that an environment is more than an OS.

Environment cards can show:

```text
CPU
████████
4 cores
2.4 GHz

MEMORY
██████░░
8 / 16 GB

NETWORK
180ms
2% loss

STORAGE
512 GB
```

For the landing page, hardware can be shown much more visually.

Inside the dashboard, prioritize readability.

---

# 40. ENVIRONMENT DIFFERENCE VIEW

A particularly useful screen:

```text
YOUR MACHINE                 TARGET

macOS 15                     Windows 11
M3                           x86_64
16 GB                        8 GB
0ms                          180ms
0% loss                      2% loss
en-IN                        en-IN
```

Highlight only the differences.

This makes the concept immediately understandable.

---

# 41. CLOUD EXECUTION

Cloud execution should look like the same environment being moved elsewhere.

Example:

```text
LOCAL

Cannot reproduce target CPU/RAM combination

[ Run in Cloud ]

        ↓

CLOUD WORKER

Environment:
Windows
4 cores
8 GB
500ms
2% loss

Status:
Running
```

The cloud should not feel like a separate product.

It is simply another execution location.

---

# 42. LOCAL-FIRST DESIGN

The product must work without internet for the core demo.

Design the UI so:

```text
LOCAL
● Connected
```

and:

```text
CLOUD
○ Available
```

The application should clearly distinguish local execution from cloud execution.

Sponsor integrations can be optional.

Do not make the primary workflow dependent on internet access.

---

# 43. SPONSOR INTEGRATIONS

The primary sponsor integration should be infrastructural rather than cosmetic.

### n8n

Use it for workflow orchestration around Morph.

Possible workflow:

```text
Morph run completed
       ↓
n8n
       ↓
Store/report result
       ↓
Trigger follow-up action
```

If n8n is unavailable:

The Morph core must continue working.

The UI should simply hide or disable the integration.

### Tin

If used as cloud infrastructure, it should host the cloud execution worker.

Again:

If unavailable, local execution must continue.

Do NOT create a dependency where the demo dies if a sponsor service is unavailable.

---

# 44. SPONSOR UI

Sponsor logos should NOT dominate the product.

A small:

```text
Cloud execution powered by ...
```

or:

```text
Workflow powered by ...
```

is enough.

The product must remain the hero.

---

# 45. TERMINAL

Terminal is important because the product is for developers.

Terminal design should feel native to the target OS.

Example:

Windows:

```text
C:\Morph\app> morph run
```

Linux:

```text
user@morph:~/app$ morph run
```

macOS:

```text
user@mac morph % morph run
```

The commands should be real wherever possible.

---

# 46. LOG VIEW

Logs should not overwhelm the interface.

Use:

- Monospace
- Timestamp
- Severity
- Source
- Expandable details

Example:

```text
14:32:10  INFO   Application started
14:32:11  INFO   Request sent
14:32:12  WARN   Request timeout
14:32:12  ERROR  Connection failed
```

Clicking an error should reveal relevant context.

---

# 47. SYSTEM TELEMETRY

Show only useful telemetry.

Potential metrics:

- CPU usage
- Memory usage
- Network latency
- Packet loss
- Request duration
- Application runtime
- Exit code

The dashboard should not become a monitoring product.

Telemetry exists to explain the reproduction.

---

# 48. EXPERIMENT HISTORY

Every experiment should produce a compact record.

Example:

```text
Experiment #12

Changed:
Latency

From:
0ms

To:
500ms

Result:
PASS → FAIL

Confidence:
High
```

Click for details.

---

# 49. RUN STATES

Every execution should have obvious states:

### Idle

Ready to run.

### Preparing

Environment is being configured.

### Running

Application is executing.

### Failed

Application failed.

### Reproduced

The expected failure was successfully reproduced.

### Passed

Application succeeded.

### Inconclusive

Results are not strong enough.

Use consistent visual semantics across the product.

---

# 50. LOADING / TRANSITION STATES

Because the product involves system configuration, transitions should feel intentional.

Instead of:

"Loading..."

Use:

```text
Preparing environment

Applying:
✓ CPU
✓ Memory
✓ Network
✓ Locale
✓ Filesystem

Starting application...
```

This gives the user confidence that something meaningful is happening.

---

# 51. RESPONSIVE DESIGN

Primary target:

Desktop.

This is a developer tool and hackathon demonstration.

Prioritize:

- 1440px
- 1600px
- 1920px

Laptop widths must still work.

Mobile is NOT a priority.

Do not spend hackathon time building a mobile version.

---

# 52. COMPONENT SYSTEM

Build reusable components early.

Required:

- Environment card
- Environment metric
- Status badge
- Run button
- Environment selector
- OS workspace window
- Terminal
- Log row
- Experiment result
- Comparison row
- Timeline
- Root cause card
- Regression test card
- Modal
- Toast
- Navigation
- Tabs
- Slider
- Toggle
- Data table

Components should support multiple states.

---

# 53. Figma STRUCTURE

Recommended Figma structure:

```text
00 — Cover
01 — Foundations
02 — Components
03 — Landing Page
04 — Environment Library
05 — Environment Detail
06 — OS Workspaces
07 — Reproduction
08 — Experiments
09 — RCA
10 — Regression
11 — CI
12 — Demo Flow
13 — Prototype
```

---

# 54. OS WORKSPACE COMPONENT LIBRARY

Create a reusable base workspace.

```text
OSWorkspace
├── Desktop
├── WindowManager
├── ApplicationWindow
├── Terminal
├── FileExplorer
├── SystemPanel
└── EnvironmentOverlay
```

Then create:

```text
WindowsWorkspace
LinuxWorkspace
MacOSWorkspace
```

The same application window should be able to render inside each.

---

# 55. DO NOT BUILD THREE FULL OPERATING SYSTEMS

This is extremely important.

We are NOT trying to build:

- Windows
- Linux
- macOS

inside Morph.

We are creating an immersive environment representation.

The application execution and environment controls are separate from the visual workspace.

The designer should therefore prioritize recognizable details rather than trying to reproduce every OS feature.

---

# 56. ACCESSIBILITY

At minimum:

- Good text contrast
- Keyboard navigation for important controls
- Clear focus states
- Do not rely only on color to communicate status
- Readable terminal text
- Reasonable font sizes

Do not sacrifice readability for visual effects.

---

# 57. MOTION SYSTEM

Motion should explain system transitions.

Good animations:

- Environment entering
- OS switching
- Hardware zoom
- Environment loading
- Experiment progression
- PASS/FAIL state
- Root-cause reveal

Avoid:

- Constant floating elements
- Excessive parallax
- Every card animating
- Long loading animations
- Decorative particle systems

Motion should have a purpose.

---

# 58. LANDING PAGE MOTION PRIORITY

If time is limited:

Priority 1:
OS/hardware visual transition

Priority 2:
Enter Morph

Priority 3:
Environment transformation

Priority 4:
Product reveal

Everything else is optional.

---

# 59. DESIGN PRIORITY ORDER

The designer should work in this order:

## Priority 1

Main application shell.

## Priority 2

Environment library.

## Priority 3

Environment detail.

## Priority 4

OS-adaptive workspace.

## Priority 5

Experiment interface.

## Priority 6

RCA interface.

## Priority 7

Regression test interface.

## Priority 8

Demo flow.

## Priority 9

Landing page.

## Priority 10

Extra polish.

Do NOT reverse this order.

A beautiful landing page with a weak product will hurt the project.

---

# 60. 24-HOUR DESIGN STRATEGY

The design person should not spend the first half of the hackathon perfecting Figma.

The goal is to get a usable visual system into the implementation quickly.

Recommended sequence:

### Hours 0–2

Design foundations:

- Typography
- Colors
- Spacing
- Components
- Main shell

### Hours 2–5

Environment screens.

### Hours 5–8

OS-adaptive workspace.

### Hours 8–11

Experiment + failure UI.

### Hours 11–14

RCA + regression.

### Hours 14–17

Demo polish.

### Hours 17–21

Landing page.

### Hours 21–24

Polish and fix inconsistencies.

---

# 61. DESIGNER'S HARD CUT LIST

Do NOT attempt:

- Full mobile UI
- Full OS emulation
- Fully functional desktop applications
- Hundreds of OS-specific UI elements
- Complex 3D hardware simulation if it delays the product
- Huge design systems
- Multiple themes
- Advanced accessibility beyond the basics
- Dozens of dashboard pages
- Full cloud management UI
- Full CI management UI

The core product experience comes first.

---

# 62. WHAT THE JUDGE SHOULD SEE

Within the first minute:

```text
This is a machine environment.

This is the machine where the problem happened.

Morph can recreate it.

Now watch the failure happen again.
```

Within the next few minutes:

```text
Morph changes one condition.

The failure disappears/reappears.

The system identifies the relevant condition.

The developer fixes the bug.

Morph replays the same environment.

It passes.

The failure becomes a regression test.
```

That is the entire visual narrative.

---

# 63. FINAL VISUAL TEST

Before calling a screen finished, ask:

### Does this look like a generic SaaS dashboard?

If yes:
Redesign it.

### Does the user immediately understand what environment they are in?

If no:
Improve environment identity.

### Does the UI show what changed?

If no:
Improve comparison.

### Does the UI show why the failure happened?

If no:
Improve evidence hierarchy.

### Does the UI make reproduction feel real?

If no:
Improve the OS-adaptive workspace and execution states.

---

# 64. THE CORE DESIGN IDEA

Morph's visual identity should ultimately be built around one concept:

> **You are not looking at another machine. You are entering its reality.**

The dashboard tells the developer what environment exists.

The OS-adaptive workspace makes that environment tangible.

The experiment interface explains what caused the failure.

The RCA view provides evidence.

The regression system makes the discovery permanent.

The landing page makes the entire idea visually understandable before the developer has even used the product.

---

# 65. One-Line Design Direction

**Build Morph like an immersive systems laboratory, not a SaaS dashboard: when the target environment changes, the interface itself should change with it.**
