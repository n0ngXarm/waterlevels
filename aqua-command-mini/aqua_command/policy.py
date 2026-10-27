"""File-snapshot interpretation, never live status. All gates precede ON/OFF."""
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from .importer import RawRecord

STAMP_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$')


@dataclass(frozen=True)
class Evaluated:
    raw: RawRecord
    tag: str
    timestamp: datetime | None
    age_seconds: float | None
    state: str
    reasons: tuple[str, ...]
    decision: str


def _timestamp(text, offset):
    value = text.strip()
    if not value:
        return None, 'TIMESTAMP_MISSING'
    if len(value) > 40 or not STAMP_PATTERN.fullmatch(value):
        return None, 'TIMESTAMP_INVALID_ISO8601_REQUIRED'
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            if offset is None:
                return None, 'TIMEZONE_REQUIRED'
            sign = 1 if offset[0] == '+' else -1
            delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6])) * sign
            stamp = stamp.replace(tzinfo=timezone(delta))
        if abs(stamp.utcoffset()) > timedelta(hours=14):
            return None, 'TIMESTAMP_OFFSET_INVALID'
        return stamp.astimezone(timezone.utc), ''
    except (ValueError, OverflowError):
        return None, 'TIMESTAMP_INVALID_ISO8601_REQUIRED'


def evaluate(imported, profile, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('NOW_MUST_HAVE_TIMEZONE')
    now = now.astimezone(timezone.utc)
    if imported.kind != 'runtime_values':
        return []
    result = []
    for raw in imported.records:
        tag = raw.tag.strip()
        rule = profile.tags.get(tag)
        reasons = [raw.error] if raw.error else []
        if rule is None:
            reasons.append('TAG_NOT_ALLOWED')
        stamp, error = _timestamp(raw.timestamp_raw, profile.source_utc_offset)
        if error:
            reasons.append(error)
        age = (now - stamp).total_seconds() if stamp else None
        if age is not None:
            if age > profile.freshness_seconds:
                reasons.append('STALE')
            if age < -profile.future_tolerance_seconds:
                reasons.append('FUTURE_TIMESTAMP')
        if rule is not None:
            if raw.value_raw.strip() not in rule['mapping']:
                reasons.append('VALUE_NOT_MAPPED')
            if raw.quality_raw.strip().casefold() not in {q.casefold() for q in rule['good_quality']}:
                reasons.append('QUALITY_NOT_ACCEPTED')
        state = 'ERROR' if raw.error else 'UNKNOWN'
        if not reasons:
            state = rule['mapping'][raw.value_raw.strip()]
        result.append(Evaluated(raw, tag, stamp, age, state, tuple(reasons), 'BLOCKED' if reasons else 'CANDIDATE'))

    groups = defaultdict(list)
    for index, item in enumerate(result):
        if item.tag in profile.tags:
            groups[item.tag].append(index)
    for indices in groups.values():
        if any(result[index].timestamp is None for index in indices):
            for index in indices:
                item = result[index]
                result[index] = replace(item, state='ERROR' if item.raw.error else 'UNKNOWN',
                                        reasons=item.reasons + ('UNORDERED_SAMPLE',), decision='BLOCKED')
            continue
        by_time = defaultdict(list)
        for index in indices:
            by_time[result[index].timestamp].append(index)
        latest = max(by_time)
        for stamp, members in by_time.items():
            samples = {(result[i].raw.value_raw.strip(), result[i].raw.quality_raw.strip().casefold(), result[i].raw.error)
                       for i in members}
            if len(samples) > 1:
                for index in members:
                    item = result[index]
                    result[index] = replace(item, state='ERROR' if item.raw.error else 'UNKNOWN',
                                            reasons=item.reasons + ('CONFLICTING_SAMPLES',), decision='BLOCKED')
                continue
            for position, index in enumerate(members):
                item = result[index]
                if item.decision == 'CANDIDATE':
                    decision = 'SUPERSEDED' if stamp < latest else ('DUPLICATE_IN_FILE' if position else 'CANDIDATE')
                    result[index] = replace(item, decision=decision)
    return result
