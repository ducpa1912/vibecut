# Video links · yt-dlp first, sidecars optional

VibeCut can start from a URL instead of a file. **yt-dlp is the default path**
for common sites and runs inside the VibeCut Python process. Cobalt is an
optional fallback after yt-dlp fails, and xhs_get handles RedNote links. Both
sidecars are external services: they are never bundled and never started by
VibeCut.

```
VibeCut URL bar
  ├── yt-dlp (default, in-process, Unlicense)
  │     YouTube · TikTok · Instagram · X · Reddit · Vimeo · direct media
  ├── Cobalt (optional retry or explicit mode, AGPL-3.0, separate service)
  └── xhs_get (RedNote only, GPL-3.0, separate service)
        ↓
  local source file
        ↓
  probe → dissect → Smart Cut → audio → render
```

## Requirements

- Python 3.11 or newer.
- `ffmpeg` and `ffprobe` on `PATH` for probe, merge, cut and render.
- The Python packages in `requirements.txt`, including `yt-dlp`.

```bash
cd vibecut
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./run.sh
```

The default yt-dlp path needs no Node.js, Docker, Cobalt or xhs_get for
YouTube, TikTok, Instagram, X, Reddit, Vimeo or a direct video URL.

## Network safety

The URL bar is meant for public internet links. It rejects `localhost`,
private, loopback, link-local and reserved IP literals; use the local-path
input for a file already on the machine. Cookie files are read only from Setup,
never from a request body.

When VibeCut is bound beyond loopback (for example `VIBECUT_HOST=0.0.0.0` in
Docker), set `VIBECUT_TOKEN` before enabling the app. Without a token every
`/api/*` route except `/api/health` returns 403 on a non-loopback bind, so the
saved XHS token and settings cannot be read remotely.

The app rejects obvious private targets, but no application-level URL checker
can fully stop DNS rebinding, redirects, or a hostile extractor. Treat URL
ingest as a privileged network feature: use a token, bind to loopback, and
apply network egress policy when the app is shared.

## How a link is routed

Setup stores the provider mode in `ingest.provider`:

| Value | Behavior |
|---|---|
| `auto` (default) | RedNote/Xiaohongshu hosts go to `xhs`. Every other HTTP(S) link tries `yt-dlp` first; if it fails and **Fallback after yt-dlp** is enabled with a Cobalt URL, VibeCut retries once through `cobalt`. |
| `ytdlp` | Force the in-process yt-dlp provider. No fallback. |
| `cobalt` | Force the optional Cobalt HTTP sidecar. No fallback. |
| `xhs` | Force the optional xhs_get sidecar. No fallback. |

An API request may also pass `provider` to override the mode for one URL.
Explicit modes try only the named provider. Cancellation is final and never
starts a fallback. RedNote links never fall back to Cobalt.

If every provider in the chain fails, the error shown is the first provider's
error (normally yt-dlp), and the job metadata records each attempt. Cobalt is
never contacted when yt-dlp succeeds.

RedNote links are routed to xhs_get in `auto` mode. Explicit `ytdlp` normalizes
`rednote.com` / `xiaohongshu.com` note URLs before calling yt-dlp. If xhs_get is
not configured in auto mode, the link fails with
"XHS service URL is not set. Set it in Setup first."

## yt-dlp (default)

The provider resolves one URL, downloads the best matching video into a
temporary path, returns metadata, and lets the normal probe/analysis pipeline
continue. It does not require a server, API key, or external process.

### Ingest settings

| Key | Default | Allowed |
|---|---|---|
| `ytdlp_quality` | `max` | `max`, `2160`, `1440`, `1080`, `720`, `480`, `360` |
| `ytdlp_codec` | `h264` | `h264`, `any` |
| `ytdlp_container` | `mp4` | `mp4`, `mkv`, `webm` |
| `ytdlp_audio` | `best` | `best`, `192`, `128` |
| `ytdlp_cookies` | `none` | `none`, `file`, `browser` |
| `ytdlp_browser` | `safari` | Browser name understood by yt-dlp |
| `ytdlp_cookie_file` | empty | Path to a Netscape `cookies.txt` |

The same values can be overridden per request with `ingest_options`:
`quality`, `codec`, `container`, `audio`, `cookies`, `browser`.
`ytdlp_cookie_file` is intentionally not request-overridable; it can only be
set in Setup. A saved cookie mode still applies when a request says `none`;
set the saved mode to `none` to turn cookies off. A request may switch to
`file` or `browser` without changing the saved setting.

