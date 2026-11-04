# Real media for Classic's tests

Tests never make video, sound or pictures, not even throwaway files. They read
real files from `data/media/` in the Classic checkout. That folder is gitignored.

Name each file exactly as below. Any file extension works (`.mp4`, `.mov`, `.m4a`, `.wav`).
When a file is missing or does not fit, each test that needs it is skipped with a
line naming the file, and the end of the test run counts the tests waiting on each file.
Tests that have never run on a real file can still need their checks adjusted
the first time the file arrives.

| File name | What it must be | Shortest length | Exact size |
|---|---|---|---|
| `portrait-video` | Your own vertical video with someone talking | 30 s | 1080x1920 |
| `wide-video` | Your own horizontal video with sound | 24 s | 1920x1080 |
| `silent-video` | Your own video with no sound track at all | 2 s | any |
| `light-in-dark` | A still shot of one small bright light in a dark room, nothing else bright | 2 s | 1920x1080 |
| `voice-clean` | One person talking in a quiet room, no music | 90 s | |
| `voice-noisy` | One person talking with loud background noise | 4 s | |
| `voice-hum` | One person holding one steady hum, no words | 2 s | |
| `talk-over-music` | People talking with music behind them (opt-in test, `VIBECUT_VOICE_ACCEPTANCE=1`) | 90 s | |
| `music` | A music track you have the rights to | 8 s | |
| `metronome-120bpm` | A metronome at 120 BPM, nothing else in the sound | 8 s | |
| `room-silence` | A quiet room with nobody talking | 6 s | |
| `bright-photo` | A JPEG photo that is almost all white, like a white wall | | |

`tests/real_media.py` holds this list. `tests/test_no_generated_media.py` fails if a test
starts generating media again.

Some tests fake every step that would read a file, such as a faked speech provider. They
write a few bytes that cannot be played (`PLACEHOLDER_WAV`), because no picture or sound
is involved.
