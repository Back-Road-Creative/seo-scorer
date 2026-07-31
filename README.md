# seo-scorer

Score and shape SEO metadata — titles, descriptions, tags — without installing
anything. The scoring half of this package imports nothing outside the Python
standard library, makes no network calls, and downloads no corpora. Same input,
same output, on any machine, offline.

An optional append-only event store is included for recording what you generated
and how it performed over time.

## Why it exists

Most SEO tooling is a service: you send it your text, it sends back a number you
cannot reproduce. That is a poor fit for a build step. If a title fails a check
at 3am in CI, you want to know exactly which rule it failed and be able to run
the same check on your laptop with no key, no quota, and no network.

So this library is deliberately small and boring:

- **Rules you can read.** The structure score is four thresholds. They are in
  one method, documented, and you can override them.
- **No hidden inputs.** No model, no corpus download, no API. Nothing to go
  stale between runs.
- **Honest about scope.** It scores *format*, not truth. See
  [What it does not do](#what-it-does-not-do).

## Install

```bash
pip install seo-scorer            # scoring only, zero dependencies
pip install "seo-scorer[store]"   # adds the event store (needs filelock)
```

Requires Python 3.11 or newer.

## Quick start

```python
from seo_scorer import SEOScorer, YouTubeAdapter, PlatformValidator
from seo_scorer import SEOMetadata, Platform, ContentType

scorer = SEOScorer()

body = """
Mount Baker is a stratovolcano in the North Cascades. The Heliotrope Ridge
trail climbs through old-growth forest to the toe of the Coleman Glacier.
Most walkers turn around at the glacier overlook.
"""

keywords = scorer.extract_keywords(topic="Heliotrope Ridge Trail", body=body)
# ['heliotrope', 'ridge', 'trail', 'glacier', 'mount', 'baker',
#  'stratovolcano', 'north', 'cascades', 'climbs', 'growth', 'forest',
#  'coleman', 'walkers', 'turn']

title = scorer.optimize_title("heliotrope ridge trail: a full guide", limit=70)
# 'Heliotrope Ridge Trail: A Full Guide'

score = scorer.seo_structure_score(title, description=body, tags=keywords)
# 0.4  -- the tag count and the keyword-in-title check pass; the title is
#         under 40 characters and the description under 300, so those score 0

print(f"{scorer.readability(body):.0f}")  # Flesch Reading Ease -> 65
```

Then check the result against a platform's hard limits:

```python
metadata = SEOMetadata(
    site_id="my_site",
    content_id="heliotrope-ridge",
    platform=Platform.YOUTUBE,
    content_type=ContentType.VIDEO,
    title=title,
    description=body,
    tags=keywords,
    quality_score=score,
)

result = PlatformValidator(YouTubeAdapter()).validate(metadata)

print(result.is_valid)  # True -- nothing exceeds a hard limit
print(result.warnings)
# ['Low structure score (0.40). Consider adjusting title, description, or tags.']
print(result.metadata.validation_status)  # 'valid'
```

`validate` never mutates its input. It returns a copy with
`validation_status` and `validation_errors` filled in.

## What is in the box

### `SEOScorer`

Stateless. Reuse one instance anywhere, including across threads.

| Method | Returns |
| --- | --- |
| `extract_keywords(topic, body=None, transcript=None, limit=15)` | Keywords by frequency, then proper nouns |
| `optimize_title(title, limit=70)` | Title-cased, truncated at a word boundary |
| `optimize_description(description, limit=160)` | Truncated at a sentence boundary where possible |
| `optimize_tags(tags, limit=10)` | Lower-cased, de-duplicated, capped |
| `seo_structure_score(title, description, tags)` | `0.0`-`1.0` |
| `keyword_density(text, keywords)` | Primary keyword's share of words |
| `readability(text)` | Flesch Reading Ease, `0`-`100` |
| `count_syllables(word)` | Approximate syllable count |
| `make_content_id(topic)` | `"slug_YYYYMMDD_HHMMSS"` |

`transcript` is a list of dicts with a `"text"` key, which is the shape most
speech-to-text tools emit — the rest of each entry is ignored.

### The structure score

Four components, strictly scored. Each either meets its bar or contributes zero;
there are no partial credits.

| Component | Bar | Weight |
| --- | --- | --- |
| Title length | 40-70 characters | 0.3 |
| Description length | 300 characters or more | 0.3 |
| Tag count | 10-15 | 0.2 |
| Keyword in title | one of the first three tags appears in the title | 0.2 |

The thresholds suit a long-form video platform, where a detailed description and
a full tag set help discovery. For a search-snippet or short-form surface they
are wrong — subclass and override:

```python
class SnippetScorer(SEOScorer):
    def seo_structure_score(self, title, description, tags):
        score = 0.0
        if 50 <= len(title) <= 60:  # search result heading width
            score += 0.4
        if 120 <= len(description) <= 160:  # search result snippet width
            score += 0.4
        if 3 <= len(tags) <= 10:
            score += 0.2
        return score
```

### Platform adapters

Each adapter answers four questions — title limit, description limit, tag limit,
tag format — and inherits three validators for free.

| Adapter | Title | Description | Tags | Tag format |
| --- | --- | --- | --- | --- |
| `YouTubeAdapter` | 70 | 5000 | 15 | `ai, machine learning` |
| `BlogAdapter` | 60 | 160 | 10 | `["ai", "machine-learning"]` |
| `TwitterAdapter` | 50 | 280 | 3 | `#ai #machinelearning` |

Add your own by subclassing `BasePlatformAdapter`:

```python
from seo_scorer import BasePlatformAdapter, Platform


class NewsletterAdapter(BasePlatformAdapter):
    @property
    def platform_type(self):
        return Platform.BLOG

    def get_title_limit(self):
        return 90

    def get_description_limit(self):
        return 300

    def get_tag_limit(self):
        return 5

    def format_tags(self, tags):
        return [t.lower() for t in tags]


NewsletterAdapter().validate_title("x" * 91)  # False
```

### The event store (optional)

`seo_scorer.store` is an append-only JSONL log with an advisory file lock, so
several processes can write to one directory safely. It is the only module that
needs a third-party package.

```python
from datetime import datetime, timezone
from seo_scorer import SEOEvent, EventType
from seo_scorer.store import SEOEventStore

store = SEOEventStore("./seo-events")

store.append_event(
    SEOEvent(
        event_id="evt_001",
        event_type=EventType.METADATA_GENERATED,
        site_id="my_site",
        content_id="heliotrope-ridge",
        timestamp=datetime.now(timezone.utc).isoformat(),
        data={"title": title, "score": score},
    )
)

store.query_by_site("my_site", event_type=EventType.METADATA_GENERATED, limit=10)
store.get_by_content_id("my_site", "heliotrope-ridge")
```

On disk:

```
seo-events/
  events.jsonl    # the log — one JSON event per line, append-only
  index.json      # site/type/date/content indexes — a cache
  .lock           # advisory lock guarding writes
```

Every line carries a CRC32 checksum, so a truncated or hand-edited line is
detected on read rather than deserialising into wrong data. A bad line costs you
that line and nothing else: queries log it and move on.

`events.jsonl` is the source of truth and `index.json` is only a cache, so
deleting the index is safe — it is rebuilt by scanning the log on the next open.
The same happens automatically if the index is unreadable.

`upsert_event` exists for last-write-wins on an event id, but it rewrites the
whole file. Prefer `append_event`.

## What it does not do

Read this before you wire the score into a gate.

- **It scores format, not truth.** Well-formed but fabricated, self-contradictory,
  or keyword-stuffed text scores exactly as high as accurate text. A title and a
  description that flatly disagree still score 1.0. Correctness is not derivable
  from a title, a description, and a tag list, so this library does not pretend
  to derive it. Check facts separately.
- **The thresholds are conventions, not measurements.** They reflect widely
  repeated platform guidance, not an experiment on your audience. Treat a change
  from 0.7 to 1.0 as "now shaped the way the rules ask for", not as a traffic
  forecast.
- **Keyword extraction is frequency plus capitalisation.** No stemming, no
  lemmatisation, no embeddings, no phrase detection beyond runs of capitalised
  words. It is a fast first pass over English text, and it is only tuned for
  English. Feed it something else and you will get tokens back, but not insight.
- **The syllable count is a heuristic**, so Flesch scores are approximate. They
  are useful for comparing two drafts of the same text, not for certifying a
  reading level.
- **The store is a file, not a database.** Queries scan the log from the start;
  the indexes speed up nothing today, they are bookkeeping for callers that want
  a set of ids. At millions of events you want a real database. There is no
  compaction and no retention policy.
- **The lock is advisory and local.** It guards concurrent writers on one
  machine. It does nothing across NFS or between containers that do not share
  the filesystem.
- **Store files are created group-writable (0o664)** so several accounts in a
  shared group can use one store directory. If that is wider than you want, set
  `seo_scorer.store.LOCK_MODE` before creating a store, or put the directory
  somewhere with a restrictive ACL.

## Roadmap

- Confidence-scored autofix: given a validation failure, propose the minimal
  edit that clears it, with a confidence value so a caller can decide whether to
  apply it automatically. Not shipped — it will land when it has tests.

## Development

From a clone of this repository:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[store,dev]"

pytest
ruff check .
ruff format --check .
```

CI additionally installs the package with no extras and asserts that
`import seo_scorer` works with zero third-party packages present. If you add a
dependency to the scoring half, that job fails — which is the point.

## Licence

MIT. See [LICENSE](LICENSE).
