"""Blog adapter: search-result constraints and slugified tags.

Tuned for a static site generator feeding Google's result snippet.
"""

import re

from ..metadata import Platform
from .base import BasePlatformAdapter


class BlogAdapter(BasePlatformAdapter):
    """Blog constraints.

    - Titles: 60 characters, the width of a search result heading
    - Meta descriptions: 160 characters, the width of a result snippet
    - Tags: 5-10 taxonomy keywords
    - Tag format: slugified, because tags become URLs
    """

    @property
    def platform_type(self) -> Platform:
        return Platform.BLOG

    def get_title_limit(self) -> int:
        """Return 60 — the width of a search result heading."""
        return 60

    def get_description_limit(self) -> int:
        """Return 160 — the width of a search result snippet."""
        return 160

    def get_tag_limit(self) -> int:
        """Return 10 — a taxonomy wider than this stops being a taxonomy."""
        return 10

    def format_tags(self, tags: list[str]) -> list[str]:
        """Slugify tags so each one can be a URL segment.

        Args:
            tags: Tag strings; anything past the tag limit is dropped.

        Returns:
            For example, ``["AI Tech", "Machine Learning"]`` becomes
            ``["ai-tech", "machine-learning"]``.
        """
        limited_tags = tags[: self.get_tag_limit()]
        return [self._slugify(tag) for tag in limited_tags]

    def _slugify(self, text: str) -> str:
        """Convert text to a URL-safe slug.

        Examples:
            ``"Machine Learning"`` -> ``"machine-learning"``,
            ``"AI & ML"`` -> ``"ai-ml"``,
            ``"Python 3.11"`` -> ``"python-311"``.
        """
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text)
        return text.strip("-")
