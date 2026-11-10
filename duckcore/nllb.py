"""Local NLLB translation through CTranslate2.

The model is data, not code: the optional pack contains a converted int8
CTranslate2 NLLB-200 600M model and its SentencePiece vocabulary. Apple
Translation remains the first choice; this is the offline fallback and the
custom-model path.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from duckcore import app_settings, packs

LANGUAGE_CODES = {
    "en": "eng_Latn",
    "vi": "vie_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
}

_LOCK = threading.Lock()
_ENGINES: dict[str, tuple[Any, Any]] = {}


def _settings(data_root: Path) -> dict[str, Any]:
    try:
        return app_settings.load(data_root)
    except Exception:  # noqa: BLE001
        return {}


def model_dir(data_root: Path, *, custom_path: str = "") -> Path | None:
    """Resolve the selected NLLB model directory."""
    settings = _settings(data_root)
    engine = str(settings.get("translation_engine") or "auto").lower()
    configured = str(custom_path or settings.get("translation_model_path") or "").strip()
    if engine == "custom" and configured:
        path = Path(configured).expanduser()
        if (path / "model.bin").is_file():
            return path
        return None
    if engine in {"auto", "nllb"}:
        installed = packs.installed_path(data_root, "translation-nllb")
        if installed is not None:
            return installed
    return None


def available(data_root: Path) -> bool:
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except ImportError:
        return False
    return model_dir(data_root) is not None


def _load(path: Path) -> tuple[Any, Any]:
    key = str(path.resolve())
    with _LOCK:
        cached = _ENGINES.get(key)
        if cached is not None:
            return cached
        import ctranslate2
        import sentencepiece

        translator = ctranslate2.Translator(
            str(path), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=4,
        )
        tokenizer = sentencepiece.SentencePieceProcessor(
            model_file=str(path / "sentencepiece.bpe.model"),
        )
        _ENGINES[key] = (translator, tokenizer)
        return translator, tokenizer


def translate_lines(
    lines: list[str],
    *,
    source: str,
    target: str,
    data_root: Path,
    custom_path: str = "",
) -> list[str]:
    source_code = LANGUAGE_CODES.get(str(source or "").lower())
    target_code = LANGUAGE_CODES.get(str(target or "").lower())
    if not source_code or not target_code:
        raise ValueError("Choose English, Vietnamese, Chinese or Japanese.")
    path = model_dir(data_root, custom_path=custom_path)
    if path is None:
        raise ValueError(
            "NLLB is not installed. Download the translation pack in Settings, "
            "or choose a custom CTranslate2 model folder."
        )
    if not lines:
        return []
    translator, tokenizer = _load(path)
    source_rows = [
        [source_code] + list(tokenizer.encode(text, out_type=str)) + ["</s>"]
        for text in lines
    ]
    results = translator.translate_batch(
        source_rows,
        target_prefix=[[target_code] for _ in source_rows],
        batch_type="tokens",
        beam_size=4,
        max_batch_size=2048,
        max_decoding_length=512,
    )
    output: list[str] = []
    for result in results:
        tokens = list(result.hypotheses[0])
        if tokens and tokens[0] == target_code:
            tokens = tokens[1:]
        output.append(str(tokenizer.decode(tokens)).strip())
    if len(output) != len(lines):
        raise ValueError("NLLB returned the wrong line count.")
    return output
