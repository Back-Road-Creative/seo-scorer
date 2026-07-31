"""Tests for SEOScorer: extraction, optimisation, and scoring."""

import pytest

from seo_scorer.scoring import BaseSEOGenerator, SEOScorer


@pytest.fixture
def scorer():
    return SEOScorer()


class TestKeywordExtraction:
    def test_extracts_keywords_from_body_text(self, scorer):
        text = """
        Artificial intelligence and machine learning are transforming technology.
        Deep learning models use neural networks to process data.
        AI systems can automate complex tasks efficiently.
        """

        keywords = scorer.extract_keywords(topic="AI Technology", body=text)

        assert isinstance(keywords, list)
        assert keywords
        assert any("artificial" in kw for kw in keywords)
        assert any("learning" in kw for kw in keywords)

    def test_extracts_keywords_from_transcript(self, scorer):
        transcript = [
            {"speaker": "Host", "text": "Today we're discussing Python programming"},
            {
                "speaker": "Guest",
                "text": "Python is great for data science and machine learning",
            },
            {"speaker": "Host", "text": "What libraries do you recommend?"},
            {
                "speaker": "Guest",
                "text": "NumPy, Pandas, and scikit-learn are essential",
            },
        ]

        keywords = scorer.extract_keywords(
            topic="Python Programming", transcript=transcript
        )

        assert any("python" in kw for kw in keywords)

    def test_removes_stopwords(self, scorer):
        keywords = scorer.extract_keywords(
            topic="Test", body="the quick brown fox jumps over the lazy dog"
        )

        for stopword in ("the", "over", "a", "an", "and", "or", "but"):
            assert stopword not in keywords

    def test_keeps_terms_containing_digits(self, scorer):
        keywords = scorer.extract_keywords(
            topic="Codecs", body="the h264 codec and the h265 codec are compared"
        )

        assert "h264" in keywords
        assert "h265" in keywords

    def test_handles_hyphenated_product_names(self, scorer):
        text = "GPT-4 and Claude-3 are AI models. Python 3.11 introduced new features."

        keywords = scorer.extract_keywords(topic="AI Models", body=text)

        assert any("claude" in kw for kw in keywords)

    def test_surfaces_proper_nouns_a_frequency_count_would_miss(self, scorer):
        # "Mount Rainier" appears once, so frequency alone would bury it.
        text = "We walked for hours. The weather turned. Mount Rainier stayed hidden."

        keywords = scorer.extract_keywords(topic="Field notes", body=text)

        assert "mount rainier" in keywords

    def test_respects_the_limit(self, scorer):
        long_text = " ".join(f"word{i}" for i in range(100))

        keywords = scorer.extract_keywords(topic="Test", body=long_text)

        assert len(keywords) <= 15

    def test_custom_limit(self, scorer):
        long_text = " ".join(f"word{i}" for i in range(100))

        keywords = scorer.extract_keywords(topic="Test", body=long_text, limit=5)

        assert len(keywords) == 5

    def test_empty_input_returns_empty_list(self, scorer):
        assert scorer.extract_keywords(topic="") == []

    def test_is_deterministic(self, scorer):
        text = "Coastal trails and coastal weather shape the coastal route."

        first = scorer.extract_keywords(topic="Coastal Route", body=text)
        second = scorer.extract_keywords(topic="Coastal Route", body=text)

        assert first == second


class TestTitleOptimisation:
    def test_truncates_at_a_word_boundary(self, scorer):
        long_title = (
            "This is a very long title that exceeds the maximum character "
            "limit and needs to be truncated properly"
        )

        optimized = scorer.optimize_title(long_title, limit=70)

        assert len(optimized) <= 70
        assert optimized.endswith("...")
        assert not optimized[:-3].endswith(" ")

    def test_applies_title_case(self, scorer):
        optimized = scorer.optimize_title(
            "understanding machine learning basics", limit=100
        )

        assert optimized == "Understanding Machine Learning Basics"

    def test_leaves_a_short_title_alone(self, scorer):
        optimized = scorer.optimize_title("Short Title", limit=70)

        assert optimized == "Short Title"
        assert not optimized.endswith("...")

    def test_truncation_keeps_the_leading_words(self, scorer):
        optimized = scorer.optimize_title(
            "How to Build Machine Learning Models for Production", limit=40
        )

        assert len(optimized) <= 40
        assert "Machine Learning" in optimized


