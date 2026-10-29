# Voice Room lane

The Voice Room is its own lane, with its own port, data folder, media library
and recordings. It shares no runtime file with Classic or Studio.

| Item | Value |
|---|---|
| Branch | `voice-room` |
| Previous version | `vibecut-room-prv` worktree, branch `vibecut-room-prv` |
| Port | `8797` |
| Data | `~/vibecut-lanes/voice` |
| Media | `~/vibecut-lanes/media/voiceroom` |
| Recordings | `~/vibecut-lanes/recordings/voiceroom` |

Port `8787` and the founder's data are never used.

## Start and stop

```bash
scripts/voice-serve.sh
```

It refuses a busy port and writes the server PID to
`~/vibecut-lanes/voice/server.pid`. Stop only that PID. Do not `pkill` by
pattern.

## Record a real flow

```bash
scripts/voice-record.sh
```

The browser opens on `http://127.0.0.1:8797/voices`. Click the real flow; close
the browser when done. The Playwright trace lands in
`~/vibecut-lanes/recordings/voiceroom/<date-time>/trace.zip`.

The founder tests, by hand, with real files. No test video, sound or generated
test file stands in for real media.

## Media library

Local copies in `~/vibecut-lanes/media/voiceroom`:

| File | Length | Picture |
|---|---:|---|
| `cn-1min29s-720x1280-voice-subtiltle.mp4` | 1:29 | 720×1280 |
| `en-5mins-640x360-voice-text-overlay.mp4` | 5:25 | 640×360 |
| `en-17mins4s-540x360-talking-head-voice-only.mp4` | 17:04 | 540×360 |
| `en-46s-1080x1080-big-text-overlay-sub.mp4` | 0:46 | 1080×1080 |
| `en-53s-1080x1920-subtitle.mp4` | 0:53 | 1080×1920 |
| `en-53s-1440x2560-talking-head-voice-subtitle.mp4` | 0:53 | 1440×2560 |
| `music-bg-41s-1080x1920-text-overlay.mp4` | 0:41 | 1080×1920 |
| `no-voice-1min-1080x1920-text-overlay.mp4` | 1:00 | 1080×1920 |

Downloaded Shorts, also in the same folder:

| File | Length |
|---|---:|
| `Bác sĩ xếp hạng các loại nước ảnh hưởng đến thận ｜ ThS.BS Trần Quốc Phong [8hT0lcEKbSc].webm` | 1:48 |
| `Give Actionable Advice Fast [ubLqcZKgSNo].webm` | 0:45 |
| `How to speak to 2 cameras. [MD0V2Q6HpIo].webm` | 0:29 |
| `Own Your Links Now! [GEHJwh9vcaY].webm` | 0:39 |
| `유부녀 친구의 남친을 뺏어버린 친구 ㄷㄷ #넷플릭스 #더글로리 [XEiI_GL7EpY].webm` | 0:50 |

## Voice extraction

Voice extraction is already part of this lane through commit `92200c0`
(`fix(voice): import language, clone engine, scripted keep, silent search,
voice queue`). The separate `vibecut-voice-extract` worktree has no newer code.
