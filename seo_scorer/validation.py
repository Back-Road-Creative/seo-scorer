"""Validate metadata against a platform's limits.

Hard limits become errors — the platform will reject the upload.
Everything else is a warning: worth fixing, not worth blocking on.
"""

from dataclasses import dataclass, replace

from .metadata import SEOMetadata
from .platforms.base import BasePlatformAdapter


@dataclass
class ValidationResult:
    """Outcome of a validation run."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    metadata: SEOMetadata


class PlatformValidator:
    """Validate SEO metadata against one platform's rules.

    Errors (block publication):

    - Title longer than the platform's limit
    - Description longer than the platform's limit
    - More tags than the platform accepts

    Warnings (advisory only):

    - Title under 30 characters
    - Description under 100 characters
    - Fewer than 3 tags
    - Structure score below 0.5
    """

    def __init__(self, platform: BasePlatformAdapter):
        """Bind the validator to a platform adapter.

        Args:
            platform: The adapter supplying the limits.
        """
        self.platform = platform

    def validate(self, metadata: SEOMetadata) -> ValidationResult:
        """Validate ``metadata`` against the platform's rules.

        Args:
            metadata: The metadata to check.

        Returns:
            A :class:`ValidationResult`. Its ``metadata`` is a copy with
            ``validation_status`` and ``validation_errors`` filled in;
            the input is left untouched.
        """
        errors: list[str] = []
        warnings: list[str] = []

        title_limit = self.platform.get_title_limit()
        if len(metadata.title) > title_limit:
            errors.append(
                f"Title exceeds {title_limit} character limit "
                f"(current: {len(metadata.title)} chars)"
            )
        elif len(metadata.title) < 30:
            warnings.append(
                f"Title is short ({len(metadata.title)} chars). "
                f"Recommended: {title_limit - 10}-{title_limit} chars"
            )

        desc_limit = self.platform.get_description_limit()
        if len(metadata.description) > desc_limit:
            errors.append(
                f"Description exceeds {desc_limit} character limit "
                f"(current: {len(metadata.description)} chars)"
            )
        elif len(metadata.description) < 100:
            warnings.append("Description is short. More detail improves SEO.")

        tag_limit = self.platform.get_tag_limit()
        if len(metadata.tags) > tag_limit:
            errors.append(
                f"Tag count exceeds {tag_limit} limit "
                f"(current: {len(metadata.tags)} tags)"
            )
        elif len(metadata.tags) < 3:
            warnings.append("Few tags provided. 5-10 tags recommended for SEO.")

        if metadata.quality_score and metadata.quality_score < 0.5:
            warnings.append(
                f"Low structure score ({metadata.quality_score:.2f}). "
                "Consider adjusting title, description, or tags."
            )

        is_valid = len(errors) == 0

        updated_metadata = replace(
            metadata,
            validation_status="valid" if is_valid else "invalid",
            validation_errors=errors,
        )

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            metadata=updated_metadata,
        )
