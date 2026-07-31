"""YouTube adapter: long-form video constraints and tag formatting."""

from ..metadata import Platform
from .base import BasePlatformAdapter


class YouTubeAdapter(BasePlatformAdapter):
    """YouTube constraints.

    - Titles: 70 characters, so the whole title survives mobile truncation
    - Descriptions: 5000 characters, the platform maximum
    - Tags: about 15, which fits the roughly 500-character tag budget
    - Tag format: comma-separated and case-insensitive
    """

    @property
    def platform_type(self) -> Platform:
        return Platform.YOUTUBE

    def get_title_limit(self) -> int:
        """Return 70 — the length that stays readable on mobile."""
        return 70

    def get_description_limit(self) -> int:
        """Return 5000 — the platform maximum."""
        return 5000

    def get_tag_limit(self) -> int:
        """Return 15 — about what fits the ~500-character tag budget."""
        return 15

    def format_tags(self, tags: list[str]) -> str:
        """Format tags as a lower-cased, comma-separated string.

        Args:
            tags: Tag strings; anything past the tag limit is dropped.

        Returns:
            For example, ``["AI", "Machine Learning"]`` becomes
            ``"ai, machine learning"``.
        """
        limited_tags = tags[: self.get_tag_limit()]
        return ", ".join(tag.lower() for tag in limited_tags)
