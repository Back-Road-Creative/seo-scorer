"""Append-only JSONL event store with file locking and index recovery.

This is the one module in the package with a third-party dependency
(``filelock``). Install it with the ``store`` extra::

    pip install "seo-scorer[store]"

Layout on disk, under the directory you hand to :class:`SEOEventStore`::

    events.jsonl    # the log — one JSON event per line, append-only
    index.json      # site/type/date/content indexes, rebuildable
    .lock           # advisory lock guarding writes

``events.jsonl`` is the source of truth. ``index.json`` is a cache: if
it is missing or unreadable it is rebuilt by scanning the log, so
deleting it is always safe.
"""

import contextlib
import json
import logging
from pathlib import Path

try:
    from filelock import FileLock
except ImportError as exc:
    raise ImportError(
        "seo_scorer.store requires the 'filelock' package. "
        'Install it with: pip install "seo-scorer[store]"'
    ) from exc

from .events import EventType, SEOEvent

logger = logging.getLogger(__name__)

#: Mode applied to the lock and log files: 0o664, group-writable.
#:
#: ``filelock.FileLock`` defaults to 0o644 (writable by the owner only).
#: When two accounts that share a group take turns running the same job
#: against the same store directory, whichever account did not create
#: the lock file hits ``PermissionError`` on acquisition even though the
#: group grants access. Widening the mode to 0o664 makes the store
#: usable from any account in the owning group.
#:
#: Set a stricter mode here if your store is only ever written by one
#: account, or place the store on a directory with a restrictive ACL.
LOCK_MODE = 0o664

#: Alias for the previous constant name.
_LOCK_MODE = LOCK_MODE


def group_writable_filelock(lock_path: Path) -> FileLock:
    """Build a :class:`filelock.FileLock` with :data:`LOCK_MODE`.

    Wrapped in a function so the mode is set in exactly one place. Use
    it as a context manager, exactly like ``FileLock``.
    """
    return FileLock(str(lock_path), mode=LOCK_MODE)


#: Alias for the previous helper name.
_group_writable_filelock = group_writable_filelock


