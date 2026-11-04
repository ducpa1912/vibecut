"""AI fill feature contract: STTN/LaMa models and span filling."""

from core.contracts import FeatureContract

FEATURE = FeatureContract(
    id="ai_fill",
    version="1.0.0",
    requires_core=">=1.0,<2.0",
    api="models_dir, method_status, prepare_span, fill_frame, mask",
)

import textfill as _textfill  # noqa: E402

DEFAULT_METHOD = _textfill.DEFAULT_METHOD
FillCancelled = _textfill.FillCancelled
FillError = _textfill.FillError
METHOD_COPY = _textfill.METHOD_COPY
METHODS = _textfill.METHODS
MODEL_FILES = _textfill.MODEL_FILES
mask = _textfill.mask
masks = mask


def models_dir(data_root):
    return _textfill.models_dir(data_root)


def model_path(method, directory):
    return _textfill.model_path(method, directory)


def missing_model(method, directory):
    return _textfill.missing_model(method, directory)


def method_problem(method, directory):
    return _textfill.method_problem(method, directory)


def model_signature(methods, directory):
    return _textfill.model_signature(methods, directory)


def span_key(**kwargs):
    return _textfill.span_key(**kwargs)


def busy():
    return _textfill.busy()


def release_fillers():
    return _textfill.release_fillers()


def estimate_span(*args, **kwargs):
    return _textfill.estimate_span(*args, **kwargs)


def estimate_summary(*args, **kwargs):
    return _textfill.estimate_summary(*args, **kwargs)


def prepare_span(*args, **kwargs):
    return _textfill.prepare_span(*args, **kwargs)


def fill_frame(*args, **kwargs):
    return _textfill.fill_frame(*args, **kwargs)


__all__ = [
    "DEFAULT_METHOD", "FEATURE", "FillCancelled", "FillError", "METHOD_COPY",
    "METHODS", "MODEL_FILES", "busy", "estimate_span", "estimate_summary",
    "fill_frame", "mask", "masks", "method_problem", "missing_model",
    "model_path", "model_signature", "models_dir", "prepare_span",
    "release_fillers", "span_key",
]
