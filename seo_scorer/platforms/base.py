"""The contract every platform adapter implements."""

from abc import ABC, abstractmethod

from ..metadata import Platform


class BasePlatformAdapter(ABC):
    """Abstract base class for platform-specific adapters.

    Each platform supplies its own length limits and tag formatting; the
    three ``validate_*`` helpers are derived from those limits, so a
    subclass only has to answer four questions.
    """

    @property
    @abstractmethod
    def platform_type(self) -> Platform:
        """Return the platform enum value."""

    @abstractmethod
    def get_title_limit(self) -> int:
        """Return the maximum title length, in characters."""

    @abstractmethod
    def get_description_limit(self) -> int:
        """Return the maximum description length, in characters."""

    @abstractmethod
    def get_tag_limit(self) -> int:
        """Return the maximum number of tags."""

    @abstractmethod
    def format_tags(self, tags: list[str]):
        """Format tags according to the platform's convention.

        Returns:
            Whatever shape the platform expects — a string or a list.

        Examples:
            - Long-video: ``"ai, machine learning, podcast"``
            - Microblog: ``"#ai #machinelearning #podcast"``
            - Blog: ``["ai", "machine-learning", "podcast"]``
        """

    def validate_title(self, title: str) -> bool:
        """Return True when the title is within the platform's limit."""
        return len(title) <= self.get_title_limit()

    def validate_description(self, description: str) -> bool:
        """Return True when the description is within the platform's limit."""
        return len(description) <= self.get_description_limit()

    def validate_tags(self, tags: list[str]) -> bool:
        """Return True when the tag count is within the platform's limit."""
        return len(tags) <= self.get_tag_limit()
