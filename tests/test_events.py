"""Tests for SEOEvent serialisation and checksum validation."""

import json
import zlib

import pytest

from seo_scorer.events import EventType, SEOEvent


def _event(**overrides) -> SEOEvent:
    fields = {
        "event_id": "evt_001",
        "event_type": EventType.METADATA_GENERATED,
        "site_id": "test_site",
        "content_id": "content_001",
        "timestamp": "2026-01-16T12:00:00.000000+00:00",
        "data": {"title": "Test Title"},
    }
    fields.update(overrides)
    return SEOEvent(**fields)


def _checksummed(payload: dict) -> str:
    """Encode a payload the way the store does, checksum included."""
    json_str = json.dumps(payload, separators=(",", ":"))
    return json.dumps(
        {**payload, "checksum": zlib.crc32(json_str.encode("utf-8"))},
        separators=(",", ":"),
    )


class TestEventType:
    def test_values(self):
        assert EventType.METADATA_GENERATED.value == "metadata_generated"
        assert EventType.METADATA_UPDATED.value == "metadata_updated"
        assert EventType.VALIDATION_FAILED.value == "validation_failed"
        assert EventType.VALIDATION_PASSED.value == "validation_passed"
        assert EventType.AUTO_FIX_APPLIED.value == "auto_fix_applied"
        assert EventType.PERFORMANCE_UPDATED.value == "performance_updated"
        assert EventType.METADATA_PUBLISHED.value == "metadata_published"

    def test_values_are_unique(self):
        values = [member.value for member in EventType]
        assert len(values) == len(set(values))


class TestConstruction:
    def test_required_fields(self):
        event = _event(data={"title": "Test Title", "quality_score": 0.85})

        assert event.event_id == "evt_001"
        assert event.event_type == EventType.METADATA_GENERATED
        assert event.site_id == "test_site"
        assert event.data["quality_score"] == 0.85

    def test_metadata_defaults_to_none(self):
        assert _event().metadata is None

    def test_metadata_can_carry_system_fields(self):
        event = _event(metadata={"actor": "automated", "version": "1.0"})

        assert event.metadata["actor"] == "automated"


class TestSerialisation:
    def test_to_jsonl_is_one_line_of_json(self):
        line = _event(metadata={"actor": "system"}).to_jsonl()

        assert "\n" not in line
        data = json.loads(line)
        assert data["event_id"] == "evt_001"
        assert data["event_type"] == "metadata_generated"
        assert data["data"] == {"title": "Test Title"}
        assert data["metadata"] == {"actor": "system"}
        assert isinstance(data["checksum"], int)

    def test_checksum_covers_every_field_but_itself(self):
        data = json.loads(_event().to_jsonl())
        stored_checksum = data.pop("checksum")

        recomputed = zlib.crc32(json.dumps(data, separators=(",", ":")).encode("utf-8"))

        assert stored_checksum == recomputed

    def test_absent_metadata_serialises_as_an_empty_dict(self):
        assert json.loads(_event().to_jsonl())["metadata"] == {}

    def test_roundtrip_preserves_every_field(self):
        original = _event(
            event_id="evt_123",
            event_type=EventType.PERFORMANCE_UPDATED,
            site_id="my_site",
            content_id="post_456",
            data={"views": 1250, "clicks": 87, "impressions": 5000, "ctr": 0.0174},
            metadata={"source": "analytics_import", "version": "1.0"},
        )

        restored = SEOEvent.from_jsonl(original.to_jsonl())

        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.site_id == original.site_id
        assert restored.content_id == original.content_id
        assert restored.timestamp == original.timestamp
        assert restored.data == original.data
        assert restored.metadata == original.metadata

    def test_roundtrip_preserves_nested_data(self):
        payload = {
            "metadata": {
                "title": "Test Title",
                "tags": ["ai", "seo", "testing"],
                "quality_metrics": {"score": 0.87, "readability": 72.3},
            },
            "fixes_applied": [{"fix_id": "title_truncate", "confidence": 0.95}],
        }

        restored = SEOEvent.from_jsonl(_event(data=payload).to_jsonl())

        assert restored.data == payload

    def test_event_type_survives_the_roundtrip_as_an_enum(self):
        restored = SEOEvent.from_jsonl(
            _event(event_type=EventType.AUTO_FIX_APPLIED).to_jsonl()
        )

        assert restored.event_type is EventType.AUTO_FIX_APPLIED


class TestChecksumValidation:
    def test_tampered_data_is_rejected(self):
        data = json.loads(_event().to_jsonl())
        data["data"]["title"] = "Corrupted"

        with pytest.raises(ValueError, match="Checksum mismatch"):
            SEOEvent.from_jsonl(json.dumps(data))

    def test_a_line_with_no_checksum_is_accepted(self):
        line = json.dumps(
            {
                "event_id": "evt_001",
                "event_type": "metadata_generated",
                "site_id": "test_site",
                "content_id": "content_001",
                "timestamp": "2026-01-16T12:00:00.000000+00:00",
                "data": {},
                "metadata": {},
            }
        )

        assert SEOEvent.from_jsonl(line).event_id == "evt_001"

    def test_a_line_with_no_metadata_key_defaults_to_an_empty_dict(self):
        line = _checksummed(
            {
                "event_id": "evt_001",
                "event_type": "metadata_generated",
                "site_id": "test_site",
                "content_id": "content_001",
                "timestamp": "2026-01-16T12:00:00.000000+00:00",
                "data": {},
            }
        )

        assert SEOEvent.from_jsonl(line).metadata == {}

    def test_an_unknown_event_type_is_rejected(self):
        line = _checksummed(
            {
                "event_id": "evt_001",
                "event_type": "not_a_real_event_type",
                "site_id": "test_site",
                "content_id": "content_001",
                "timestamp": "2026-01-16T12:00:00.000000+00:00",
                "data": {},
                "metadata": {},
            }
        )

        with pytest.raises(ValueError):
            SEOEvent.from_jsonl(line)

    def test_malformed_json_is_rejected(self):
        with pytest.raises(json.JSONDecodeError):
            SEOEvent.from_jsonl("THIS IS NOT VALID JSON{{{")
