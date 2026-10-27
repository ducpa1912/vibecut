# Sticker set

Bundled, in-house PNG stickers used by the Edit `sticker` graphic layer.
Drawn for VibeCut; no third-party artwork, emoji font or platform glyph is
required at render time. Every sticker is 512×512 RGBA.

| id | file | editor label |
|---|---|---|
| `star` | `star.png` | ⭐ |
| `heart` | `heart.png` | ❤️ |
| `sparkle` | `sparkle.png` | ✨ |
| `fire` | `fire.png` | 🔥 |
| `check` | `check.png` | ✅ |
| `arrow_up` | `arrow_up.png` | ⬆️ |
| `wow` | `wow.png` | 😮 |
| `speech` | `speech.png` | 💬 |

The public ids, filenames and emoji aliases live in `fx.STICKERS` and
`fx.EMOJI`. An Edit stores `asset {id, hash}` where `hash` is the SHA-256
prefix of the PNG bytes, so changing a sticker invalidates its layer cache.
