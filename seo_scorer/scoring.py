"""Keyword extraction, metadata optimisation, and SEO scoring.

Everything here is pure Python with no third-party dependencies and no
network access: the same input always produces the same output, on any
machine, with nothing to download first.
"""

import re
from collections import Counter
from datetime import UTC, datetime

#: Common English words that carry no topical signal. Used to filter
#: candidate keywords. Short words are dropped by a length rule anyway;
#: the entries that matter are the 4-plus letter ones ("over", "with",
#: "their", …) that would otherwise dominate a frequency count.
STOPWORDS: frozenset[str] = frozenset(
    (  # noqa: SIM905 - a list literal here is 143 lines of quotes and commas
        "a about above after again against all am an and any are aren't as "
        "at be because been before being below between both but by can "
        "cannot could couldn't did didn't do does doesn't doing don't down "
        "during each few for from further had hadn't has hasn't have "
        "haven't having he her here hers herself him himself his how i if "
        "in into is isn't it its itself just let's me more most mustn't my "
        "myself no nor not of off on once only or other ought our ours "
        "ourselves out over own same shan't she should shouldn't so some "
        "such than that the their theirs them themselves then there these "
        "they this those through to too under until up very was wasn't we "
        "were weren't what when where which while who whom why with won't "
        "would wouldn't you your yours yourself yourselves"
    ).split()
)

#: Tokeniser for keyword candidates. Runs over lower-cased text, so it
#: only needs the lower-case range; apostrophes are treated as breaks
#: ("today's" -> "today", "s").
_KEYWORD_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Tokeniser for readability. Keeps apostrophes so "don't" counts as one
#: word rather than two.
_WORD_RE = re.compile(r"[A-Za-z0-9']+")

#: Runs of capitalised words — a cheap proper-noun detector ("Mount
#: Rainier", "New South Wales").
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")

#: Sentence boundary for the Flesch calculation.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")

_VOWELS = "aeiouy"


