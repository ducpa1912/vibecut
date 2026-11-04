"""URL ingest feature contract: providers, validation and download chain."""

from core.contracts import FeatureContract

FEATURE = FeatureContract(
    id="url_ingest",
    version="1.0.0",
    requires_core=">=1.0,<2.0",
    api="registry, fallback, IngestOptions, IngestResult, IngestError",
)

from url_ingest import fallback, registry  # noqa: E402
from url_ingest.base import IngestError, IngestOptions, IngestResult, Provider  # noqa: E402

__all__ = [
    "FEATURE", "IngestError", "IngestOptions", "IngestResult", "Provider",
    "fallback", "registry",
]
