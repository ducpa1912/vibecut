# Studio B1a: read the speech again (founder runs, Claude records)

**What changed:** "Read speech" in Stories now uses the one speech-only retry. It reads the sound track again and leaves the frames, crops and plans as they are.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once.

**You need:** a video imported with **Speech** unticked, and an OpenRouter key in Setup.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | **Change video** → open the video imported without speech → **Stories** | The missing-speech note | A yellow note says the video was read without its speech, with a **Read speech** button. | |
| 2 | Click **Read speech** | Speech is read again | The button says "Reading speech…". After about 30 s for a 15 min video, the status says "Read N lines of speech (language). Find stories now." | |
| 3 | Click **Check** in the rail | Frames stay | The scene thumbnails are the same as before. Nothing was re-read. | |
| 4 | Back to **Stories** → **Find stories** | Stories use the speech | The story cards quote what people say. | |
| 5 | Repeat step 2 on a video with no voice (music only) | Silence is reported | The status says "No speech was heard in this video." | |
| 6 | Setup → remove the OpenRouter key, then repeat step 2 | No engine | A red note says no transcription engine is ready and to add an OpenRouter key. | |
