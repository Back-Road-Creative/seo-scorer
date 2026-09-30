"""Tests for SEOEventStore: appends, queries, indexes, and recovery."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from seo_scorer import store as store_module
from seo_scorer.events import EventType, SEOEvent
from seo_scorer.store import (
    _LOCK_MODE,
    LOCK_MODE,
    SEOEventStore,
    _group_writable_filelock,
    group_writable_filelock,
)

SITE = "example_site"


def _event(
    content_id: str = "content_001",
    site_id: str = SITE,
    event_id: str | None = None,
    event_type: EventType = EventType.METADATA_GENERATED,
    timestamp: str | None = None,
    data: dict | None = None,
) -> SEOEvent:
    return SEOEvent(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        site_id=site_id,
        content_id=content_id,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        data=data if data is not None else {"title": f"Test {content_id}"},
    )


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


@pytest.fixture
def store(tmp_path):
    return SEOEventStore(tmp_path / "store")


class TestInitialisation:
    def test_creates_the_directory_and_its_files(self, tmp_path):
        store = SEOEventStore(tmp_path / "nested" / "store")

        assert store.storage_path.exists()
        assert store.events_file.exists()
        assert store.index_file.exists()
        assert store.lock_file.exists()

    def test_accepts_a_string_path(self, tmp_path):
        store = SEOEventStore(str(tmp_path / "store"))

        assert isinstance(store.storage_path, Path)
        assert store.storage_path.exists()

    def test_a_fresh_store_has_empty_indexes(self, store):
        assert store.indexes == {
            "by_site": {},
            "by_type": {},
            "by_date": {},
            "by_content": {},
        }


class TestAppend:
    def test_appends_one_event(self, store):
        event_id = store.append_event(_event(event_id="evt_001"))

        assert event_id == "evt_001"
        assert len(store.events_file.read_text().splitlines()) == 1

    def test_appends_many_events(self, store):
        for i in range(5):
            store.append_event(_event(f"content_{i:03d}"))

        assert len(store.events_file.read_text().splitlines()) == 5

    def test_events_survive_a_new_store_instance(self, tmp_path):
        first = SEOEventStore(tmp_path / "store")
        first.append_event(
            _event(event_id="evt_persistent", data={"test": "persistence"})
        )

        second = SEOEventStore(tmp_path / "store")
        results = second.query_by_site(SITE)

        assert len(results) == 1
        assert results[0].event_id == "evt_persistent"
        assert results[0].data["test"] == "persistence"


class TestUpsert:
    def test_appends_when_the_id_is_new(self, store):
        store.append_event(_event(event_id="evt_001"))

        store.upsert_event(_event(event_id="evt_002"))

        assert len(store.query_by_site(SITE)) == 2

    def test_replaces_in_place_when_the_id_exists(self, store):
        store.append_event(_event(event_id="evt_001", data={"title": "before"}))
        store.append_event(_event(event_id="evt_002"))

        store.upsert_event(_event(event_id="evt_001", data={"title": "after"}))

        events = store.query_by_site(SITE)
        assert len(events) == 2
        by_id = {e.event_id: e for e in events}
        assert by_id["evt_001"].data == {"title": "after"}

    def test_keeps_the_original_line_order(self, store):
        for i in range(3):
            store.append_event(_event(event_id=f"evt_{i}"))

        store.upsert_event(_event(event_id="evt_1", data={"title": "after"}))

        assert [e.event_id for e in store.query_by_site(SITE)] == [
            "evt_0",
            "evt_1",
            "evt_2",
        ]

    def test_rebuilds_the_indexes(self, store):
        store.append_event(_event(event_id="evt_001", content_id="video_1"))

        store.upsert_event(_event(event_id="evt_001", content_id="video_1"))

        assert store.indexes["by_content"]["video_1"] == ["evt_001"]

    def test_preserves_corrupted_lines(self, store):
        store.append_event(_event(event_id="evt_001"))
        with open(store.events_file, "a") as f:
            f.write("THIS IS NOT VALID JSON{{{\n")

        store.upsert_event(_event(event_id="evt_002"))

        assert "THIS IS NOT VALID JSON{{{" in store.events_file.read_text()


class TestQuery:
    def test_filters_by_site(self, store):
        for i in range(3):
            store.append_event(_event(f"content_{i}", site_id="site_a"))
        for i in range(2):
            store.append_event(_event(f"content_{i}", site_id="site_b"))

        assert len(store.query_by_site("site_a")) == 3
        assert len(store.query_by_site("site_b")) == 2

    def test_filters_by_event_type(self, store):
        store.append_event(_event(event_type=EventType.METADATA_GENERATED))
        store.append_event(_event(event_type=EventType.VALIDATION_FAILED))
        store.append_event(_event(event_type=EventType.AUTO_FIX_APPLIED))

        results = store.query_by_site(SITE, event_type=EventType.AUTO_FIX_APPLIED)

        assert len(results) == 1
        assert results[0].event_type == EventType.AUTO_FIX_APPLIED

    def test_filters_by_date_range(self, store):
        for day in ("15", "16", "17"):
            store.append_event(
                _event(
                    event_id=f"evt_{day}",
                    timestamp=f"2026-01-{day}T10:00:00.000000+00:00",
                )
            )

        results = store.query_by_site(
            SITE,
            start_date="2026-01-16T00:00:00",
            end_date="2026-01-16T23:59:59",
        )

        assert [e.event_id for e in results] == ["evt_16"]

    def test_applies_a_limit(self, store):
        for i in range(10):
            store.append_event(_event(f"content_{i:03d}"))

        assert len(store.query_by_site(SITE, limit=5)) == 5

    def test_an_unknown_site_returns_nothing(self, store):
        store.append_event(_event())

        assert store.query_by_site("nonexistent_site") == []

    def test_an_empty_store_returns_nothing(self, store):
        assert store.query_by_site(SITE) == []

    def test_get_by_content_id(self, store):
        for i in range(3):
            store.append_event(_event("article_123", event_id=f"evt_{i}"))
        store.append_event(_event("article_456"))

        results = store.get_by_content_id(SITE, "article_123")

        assert len(results) == 3
        assert all(e.content_id == "article_123" for e in results)

    def test_get_by_content_id_is_scoped_to_the_site(self, store):
        store.append_event(_event("article_123", site_id="site_a"))
        store.append_event(_event("article_123", site_id="site_b"))

        assert len(store.get_by_content_id("site_a", "article_123")) == 1


class TestCorruptionHandling:
    def test_a_corrupted_line_costs_only_that_line(self, store):
        store.append_event(_event(event_id="evt_001"))
        with open(store.events_file, "a") as f:
            f.write('{"corrupted": "data without checksum"}\n')
        store.append_event(_event(event_id="evt_002"))

        results = store.query_by_site(SITE)

        assert [e.event_id for e in results] == ["evt_001", "evt_002"]

    def test_a_corrupted_line_is_logged_not_printed(self, store, caplog):
        store.append_event(_event(event_id="evt_001"))
        with open(store.events_file, "a") as f:
            f.write('{"corrupted": "data without checksum"}\n')

        with caplog.at_level("WARNING", logger="seo_scorer.store"):
            store.query_by_site(SITE)

        assert any("corrupted event line" in r.message.lower() for r in caplog.records)

    def test_get_by_content_id_skips_corrupted_lines(self, store):
        store.append_event(_event("article_123", event_id="evt_001"))
        with open(store.events_file, "a") as f:
            f.write("THIS IS NOT VALID JSON{{{\n")

        assert len(store.get_by_content_id(SITE, "article_123")) == 1


class TestIndexes:
    def test_an_append_updates_every_index(self, store):
        store.append_event(
            _event(
                "content_001",
                event_id="evt_001",
                timestamp="2026-01-16T10:00:00.000000+00:00",
            )
        )

        assert store.indexes["by_site"][SITE] == ["evt_001"]
        assert store.indexes["by_type"]["metadata_generated"] == ["evt_001"]
        assert store.indexes["by_date"]["2026-01-16"] == ["evt_001"]
        assert store.indexes["by_content"]["content_001"] == ["evt_001"]

    def test_a_corrupted_index_is_rebuilt_from_the_log(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")
        for i in range(3):
            store.append_event(_event(f"video_{i}"))
        assert len(store.indexes["by_site"][SITE]) == 3

        store.index_file.write_text('{"by_site": {"example_site": [CORRUPTED')

        rebuilt = SEOEventStore(tmp_path / "store")

        assert len(rebuilt.indexes["by_site"][SITE]) == 3

    def test_a_rebuild_skips_corrupted_log_lines(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")
        for i in range(3):
            store.append_event(_event(f"video_{i}"))

        lines = store.events_file.read_text().strip().split("\n")
        lines.insert(1, "THIS IS NOT VALID JSON{{{")
        store.events_file.write_text("\n".join(lines) + "\n")
        store.index_file.write_text("BROKEN")

        rebuilt = SEOEventStore(tmp_path / "store")

        assert len(rebuilt.indexes["by_site"][SITE]) == 3

    def test_a_rebuild_repopulates_every_index(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")
        store.append_event(_event("video_1"))
        store.index_file.write_text("BROKEN")

        rebuilt = SEOEventStore(tmp_path / "store")

        assert SITE in rebuilt.indexes["by_site"]
        assert EventType.METADATA_GENERATED.value in rebuilt.indexes["by_type"]
        assert "video_1" in rebuilt.indexes["by_content"]
        assert len(rebuilt.indexes["by_date"]) == 1

    def test_queries_still_work_after_a_rebuild(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")
        for i in range(5):
            store.append_event(_event(f"video_{i}"))
        store.index_file.write_text("BROKEN")

        rebuilt = SEOEventStore(tmp_path / "store")

        assert len(rebuilt.query_by_site(SITE)) == 5

    def test_a_corrupted_index_over_an_empty_log_rebuilds_to_empty(self, tmp_path):
        SEOEventStore(tmp_path / "store")
        (tmp_path / "store" / "index.json").write_text("NOT JSON")

        rebuilt = SEOEventStore(tmp_path / "store")

        assert rebuilt.indexes["by_site"] == {}

    def test_deleting_the_index_is_safe(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")
        store.append_event(_event("video_1"))

        store.index_file.unlink()
        reopened = SEOEventStore(tmp_path / "store")

        # The index is a cache: it is rebuilt from the log, not lost.
        assert reopened.indexes["by_content"]["video_1"]
        assert len(reopened.query_by_site(SITE)) == 1
        assert reopened.index_file.exists()


class TestFilePermissions:
    """Group-writable files let several accounts share one store directory."""

    def test_the_lock_mode_is_group_writable(self):
        assert LOCK_MODE == 0o664
        assert _LOCK_MODE == LOCK_MODE

    def test_the_helper_is_exported_under_both_names(self):
        assert _group_writable_filelock is group_writable_filelock

    def test_the_helper_acquires_with_the_group_writable_mode(self, tmp_path):
        lock_path = tmp_path / "x.lock"

        with group_writable_filelock(lock_path):
            assert lock_path.exists()
            assert _mode(lock_path) == 0o664, f"got {oct(_mode(lock_path))}"

    def test_the_mode_survives_the_locks_own_cleanup(self, tmp_path):
        # filelock removes the file on exit and recreates it on the next
        # acquire; both acquisitions must land on 0o664.
        lock_path = tmp_path / "y.lock"

        with group_writable_filelock(lock_path):
            assert _mode(lock_path) == 0o664
        with group_writable_filelock(lock_path):
            assert _mode(lock_path) == 0o664

    def test_the_log_file_is_group_writable_after_init(self, tmp_path):
        store = SEOEventStore(tmp_path / "store")

        assert _mode(store.events_file) == 0o664

    def test_reopening_converges_a_narrowed_mode_back(self, tmp_path):
        # Simulate a 0o644 left behind by an earlier run: reopening must
        # widen it again so the other accounts can still write.
        store = SEOEventStore(tmp_path / "store")
        store.events_file.chmod(0o644)
        assert _mode(store.events_file) == 0o644

        SEOEventStore(tmp_path / "store")

        assert _mode(store.events_file) == 0o664


class TestHistoryCompleteness:
    """Reads report what they could not read, instead of skipping silently."""

    def _filled(self, tmp_path, n=3):
        store = SEOEventStore(tmp_path / "store")
        for i in range(n):
            store.append_event(_event(f"video_{i}", event_id=f"evt_{i}"))
        return store

    def test_a_clean_log_is_complete(self, tmp_path):
        store = self._filled(tmp_path)

        result = store.query_by_site_with_history(SITE)

        assert [e.event_id for e in result.events] == ["evt_0", "evt_1", "evt_2"]
        assert result.history.status == "complete"
        assert result.history.is_complete
        assert result.history.lines_read == 3
        assert result.history.events_valid == 3
        assert result.history.lines_invalid == 0

    def test_an_empty_log_is_complete(self, store):
        history = store.scan_history()

        assert history.is_complete
        assert history.lines_read == 0

    def test_a_truncated_tail_is_a_partial_tail_not_damage(self, tmp_path):
        store = self._filled(tmp_path)
        with open(store.events_file, "a") as f:
            f.write('{"event_id": "evt_torn", "event_ty')  # no newline

        result = store.query_by_site_with_history(SITE, tail_recheck_delay=0)

        assert len(result.events) == 3
        assert result.history.status == "partial_tail"
        assert not result.history.is_complete
        assert result.history.partial_tail_line == 4
        assert result.history.damaged_line_numbers == ()
        assert result.history.lines_invalid == 1

    def test_a_damaged_middle_line_is_damage(self, tmp_path):
        store = self._filled(tmp_path)
        lines = store.events_file.read_text().splitlines()
        lines.insert(1, "NOT JSON{{{")
        store.events_file.write_text("\n".join(lines) + "\n")

        result = store.query_by_site_with_history(SITE)

        assert len(result.events) == 3
        assert result.history.status == "damaged"
        assert not result.history.is_complete
        assert result.history.damaged_line_numbers == (2,)
        assert result.history.partial_tail_line is None

    def test_a_newline_terminated_bad_last_line_is_damage(self, tmp_path):
        store = self._filled(tmp_path)
        with open(store.events_file, "a") as f:
            f.write("NOT JSON{{{\n")

        history = store.scan_history()

        assert history.status == "damaged"
        assert history.damaged_line_numbers == (4,)

    def test_damage_wins_over_a_partial_tail(self, tmp_path):
        store = self._filled(tmp_path)
        lines = store.events_file.read_text().splitlines()
        lines.insert(0, "NOT JSON{{{")
        store.events_file.write_text("\n".join(lines) + "\n" + '{"event_id": "x')

        history = store.scan_history(tail_recheck_delay=0)

        assert history.status == "damaged"
        assert history.damaged_line_numbers == (1,)
        assert history.partial_tail_line == 5

    def test_a_tail_that_completes_on_recheck_is_complete(self, tmp_path, monkeypatch):
        store = self._filled(tmp_path, n=2)
        pending = _event("video_2", event_id="evt_2").to_jsonl()
        half = len(pending) // 2
        with open(store.events_file, "a") as f:
            f.write(pending[:half])

        def finish_the_write(_seconds):
            with open(store.events_file, "a") as f:
                f.write(pending[half:] + "\n")

        monkeypatch.setattr(store_module.time, "sleep", finish_the_write)

        result = store.query_by_site_with_history(SITE, tail_recheck_delay=0.01)

        assert [e.event_id for e in result.events] == ["evt_0", "evt_1", "evt_2"]
        assert result.history.is_complete
        assert result.history.lines_invalid == 0

    def test_a_tail_that_stays_torn_is_reported_after_one_recheck(
        self, tmp_path, monkeypatch
    ):
        store = self._filled(tmp_path, n=1)
        with open(store.events_file, "a") as f:
            f.write('{"event_id": "evt_torn"')
        sleeps = []
        monkeypatch.setattr(store_module.time, "sleep", sleeps.append)

        history = store.scan_history(tail_recheck_delay=0.01)

        assert history.status == "partial_tail"
        assert sleeps == [0.01]

    def test_the_default_methods_still_return_plain_lists(self, tmp_path):
        store = self._filled(tmp_path)

        assert isinstance(store.query_by_site(SITE), list)
        assert isinstance(store.get_by_content_id(SITE, "video_0"), list)

    def test_get_by_content_id_reports_history_too(self, tmp_path):
        store = self._filled(tmp_path)
        with open(store.events_file, "a") as f:
            f.write("NOT JSON{{{\n")

        result = store.get_by_content_id_with_history(SITE, "video_1")

        assert [e.event_id for e in result.events] == ["evt_1"]
        assert result.history.status == "damaged"
        assert result.history.lines_read == 4

    def test_a_limit_stop_is_not_complete(self, tmp_path):
        store = self._filled(tmp_path)

        result = store.query_by_site_with_history(SITE, limit=1)

        assert len(result.events) == 1
        assert not result.history.exhausted
        assert not result.history.is_complete

    def test_the_log_is_never_rewritten_by_a_read(self, tmp_path):
        store = self._filled(tmp_path)
        with open(store.events_file, "a") as f:
            f.write('{"torn"')
        before = store.events_file.read_bytes()

        store.scan_history(tail_recheck_delay=0)

        assert store.events_file.read_bytes() == before
