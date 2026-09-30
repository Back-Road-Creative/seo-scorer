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
import time
from collections.abc import Callable
from dataclasses import dataclass
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


#: How long a read waits before re-reading a log whose last line looks
#: half-written. A writer appends one line at a time, so a torn tail is
#: normally gone within milliseconds.
TAIL_RECHECK_DELAY = 0.05

_BAD_LINE_ERRORS = (ValueError, json.JSONDecodeError, KeyError)


@dataclass(frozen=True)
class HistoryCompleteness:
    """What one read of the log could and could not use.

    ``status`` is one of:

    * ``"complete"`` -- every non-blank line was a valid event.
    * ``"partial_tail"`` -- the only bad line is the last one and it has
      no trailing newline: a writer is mid-append, or died mid-append.
      The read re-checked once before reporting this. The log is
      probably fine, but the history is not known to be complete.
    * ``"damaged"`` -- at least one bad line is not a torn tail, so
      events were lost to corruption that will not heal on its own.

    Only ``"complete"`` with ``exhausted`` true is safe to label
    complete; see :attr:`is_complete`.

    Attributes:
        lines_read: Non-blank lines examined.
        events_valid: Lines that parsed into an event (before filters).
        lines_invalid: Lines skipped because they did not parse or failed
            their checksum.
        invalid_line_numbers: 1-based line numbers of the skipped lines.
        partial_tail_line: 1-based number of the torn last line, if any.
        exhausted: False when a ``limit`` stopped the read early, so
            lines after the stop were not examined.
    """

    lines_read: int = 0
    events_valid: int = 0
    lines_invalid: int = 0
    invalid_line_numbers: tuple[int, ...] = ()
    partial_tail_line: int | None = None
    exhausted: bool = True

    @property
    def damaged_line_numbers(self) -> tuple[int, ...]:
        """Skipped lines that are not the torn tail."""
        return tuple(
            n for n in self.invalid_line_numbers if n != self.partial_tail_line
        )

    @property
    def status(self) -> str:
        if self.damaged_line_numbers:
            return "damaged"
        if self.partial_tail_line is not None:
            return "partial_tail"
        return "complete"

    @property
    def is_complete(self) -> bool:
        """True only if the whole log was read and every line was valid."""
        return self.status == "complete" and self.exhausted


@dataclass(frozen=True)
class QueryResult:
    """Events from a query, with the completeness of the read behind them."""

    events: list[SEOEvent]
    history: HistoryCompleteness


class SEOEventStore:
    """Append-only event store, partitioned by site.

    Writes take an advisory file lock, so several processes can append
    to one store safely. Reads are lock-free and stream the log line by
    line, so a corrupted line costs you that line and nothing else. The
    plain query methods return just the events; the ``*_with_history``
    variants and :meth:`scan_history` also say how many lines were
    skipped and whether the history is complete.
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

        Corrupted lines are skipped and logged. Use
        :meth:`query_by_site_with_history` when you need to know whether
        any were.

        Args:
            site_id: Site identifier (required).
            event_type: Keep only this event type.
            start_date: Keep events at or after this ISO timestamp.
            end_date: Keep events at or before this ISO timestamp.
            limit: Stop after this many matches.

        Returns:
            Matching events, in log order.
        """
        return self.query_by_site_with_history(
            site_id, event_type, start_date, end_date, limit
        ).events

    def query_by_site_with_history(
        self,
        site_id: str,
        event_type: EventType | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        tail_recheck_delay: float = TAIL_RECHECK_DELAY,
    ) -> QueryResult:
        """Like :meth:`query_by_site`, plus a :class:`HistoryCompleteness`.

        Args:
            site_id: Site identifier (required).
            event_type: Keep only this event type.
            start_date: Keep events at or after this ISO timestamp.
            end_date: Keep events at or before this ISO timestamp.
            limit: Stop after this many matches.
            tail_recheck_delay: Seconds to wait before re-reading once if
                the last line looks half-written.

        Returns:
            The matching events and how complete the read was.
        """

        def keep(event: SEOEvent) -> bool:
            if event.site_id != site_id:
                return False
            if event_type and event.event_type != event_type:
                return False
            if start_date and event.timestamp < start_date:
                return False
            return not (end_date and event.timestamp > end_date)

        return self._read_log(keep, limit, tail_recheck_delay)

    def get_by_content_id(self, site_id: str, content_id: str) -> list[SEOEvent]:
        """Return every event recorded for one piece of content.

        Args:
            site_id: Site identifier.
            content_id: Content identifier.

        Returns:
            The content's events, in log order.
        """
        return self.get_by_content_id_with_history(site_id, content_id).events

    def get_by_content_id_with_history(
        self,
        site_id: str,
        content_id: str,
        tail_recheck_delay: float = TAIL_RECHECK_DELAY,
    ) -> QueryResult:
        """Like :meth:`get_by_content_id`, plus a :class:`HistoryCompleteness`."""
        return self._read_log(
            lambda e: e.site_id == site_id and e.content_id == content_id,
            None,
            tail_recheck_delay,
        )

    def scan_history(
        self, tail_recheck_delay: float = TAIL_RECHECK_DELAY
    ) -> HistoryCompleteness:
        """Read the whole log and report its completeness.

        Never modifies the log. Use it before treating a set of events
        as the full record of a site.
        """
        return self._read_log(lambda e: False, None, tail_recheck_delay).history

    def _read_log(
        self,
        keep: Callable[[SEOEvent], bool],
        limit: int | None,
        tail_recheck_delay: float,
    ) -> QueryResult:
        """Stream the log, collecting events that pass ``keep``.

        Reads take no lock, so a concurrent append can leave the last
        line half-written. If the only trouble is such a tail, read once
        more after ``tail_recheck_delay`` before reporting it.
        """
        result, reasons = self._read_log_once(keep, limit)
        if result.history.partial_tail_line is not None:
            time.sleep(tail_recheck_delay)
            result, reasons = self._read_log_once(keep, limit)

        for line_number, reason in reasons:
            logger.warning("Skipping corrupted event line %d: %s", line_number, reason)
        return result

    def _read_log_once(
        self, keep: Callable[[SEOEvent], bool], limit: int | None
    ) -> tuple[QueryResult, list[tuple[int, Exception]]]:
        events: list[SEOEvent] = []
        reasons: list[tuple[int, Exception]] = []
        lines_read = 0
        events_valid = 0
        partial_tail_line: int | None = None
        exhausted = True

        with open(self.events_file) as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                lines_read += 1
                try:
                    event = SEOEvent.from_jsonl(stripped)
                except _BAD_LINE_ERRORS as e:
                    reasons.append((line_number, e))
                    # Only the last line can lack its newline, and a
                    # writer that is still mid-append is the usual reason.
                    if not line.endswith("\n"):
                        partial_tail_line = line_number
                    continue

                events_valid += 1
                if keep(event):
                    events.append(event)
                    if limit and len(events) >= limit:
                        exhausted = False
                        break

        history = HistoryCompleteness(
            lines_read=lines_read,
            events_valid=events_valid,
            lines_invalid=len(reasons),
            invalid_line_numbers=tuple(n for n, _ in reasons),
            partial_tail_line=partial_tail_line,
            exhausted=exhausted,
        )
        return QueryResult(events, history), reasons

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
    "TAIL_RECHECK_DELAY",
    "HistoryCompleteness",
    "QueryResult",
    "SEOEventStore",
    "group_writable_filelock",
]