class SEOEventStore:
    """Append-only event store, partitioned by site.

    Writes take an advisory file lock, so several processes can append
    to one store safely. Reads are lock-free and stream the log line by
    line, so a corrupted line costs you that line and nothing else.
    """

    def __init__(self, storage_path: Path):
        """Open (and create, if needed) a store directory.

        Args:
            storage_path: Directory that holds the log, index, and lock.
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.events_file = self.storage_path / "events.jsonl"
        self.index_file = self.storage_path / "index.json"
        self.lock_file = self.storage_path / ".lock"

        # Create the data and lock files group-writable. Path.touch()
        # honours the process umask (commonly 022, giving 0o644), so the
        # chmod converges the mode back to LOCK_MODE on every init —
        # whichever account creates a file first, the others can still
        # write. The lock file is pre-created so callers can see it;
        # filelock recreates it under LOCK_MODE on each acquire anyway.
        for path in (self.events_file, self.lock_file):
            path.touch(exist_ok=True)
            with contextlib.suppress(OSError, PermissionError):
                path.chmod(LOCK_MODE)

        self._load_indexes()

    # ---------------------------------------------------------------- #
    # Writes
    # ---------------------------------------------------------------- #

    def append_event(self, event: SEOEvent) -> str:
        """Append one event to the log.

        Args:
            event: The event to append.

        Returns:
            The event's ``event_id``.
        """
        with group_writable_filelock(self.lock_file):
            with open(self.events_file, "a") as f:
                f.write(event.to_jsonl() + "\n")

            self._update_indexes(event)

        return event.event_id

    def upsert_event(self, event: SEOEvent) -> str:
        """Insert an event, or replace the existing one with the same id.

        This rewrites the whole log, so it costs O(n) in the number of
        stored events — reach for :meth:`append_event` unless you
        genuinely need last-write-wins on an id. Corrupted lines are
        copied through untouched rather than dropped.

        Args:
            event: The event to insert or replace.

        Returns:
            The event's ``event_id``.
        """
        with group_writable_filelock(self.lock_file):
            lines: list[str] = []
            replaced = False
            if self.events_file.exists():
                with open(self.events_file) as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            existing = SEOEvent.from_jsonl(stripped)
                            if existing.event_id == event.event_id:
                                lines.append(event.to_jsonl())
                                replaced = True
                            else:
                                lines.append(stripped)
                        except (ValueError, json.JSONDecodeError, KeyError):
                            lines.append(stripped)

            if not replaced:
                lines.append(event.to_jsonl())

            with open(self.events_file, "w") as f:
                for line in lines:
                    f.write(line + "\n")

            # The log was rewritten, so the indexes no longer describe
            # it. Rebuilding is the simplest thing that is certainly
            # correct.
            self.indexes = self._empty_indexes()
            self._rebuild_indexes()

        return event.event_id

    # ---------------------------------------------------------------- #
    # Reads
    # ---------------------------------------------------------------- #

    def query_by_site(
        self,
        site_id: str,
        event_type: EventType | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[SEOEvent]:
        """Return events for one site, oldest first.

        Every query is scoped to a site, so one site's events can never
        leak into another's results. Date comparison is a string
        comparison, which is correct for ISO 8601 timestamps in a single
        timezone; normalise to UTC before storing if you mix offsets.

        Args:
            site_id: Site identifier (required).
            event_type: Keep only this event type.
            start_date: Keep events at or after this ISO timestamp.
            end_date: Keep events at or before this ISO timestamp.
            limit: Stop after this many matches.

        Returns:
            Matching events, in log order.
        """
        events: list[SEOEvent] = []

        with open(self.events_file) as f:
            for line in f:
                try:
                    event = SEOEvent.from_jsonl(line.strip())

                    if event.site_id != site_id:
                        continue

                    if event_type and event.event_type != event_type:
                        continue

                    if start_date and event.timestamp < start_date:
                        continue
                    if end_date and event.timestamp > end_date:
                        continue

                    events.append(event)

                    if limit and len(events) >= limit:
                        break

                except (ValueError, json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping corrupted event line: %s", e)
                    continue

        return events

    def get_by_content_id(self, site_id: str, content_id: str) -> list[SEOEvent]:
        """Return every event recorded for one piece of content.

        Args:
            site_id: Site identifier.
            content_id: Content identifier.

        Returns:
            The content's events, in log order.
        """
        events: list[SEOEvent] = []

        with open(self.events_file) as f:
            for line in f:
                try:
                    event = SEOEvent.from_jsonl(line.strip())

                    if event.site_id == site_id and event.content_id == content_id:
                        events.append(event)

                except (ValueError, json.JSONDecodeError, KeyError):
                    continue

        return events

    # ---------------------------------------------------------------- #
    # Indexes
    # ---------------------------------------------------------------- #

    def _load_indexes(self) -> None:
        """Load the index file, rebuilding it from the log if unusable."""
        if self.index_file.exists():
            try:
                with open(self.index_file) as f:
                    self.indexes = json.load(f)
                return
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Index file corrupted (%s), rebuilding from events.jsonl", e
                )

        # No index, or an unreadable one: rebuild by scanning the log.
        # On a brand-new store the log is empty, so this is the same as
        # starting blank — which is why deleting index.json is safe.
        self.indexes = self._empty_indexes()
        self._rebuild_indexes()

    @staticmethod
    def _empty_indexes() -> dict[str, dict[str, list[str]]]:
        return {
            "by_site": {},
            "by_type": {},
            "by_date": {},
            "by_content": {},
        }

    def _rebuild_indexes(self) -> None:
        """Rebuild every index by scanning the log. Corrupted lines are skipped."""
        rebuilt = 0
        skipped = 0
        with open(self.events_file) as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = SEOEvent.from_jsonl(stripped)
                    self._update_indexes_in_memory(event)
                    rebuilt += 1
                except (ValueError, json.JSONDecodeError, KeyError):
                    skipped += 1
                    continue
        self._save_indexes()
        logger.info(
            "Index rebuilt: %d events indexed, %d corrupted lines skipped",
            rebuilt,
            skipped,
        )

    def _update_indexes_in_memory(self, event: SEOEvent) -> None:
        """Add one event to the in-memory indexes without persisting."""
        self.indexes["by_site"].setdefault(event.site_id, []).append(event.event_id)
        self.indexes["by_type"].setdefault(event.event_type.value, []).append(
            event.event_id
        )
        # Date key is the YYYY-MM-DD prefix of the ISO timestamp.
        self.indexes["by_date"].setdefault(event.timestamp[:10], []).append(
            event.event_id
        )
        self.indexes["by_content"].setdefault(event.content_id, []).append(
            event.event_id
        )

    def _update_indexes(self, event: SEOEvent) -> None:
        """Add one event to the indexes and persist them."""
        self._update_indexes_in_memory(event)
        self._save_indexes()

    def _save_indexes(self) -> None:
        """Write the indexes to disk."""
        with open(self.index_file, "w") as f:
            json.dump(self.indexes, f, indent=2)


__all__ = [
    "LOCK_MODE",
    "SEOEventStore",
    "group_writable_filelock",
]