`h264` asks yt-dlp to prefer an AVC video stream so the result plays in the
widest range of editors and browsers. If the site has no AVC stream, the
provider falls back to the best available stream. `max` can download a very
large file; check free disk space before ingesting a 4K source.

`mp4` is the preferred merge container. yt-dlp may fall back to `mkv` when the
available codec pair cannot be placed in mp4. Select `mkv` or `webm` to change
the preference. VibeCut probes the downloaded file anyway, so a valid video in
a different container still proceeds.

### Playlists and multi-item links

Playlist links are not bulk-downloaded. Inspection returns a picker payload
with up to 200 entries (title, duration, thumbnail, uploader, URL). The job
endpoint accepts one chosen video URL. A direct create-job request for a
multi-item link is rejected with HTTP 409 and an instruction to paste a single
video link.

The picker is a client contract: selecting an entry submits that entry's URL
as a normal single-video job. No bulk download or background playlist sync
exists.

### Cookies

The default is `none`: VibeCut does not read any cookie store, and public
videos work without sign-in.

- `file` reads a user-supplied Netscape `cookies.txt`. A missing path is a
  configuration error; a malformed file is reported by yt-dlp.
- `browser` asks yt-dlp to read the browser's default profile. On macOS this
  may require Keychain access, Full Disk Access, or a closed browser so the
  cookie database is not locked. Custom browser profiles are not supported.
- VibeCut stores the cookie-file path, not the cookie contents. yt-dlp reads
  the file or browser store locally and sends the relevant cookies only to the
  video host. Cookie values are never written to job history.
- Cookies do not grant rights to private, paid, or DRM-protected content. Use
  them only for content you are allowed to access.

### Cancel

Cancel sets a cooperative event. The download progress hook checks it and
aborts; the temporary `.ingest-*` file is removed in a `finally` block. The job
is marked failed with "Download cancelled" and the attempt is recorded in
history. A blocked network read may take until the next progress callback
before the worker notices the cancel.

### Errors

| Situation | Message |
|---|---|
| Package missing | `yt-dlp is not installed. Install the yt-dlp Python package.` |
| Private video | `This video is private.` |
| Age gate | `This video is age-gated. Add cookies in Setup.` |
| Sign-in required | `This video needs a signed-in cookie. Add cookies in Setup.` |
| Unsupported site | `yt-dlp does not support this URL.` |
| Region lock | `This video is region-restricted.` |
| Deleted/missing | `The video was not found.` |
| Audio-only result | `This link is audio-only; VibeCut needs a video file.` |
| No file produced | `yt-dlp finished but no video file was produced.` |

Other extractor errors are passed through, trimmed to 400 characters. Update
yt-dlp first when a previously working site fails:

```bash
python -m pip install -U yt-dlp
```

## Cobalt (optional fallback)

Cobalt is a separate AGPL-3.0 service. It is not part of the VibeCut process,
is not bundled, and is never contacted when yt-dlp succeeds. In `auto` mode it
is retried only after yt-dlp fails and only when **Fallback after yt-dlp** is
enabled in Setup with a valid Cobalt URL.
Select `cobalt` to force it for a link. The hosted `api.cobalt.tools` API is
rejected; configure your own instance.

```bash
# separate directory, outside the VibeCut tree
git clone https://github.com/imputnet/cobalt.git
cd cobalt
# copy docs/examples/docker-compose.example.yml to docker-compose.yml
# set API_URL to this instance's URL
docker compose up -d
```

Default settings:

```text
Service URL:       http://127.0.0.1:9000/
Quality:           1080
Codec:             h264
Local processing:  preferred
```

The API key is optional unless the instance requires authentication. VibeCut
sends `localProcessing` and performs merge/remux with local ffmpeg for
`local-processing` responses. It rejects audio-only, GIF, HLS, and multi-item
picker responses for the video-ingest path.

Cobalt code, assets and branding stay outside VibeCut. Distribution rules:
`docs/licensing.md`.

## xhs_get / RedNote (optional sidecar)

xhs_get is a separate GPL-3.0 program. It is not bundled and is only used for
RedNote/Xiaohongshu links. Start its web API:

```bash
git clone https://github.com/ducpa1912/thu-do-dl.git xhs_get
cd xhs_get
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py xhs-get web --host 127.0.0.1 --port 5789
```

Default settings:

