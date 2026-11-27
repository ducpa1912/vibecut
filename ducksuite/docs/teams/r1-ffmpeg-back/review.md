# R1 · FFmpeg bundle repair

**Verdict** — Pass for the Codex dev bundle. Ready for PO integration on `ducksuite`.

The build stages FFmpeg and FFprobe 7.1.1 alongside dav1d. Both executables resolve the decoder through `@loader_path/libdav1d.7.dylib`. The configure prefix is independent of the checkout. The version banner and configure flags are in `build/ffmpeg-lgpl/BUILD.txt`. The source archive for the offer is in `build/ffmpeg-src/ffmpeg-7.1.1.tar.xz` (SHA-256 `733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1`).

The packaging step now fails on a missing helper. Exercised each missing input against the packaging block. Each exited 1 by default and emitted its original warning and exited 0 with `DUCK_ALLOW_NO_FFMPEG=1`. A complete bundle is checked before local signing. The checker runs both tools, checks the configuration and inspects the load commands of all three files.

## Real bundle evidence

Built `build/DuckSuite.app` once using the dev build script with an offline private copy of the build venv. Repeated the helper check after local signing.

```text
$ scripts/check-bundle-helpers.sh build/DuckSuite.app
Verified bundled ffmpeg, ffprobe and libdav1d.7.dylib
```

- Both tools reported 7.1.1. The decoder list included `libdav1d` for AV1. Both banners enabled dav1d and disabled GPL, nonfree and network support.
- `otool -L` showed only system dependencies and the sibling dav1d library. `strings` found zero `/Users/` entries in either executable.
- Full suite on the built bundle passed, 392 tests in 53.75 s with five warnings. JavaScript syntax passed. Fake-bundle cases covered missing FFprobe, GPL, nonfree and Homebrew linkage.
- No app launch or media decode was exercised. Creator playback and the real Check/Render flow remain for the PO and founder. The existing core helper-directory lookup covers this bundle layout.
