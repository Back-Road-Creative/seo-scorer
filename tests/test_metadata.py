"""Tests for the SEOMetadata dataclass and its enums."""

from datetime import datetime

import pytest

from seo_scorer.metadata import ContentType, Platform, SEOMetadata


def _metadata(**overrides) -> SEOMetadata:
    fields = {
        "site_id": "test_site",
        "content_id": "test_001",
        "platform": Platform.YOUTUBE,
        "content_type": ContentType.VIDEO,
        "title": "Test Video Title",
        "description": "Test description for video",
        "tags": ["test", "video", "seo"],
    }
    fields.update(overrides)
    return SEOMetadata(**fields)


class TestConstruction:
    def test_required_fields(self):
        metadata = _metadata()

        assert metadata.site_id == "test_site"
        assert metadata.content_id == "test_001"
        assert metadata.platform == Platform.YOUTUBE
        assert metadata.content_type == ContentType.VIDEO
        assert metadata.title == "Test Video Title"
        assert metadata.tags == ["test", "video", "seo"]

    def test_missing_required_fields_raise(self):
        with pytest.raises(TypeError):
            SEOMetadata(site_id="test_site", platform=Platform.YOUTUBE)

    def test_optional_field_defaults(self):
        metadata = _metadata()

        assert metadata.url is None
        assert metadata.canonical_url is None
        assert metadata.thumbnail_url is None
        assert metadata.author is None
        assert metadata.published_date is None
        assert metadata.youtube_metadata == {}
        assert metadata.blog_metadata == {}
        assert metadata.social_metadata == {}
        assert metadata.quality_score is None
        assert metadata.keyword_density is None
        assert metadata.readability_score is None
        assert metadata.validation_status == "pending"
        assert metadata.validation_errors == []
        assert metadata.fixes_applied == []
        assert metadata.generated_by == "seo_scorer"
        assert metadata.version == 1

    def test_generated_at_is_an_iso_timestamp(self):
        parsed = datetime.fromisoformat(_metadata().generated_at)

        assert isinstance(parsed, datetime)
        assert parsed.tzinfo is not None

    def test_mutable_defaults_are_not_shared(self):
        first = _metadata()
        second = _metadata()

        first.validation_errors.append("boom")

        assert second.validation_errors == []


class TestImmutability:
    def test_fields_cannot_be_reassigned(self):
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            _metadata().title = "Modified Title"

    def test_with_fixes_returns_a_new_instance(self):
        original = _metadata()

        fixed = original.with_fixes(["title_truncated", "tags_optimized"])

        assert original.fixes_applied == []
        assert fixed.fixes_applied == ["title_truncated", "tags_optimized"]
        assert fixed.site_id == original.site_id
        assert fixed.title == original.title
        assert fixed is not original

    def test_with_fixes_accumulates(self):
        once = _metadata().with_fixes(["a"])
        twice = once.with_fixes(["b"])

        assert twice.fixes_applied == ["a", "b"]
        assert once.fixes_applied == ["a"]


class TestSerialisation:
    def test_to_dict_stringifies_the_enums(self):
        data = _metadata(quality_score=0.85, keyword_density=0.05).to_dict()

        assert data["platform"] == "youtube"
        assert data["content_type"] == "video"
        assert data["quality_score"] == 0.85

    def test_from_dict_restores_the_enums(self):
        metadata = SEOMetadata.from_dict(
            {
                "site_id": "test_site",
                "content_id": "test_001",
                "platform": "youtube",
                "content_type": "video",
                "title": "Test Title",
                "description": "Test description",
                "tags": ["ai", "seo"],
                "quality_score": 0.85,
            }
        )

        assert metadata.platform == Platform.YOUTUBE
        assert metadata.content_type == ContentType.VIDEO
        assert metadata.quality_score == 0.85

    def test_from_dict_does_not_mutate_its_input(self):
        data = _metadata().to_dict()

        SEOMetadata.from_dict(data)

        assert data["platform"] == "youtube"

    def test_roundtrip_preserves_every_field(self):
        original = _metadata(
            platform=Platform.BLOG,
            content_type=ContentType.BLOG_POST,
            quality_score=0.92,
            keyword_density=0.03,
            readability_score=68.5,
            blog_metadata={"categories": ["Tech"], "series": "Field Notes"},
        )

        restored = SEOMetadata.from_dict(original.to_dict())

        assert restored == original


class TestEnums:
    def test_platform_values(self):
        assert [p.value for p in Platform] == [
            "youtube",
            "blog",
            "twitter",
            "instagram",
            "tiktok",
            "linkedin",
        ]

    def test_content_type_values(self):
        assert [c.value for c in ContentType] == [
            "video",
            "short",
            "blog_post",
            "social_post",
            "podcast",
            "trail_guide",
        ]
