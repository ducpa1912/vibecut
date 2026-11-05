# AI clean quick test (founder's workflow)

**Why:** the founder's own short path for judging AI text removal: speed and result, nothing else. Each step below names what automation will drive later, so the same run can become a script without changing the workflow.

**Founder runs it, on a real video. No generated media.** One video stays the test target, so runs can be compared.

## Steps

| # | Do | Expected | Automation later |
|---|---|---|---|
| 1 | Import: add the video | It reads, and Moments opens | `#st-file-input`, then wait for `GET /api/jobs/{id}/status` to be ready |
| 2 | Moments: **Edit full video** | Edit opens on the whole video | `.st-moments-full-video` |
| 3 | Clean: **Scan video** | Found on screen lists each line once. Logos on objects start unticked | `[data-layer="clean"]`, then `.st-clean-scan-start` with the text `Scan video`. Wait for `GET /api/jobs/{id}/check` to return 200 |
| 4 | Untick what is not burned-in text, like a logo on a cup or words on a book. Tick anything missed | Only burned-in text stays ticked | `.st-found-row`, `.st-found-tick`, chosen by the golden file |
| 5 | Press **Clean N**, and note the estimate under Clean layers | Boxes fit each line, at its time, with no box over another | `.st-auto-clean-run`, then read `.st-fill-estimate` |
| 6 | Press **Finish**, pick 1080, and queue. Note the estimate | The same estimate as Edit | `#st-edit-finish`, `.st-seg-btn` with the text `1080`, then `.st-finish-queue-all`. Option: `.st-finish-reuse` |
| 7 | Wait for it, and note the first countdown and the real time | The countdown is close to the real time | Poll `GET /api/story-queues` until the item is `done` |
| 8 | Watch the video through. Note each problem with its time, and a score out of 10 | Text gone, with no ghost, blur patch or smear | The score stays the founder's |

## Record each run

| Date | Video | Code | Option | Estimate | First countdown | Real time | Score | Problems (time: what) |
|---|---|---|---|---|---|---|---|---|
| 2026-11-05 | Coffee garden, 59.6 s | before `ef61c18` | off | 2 h | | about 2 h | 6.5/10 | 22 to 25 s: text left; 28 to 31 s, 49 to 51 s: distortion on movement |
| 2026-11-05 | Same | `632dc3a` | off | 2 h 42 min for 1171 frames (a stale rate, since fixed) | 30 min, then 23 min with Chrome tabs closed | 11 min 39 s (fill 11 min 25 s) | not scored yet | not reviewed yet |

## The numbers

With the founder's go-ahead for that job, this reads the run and changes nothing:

```bash
python3 scripts/clean_test_report.py JOB_ID
```

It gives lines found, lines left out, tallest box, overlapping boxes, seconds and frames cleaned, each render stage's time, and fill seconds per frame.

The founder's choice on a good run becomes the golden file for that video, kept beside its media and outside the repo. A later run is then checked against it:

```bash
python3 scripts/clean_test_report.py JOB_ID --write-golden ~/vibecut-lanes/media/studio/coffee-garden.golden.json
```

```bash
python3 scripts/clean_test_report.py JOB_ID --golden ~/vibecut-lanes/media/studio/coffee-garden.golden.json --save
```

## What automation needs

1. A real video and its golden file in `~/vibecut-lanes/media/studio/`, chosen by the founder.
2. A Playwright run of steps 1 to 7, using the selectors above, on Studio's own port and only with no render running.
3. The report above, saved to `test-results/studio-clean.jsonl`, so speed and box numbers can be compared over time.

Automation can check speed, what was found, and the boxes. Whether the result looks right stays with the founder.
