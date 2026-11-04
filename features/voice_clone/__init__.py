"""Voice clone feature contract: clean references and clone routes."""

from core.contracts import FeatureContract

FEATURE = FeatureContract(
    id="voice_clone",
    version="1.0.0",
    requires_core=">=1.0,<2.0",
    api="router, forget_job, extract_clean_voice, find_voice_candidates",
)

from routes_voice_clone import forget_job, router  # noqa: E402
from voice_clone import (  # noqa: E402
    CloneError,
    create_clone,
    delete_clone,
    list_clones,
    prepare_sample,
    rename,
    sample_path,
    speech_fields,
    speech_windows,
    voice_options,
)
from voice_extract import (  # noqa: E402
    available_backends,
    extract_clean_voice,
    find_voice_candidates,
)

__all__ = [
    "CloneError", "FEATURE", "available_backends", "create_clone",
    "delete_clone", "extract_clean_voice", "find_voice_candidates",
    "forget_job", "list_clones", "prepare_sample", "rename", "router",
    "sample_path", "speech_fields", "speech_windows", "voice_options",
]
