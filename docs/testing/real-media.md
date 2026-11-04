# Real files the tests need

No test makes its own audio or video. The founder's rule: "They should ask for real media not invented one." Tests read real files from `data/media` in this worktree, which is git-ignored. A missing file makes its test skip and name the file, and the end of every run lists what is waiting.

Counted 2026-11-05 with `data/media` empty: **125 tests waiting** in the normal run. A test that needs two files counts under both, so the rows add up to more than 125.

| File in `data/media` | What it must be | Tests waiting | Opt-in tests also waiting |
|---|---|---|---|
| `speech.wav` | One person talking clearly with natural pauses and no music, starting right at 0:00, at least 90 s. | 57 | 1 (`VIBECUT_LIVE_STT=1`) |
| `talking-video.mp4` | A landscape 1920x1080 video of someone talking, with sound, at least 30 s. | 47 | |
| `silence.wav` | A silent recording with the input muted, so no room sound, at least 20 s. | 15 | |
| `music.wav` | An instrumental music track you may use, at least 120 s. | 9 | 1 (`VIBECUT_FIXTURE_B`) |
| `clipped-speech.wav` | Talking recorded too hot, so it distorts and clips, at least 6 s. | 2 | |
| `vertical-video.mp4` | A vertical 1080x1920 video, at least 26 s. | 1 | |
| `silent-video.mp4` | A video with no audio track at all, at least 2 s. | 1 | |
| `bright-dot-video.mp4` | A 1920x1080 video of one small bright object on a dark background, at least 2 s. | 1 | |
| `music-120bpm.wav` | Instrumental music with a steady 120 BPM beat, at least 8 s. | 1 | |
| `hiss.wav` | Only faint room hiss or fan noise, with no voice, at least 2 s. | 1 | |
| `quiet-speech.wav` | Someone talking far from the mic, recorded very quietly, at least 2 s. | 1 | |
| `loud-speech.wav` | Someone talking very loudly and close to the mic, not distorted, at least 2 s. | 1 | |
| `noisy-speech.wav` | Talking over strong background noise, at least 4 s. | 1 | |
| `mixed-voice.wav` | One main speaker with music, room echo and a second speaker talking over them for a moment, at least 90 s. | 0 | 3 (`VIBECUT_VOICE_ACCEPTANCE=1`) |

## What happens when a file arrives

Each test takes a copy of the stretch it needs, cut with ffmpeg into its own temporary folder, because the code under test moves, cleans or deletes what it is given. The founder's file is never changed.

These tests were written against generated signals. Their assertions have not yet run against real files, so some will need adjusting, for example exact silence levels or the music score.

## Guards

- `tests/test_no_generated_media.py` fails if a test goes back to making audio or video.
- `tests/conftest.py` fails a test that asked for a missing file and still passed, because a worker thread lost the skip.

## Not changed

Tests that write placeholder bytes to a file with a media name, such as `b"x"` in `a.mp4`, hold no sound or picture and nothing decodes them. They remain until the founder decides.
