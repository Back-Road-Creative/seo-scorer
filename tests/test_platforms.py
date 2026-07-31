"""Tests for the platform adapters."""

import pytest

from seo_scorer.metadata import Platform
from seo_scorer.platforms import (
    BasePlatformAdapter,
    BlogAdapter,
    TwitterAdapter,
    YouTubeAdapter,
)


class TestYouTubeAdapter:
    @pytest.fixture
    def adapter(self):
        return YouTubeAdapter()

    def test_platform_type(self, adapter):
        assert adapter.platform_type == Platform.YOUTUBE

    def test_limits(self, adapter):
        assert adapter.get_title_limit() == 70
        assert adapter.get_description_limit() == 5000
        assert adapter.get_tag_limit() == 15

    def test_formats_tags_comma_separated_and_lowercase(self, adapter):
        formatted = adapter.format_tags(["AI", "Machine Learning", "Python"])

        assert formatted == "ai, machine learning, python"
        assert "#" not in formatted

    def test_drops_tags_past_the_limit(self, adapter):
        formatted = adapter.format_tags([f"tag{i}" for i in range(20)])

        assert len(formatted.split(", ")) == 15

    def test_validate_title(self, adapter):
        assert adapter.validate_title("A" * 70) is True
        assert adapter.validate_title("A" * 71) is False

    def test_validate_description(self, adapter):
        assert adapter.validate_description("A" * 5000) is True
        assert adapter.validate_description("A" * 5001) is False

    def test_validate_tags(self, adapter):
        assert adapter.validate_tags(["tag"] * 15) is True
        assert adapter.validate_tags(["tag"] * 16) is False


class TestBlogAdapter:
    @pytest.fixture
    def adapter(self):
        return BlogAdapter()

    def test_platform_type(self, adapter):
        assert adapter.platform_type == Platform.BLOG

    def test_limits(self, adapter):
        assert adapter.get_title_limit() == 60
        assert adapter.get_description_limit() == 160
        assert adapter.get_tag_limit() == 10

    def test_formats_tags_as_slugs(self, adapter):
        formatted = adapter.format_tags(["Machine Learning", "AI Technology"])

        assert formatted == ["machine-learning", "ai-technology"]

    def test_drops_tags_past_the_limit(self, adapter):
        assert len(adapter.format_tags([f"tag{i}" for i in range(20)])) == 10

    @pytest.mark.parametrize(
        ("raw", "slug"),
        [
            ("Machine Learning", "machine-learning"),
            ("AI & ML", "ai-ml"),
            ("Python 3.11", "python-311"),
            ("  Extra  Spaces  ", "extra-spaces"),
            ("multiple___underscores", "multiple-underscores"),
            ("word--with---many----hyphens", "word-with-many-hyphens"),
        ],
    )
    def test_slugify(self, adapter, raw, slug):
        assert adapter._slugify(raw) == slug


class TestTwitterAdapter:
    @pytest.fixture
    def adapter(self):
        return TwitterAdapter()

    def test_platform_type(self, adapter):
        assert adapter.platform_type == Platform.TWITTER

    def test_limits(self, adapter):
        assert adapter.get_title_limit() == 50
        assert adapter.get_description_limit() == 280
        assert adapter.get_tag_limit() == 3

    def test_formats_tags_as_hashtags(self, adapter):
        formatted = adapter.format_tags(["ai", "machine learning", "python"])

        assert formatted == "#ai #machinelearning #python"

    def test_strips_separators_that_would_end_a_hashtag(self, adapter):
        assert adapter.format_tags(["road-trip", "long_drive"]) == (
            "#roadtrip #longdrive"
        )

    def test_drops_tags_past_the_limit(self, adapter):
        assert adapter.format_tags(["a", "b", "c", "d"]) == "#a #b #c"


class TestAdapterInterface:
    def test_every_adapter_satisfies_the_contract(self):
        for adapter in (YouTubeAdapter(), BlogAdapter(), TwitterAdapter()):
            assert isinstance(adapter, BasePlatformAdapter)
            assert isinstance(adapter.platform_type, Platform)
            assert isinstance(adapter.get_title_limit(), int)
            assert isinstance(adapter.get_description_limit(), int)
            assert isinstance(adapter.get_tag_limit(), int)
            assert adapter.format_tags(["one", "two"])

    def test_the_base_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            BasePlatformAdapter()

    def test_a_custom_adapter_gets_the_validators_for_free(self):
        class PodcastAdapter(BasePlatformAdapter):
            @property
            def platform_type(self):
                return Platform.LINKEDIN

            def get_title_limit(self):
                return 5

            def get_description_limit(self):
                return 10

            def get_tag_limit(self):
                return 1

            def format_tags(self, tags):
                return list(tags)

        adapter = PodcastAdapter()

        assert adapter.validate_title("abcde") is True
        assert adapter.validate_title("abcdef") is False
        assert adapter.validate_description("0123456789") is True
        assert adapter.validate_description("01234567890") is False
        assert adapter.validate_tags(["one"]) is True
        assert adapter.validate_tags(["one", "two"]) is False
