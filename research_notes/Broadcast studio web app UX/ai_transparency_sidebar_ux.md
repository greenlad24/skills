# AI Transparency Sidebar and Human Override UX for a Live Show Control App (Sunrise Jam)

Context: a web app where Claude auto-directs cameras and auto-mixes 16 audio channels for a live band show. The user wants a very simple UI with every background process visible in a sidebar that can open or minimize. Research date: Oct 2026.

Verification tags (user's rule):
- **[GUIDELINE]**: an established published guideline (Microsoft HAX, Google PAIR, NN/g, Material, Apple HIG) or a peer-reviewed human-factors framework.
- **[VIDEO 100k+]**: a YouTube video with 100k or more views (view count from yt.py search, Oct 2026).
- **[2+ CHANNELS]**: corroborated by two or more independent channels or sources.
- **[UNVERIFIED]**: a single low-view or vendor/forum claim (also collected in the Gaps of Q3).

Source access notes: pair.withgoogle.com, nngroup.com, m3.material.io and smashingmagazine.com did not resolve from the sandbox (DNS failure). Their content comes from search-result snippets and secondary summaries, which is flagged where it applies. Apple HIG pages are rendered with JavaScript and returned no body text. Only the Microsoft HAX pattern library was fetched in full.

## Q1. Which principles are well established for trustworthy automation UI (cite guidelines)?

### Takeaway
Microsoft's 18 HAX guidelines, Google PAIR's Explainability + Trust chapter, NN/g's heuristics and the Parasuraman/Sheridan levels-of-automation framework agree on six points. Always show system status. Make clear why the AI acted. Express confidence at a precision the system actually has. Make dismissal, correction and undo cheap. Provide global controls such as autonomy levels and kill switches. Notify users about changes, and avoid mode confusion. These principles map directly onto a sidebar made of an activity feed, process status, an autonomy switch and per-control locks.

### Cited Findings
**Microsoft HAX guidelines (all 18, verbatim titles) [GUIDELINE]**: [HAX pattern library](https://www.microsoft.com/en-us/haxtoolkit/library/pattern/)
- G1 "Make clear what the system can do." G2 "Make clear how well the system can do what it can do." G3 "Time services based on context." G4 "Show contextually relevant information." G5 "Match relevant social norms." G6 "Mitigate social biases." G7 "Support efficient invocation." G8 "Support efficient dismissal." G9 "Support efficient correction." G10 "Scope services when in doubt." G11 "Make clear why the system did what it did." G12 "Remember recent interactions." G13 "Learn from user behavior." G14 "Update and adapt cautiously." G15 "Encourage granular feedback." G16 "Convey the consequences of user actions." G17 "Provide global controls." G18 "Notify users about changes."
- The guidelines are organized by phase: "upon initial interaction, during interaction, when the AI system is wrong, and over time." Source: [HAX guidelines page](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/)
- Named patterns that apply directly here: [HAX pattern library](https://www.microsoft.com/en-us/haxtoolkit/library/pattern/)
  - G2: "2A/2B: Match the level of precision in UI communication with the system performance (Language / Numbers)", "2C: Report system performance information" and "2D: Provide low performance alerts".
  - G9: "9A: Switch classification decisions", "9B: Rich and detailed edits", "9C: Undo automated actions" and "9E: Batch-editing data".
  - G10: "10A: Disambiguate before acting" and "10C: Fall back to other strategies".
  - G11: "11A: Local explanations", "11B: Global explanations", "11C: Present properties of system outputs", "11D: Map system input attributes to system outputs", "11F: Example-based explanations" and "11G: 'What if?' explanations".
  - G16: "16A: Feedforward: convey the consequences of user actions before the user takes action", "16B: Feedback … after", and "16C: Remind of consequences of a past action and ask for reconfirmation".

**Google PAIR People + AI Guidebook, Explainability + Trust [GUIDELINE]** (from search snippets; the page was unreachable): [PAIR chapter](https://pair.withgoogle.com/chapter/explainability-trust/), [PDF](https://pair.withgoogle.com/chapter/People%20+%20AI%20Guidebook%20-%20Explainability%20+%20Trust.pdf)
- The chapter states: "If, when, and how the system calculates and shows confidence levels can be critical in informing the user's decision making and calibrating their trust."
- Its key considerations are calibrating trust, optimizing for understanding, and managing the AI's influence on decisions. Trust calibration is planned over the life of the product.
- Related research: confidence scores help calibrate trust, but calibration alone did not improve AI-assisted decisions (Zhang et al., FAT* 2020, [arXiv 2001.02114](https://arxiv.org/abs/2001.02114v1)). A review summarizes that stating confidence in words ("propositional format") supported calibration better than feature graphs ([Frontiers in Neuroscience review](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2022.883385/epub)).

**NN/g heuristics [GUIDELINE]** (the wording is quoted through secondary sources because nngroup.com was unreachable):
- Heuristic 1, Visibility of system status: "The design should always keep users informed about what is going on, through appropriate feedback within a reasonable amount of time." Sources: [uxdesign.cc summary](https://uxdesign.cc/exploring-usability-heuristics-visibility-of-system-status-30c7ef077adf), [uxplanet](https://uxplanet.org/all-about-usability-heuristic-1-visibility-of-system-status-50e252522e41)
- NN/g separates three ways of communicating status: **validations** (errors on user input), **notifications** (messages about system events) and **indicators** (cues that make an element stand out, used alone or alongside the others). The right one depends on urgency, the type of information, and whether the user must act. Source: [NN/g Indicators, Validations, Notifications](https://nngroup.com/articles/indicators-validations-notifications)

**Levels of automation and mode confusion [GUIDELINE: human factors literature]**
- Parasuraman, Sheridan and Wickens (2000) define levels of automation for each of four stages: information acquisition, analysis, decision and action selection, and action implementation. Each function can be automated to a different degree. Source: [summary](https://andrewclark.super.site/all-media/a-model-for-types-and-levels-of-human-interaction-with-automation), [DTIC review](https://apps.dtic.mil/sti/pdfs/ADA461061.pdf)
- "Automation surprise" happens when the system's behavior departs from the operator's mental model. Mode confusion, where "a machine [is] in a different mode from that anticipated by the user", is the most famous case, and "false or unclear display of information" is a contributing interface factor. A survey of 145 airline pilots found mode confusion about 2 times per year, more often among less experienced pilots. Source: [JATM review](https://jatm.com.br/jatm/article/download/1280/952/6236)

**Human-in / on / out-of-the-loop spectrum [2+ CHANNELS]**
- IBM Technology describes three positions. In the loop: the system stops and waits for a human to approve. On the loop: the AI acts autonomously while a human monitors and keeps "veto power to hit the kill switch or override". Out of the loop: full autonomy. IBM's example of on-the-loop is supervised self-driving. Source: What is Human In The Loop with AI? — IBM Technology (48k views) — https://www.youtube.com/watch?v=9iS-YYLIXiw
- Smashing Magazine (Victor Yocco, Feb 2026) gives six agentic patterns arranged by stage. Before the action: **Intent Preview** and **Autonomy Dial**. During the action: **Explainable Rationale** and **Confidence Signal**. After the action: **Action Audit & Undo** and **Escalation Pathway**. This comes from search snippets; the body text could not be fetched. Source: [Smashing: Designing For Agentic AI](https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)
- Maersk's design system AI checklist requires explicit user confirmation before high-impact or irreversible AI actions. Source: [Maersk AI checklist](https://designsystem.maersk.com/ai/guidelines/checklist/)

### Inferences
Each pattern requested for Sunrise Jam maps to an established guideline:

| Sunrise Jam pattern | Guideline basis | Concrete implementation |
|---|---|---|
| Activity feed (what changed, why, confidence, before/after) | HAX G11 (11A local explanation, 11C output properties), G16B feedback, NN/g H1 | One row per AI action: time, icon, a one-line verb sentence ("Cut to Cam 3, drummer fill"), a chip for the reason, a confidence word, and an Undo button. A row expands to show before/after values (fader -12 to -8 dB) and the inputs that triggered it (11D). |
| Confidence | HAX 2A/2B (match precision), PAIR | Use words or 3 levels ("sure / likely / guessing") rather than "87.3%". Show confidence only where it changes what the user does, such as low confidence triggering a request for help. |
| Undo / rollback | HAX G9, 9C "Undo automated actions", NN/g H3 user control | Per-action undo in the feed, "Revert last 30 s of mix changes", and snapshot restore. Undo of a camera cut makes no sense once the cut has aired, so offer "go back to previous shot" instead. |
| Locks ("AI hands off") | HAX G17 global controls, G9 correction, levels-of-automation per function | A lock icon on each fader and camera tile. A locked control is excluded from AI action, and the feed records "Skipped: channel 5 locked by you". |
| Autonomy levels (manual / assist / auto) | Parasuraman levels per stage; IBM in/on/out of loop; Smashing Autonomy Dial | Set the level separately for Director and Mixer. Assist = AI proposes in the preview slot and the human takes it. Auto = AI acts and the human is on the loop with veto. Manual = AI only observes and logs suggestions. |
| Mode awareness | Mode-confusion literature; HAX G18 | Keep the current mode visible at all times, even in the collapsed rail: a "DIR AUTO" / "MIX ASSIST" badge. Every mode change, including automatic fallbacks, is a feed event. |
| Explanation on demand | HAX 11A/11G, PAIR; Kole Jain progressive disclosure | Show a short reason inline and keep the detail ("Why?" plus the inputs the listener model heard) behind an expander or hover. Never auto-open it during the show. |
| Escalation | HAX 10A/10C, 2D low-performance alerts; Smashing Escalation Pathway | When confidence is low or an input drops, the AI holds a safe state (wide shot, last good mix), raises one alert, and asks for help instead of guessing. |

### Gaps
- PAIR, NN/g and Smashing page bodies could not be fetched (DNS). The quotes come from search snippets or secondary summaries. Verify the exact wording before quoting in shipped documents.
- No guideline gives numeric thresholds such as an undo window length or an alert rate limit for live media. These need to be decided through testing.

## Q2. What do high-view YouTube UX and product-design videos recommend for dashboards, sidebars and real-time monitoring UIs?

### Takeaway
The high-view design videos agree on five points. Let the data shape the UI: time-ordered events belong in a timeline, not a table. Use color only when the data means something. Use progressive disclosure and tooltips. Treat the sidebar as the persistent spine, with icons plus short labels, badges, and a collapsed icon rail that shows tooltips. Be ruthless about what to leave out, and give each number context. Agent products such as GitHub Copilot expose background work as a live checklist plan, with the full session log one click away.

### Cited Findings
**Timeline over table for time-based events [VIDEO 100k+]**
- Kole Jain: time-ordered data "isn't the best format" as a table. Arranged as a timeline, "it starts to become a lot easier to follow", and that timeline "could then be tucked into a sidebar pop out". Source: The 3 dashboard UI flaws that give away you've NEVER built one — Kole Jain (156k) — https://www.youtube.com/watch?v=Ksx9C2-3yMo

**Color comes from data, and red means urgent [VIDEO 100k+, 2+ CHANNELS]**
- Kole Jain: dashboard colors "shouldn't just be sprinkled in… It should come from the data itself". In activity logs, "the red icon in the chip draws your eye to it because the action is urgent". Avatars or icons identify "who did what" faster than names. Source: same Kole Jain video — https://www.youtube.com/watch?v=Ksx9C2-3yMo
- Geckoboard: "If your entire dashboard is red and green, then the significance of those colors is greatly reduced". Give numbers context with a status indicator or comparison. Put the most important metric "bigger… top left-hand corner". Group related metrics. Keep a high data-ink ratio by removing decorative grid lines, icons and labels. Round overly precise numbers. Avoid notes and caveats that become "visual noise". Source: 12 Dashboard design tips for better data visualization — Geckoboard (296k) — https://www.youtube.com/watch?v=t3cAUt7sOQg

**Progressive disclosure, the "spectrum of explicitness", and tooltips [VIDEO 100k+]**
- Kole Jain: secondary actions go behind hover or popovers, and primary actions stay always visible. "What's missing… on all beginner dashboards are tooltips." Sequence information "so that the user is never overwhelmed." Source: https://www.youtube.com/watch?v=Ksx9C2-3yMo

**Sidebar as the spine, with a collapsible rail, badges and an active state [VIDEO 100k+, 2+ CHANNELS]**
- Kole Jain: the sidebar "houses most of the persistent and globally relevant elements… the spine of your product". Use "a recognizable icon and a short title… especially helpful if you plan on making your sidebar collapsible" and if you "add a notification number or a new chip". Group links to reduce cognitive load and push rarely used items (settings, help) to the bottom. Keep a clear active state. Notifications can sit in the sidebar's spare space, as Dub and Linear do. Source: EVERYTHING you need to know to build a Dashboard UI in 8 minutes — Kole Jain (361k) — https://www.youtube.com/watch?v=B7k5rOgmOGY
- Kole Jain (same video): **toasts** "are the notification system of your dashboard" because they inform without "taking over the entire screen", and they are good for warning or error states. **Popovers** are non-blocking. **Modals** are blocking, so reserve them for things that must be resolved.
- UX with Luke: build a "collapsed" variant of each nav item and "add tool tips so that in the collapse state when you hover over an icon, you actually know what you're clicking on". Center icons in the collapsed state and use fixed item heights (48 px) and icon boxes (20 px) so nothing shifts between states. Source: Create a Collapsible Sidebar in Figma like a PRO! — UX with Luke (102k) — https://www.youtube.com/watch?v=FuoP3HS3FB8
- Material 3 (Expressive): the navigation rail has a **collapsed** and an **expanded** form, and the expanded rail replaces the drawer. It can be **non-modal** (sits beside the content) or **modal** (overlays it). The collapsed rail is always visible with 3 to 7 items, and it is meant for medium and larger windows. This comes from secondary sources because m3.material.io was unreachable. Sources: [9to5Google](https://9to5google.com/2025/05/14/material-3-expressive-navigation/), [SAP Fiori M3 rail usage](https://www.sap.com/design-system/fiori-design-android/v26-4/components/m3-standard-components/navigation-rail/usage) [GUIDELINE, secondary]

**Agent background-work visibility (GitHub Copilot coding agent) [GUIDELINE-backed: HAX G11/G18 + official vendor demo]**
- The agent works in the background and opens a draft PR straight away. The PR body shows "here's my plan" and the agent "gradually tick[s] off things from that list as it works". A separate **session view** shows the detailed log of tools used, files read and tests run. The agent "pings me for review" when done, and the user steers it with comments. Source: How the GitHub Copilot coding agent works — GitHub (75k) — https://www.youtube.com/watch?v=1GVBRhDI5No (below 100k; the pattern matches HAX G11 and G18).
- VS Code ships "Agent Debug Logs and Chat Debug View" for reviewing agent work. Source: Review agents work with Agent Debug Logs… — Visual Studio Code (12k, title only) — https://www.youtube.com/watch?v=aW2jlbbUREc [UNVERIFIED alone; supports the two-level "summary plus full log" pattern]

### Inferences
- **Two-level transparency**, following Copilot: in the sidebar, show a summary with a plan or checklist and a short feed. Keep the raw log (every model call, every parameter) behind "Open full log" in a drawer or separate route. The summary feed should show only *decisions and state changes*, not every tick.
- **Sidebar layout for Sunrise Jam**, ordered by importance (Geckoboard's top-left rule):
  1. Autonomy and mode block: Director and Mixer level, plus one "Take control (all manual)" button.
  2. Process health: a compact status list (connections, encoders, audio pipeline, listener model, director). Each row has a dot, a name and a value, such as "Encoder 6.0 Mbps · 0 dropped".
  3. Activity feed as a timeline, newest first, grouped by agent (Director / Mixer).
  4. Collapsed state: a 56 to 72 px icon rail with one icon per section, status dots, count badges for unseen warnings, a mode badge, and tooltips on hover. A pin toggle keeps the panel open, and the open/closed choice is remembered per user.
- **Avoid redundancy**: if every process is green, show one "All systems OK" line and collapse the details. Geckoboard warns that an all red-and-green screen loses meaning.

### Gaps
- No high-view video focused specifically on *agent* activity feeds. Videos on "agentic UX" had fewer than 300 views (for example ScaleUp University, Belfast Design), so the agent-specific guidance rests on HAX, Smashing and the GitHub demo.
- The iZotope Mix Assistant tutorials (192k and 141k views, https://www.youtube.com/watch?v=gUD2G9nCc0k, https://www.youtube.com/watch?v=vsjZop8_Fq4) had no retrievable transcript. Their UI patterns (assistant proposes a target, user adjusts and accepts) are **not verified** from transcript here.
- The Tesla visualization videos found (Carscoops 300k, a 32-second clip) have no usable narration. See Q3 for the forum-sourced Tesla UI notes.

## Q3. Best practices for live-ops and broadcast control rooms: attention management and color coding (red = on air / tally, green = preview)

### Takeaway
Broadcast has a strong, near-universal convention. **Red = program / on air** and **green = preview / next**. Tally exists so that whatever is live is untouchable. Preview/program (Studio Mode) is the standard way to stage a change before it goes live. For an AI director, this suggests: show the AI's *next* intended shot in green as the preview, and keep red reserved strictly for what is live. During a show, alerts should go only to things that need action now. Everything else waits in the feed.

### Cited Findings
**Red = live, green = preview [2+ CHANNELS / vendor documentation]**
- Tally lights are typically red for on-air. Some switchers also send a preview tally, "typically green", which "changes to red" once the switch happens. Source: [Wikipedia: Tally light](https://wikipedia.com/wiki/Tally_light)
- SKAARHOJ tally boxes show program as red and preview as green for ATEM and vMix, and the operator LED can be dimmed in low light. Source: [SKAARHOJ Tally Box](https://www.skaarhoj.com/product/tally-box)
- The bit mapping differs in TSL 3.1: on Cyanview, "Tally 1" is green and "Tally 2" is red. Verify the mapping on any integration. Source: [Cyanview tally input](https://support.cyanview.com/docs/Configuration/Tally/TallyInput)

**Tally prevents operators from touching what is live [VIDEO 100k+]**
- Filmmaker IQ: with human camera operators, you need talkback and "a tally light system to let the operator know when they are live and not to do anything funky when they're on live". Without a preview monitor (original ATEM Mini), "you had no way to preview" the next camera. Source: The Basics of Multi-Cam Live Production — Filmmaker IQ (157k) — https://www.youtube.com/watch?v=7FXEUDBS9R0

**Preview vs program staging [VIDEO 100k+]**
- Justin Brown (Primal Video): OBS Studio Mode shows "program… what's going live" next to a preview, so you don't "push it live… until we're ready". Beginners may prefer it off "for simplicity". Source: How to Use OBS Studio - Complete OBS Tutorial for Beginners — Justin Brown - Primal Video (1.64M) — https://www.youtube.com/watch?v=9z9GiEM4uvA

**Car autopilot status conventions [UNVERIFIED: forum and press, not Tesla documentation]**
- Tesla: a gray steering-wheel icon means Autosteer is available, and a blue icon means it is engaged. Chimes mark engagement and disengagement. Sources: [TMC forum](https://www.teslamotorsclub.com/tmc/threads/small-steaming-wheel-icon-upper-left-side-of-interface.131138/), [Electrek](https://electrek.co/2019/04/10/tesla-autopilot-isnt-on-idiot-safety-feature/)
- Industry practice: a red "take over" light means immediate action is required. Source: [VW take-over-steering warning](https://volkswagen-uk.lighthouselabs.eu/en/owners-and-services/my-car/warning-light/electric-take-over-steering-immediately.html)
- A 2023 study tested multimodal displays that signal *automation limits* to support mode awareness and calibrated trust in partially automated driving. Source: [Frontiers in Psychology 2023](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2023.1107847/pdf) [GUIDELINE: peer-reviewed]

**Alert severity hierarchy [GUIDELINE (NN/g) + vendor practice]**
- NN/g: choose between an indicator, a notification and a validation by urgency and by whether action is needed. Source: [NN/g](https://nngroup.com/articles/indicators-validations-notifications)
- Ops tools use 3 to 5 severity levels that drive color and filtering (Novu: High / Medium / Low / None; VMware: Critical through Normal). Sources: [Novu](https://novu.co/changelog/notification-severity/), [VMware TCO guide](https://docs.vmware.com/en/VMware-Telco-Cloud-Operations/1.0/vmware-tco-10-user-guide/GUID-7E0B8687-DFAA-45BD-AA69-5805EF5F403B.html)
- Only *material* agent state transitions should trigger an alert or ARIA live-region announcement, not every update. Source: [Gravitee: AI agent status badges](https://gravitee.io/corpus/gen-2232/bootstrap-front-end-framework/ai-agent-status-badges.html) [UNVERIFIED, single vendor]

### Inferences: recommended live-show attention model for Sunrise Jam
- **Color tokens**, reserved and never reused decoratively:
  - Red = on air / program tally. Use it only on the live camera tile and the "LIVE" stream state. Do not use red for ordinary errors: use a distinct magenta/red-orange plus an icon, or red with a warning glyph and text, so "live" and "broken" are never confused.
  - Green = preview / AI's next shot.
  - Amber = needs attention.
  - Blue or neutral = AI-engaged mode indicator, following Tesla's blue-means-engaged pattern (unverified).
  - Gray = idle or manual.
  - Never rely on color alone: add an icon and a text label for color-blind operators.
- **Four alert tiers**:
  1. **Critical (act now)**: the stream is down, audio is silent or clipping on master, or an encoder dropped. Show a persistent banner that is visible even with the sidebar collapsed, the rail icon pulses, and an optional audible cue goes to the operator's headphones only. The AI also falls back to a safe state, following HAX G10.
  2. **Warning**: low AI confidence, a degraded input, or high packet loss. Show an amber badge on the rail icon and a pinned item at the top of the feed. No popup.
  3. **Info**: normal AI decisions, such as a cut or a fader move. These go only into the feed, with no badge or with a muted count.
  4. **Debug**: model-call logs. These appear only in the full log view.
- **Distraction budget during the show**: no modals and no auto-expanding panels. Throttle feed animation (fade in, no sliding or bouncing). Coalesce bursts ("Mixer: 6 small fader moves, last 10 s"). Rate-limit toasts. Provide a "Show mode / Focus" toggle that suppresses info-level badges.
- **Preview-first AI director (Assist mode)**: the AI places its proposed next shot in a green preview slot with a countdown ("Cutting to Cam 2 in 3 s · Veto"). This gives feedforward (HAX 16A) and a veto window without blocking the show. In Auto mode the cut happens, and the feed row offers "Back to previous shot".
- **Locks act as human tally**: a locked fader or camera shows a lock icon and a distinct outline. The AI must never act on it, and attempted actions are logged as "skipped (locked)" so trust builds visibly.
- **One big global override**: an always-visible "Take manual control" or "AI pause" control in the rail (HAX G17), with a single shortcut key. Resuming should require one confirmation step (HAX 16C) and should resume from the current human state, not snap back to the AI's old state.

### Gaps
- No primary source was found for formal broadcast-industry color *standards*. The red/green tally convention is documented by vendors and by Wikipedia, not by a standards body (no SMPTE/EBU document was found).
- No official Tesla documentation was retrieved. The gray/blue/red icon semantics come from forums and press and are **unverified**.
- The SNL control-room video (849k views, https://www.youtube.com/watch?v=KpAyaJuyN8s) had no retrievable transcript, so its control-room practices could not be cited.
- No source was found on Descript's or Adobe's AI-feature UI (for example Descript Underlord's change log, or Adobe Enhance Speech before/after toggles). Their before/after comparison pattern is not verified here.
- The ATEM, iZotope and Copilot details are product-specific and may have changed by 2026. Re-check them before citing specific UI behavior.

### Unverified list (single low-view or single-vendor claims)
- The VS Code agent debug log view as a pattern (12k views, title only).
- PTZOptics on tally lights with PTZ cameras: many churches and small shows run on volunteer operators, so operation "needs to be easy" (PTZOptics survey, 10.8k views, https://www.youtube.com/watch?v=NkEV_8HYusI).
- Gravitee: alert only on material agent state transitions.
- Tesla icon colors (forum).
- Agentic UX videos below 300 views (Databricks "Autonomy Dial Framework", 99 views, https://www.youtube.com/watch?v=Qf3V-oPfE8E). The concept is corroborated by Smashing's "Autonomy Dial" pattern, so the *concept* is 2+ sources, but the video itself is low-view.