class TestDescriptionOptimisation:
    def test_truncates_at_a_sentence_boundary(self, scorer):
        long_desc = (
            "First sentence here. Second sentence here. Third sentence here. "
            "Fourth sentence that makes it too long. Fifth sentence."
        )

        optimized = scorer.optimize_description(long_desc, limit=100)

        assert len(optimized) <= 100
        assert optimized.endswith(".")

    def test_leaves_a_short_description_alone(self, scorer):
        assert scorer.optimize_description("Short enough.", limit=160) == (
            "Short enough."
        )

    def test_hard_truncates_when_the_first_sentence_is_too_long(self, scorer):
        one_long_sentence = "x" * 300

        optimized = scorer.optimize_description(one_long_sentence, limit=100)

        assert len(optimized) == 100
        assert optimized.endswith("...")


class TestTagOptimisation:
    def test_deduplicates_case_insensitively(self, scorer):
        tags = ["AI", "ai", "Machine Learning", "machine learning", "Python", "python"]

        optimized = scorer.optimize_tags(tags, limit=10)

        assert optimized == ["ai", "machine learning", "python"]

    def test_caps_the_count(self, scorer):
        tags = [f"tag_{i}" for i in range(20)]

        assert len(scorer.optimize_tags(tags, limit=10)) == 10


class TestStructureScore:
    """Strict scoring — miss a criterion and it contributes zero."""

    @staticmethod
    def _optimal(scorer, title="x" * 50, desc="x" * 500, tags=None):
        if tags is None:
            tags = ["x"] * 12
        return scorer.seo_structure_score(title, desc, tags)

    def test_all_four_components_optimal_scores_one(self, scorer):
        assert self._optimal(scorer) == 1.0

    def test_short_title_loses_the_title_component(self, scorer):
        assert scorer.seo_structure_score("Short x", "x" * 500, ["x"] * 12) == 0.7

    def test_short_description_loses_the_description_component(self, scorer):
        assert scorer.seo_structure_score("x" * 50, "short", ["x"] * 12) == 0.7

    def test_too_few_tags_loses_the_tag_component(self, scorer):
        assert scorer.seo_structure_score("x" * 50, "x" * 500, ["x"] * 3) == 0.8

    def test_no_tag_in_title_loses_the_keyword_component(self, scorer):
        score = scorer.seo_structure_score(
            "A" * 50, "x" * 500, ["zzz_not_in_title"] * 12
        )
        assert score == 0.8

    def test_everything_wrong_scores_zero(self, scorer):
        assert scorer.seo_structure_score("Hi", "Hi", ["zzz"]) == 0.0

    @pytest.mark.parametrize(
        ("title_len", "expected"),
        [(39, 0.7), (40, 1.0), (70, 1.0), (71, 0.7)],
    )
    def test_title_length_boundaries(self, scorer, title_len, expected):
        assert self._optimal(scorer, title="x" * title_len) == expected

    @pytest.mark.parametrize(
        ("desc_len", "expected"),
        [(299, 0.7), (300, 1.0), (2000, 1.0)],
    )
    def test_description_length_boundaries(self, scorer, desc_len, expected):
        assert self._optimal(scorer, desc="x" * desc_len) == expected

    @pytest.mark.parametrize(
        ("tag_count", "expected"),
        [(9, 0.8), (10, 1.0), (15, 1.0), (16, 0.8)],
    )
    def test_tag_count_boundaries(self, scorer, tag_count, expected):
        assert self._optimal(scorer, tags=["x"] * tag_count) == expected

    def test_keyword_match_is_case_insensitive(self, scorer):
        title = "Coastal Route Overview For Long Winter Evenings Ahead"
        tags = ["COASTAL ROUTE"] + [f"tag{i}" for i in range(11)]

        assert scorer.seo_structure_score(title, "x" * 400, tags) == 1.0

    def test_a_realistic_metadata_set_scores_one(self, scorer):
        """A metadata set shaped the way the scorer asks for scores 1.0."""
        title = "POV Driving the Coast Road | Northern Highlands"  # 46 chars
        description = (
            "Join me for a relaxing drive along the northern coast road.\n\n"
            "This full-length scenic drive follows the coastline from the "
            "harbour village out to the northern headland, past three sea "
            "stacks and a lighthouse. No commentary and no music, just the "
            "road and the weather.\n\n"
            "Route: harbour village to northern headland\n"
            "Duration: 62m 27s\n"
            "Conditions: overcast, light rain after the halfway point\n\n"
            "Subscribe for more drives, and tell me where to point the "
            "camera next."
        )
        tags = [
            "POV driving",
            "scenic drive",
            "road trip",
            "driving video",
            "4K driving",
            "relaxing drive",
            "virtual travel",
            "dashcam",
            "drive with me",
            "scenic route",
            "POV",
            "long drive",
            "coast road",
            "northern headland",
            "lighthouse",
        ]

        assert len(description) >= 300
        assert scorer.seo_structure_score(title, description, tags) == 1.0


