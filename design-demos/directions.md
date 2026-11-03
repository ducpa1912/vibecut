# VibeCut Edit — three directions

Project: VibeCut Studio, local video-to-Shorts editor.
Audience: solo creators working through a long recording for 20–60 minutes.
Core job: pick a moment, keep the story, remove old text, translate and write the cut, export.

The three directions keep the same content:

- Video: **How do you stop people from interrupting you?**
- Moment: **If you know there's a serial interrupter** · 0:01.5–0:25.8 · 21.5 s · 9:16
- 15 scene clips, 16 transcript lines, 16 caption cues
- English source, Vietnamese target
- Layers: Remove text 3, Text 1, Captions 16, Audio 1

## Six candidates

| # | Logic | Source | Skeleton | Main material | Risk |
|---|---|---|---|---|---|
| A1 | Best designer — restrained cutting desk | Final Cut Pro magnetic timeline, refined through Dieter Rams’ “less but better” | Preview is the room; one vertical tool rail; filmstrip is the only dense object | Vertical frame + contact strip | Too close to the current Studio |
| A2 | Best designer — contact-sheet editor | Magnum contact sheets, editorial photo desk | Scenes as a wall of frames; inspector is a margin note | Scene stills at full bleed | Can feel like a gallery, not an editor |
| B1 | Real reference — transcript-first | Descript’s transcript editor | Left transcript, middle storyboard, right preview | Words + scene cards | Reading dominates the picture |
| B2 | Real reference — mobile storyboard | CapCut’s scene strip, enlarged for desktop | Horizontal story cards with large preview | Thumbnail cards | Weak for 15 scenes |
| C1 | Seconds wheel — Swiss editorial grid | Müller-Brockmann grid, current seconds 09 | Strict 12-column paper edit, no bottom rail | Type + scene index | Too cold for motion work |
| C2 | Seconds wheel — technical control room | DaVinci Resolve color page, Ableton session view | Timeline on top, preview below, transcript as a console | Lanes and timecode | Dense for a first-time creator |

Final three: **A1 Cutting Table**, **B1 Paper Edit**, **C2 Control Room**.

---

## Direction 1 — Cutting Table

**Logic and source.** Best designer: a film cutter’s desk, refined through Dieter Rams. Not a dashboard. The frame is the work; every other surface is a tool within reach.

**Borrowed rules.** One dominant object (the vertical frame), one contact strip, one tool rail. Warm neutral surfaces, no card grid. Tool labels stay visible; no icon-only guessing.

**Main material.** The founder’s actual frame, full height, with safe zones and old subtitle boxes.

**Skeleton.** 64px tool rail · frame · 336px scene inspector; 220px film timeline below.

**Courage.** The preview owns the screen; the timeline is a physical strip of frames, not a row of pills.

**Form from content.** A talking-head Short is watched as a frame. The editor should feel like the frame is being worked on, not a form around it.

---

## Direction 2 — Paper Edit

**Logic and source.** Real reference: Descript’s transcript-first editor, rethought as an editorial spread rather than a document app.

**Borrowed rules.** Read the cut before watching it. Transcript line and scene card share one row. Light surface, ink text, one blue accent. No dark chrome.

**Main material.** Words and scene stills side by side.

**Skeleton.** 360px transcript · flexible storyboard · 400px sticky preview and actions.

**Courage.** No bottom timeline on first view. The storyboard is the timeline until the creator opens the precision controls.

**Form from content.** Interruption advice is a spoken story. The words are the edit; the picture proves the words.

---

## Direction 3 — Control Room

**Logic and source.** Real reference: DaVinci Resolve’s color page and Ableton’s session view, adapted for an AI-assisted Shorts editor.

**Borrowed rules.** Time is the top layer. Every lane has a role; selected data carries the only strong hue. Dense but aligned.

**Main material.** A 15-clip scene lane over sentence, clean, caption and audio lanes, with a live transcript console.

**Skeleton.** Timeline top half · preview left · transcript and copy right · narrow tool rail.

**Courage.** Let the timeline be the biggest object. This is an editor for creators who will make ten cuts, not one.

**Form from content.** A 21-second cut out of a 26-second source needs clip-level control. The interface makes the cut visible before the picture.

---

## Shared constraints

- No gradients, glows, glass or decorative blobs.
- No fake metrics. Every number comes from the job above.
- No icon-only tool rail without labels at desktop.
- Real scene stills from the founder’s video, not stock.
- Timecode and durations use tabular figures.
- Tool rail, scene rows and timeline bars are keyboard reachable.
- The preview is never covered by a panel.
- Light and dark directions both keep 4.5:1 body contrast.

---

## Direction 4 — Moment Board (revision from founder feedback)

**Logic and source.** The founder’s correction: the first three directions made the cut hard to review. This version makes the selected scene order the first thing on screen, then puts one tool rail and one preview under it, with the transcript on the right.

**Borrowed rules.** 1:1 contact sheet for review; numbered cut order; only selected scenes by default; Add scene expands source scenes for drag into the cut. Tool rail from Cutting Table. Transcript and translation from Control Room. Compact five-lane timeline with lock and hide.

**Main material.** The five selected scenes at 1:1 with role labels, the frame, the full transcript.

**Skeleton.** 50px top bar · 120px moment board · 220px tool rail + preview + 380px transcript · 250px timeline.

**Courage.** The moment board is a review surface, not a filmstrip. Selected order, role and duration are visible before any editing control.

**Form from content.** A 21-second cut is five decisions. Show those five first; everything else is secondary.

**Tools.** Clean (detected wrap + model), TextFX, Audio, Caption.

**Timeline lanes.** Scene, Detected text (overlapping), Transcript, Voice over, Caption. Every lane can lock or hide.
