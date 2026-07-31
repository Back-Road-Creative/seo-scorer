"""Tests for PlatformValidator."""

import pytest

from seo_scorer.metadata import ContentType, Platform, SEOMetadata
from seo_scorer.platforms import BlogAdapter, YouTubeAdapter
from seo_scorer.validation import PlatformValidator, ValidationResult


def _metadata(**overrides) -> SEOMetadata:
    fields = {
        "site_id": "test_site",
        "content_id": "test_001",
        "platform": Platform.YOUTUBE,
        "content_type": ContentType.VIDEO,
        "title": "Great AI Tutorial For Curious Beginners Everywhere",
        "description": "Learn AI fundamentals in this guide. " * 4,
        "tags": ["ai", "tutorial", "machine-learning"],
    }
    fields.update(overrides)
    return SEOMetadata(**fields)


class TestValidationResult:
    def test_holds_a_valid_outcome(self):
        result = ValidationResult(
            is_valid=True, errors=[], warnings=[], metadata=_metadata()
        )

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_holds_an_invalid_outcome(self):
        result = ValidationResult(
            is_valid=False,
            errors=["Title exceeds 70 character limit"],
            warnings=[],
            metadata=_metadata(),
        )

        assert result.is_valid is False
        assert len(result.errors) == 1


class TestPlatformValidator:
    @pytest.fixture
    def youtube(self):
        return PlatformValidator(YouTubeAdapter())

    @pytest.fixture
    def blog(self):
        return PlatformValidator(BlogAdapter())

    def test_accepts_metadata_within_every_limit(self, youtube):
        result = youtube.validate(_metadata())

        assert result.is_valid is True
        assert result.errors == []

    def test_rejects_a_title_over_the_limit(self, youtube):
        result = youtube.validate(_metadata(title="A" * 75))

        assert result.is_valid is False
        assert any("title" in err.lower() and "70" in err for err in result.errors)

    def test_rejects_a_description_over_the_limit(self, youtube):
        result = youtube.validate(_metadata(description="A" * 5001))

        assert result.is_valid is False
        assert any(
            "description" in err.lower() and "5000" in err for err in result.errors
        )

    def test_rejects_too_many_tags(self, youtube):
        result = youtube.validate(_metadata(tags=[f"tag_{i}" for i in range(20)]))

        assert result.is_valid is False
        assert any("tag" in err.lower() and "15" in err for err in result.errors)

    def test_applies_the_bound_platforms_limits(self, blog):
        result = blog.validate(
            _metadata(
                platform=Platform.BLOG,
                content_type=ContentType.BLOG_POST,
                title="A" * 65,
            )
        )

        assert result.is_valid is False
        assert any("60" in err for err in result.errors)

    def test_reports_every_error_at_once(self, youtube):
        result = youtube.validate(
            _metadata(
                title="A" * 80,
                description="B" * 5100,
                tags=[f"tag_{i}" for i in range(20)],
            )
        )

        assert result.is_valid is False
        assert len(result.errors) >= 3

    def test_warnings_do_not_invalidate(self, blog):
        result = blog.validate(
            _metadata(
                platform=Platform.BLOG,
                content_type=ContentType.BLOG_POST,
                title="Short",
                description="Also short",
                tags=["test"],
                quality_score=0.45,
            )
        )

        assert result.is_valid is True
        assert len(result.warnings) == 4

    def test_a_low_structure_score_only_warns(self, youtube):
        result = youtube.validate(_metadata(quality_score=0.2))

        assert result.is_valid is True
        assert any("structure score" in w.lower() for w in result.warnings)

    def test_stamps_the_status_onto_a_copy(self, youtube):
        original = _metadata(title="A" * 75)

        result = youtube.validate(original)

        assert result.metadata.validation_status == "invalid"
        assert result.metadata.validation_errors == result.errors
        # The input is untouched.
        assert original.validation_status == "pending"
        assert original.validation_errors == []

    def test_stamps_valid_on_a_clean_pass(self, youtube):
        result = youtube.validate(_metadata())

        assert result.metadata.validation_status == "valid"
        assert result.metadata.validation_errors == []