```text
Service URL:       http://127.0.0.1:5789
Access token:      only when xhs_get friends mode is enabled
Fresh download:    on (no_record=true)
Interval:          12 seconds
```

### Single note

Paste the full share link. It must contain `xsec_token`:

```text
https://www.rednote.com/explore/<id>?xsec_token=...
```

A bare `/explore/<id>` returns 404 from RedNote. `xhslink.com` / `xhslink.cn`
short links work when they resolve to a tokenized note.

VibeCut submits one `kind: "links"` job, waits for completion, and imports the
first video deliverable or downloaded file.

### Cookie / sign-in

The RedNote cookie **stays in xhs_get**. VibeCut never reads
`~/.config/xhs_get/cookie.txt`.

In VibeCut Setup:

- **Open sign-in** opens the xhs_get page; scan the QR there.
- **Copy login link** copies the `#t=<token>` invite when an access token is
  saved.
- **Cookie handoff** accepts the full Cookie header and forwards it to
  xhs_get. It is not saved to VibeCut's settings.
- **Check session** reads `/api/state`.
- **Test XHS** checks the service and session.

Friends mode requires the access token from xhs_get. Generate it with:

```bash
cd xhs_get
.venv/bin/python main.py xhs-get users list
# or rotate/create an account; the command prints the invite link once
```

Use a dedicated VibeCut account or the xhs_get admin account. If xhs_get runs
single-user (no `users.json`), no token is needed and files are read from its
download folder.

## Failure behavior

| Situation | Behavior |
|---|---|
| yt-dlp missing | Inline install error; if Cobalt fallback is enabled, one Cobalt retry is allowed. |
| yt-dlp extractor outdated | Site error is surfaced; upgrade yt-dlp and retry. |
| yt-dlp fails, Cobalt fallback enabled | One Cobalt retry; success continues normally, both-fail shows the yt-dlp error and records both attempts. |
| yt-dlp fails, fallback off | yt-dlp error; no sidecar call. |
| Explicit provider fails | Its error; no fallback. |
| Playlist or multi-item link | Picker payload on inspect; job creation rejects with 409. |
| Private / age-gated / members-only | Clear error; cookies are optional, no bypass. |
| DRM-protected stream | Unsupported; no decryption or bypass path. |
| Download cancelled | Worker stops, temp file removed, job marked failed. |
| Disk full / permission denied | Job failed with the OS error; no analysis starts. |
| ffmpeg missing | Probe or merge fails; install ffmpeg/ffprobe. |
| Cobalt down, explicit mode | Inline "Start the cobalt service" error; no job. |
| Cobalt down, auto fallback enabled | Both attempts fail; the yt-dlp error is shown and the Cobalt attempt is recorded. |
| xhs_get down | Inline service error. |
| XHS missing token | Setup says "Needs token". |
| XHS missing cookie | Open sign-in / cookie handoff. |
| Tokenless RedNote link | Warning before a job is created. |
| Expired XHS session | Error surfaced in Setup, progress and history. |

## License boundary

VibeCut is proprietary. The Cobalt and XHS clients in `url_ingest/` are
original HTTP clients; the yt-dlp integration uses only the public package
API. No Cobalt or xhs_get source is imported or copied. Running optional
sidecars as separate processes keeps them outside the VibeCut work.

Read `docs/licensing.md` for the dependency table, third-party notice rules,
sidecar source-offer requirements, SBOM commands, and the release checklist.
Run the gate before a release:

```bash
python3 scripts/check_proprietary_deps.py
```

Not legal advice.

## Troubleshooting

- **`yt-dlp is not installed`** — activate the project venv and run
  `python -m pip install -r requirements.txt`.
- **YouTube/TikTok suddenly fails** — update yt-dlp first; extractors change
  frequently.
- **403 or "sign in"** — try a `cookies.txt` file in Setup (cookie mode
  `file`), or browser mode. Close the browser if its cookie database is
  locked. Use only content you may access.
- **Playlist link** — choose one video; VibeCut does not download a whole
  playlist.
- **RedNote link fails** — start xhs_get, set its URL, and use a tokenized
  share link. yt-dlp is not the RedNote path.
- **Cobalt link fails** — in `auto`, read the yt-dlp error first; Cobalt is a
  retry, not the primary path. Set `provider` to `cobalt` to force it and
  confirm the instance is running.
- **No Node/Docker on this machine** — nothing to install for the default
  yt-dlp path.
