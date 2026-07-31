"""Microblog adapter: post-length constraints and hashtag formatting."""

from ..metadata import Platform
from .base import BasePlatformAdapter


class TwitterAdapter(BasePlatformAdapter):
    """Short-post constraints.

    - Post length: 280 characters
    - Lead line: 50 characters, leaving room for a link preview
    - Hashtags: 1-2 read well, 3 is the practical ceiling
    """

    @property
    def platform_type(self) -> Platform:
        return Platform.TWITTER

    def get_title_limit(self) -> int:
        """Return 50 — a lead line that leaves room for a link preview."""
        return 50

    def get_description_limit(self) -> int:
        """Return 280 — the post character limit."""
        return 280

    def get_tag_limit(self) -> int:
        """Return 3 — past this, hashtags cost more engagement than they earn."""
        return 3

    def format_tags(self, tags: list[str]) -> str:
        """Format tags as space-separated hashtags.

        Spaces, hyphens, and underscores are stripped, because a hashtag
        ends at the first one of those.

        Args:
            tags: Tag strings; anything past the tag limit is dropped.

        Returns:
            For example, ``["ai", "machine learning"]`` becomes
            ``"#ai #machinelearning"``.
        """
        limited_tags = tags[: self.get_tag_limit()]

        hashtags = []
        for tag in limited_tags:
            clean_tag = tag.replace(" ", "").replace("-", "").replace("_", "")
            hashtags.append(f"#{clean_tag.lower()}")

        return " ".join(hashtags)
