"""Event definitions for the append-only SEO event store.

Events carry a CRC32 checksum so a truncated or hand-edited line is
detected on read rather than silently deserialising into wrong data.
"""

import json
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(Enum):
    """Event types recorded by the store."""

    METADATA_GENERATED = "metadata_generated"
    METADATA_UPDATED = "metadata_updated"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PASSED = "validation_passed"
    AUTO_FIX_APPLIED = "auto_fix_applied"
    PERFORMANCE_UPDATED = "performance_updated"
    COMMUNITY_UPDATED = "community_updated"
    DEMOGRAPHICS_UPDATED = "demographics_updated"
    METADATA_PUBLISHED = "metadata_published"


@dataclass
class SEOEvent:
    """A single state change in the SEO system.

    Events are append-only and never modified in place, which is what
    makes a complete audit trail, time-travel queries, and corruption
    detection possible.
    """

    event_id: str  # Unique event identifier (a UUID works well)
    event_type: EventType  # Type of event
    site_id: str  # Partition key for multi-site isolation
    content_id: str  # Content reference
    timestamp: str  # ISO 8601 UTC timestamp
    data: dict[str, Any]  # Event payload
    metadata: dict[str, Any] | None = None  # System metadata (version, actor…)
    checksum: int | None = None  # CRC32, computed on serialisation

    def to_jsonl(self) -> str:
        """Serialise to one JSONL line, appending a CRC32 checksum.

        The checksum covers the compact JSON encoding of every field
        *except* the checksum itself, so it can be recomputed on read.
        """
        data: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "site_id": self.site_id,
            "content_id": self.content_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata if self.metadata is not None else {},
        }

        json_str = json.dumps(data, separators=(",", ":"))
        data["checksum"] = zlib.crc32(json_str.encode("utf-8"))

        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_jsonl(cls, line: str) -> "SEOEvent":
        """Deserialise one JSONL line, validating the checksum.

        A line with no ``checksum`` field is accepted as-is, so logs
        written before checksums existed still load.

        Raises:
            ValueError: If the stored checksum does not match the data.
        """
        data = json.loads(line)

        stored_checksum = data.pop("checksum", None)

        if stored_checksum is not None:
            json_str = json.dumps(data, separators=(",", ":"))
            computed_checksum = zlib.crc32(json_str.encode("utf-8"))

            if computed_checksum != stored_checksum:
                raise ValueError(
                    f"Checksum mismatch: computed={computed_checksum}, "
                    f"stored={stored_checksum}. Data may be corrupted."
                )

        data["event_type"] = EventType(data["event_type"])

        if "metadata" not in data:
            data["metadata"] = {}

        return cls(**data)