class TestKeywordDensity:
    def test_counts_the_primary_keyword(self, scorer):
        text = "python programming python code python tutorial"

        density = scorer.keyword_density(text, ["python", "programming", "code"])

        assert density == pytest.approx(3 / 6)

    def test_empty_inputs_score_zero(self, scorer):
        assert scorer.keyword_density("", ["python"]) == 0.0
        assert scorer.keyword_density("some text", []) == 0.0


class TestReadability:
    def test_simple_text_scores_high(self, scorer):
        score = scorer.readability("The cat sat on the mat. The dog ran in the park.")

        assert 0.0 <= score <= 100.0
        assert score > 60

    def test_dense_text_scores_lower_than_simple_text(self, scorer):
        simple = scorer.readability("The dog ran. The cat sat. The sun set.")
        dense = scorer.readability(
            "Notwithstanding the aforementioned considerations, the "
            "institutional methodology necessitates comprehensive "
            "reevaluation of interdependent organisational hierarchies."
        )

        assert dense < simple

    def test_empty_text_scores_zero(self, scorer):
        assert scorer.readability("") == 0.0
        assert scorer.readability("   ") == 0.0

    def test_text_without_a_sentence_terminator_still_scores(self, scorer):
        assert scorer.readability("a short line with no full stop") > 0.0


class TestSyllableCount:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [("cat", 1), ("python", 2), ("programming", 3), ("artificial", 4)],
    )
    def test_counts_syllables(self, scorer, word, expected):
        assert scorer.count_syllables(word) == expected

    def test_never_returns_zero(self, scorer):
        assert scorer.count_syllables("rhythm") >= 1
        assert scorer.count_syllables("") == 1


class TestContentId:
    def test_slugifies_the_topic_and_appends_a_timestamp(self, scorer):
        content_id = scorer.make_content_id("Understanding Machine Learning")

        assert content_id.startswith("understanding-machine-learning_")
        assert " " not in content_id

    def test_strips_punctuation(self, scorer):
        assert scorer.make_content_id("Hello, World!").startswith("hello-world_")


class TestCompatibilityAliases:
    """The underscore-prefixed names existing subclasses call still resolve."""

    def test_class_alias(self):
        assert BaseSEOGenerator is SEOScorer

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("_extract_keywords", "extract_keywords"),
            ("_optimize_title", "optimize_title"),
            ("_optimize_description", "optimize_description"),
            ("_optimize_tags", "optimize_tags"),
            ("_calculate_seo_structure_score", "seo_structure_score"),
            ("_calculate_quality_score", "seo_structure_score"),
            ("_calculate_keyword_density", "keyword_density"),
            ("_calculate_readability", "readability"),
            ("_count_syllables", "count_syllables"),
            ("_generate_content_id", "make_content_id"),
        ],
    )
    def test_method_aliases(self, old, new):
        assert getattr(SEOScorer, old) is getattr(SEOScorer, new)

    def test_a_subclass_can_still_call_the_old_names(self):
        class LegacySubclass(BaseSEOGenerator):
            def title_for(self, topic):
                return self._optimize_title(topic, limit=40)

        assert LegacySubclass().title_for("a coastal route") == "A Coastal Route"
