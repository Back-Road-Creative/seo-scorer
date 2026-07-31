"""Core SEO metadata structures.

Defines the :class:`SEOMetadata` dataclass and the enums for platform and
content types.
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Platform(Enum):
    """Supported platforms for SEO optimisation."""

    YOUTUBE = "youtube"
    BLOG = "blog"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"


class ContentType(Enum):
    """Types of content that can be optimised."""

    VIDEO = "video"
    SHORT = "short"
    BLOG_POST = "blog_post"
    SOCIAL_POST = "social_post"
    PODCAST = "podcast"
    TRAIL_GUIDE = "trail_guide"


@dataclass(frozen=True)
class SEOMetadata:
    """Complete SEO metadata for any content type on any platform.

    Frozen (immutable) so it can be used as an event payload without a
    later mutation silently rewriting history. All state changes create a
    new instance — see :meth:`with_fixes` and :func:`dataclasses.replace`.
    """

    # Identity (required)
    site_id: str  # Partition key when one process serves several sites
    content_id: str  # Unique within a site
    platform: Platform  # Target platform
    content_type: ContentType  # Content category

    # Core SEO fields (required)
    title: str  # Primary headline
    description: str  # Long-form description
    tags: list[str]  # Keywords / hashtags

    # Extended metadata (optional)
    url: str | None = None  # Canonical URL
    canonical_url: str | None = None  # SEO canonical, if different
    thumbnail_url: str | None = None  # Visual preview
    author: str | None = None  # Content creator
    published_date: str | None = None  # ISO 8601 timestamp

    # Platform-specific data (optional)
    youtube_metadata: dict[str, Any] = field(default_factory=dict)
    # Example: {"playlist": "Season 1", "category": "Science & Technology"}

    blog_metadata: dict[str, Any] = field(default_factory=dict)
    # Example: {"categories": ["Tech"], "series": "Field Notes"}

    social_metadata: dict[str, Any] = field(default_factory=dict)
    # Example: {"cta": "Link in bio", "mention": "@example"}

    # Quality metrics (populated by the scorer)
    quality_score: float | None = None  # 0.0-1.0 SEO structure score
    keyword_density: float | None = None  # Primary keyword share of words
    readability_score: float | None = None  # Flesch Reading Ease

    # System metadata
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    generated_by: str = "seo_scorer"
    version: int = 1  # Schema version
    validation_status: str = "pending"  # pending / valid / invalid
    validation_errors: list[str] = field(default_factory=list)

    # Fix tracking
    fixes_applied: list[str] = field(default_factory=list)
    # Example: ["title_truncated_to_70", "tags_deduplicated"]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict (enums become strings)."""
        data = asdict(self)
        data["platform"] = self.platform.value
        data["content_type"] = self.content_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SEOMetadata":
        """Deserialise from a dict produced by :meth:`to_dict`."""
        data = data.copy()
        data["platform"] = Platform(data["platform"])
        data["content_type"] = ContentType(data["content_type"])
        return cls(**data)

    def with_fixes(self, fixes: list[str]) -> "SEOMetadata":
        """Return a new instance with ``fixes`` appended to ``fixes_applied``.

        Args:
            fixes: Fix identifiers to record.

        Returns:
            A new ``SEOMetadata``; the receiver is unchanged.
        """
        updated_fixes = list(self.fixes_applied) + fixes
        return replace(self, fixes_applied=updated_fixes)
