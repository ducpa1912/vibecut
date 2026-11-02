# Manual test: HeyGen Voice Turbo (free) as the first voice route

**Change under test:** commit `4c4f98e`.
**Free tier ends:** 2026-11-30, per OpenRouter. After that date, the route should fail and the next route (MiniMax) should take over.
**Setup:** start the app normally (`python3 app.py`). Use any imported video that has at least one story.

The founder runs the steps below. Claude records the result of each one in the **Result** column.

| # | Action: where to click | Intent: what it proves | Expected | Result |
|---|---|---|---|---|
| 1 | Open `/_ductator`. Go to the **Voice-over** workflow card. | The saved workflow has HeyGen at the top. | First route is `openrouter · heygen/heygen-voice-1-turbo:free`, then `minimax · speech-2.8-turbo`. | |
| 2 | On the same card, open the model dropdown of route 1. | The admin catalog lists the model. | "HeyGen Voice Turbo Free" is listed. | |
| 3 | Studio: **Stories**, pick a story, then **Edit → Audio**. In the **Voice** card, open **Voice engine**. | The Studio picker shows the engine. | "HeyGen Voice Turbo · cloud, free" is listed and enabled. This needs the OpenRouter key. | |
| 4 | Choose **HeyGen Voice Turbo**, then open **Voice**. | Voice list. | 10 voices: Nadine, Tabitha, Bram, Gareth, Noelle, Meredith, Sabrina, Lucian, Weston, Vincent. | |
| 5 | Pick **Nadine**, then click **Preview voice**. | Live synthesis (PCM to WAV). | A clean sample plays within about 2 s. It has no static, the speed is right, and the pitch is not chipmunk. | |
| 6 | Pick **Bram**, then click **Preview voice** again. | The voice ID is passed through. | A different, male voice plays. | |
| 7 | Set mode **Voice-over** and render the story. | Full story voice through the workflow's first route. | The render finishes and the voice is HeyGen for every line, with no mixed voices. | |
| 8 | Optional: set mode **Dub** to Vietnamese or Chinese, then render. | Non-English with HeyGen (39 languages). | The voice is understandable and the lines fit their slots. | |
| 9 | Optional: Classic UI (`/?classic=1`), voice engine dropdown. | Classic fallback. | "OpenRouter HeyGen Voice Turbo (free)" is listed. | |

Things to tell Claude for each step: pass or fail, what you saw, and any error text exactly as shown.
