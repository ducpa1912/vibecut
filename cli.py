"""VibeCut command line: analyze, render, batch and watch without the web UI.

Examples
--------
    python3 cli.py analyze clip.mp4
    python3 cli.py render clip.mp4 --target 30 --captions
    python3 cli.py render --job 0c354657dc1a --target 15 --quality draft
    python3 cli.py batch ./footage --out ./reels --targets 15 30
    python3 cli.py watch ./inbox --out ./reels
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import pipeline
import audio
import render

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg"}


def _data_dir(raw: str | None) -> Path:
    return Path(raw or "data").expanduser().resolve()


def _jobs_dir(data: Path) -> Path:
    jobs = data / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    return jobs


def _job_path(data: Path, job_id: str) -> Path:
    return _jobs_dir(data) / job_id / "job.json"


def _load_job(data: Path, job_id: str) -> dict:
    path = _job_path(data, job_id)
    if not path.is_file():
        raise SystemExit(f"No job {job_id} under {_jobs_dir(data)}")
    return json.loads(path.read_text())


def _save_job(data: Path, job: dict) -> None:
    directory = _jobs_dir(data) / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _progress(stage: str, fraction: float, message: str) -> None:
    print(f"[{stage}] {fraction * 100:5.1f}% {message}", file=sys.stderr)


def _analyze(path: Path, data: Path, options: dict) -> dict:
    meta = pipeline.probe(path)
    job_id = uuid.uuid4().hex[:12]
    directory = _jobs_dir(data) / job_id
    directory.mkdir(parents=True, exist_ok=True)
    started = time.time()
    analysis = pipeline.analyze_source(
        str(path), meta, directory, options,
        lambda stage, fraction, message: _progress(stage, fraction, message),
    )
    job = {
        "id": job_id,
        "created": time.time(),
        "updated": time.time(),
        "status": "ready",
        "progress": 1.0,
        "message": f"{analysis['scene_count']} moments",
        "error": None,
        "options": options,
        "source": {**meta, "path": str(path), "name": path.name},
        "analysis": analysis,
        "renders": {},
    }
    _save_job(data, job)
    print(
        f"{job_id}  {path.name}  {analysis['scene_count']} scenes  "
        f"{analysis.get('deep_count', analysis['scene_count'])} deep  "
        f"{time.time() - started:.1f}s  hook {analysis['hook_scene']}",
        file=sys.stderr,
    )
    return job


def _job_for(source: Path, data: Path, options: dict) -> dict:
    """Reuse the newest ready job for this file, else analyze it."""
    resolved = str(source.expanduser().resolve())
    newest = None
    for path in _jobs_dir(data).glob("*/job.json"):
        try:
            job = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if job.get("status") != "ready" or job.get("source", {}).get("path") != resolved:
            continue
        if newest is None or job.get("updated", 0) > newest.get("updated", 0):
            newest = job
    return newest or _analyze(source, data, options)


def _render_job(job: dict, data: Path, args: argparse.Namespace) -> list[Path]:
    analysis = job["analysis"]
    scenes = analysis["scenes"]
    job_dir = _jobs_dir(data) / job["id"]
    outputs: list[Path] = []
    for target in args.targets:
        plan = pipeline.build_plan(
            scenes, job["source"]["duration"], target,
            args.hook, analysis.get("hook_scene"),
        )
        plan["_scenes"] = scenes
        plan["_source_lang"] = (analysis.get("engine") or {}).get("transcript_language") or "en"
        audio_plan = _audio_plan(args)

        def progress(fraction: float, message: str) -> None:
            print(f"  {target}s {fraction * 100:5.1f}% {message}", file=sys.stderr)

        result = render.render_reel(
            job["source"]["path"], job["source"], job_dir, plan,
            f"{Path(job['source']['name']).stem} · {target}s cut",
            progress,
            quality=args.quality,
            aspect=args.aspect,
            encoder=args.encoder,
            captions=args.captions,
            audio_plan=audio_plan,
        )
        output = job_dir / "renders" / result["path"]
        outputs.append(output)
        print(output, file=sys.stderr)
    return outputs


def _audio_plan(args: argparse.Namespace) -> dict | None:
    mode = getattr(args, "audio_mode", "keep") or "keep"
    if mode == "keep":
        return None
    plan: dict = {"mode": mode}
    target = getattr(args, "translate", None)
    plan["translate"] = (
        {"target": target, "provider": getattr(args, "translate_provider", "auto") or "auto"}
        if target else None
    )
    if mode != "music":
        plan["voice"] = {
            "engine": getattr(args, "voice_engine", "say"),
            "voice": getattr(args, "voice", "") or "",
            "rate": float(getattr(args, "voice_rate", 1.0) or 1.0),
            "gain_db": 0,
        }
    if mode == "bed":
        plan["music"] = {"source": "none"}
    else:
        plan["music"] = {
            "source": getattr(args, "music", "none") or "none",
            "track": getattr(args, "music_track", "") or "",
            "prompt": getattr(args, "music_prompt", "") or "auto",
            "gain_db": -18,
            "duck": True,
        }
    return plan


def _options(args: argparse.Namespace) -> dict:
    return {
        "ocr": not args.no_ocr,
        "transcribe": bool(args.transcribe),
        "smart_crop": not args.no_crop,
    }


def _add_analysis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-ocr", action="store_true", help="Skip on-screen text reading.")
    parser.add_argument("--transcribe", action="store_true", help="Run Whisper for speech.")
    parser.add_argument("--no-crop", action="store_true", help="Disable smart crop.")


def _add_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", dest="targets", type=int, action="append",
                        help="Reel length in seconds (repeatable).")
    parser.add_argument("--targets", dest="targets", type=int, nargs="+",
                        help="One or more reel lengths.")
    parser.add_argument("--hook", type=int, default=None, help="Hook scene id.")
    parser.add_argument("--quality", choices=("final", "draft"), default="final")
    parser.add_argument("--aspect", choices=sorted(render.ASPECTS), default="9:16")
    parser.add_argument("--encoder", default=None, help="auto, videotoolbox or libx264.")
    parser.add_argument("--captions", action="store_true", help="Burn OCR/speech captions.")
    parser.add_argument("--audio-mode", choices=("keep", "full", "bed", "voice", "music"),
                        default="keep", help="Replace or keep the original audio.")
    parser.add_argument("--translate", default=None, help="Target language code, e.g. en.")
    parser.add_argument("--translate-provider", choices=("auto", "apple_fm", "argos", "marian", "ollama"),
                        default="auto")
    parser.add_argument("--voice-engine", choices=("say", "piper", "kokoro", "elevenlabs"),
                        default="say")
    parser.add_argument("--voice", default="", help="Voice id for the chosen engine.")
    parser.add_argument("--voice-rate", type=float, default=1.0)
    parser.add_argument("--music", choices=("none", "library", "cc0", "stable-small", "stable-1.0"),
                        default="none")
    parser.add_argument("--music-track", default="", help="Track path or name; empty = auto mood.")
    parser.add_argument("--music-prompt", default="", help="Prompt for Stable Audio; empty = auto.")
    parser.set_defaults(targets=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibecut", description="Local-first reel cutter.")
    parser.add_argument("--data", default=None, help="Data directory (default ./data).")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, **kwargs) -> argparse.ArgumentParser:
        child = sub.add_parser(name, **kwargs)
        child.add_argument("--data", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return child

    analyze = add("analyze", help="Analyze one video.")
    analyze.add_argument("source", type=Path)
    _add_analysis_options(analyze)

    render_cmd = add("render", help="Render reels from a video or an existing job.")
    render_cmd.add_argument("source", type=Path, nargs="?")
    render_cmd.add_argument("--job", default=None, help="Existing job id.")
    _add_render_options(render_cmd)

    batch = add("batch", help="Analyze and render every video in a folder.")
    batch.add_argument("folder", type=Path)
    batch.add_argument("--out", type=Path, default=None, help="Copy finished reels here.")
    _add_analysis_options(batch)
    _add_render_options(batch)

    watch = add("watch", help="Watch a folder and process new videos.")
    watch.add_argument("folder", type=Path)
    watch.add_argument("--out", type=Path, default=None)
    watch.add_argument("--interval", type=float, default=5.0)
    _add_analysis_options(watch)
    _add_render_options(watch)

    add("jobs", help="List analyzed jobs.")

    clean = add("clean", help="Delete working files for jobs; the source video stays.")
    clean.add_argument("--job", default=None, help="Job id. Omit with --all.")
    clean.add_argument("--all", action="store_true", help="Clean every finished job.")
    clean.add_argument("--profile", choices=("workfiles", "renders", "all"),
                       default="workfiles")

    audit = add("audit", help="Show everything this project installed and its size.")
    audit.add_argument("--pair", nargs=2, action="append", default=None,
                       metavar=("SRC", "TGT"),
                       help="Also check an Apple Translation language pair.")
    return parser


def _normalize_targets(args: argparse.Namespace) -> None:
    targets = args.targets or [30]
    if isinstance(targets, int):
        targets = [targets]
    args.targets = sorted({int(target) for target in targets if int(target) > 0})


def _copy_out(outputs: list[Path], out: Path | None) -> None:
    if not out:
        return
    import shutil

    out.mkdir(parents=True, exist_ok=True)
    for output in outputs:
        shutil.copy2(output, out / output.name)


def _process(source: Path, data: Path, args: argparse.Namespace) -> None:
    options = _options(args)
    job = _job_for(source, data, options)
    _normalize_targets(args)
    outputs = _render_job(job, data, args)
    _copy_out(outputs, getattr(args, "out", None))


def _dir_size(path: Path, dedupe: bool = True) -> int:
    total = 0
    seen: set[str] = set()
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        try:
            if not item.is_file():
                continue
            real = str(item.resolve())
            if dedupe and real in seen:
                continue
            seen.add(real)
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _module_size(spec) -> int:
    locations = getattr(spec, "submodule_search_locations", None)
    if locations:
        return _dir_size(Path(next(iter(locations))))
    if spec.origin and spec.origin.endswith(".py"):
        try:
            return Path(spec.origin).stat().st_size
        except OSError:
            return 0
    return 0


def _mb(size: int) -> str:
    return f"{size / 1e6:,.1f} MB"


AUDIT_PACKAGES = (
    ("torch", "torch"),
    ("mlx", "mlx"),
    ("mlx-whisper", "mlx_whisper"),
    ("transformers", "transformers"),
    ("piper-tts", "piper"),
    ("kokoro-onnx", "kokoro_onnx"),
    ("demucs", "demucs"),
    ("argostranslate", "argostranslate"),
    ("ctranslate2", "ctranslate2"),
    ("stable-audio-tools", "stable_audio_tools"),
    ("soundfile", "soundfile"),
)


def _site_package_size(module: str) -> int:
    import sysconfig

    purelib = Path(sysconfig.get_paths().get("purelib") or "")
    if not purelib.is_dir():
        return 0
    for candidate in (purelib / module, purelib / f"{module}.py"):
        if candidate.exists():
            return _dir_size(candidate) if candidate.is_dir() else candidate.stat().st_size
    return 0


def _audit(data: Path, pairs: list[list[str]]) -> None:
    import importlib.util
    import importlib.metadata as metadata

    print("VibeCut install audit\n")

    print("Jobs (source video + job.json always kept)")
    jobs_total = 0
    for path in sorted(_jobs_dir(data).glob("*/job.json")):
        try:
            job = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        size = _dir_size(path.parent)
        jobs_total += size
        work = _dir_size(path.parent / "thumbs") + _dir_size(path.parent / "renders")
        print(f"  {job['id']}  {_mb(size):>12}  work+renders {_mb(work):>12}  "
              f"{job.get('source', {}).get('name', '?')[:44]}")
    print(f"  total {_mb(jobs_total)}\n")

    print("Caches")
    usage = audio.cache_usage()
    for name, info in usage.items():
        if name == "total_mb":
            continue
        print(f"  {name:10} {info['files']:>4} files  {info['mb']:>10,.1f} MB")
    print(f"  total      {usage['total_mb']:>10,.1f} MB\n")

    print("Model folders")
    for label, path in (
        ("piper voices", data / "voices" / "piper"),
        ("kokoro models", data / "models" / "kokoro"),
    ):
        print(f"  {label:14} {_mb(_dir_size(path)):>12}  {path}")

    hub = Path.home() / ".cache" / "huggingface" / "hub"
    if hub.is_dir():
        for model in sorted(hub.glob("models--*")):
            print(f"  HF {model.name[8:]:40} {_mb(_dir_size(model)):>12}")

    argos = Path.home() / ".local" / "share" / "argos-translate" / "packages"
    if argos.is_dir():
        for package in sorted(argos.glob("*")):
            print(f"  argos {package.name:38} {_mb(_dir_size(package)):>12}")
    print()

    print("Python packages used by VibeCut")
    for label, module in AUDIT_PACKAGES:
        spec = importlib.util.find_spec(module)
        size = _module_size(spec) if spec else _site_package_size(module)
        if not size:
            continue
        try:
            version = metadata.version(label)
        except metadata.PackageNotFoundError:
            version = "?"
        print(f"  {label:20} {version:>12}  {_mb(size):>12}")
    print()

    print("Translation engines")
    for provider in audio.translate_providers():
        state = "ready" if provider["available"] else "missing"
        print(f"  {provider['id']:10} {state:8} {provider['name']}")
    for pair in pairs:
        if len(pair) == 2:
            status = audio.apple_pair_status(pair[0], pair[1])
            print(f"  apple {pair[0]}→{pair[1]}: {status}")
    helper = audio._apple_helper()
    print(f"  apple helper: {helper if helper else 'not built'}")
    print("  apple language packs live in System Settings → General → Language & Region\n")

    print("Remove hints")
    print("  cache only   : python3 cli.py clean --all")
    print("  one job      : python3 cli.py clean --job <id> [--profile renders|all]")
    print("  argos pair   : rm -rf ~/.local/share/argos-translate")
    print("  kokoro fp32  : delete data/models/kokoro/*.onnx not int8/fp16")
    print("  pip engines  : python3 -m pip uninstall argostranslate ctranslate2 demucs piper-tts kokoro-onnx")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data = _data_dir(args.data)

    if args.command == "analyze":
        _analyze(args.source.expanduser(), data, _options(args))
        return 0

    if args.command == "jobs":
        for path in sorted(_jobs_dir(data).glob("*/job.json")):
            job = json.loads(path.read_text())
            print(f"{job['id']}  {job.get('status'):8}  "
                  f"{job.get('source', {}).get('name', '?')}")
        return 0

    if args.command == "clean":
        import app as vibecut_app

        if args.all:
            targets = []
            for path in sorted(_jobs_dir(data).glob("*/job.json")):
                try:
                    targets.append(json.loads(path.read_text()))
                except (OSError, json.JSONDecodeError):
                    continue
        elif args.job:
            targets = [_load_job(data, args.job)]
        else:
            parser.error("clean needs --job <id> or --all")
            return 2
        for job in targets:
            if job.get("status") in {"queued", "scanning", "reading", "scoring"}:
                print(f"{job['id']}  skipped (still working)")
                continue
            removed = vibecut_app.clean_job_files(job, args.profile)
            _save_job(data, job)
            print(f"{job['id']}  removed: {', '.join(removed) or 'nothing'}")
        return 0

    if args.command == "audit":
        _audit(data, args.pair or [])
        return 0

    if args.command == "render":
        _normalize_targets(args)
        if args.job:
            job = _load_job(data, args.job)
        elif args.source:
            job = _job_for(args.source.expanduser(), data, _options(args))
        else:
            parser.error("render needs a source file or --job")
            return 2
        outputs = _render_job(job, data, args)
        _copy_out(outputs, getattr(args, "out", None))
        return 0

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        parser.error(f"{folder} is not a folder")
        return 2

    if args.command == "batch":
        for source in sorted(folder.iterdir()):
            if source.suffix.lower() in VIDEO_SUFFIXES:
                print(f"== {source.name}", file=sys.stderr)
                _process(source, data, args)
        return 0

    if args.command == "watch":
        seen: set[str] = set()
        print(f"Watching {folder} every {args.interval:.0f}s. Ctrl-C to stop.", file=sys.stderr)
        try:
            while True:
                for source in sorted(folder.iterdir()):
                    key = str(source)
                    if source.suffix.lower() in VIDEO_SUFFIXES and key not in seen:
                        seen.add(key)
                        print(f"== {source.name}", file=sys.stderr)
                        try:
                            _process(source, data, args)
                        except Exception as exc:  # noqa: BLE001
                            print(f"!! {source.name}: {exc}", file=sys.stderr)
                time.sleep(max(1.0, args.interval))
        except KeyboardInterrupt:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
