#!/usr/bin/env python3
"""One live OpenRouter request in a cloned voice: does HeyGen Voice Turbo clone it?

The Voice Room keeps each clone as a sample on this Mac and sends it with
every speech request. Tests fake that request; this script makes one real one.

What it does, with ``--yes-send-to-openrouter``:

1. Picks a cloned voice (``--voice``, or the newest clone).
2. Cuts the first ``--seconds`` (default 10) of its sample into a temporary
   clone, so the request carries about 10 s of voice, not up to 3 minutes.
3. Sends exactly one request to ``https://openrouter.ai/api/v1/audio/speech``
   (HeyGen Voice Turbo) with that sample and a short test line.
4. Deletes the temporary clone, and writes the reply to a WAV to listen to.

Without the flag it only prints what it would send and sends nothing.

It uses the OpenRouter key and the voices in ``VIBECUT_DATA`` (default:
``data/`` in this checkout), and it sends a recording of someone's voice to
OpenRouter and HeyGen. Run it only with the founder's explicit OK.

    python3 scripts/voice_live_check.py                       # dry run
    python3 scripts/voice_live_check.py --yes-send-to-openrouter
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import audio  # noqa: E402
import tts  # noqa: E402
import voice_clone  # noqa: E402

ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
DEFAULT_LINE = "Hi, this is a live check of my cloned voice in VibeCut."


def pick_clone(voice_id: str = "") -> dict:
    clones = voice_clone.list_clones()
    if voice_id:
        record = voice_clone.get_clone(voice_id)
        if record is None:
            raise SystemExit(f"No cloned voice {voice_id}. Clone one in the Voice Room first.")
        return record
    if not clones:
        raise SystemExit("No cloned voices yet. Clone one in the Voice Room first.")
    return max(clones, key=lambda row: float(row.get("created") or 0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--voice", default="", help="clone voice_id (default: the newest clone)")
    parser.add_argument("--seconds", type=float, default=10.0, help="sample length to send (8-15 s)")
    parser.add_argument("--text", default=DEFAULT_LINE, help="the line to speak")
    parser.add_argument("--out", default="", help="where to write the reply WAV")
    parser.add_argument(
        "--yes-send-to-openrouter", action="store_true",
        help="really send one request (uses the OpenRouter key, sends the voice sample)",
    )
    args = parser.parse_args(argv)

    seconds = max(voice_clone.MIN_SAMPLE_SECONDS, min(15.0, float(args.seconds)))
    text = " ".join(str(args.text or "").split())[:300] or DEFAULT_LINE
    record = pick_clone(args.voice)
    source = voice_clone.sample_path(record["voice_id"])
    if not source.is_file():
        raise SystemExit(f"The sample of {record['voice_id']} is missing.")
    out = Path(args.out or voice_clone.settings_store.DATA / "cache" / "voice-live-check.wav")

    work = Path(tempfile.mkdtemp(prefix="voice-live-check-"))
    temp_id = ""
    try:
        cut = work / "sample.mp3"
        sent_seconds = voice_clone.prepare_sample(source, cut, start=0.0, duration=seconds)
        print(f"Voice:    {record.get('name')} ({record['voice_id']}, {record.get('language') or 'no language'})")
        print(f"Sample:   {sent_seconds:.1f} s, {cut.stat().st_size // 1024} KB, cut from a {record.get('sample_seconds') or '?'} s clone")
        print(f"Request:  1 x POST {ENDPOINT} (model {tts.DEFAULT_MODELS['heygen']})")
        print(f"Line:     {text}")
        if not args.yes_send_to_openrouter:
            print("Dry run: nothing was sent. Add --yes-send-to-openrouter, with the founder's OK, to send it.")
            return 2
        if not audio.openrouter_key():
            print("No OpenRouter key in this data folder. Add one in Setup.", file=sys.stderr)
            return 1

        temp = voice_clone.create_clone(
            cut, name=f"{record.get('name') or 'Voice'} (live check)", source=record.get("source") or "me",
            consent=True, language=str(record.get("language") or ""), seconds=sent_seconds,
        )
        temp_id = temp["voice_id"]

        sent: list[str] = []
        real_open = urllib.request.urlopen

        def counted(request, *rest, **kwargs):
            url = getattr(request, "full_url", str(request))
            sent.append(url)
            if len(sent) > 1:
                raise RuntimeError("The live check sends one request only.")
            return real_open(request, *rest, **kwargs)

        urllib.request.urlopen = counted
        reply = work / "reply.wav"
        try:
            tts._openrouter_voice(text, temp_id, reply, engine="heygen", timeout=120)
        except audio.AudioError as exc:
            print(f"FAILED after {len(sent)} request(s): {exc}", file=sys.stderr)
            return 1
        finally:
            urllib.request.urlopen = real_open
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(reply, out)
        length = voice_clone._probe_seconds(out)
        print(f"OK:       {len(sent)} request, {length:.1f} s of speech written to {out}")
        print("Listen to it: does it sound like the cloned voice, not a stock voice?")
        return 0
    finally:
        if temp_id:
            voice_clone.delete_clone(temp_id)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
