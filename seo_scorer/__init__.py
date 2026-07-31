"""seo-scorer — dependency-free SEO scoring, with an optional event store.

The scoring half of this package imports nothing outside the standard
library. The event store (:mod:`seo_scorer.store`) needs ``filelock``
and is deliberately not imported here, so ``import seo_scorer`` works on
a bare install::

    from seo_scorer.store import SEOEventStore   # needs the [store] extra
"""

from .events import EventType, SEOEvent
from .metadata import ContentType, Platform, SEOMetadata
from .platforms import (
    BasePlatformAdapter,
    BlogAdapter,
    TwitterAdapter,
    YouTubeAdapter,
)
from .scoring import BaseSEOGenerator, SEOScorer
from .validation import PlatformValidator, ValidationResult

__version__ = "0.1.0"

__all__ = [
    "BasePlatformAdapter",
    "BaseSEOGenerator",
    "BlogAdapter",
    "ContentType",
    "EventType",
    "Platform",
    "PlatformValidator",
    "SEOEvent",
    "SEOMetadata",
    "SEOScorer",
    "TwitterAdapter",
    "ValidationResult",
    "YouTubeAdapter",
]
