# Safe zones — numbers and sources

Checked 2026-11-12. All margins are resolved on the platform's own canvas. The UI draws them on
the **Cut output frame**, not on the source picture.

| Guide | Canvas | Margins | Source |
|---|---|---|---|
| TikTok | 1080×1920 | top 240 px · bottom 660 px · left 120 px · right 120 px · button block x 780–960, y 840–1920 | TikTok In-Feed safe-zone template (720×1280) scaled ×1.5; measured by clipsdk and Quelta |
| Reels | 1080×1920 | top 14 % · bottom 35 % · sides 6 % (269 / 672 / 65 px) · button rail lower right | Meta Ads Guide for Reels and Stories |
| Shorts | 1080×1920 | top 288 px · bottom 672 px · left 48 px · right 192 px | Google universal vertical ad template |
| IG feed 4:5 | 1080×1350 | 10 % title-safe; no player chrome in Feed; the 3:4 profile grid trims about 34 px a side | Broadcast title-safe convention + Meta grid crop arithmetic |
| IG feed 1:1 | 1080×1080 | 10 % title-safe; the 3:4 profile grid trims about 135 px a side | Same |
| YouTube 16:9 | 1920×1080 | 10 % title-safe; no chrome over the frame | Convention. Google publishes its 16:9 template as an image, not text |

Notes:

- Platform UI moves. These are margins with room to spare, taken from ad templates that are
  stricter than organic posts. A guide is not a promise.
- A guide is drawn only when the Cut output shape matches the guide's canvas (within 1 %). Otherwise
  the panel says the Cut is another shape; no false guide is drawn.
- TikTok's right block is shown separately because the button column starts 840 px down.
- Instagram Feed draws nothing over the picture; its guides are title-safe and the profile-grid
  crop.
- YouTube 16:9 has no published text margins for the player. The 10 % title-safe box is labelled a
  convention in the UI.