class SEOScorer:
    """Keyword extraction, metadata optimisation, and SEO scoring.

    Stateless — one instance can be reused freely, including across
    threads. Subclass it to add platform-specific generation on top of
    the shared primitives.
    """

    # ---------------------------------------------------------------- #
    # Keyword extraction
    # ---------------------------------------------------------------- #

    def extract_keywords(
        self,
        topic: str,
        body: str | None = None,
        transcript: list[dict] | None = None,
        limit: int = 15,
    ) -> list[str]:
        """Extract candidate keywords from a topic, body, and transcript.

        Combines term frequency over the whole text with a pass for runs
        of capitalised words, which surfaces names and places that a raw
        frequency count would miss in a short document.

        Args:
            topic: Main topic or title seed.
            body: Full content text, if there is one.
            transcript: Dialogue entries, each a dict with a ``"text"`` key.
            limit: Maximum number of keywords to return.

        Returns:
            Keywords, most frequent first, then proper nouns.
        """
        texts = [topic] if topic else []
        if body:
            texts.append(body)
        if transcript:
            texts.extend(entry.get("text", "") for entry in transcript)

        all_text = " ".join(texts)
        if not all_text.strip():
            return []

        words = [
            word
            for word in _KEYWORD_TOKEN_RE.findall(all_text.lower())
            if len(word) > 3 and word not in STOPWORDS
        ]
        word_counts = Counter(words)

        proper_nouns = [
            term.lower() for term in _PROPER_NOUN_RE.findall(all_text) if len(term) > 3
        ]

        keywords: list[str] = []
        for word, _count in word_counts.most_common(20):
            if word not in keywords:
                keywords.append(word)
        for term in proper_nouns[:10]:
            if term not in keywords:
                keywords.append(term)

        return keywords[:limit]

    # ---------------------------------------------------------------- #
    # Metadata optimisation
    # ---------------------------------------------------------------- #

    def optimize_title(self, title: str, limit: int = 70) -> str:
        """Title-case a title and truncate it at a word boundary.

        Args:
            title: Raw title text.
            limit: Maximum character length, ellipsis included.

        Returns:
            The optimised title, never longer than ``limit``.
        """
        title = title.title()

        if len(title) > limit:
            truncated = title[: limit - 3].rsplit(" ", 1)[0]
            title = truncated + "..."

        return title

    def optimize_description(self, description: str, limit: int = 160) -> str:
        """Truncate a description, preferring a sentence boundary.

        Falls back to a hard cut with an ellipsis when even the first
        sentence is over ``limit``.

        Args:
            description: Raw description text.
            limit: Maximum character length.

        Returns:
            The optimised description, never longer than ``limit``.
        """
        if len(description) <= limit:
            return description

        sentences = description.split(". ")
        result = ""

        for sentence in sentences:
            if len(result) + len(sentence) + 2 <= limit:
                result += sentence + ". "
            else:
                break

        if result:
            return result.strip()

        return description[: limit - 3] + "..."

    def optimize_tags(self, tags: list[str], limit: int = 10) -> list[str]:
        """Lower-case tags, drop case-insensitive duplicates, cap the count.

        Args:
            tags: Raw tag list; order is preserved.
            limit: Maximum number of tags to keep.

        Returns:
            The optimised tag list.
        """
        seen: set[str] = set()
        unique_tags: list[str] = []

        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag_lower)

        return unique_tags[:limit]

    # ---------------------------------------------------------------- #
    # Scoring
    # ---------------------------------------------------------------- #

    def seo_structure_score(
        self, title: str, description: str, tags: list[str]
    ) -> float:
        """Score the SEO *structure* of a metadata set, from 0.0 to 1.0.

        This measures FORMAT fitness only — it does not assess factual
        accuracy. Well-formed but fabricated, self-contradictory, or
        keyword-stuffed text scores exactly as high as accurate text,
        because correctness is not derivable from a title, a
        description, and a tag list alone. Check factual accuracy
        separately; do not treat this number as a content-quality
        certificate.

        Scoring is strict — no participation points. Each component
        either meets the bar or contributes zero:

        - Title length, 40-70 characters (0.3)
        - Description length, 300 characters or more (0.3)
        - Tag count, 10-15 (0.2)
        - One of the first three tags appears in the title (0.2)

        The thresholds follow long-video platform conventions, where
        long descriptions and a full tag set help discovery. For a
        short-form or SERP-focused surface, subclass and override.

        Args:
            title: Metadata title.
            description: Metadata description.
            tags: Metadata tags.

        Returns:
            The structure score, 0.0 to 1.0.
        """
        score = 0.0

        title_len = len(title)
        if 40 <= title_len <= 70:
            score += 0.3

        desc_len = len(description)
        if desc_len >= 300:
            score += 0.3

        tag_count = len(tags)
        if 10 <= tag_count <= 15:
            score += 0.2

        if tags and any(tag.lower() in title.lower() for tag in tags[:3]):
            score += 0.2

        return score

    def keyword_density(self, text: str, keywords: list[str]) -> float:
        """Share of words in ``text`` that are the primary keyword.

        Args:
            text: Full text content.
            keywords: Keyword list; the first entry is the primary keyword.

        Returns:
            Density from 0.0 to 1.0, or 0.0 when either input is empty.
        """
        if not keywords or not text:
            return 0.0

        words = text.lower().split()
        if not words:
            return 0.0

        primary_keyword = keywords[0].lower()
        return words.count(primary_keyword) / len(words)

    def readability(self, text: str) -> float:
        """Flesch Reading Ease score for ``text``, from 0 to 100.

        Rough interpretation: 90-100 is very easy (about 5th grade),
        60-70 is standard (8th-9th grade), under 30 is very difficult.
        Aim for 60-70 for a general audience.

        Syllables are counted by a vowel-group heuristic, so the score
        is an approximation — useful for comparing two drafts, not for
        certifying a reading level.

        Args:
            text: Text to analyse.

        Returns:
            The score, clamped to 0.0-100.0. Empty text scores 0.0.
        """
        if not text.strip():
            return 0.0

        sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        words = _WORD_RE.findall(text)

        if not sentences or not words:
            return 0.0

        syllables = sum(self.count_syllables(word) for word in words)

        score = (
            206.835
            - 1.015 * (len(words) / len(sentences))
            - 84.6 * (syllables / len(words))
        )

        return max(0.0, min(100.0, score))

    def count_syllables(self, word: str) -> int:
        """Approximate the syllable count of a single word.

        Counts vowel groups, then subtracts one for a silent trailing
        "e". Always returns at least 1.
        """
        word = word.lower()
        count = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in _VOWELS
            if is_vowel and not previous_was_vowel:
                count += 1
            previous_was_vowel = is_vowel

        if word.endswith("e") and count > 1:
            count -= 1

        return max(1, count)

    # ---------------------------------------------------------------- #
    # Identifiers
    # ---------------------------------------------------------------- #

    def make_content_id(self, topic: str) -> str:
        """Build a slug-plus-UTC-timestamp identifier from a topic.

        Args:
            topic: Topic text.

        Returns:
            An identifier such as ``"trail-review_20260131_143000"``.
        """
        slug = re.sub(r"[^\w\s-]", "", topic.lower())
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = slug[:50]

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        return f"{slug}_{timestamp}"

    # ---------------------------------------------------------------- #
    # Compatibility aliases
    #
    # These primitives were private before they were public. The
    # underscore-prefixed names are kept so subclasses written against
    # them keep working; new code should use the public names above.
    # ---------------------------------------------------------------- #

    _extract_keywords = extract_keywords
    _optimize_title = optimize_title
    _optimize_description = optimize_description
    _optimize_tags = optimize_tags
    _calculate_seo_structure_score = seo_structure_score
    _calculate_quality_score = seo_structure_score
    _calculate_keyword_density = keyword_density
    _calculate_readability = readability
    _count_syllables = count_syllables
    _generate_content_id = make_content_id


#: Alias for the class's previous name, kept so subclasses keep importing.
BaseSEOGenerator = SEOScorer
