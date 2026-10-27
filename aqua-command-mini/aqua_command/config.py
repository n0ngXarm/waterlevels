"""Strict, non-secret policy profiles. No credentials are accepted here."""
import copy
import hashlib
import json
import re
import stat
from dataclasses import dataclass

from .paths import local_path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    profile_id: str
    tags: dict
    source_utc_offset: str | None
    freshness_seconds: int
    future_tolerance_seconds: int
    telegram: dict
    policy_id: str


def default_profile_dict():
    return {
        'schema_version': 1,
        'profile_id': 'DEMO_ONLY',
        'source_utc_offset': None,
        'freshness_seconds': 300,
        'future_tolerance_seconds': 5,
        'tags': {
            'DEMO_PUMP_01': {'mapping': {'0': 'OFF', '1': 'ON'}, 'good_quality': ['GOOD']},
            'DEMO_VALVE_01': {'mapping': {'0': 'OFF', '1': 'ON'}, 'good_quality': ['GOOD']},
        },
        'telegram': {
            'enabled': False,
            'approved_machine_ids': [],
            'approval_reference': '',
            'approved_chat_id_sha256': '',
        },
    }


def _text(value, max_length=128, allow_empty=False):
    return (isinstance(value, str) and len(value) <= max_length
            and (allow_empty or bool(value.strip()))
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def profile_from_dict(data):
    expected = set(default_profile_dict())
    if not isinstance(data, dict) or set(data) != expected:
        raise ConfigError('PROFILE_FIELDS_INVALID')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ConfigError('PROFILE_VERSION_UNSUPPORTED')
    if not isinstance(data['profile_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', data['profile_id']):
        raise ConfigError('PROFILE_ID_INVALID')
    for key, low, high in (('freshness_seconds', 1, 86400), ('future_tolerance_seconds', 0, 60)):
        if type(data[key]) is not int or not low <= data[key] <= high:
            raise ConfigError('PROFILE_TIME_LIMIT_INVALID')
    offset = data['source_utc_offset']
    if offset is not None:
        if not isinstance(offset, str) or not re.fullmatch(r'[+-](?:0\d|1[0-4]):[0-5]\d', offset):
            raise ConfigError('SOURCE_OFFSET_INVALID')
        if offset[1:3] == '14' and offset[4:] != '00':
            raise ConfigError('SOURCE_OFFSET_INVALID')
    tags = data['tags']
    if not isinstance(tags, dict) or len(tags) > 200:
        raise ConfigError('TAG_ALLOWLIST_INVALID')
    for tag, rule in tags.items():
        if not _text(tag) or tag != tag.strip() or not isinstance(rule, dict) or set(rule) != {'mapping', 'good_quality'}:
            raise ConfigError('TAG_RULE_INVALID')
        mapping = rule['mapping']
        if (not isinstance(mapping, dict) or set(mapping) != {'0', '1'}
                or not all(isinstance(value, str) for value in mapping.values())
                or set(mapping.values()) != {'ON', 'OFF'}):
            raise ConfigError('EXPLICIT_BINARY_MAPPING_REQUIRED')
        good = rule['good_quality']
        if not isinstance(good, list) or not 1 <= len(good) <= 20 or not all(_text(q, 64) and q == q.strip() for q in good):
            raise ConfigError('GOOD_QUALITY_ALLOWLIST_REQUIRED')
    telegram = data['telegram']
    if not isinstance(telegram, dict) or set(telegram) != set(default_profile_dict()['telegram']):
        raise ConfigError('TELEGRAM_FIELDS_INVALID_NO_SECRETS_ALLOWED')
    if type(telegram['enabled']) is not bool:
        raise ConfigError('TELEGRAM_ENABLED_INVALID')
    machines = telegram['approved_machine_ids']
    if (not isinstance(machines, list) or len(machines) > 20
            or not all(isinstance(m, str) and re.fullmatch(r'[a-f0-9]{64}', m) for m in machines)):
        raise ConfigError('APPROVED_MACHINE_IDS_INVALID')
    if not _text(telegram['approval_reference'], 256, allow_empty=True):
        raise ConfigError('APPROVAL_REFERENCE_INVALID')
    chat_hash = telegram['approved_chat_id_sha256']
    if not isinstance(chat_hash, str) or (chat_hash and not re.fullmatch(r'[a-f0-9]{64}', chat_hash)):
        raise ConfigError('APPROVED_RECIPIENT_HASH_INVALID')
    policy_data = {k: v for k, v in data.items() if k != 'telegram'}
    digest = hashlib.sha256(json.dumps(policy_data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    return Profile(data['profile_id'], copy.deepcopy(tags), offset, data['freshness_seconds'],
                   data['future_tolerance_seconds'], copy.deepcopy(telegram), digest)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError('DUPLICATE_PROFILE_KEY')
        result[key] = value
    return result


def load_profile(path=None):
    if path is None:
        return profile_from_dict(default_profile_dict())
    try:
        source = local_path(path)
        if not stat.S_ISREG(source.stat().st_mode):
            raise ConfigError('PROFILE_REGULAR_FILE_REQUIRED')
        with source.open('rb') as handle:
            data = handle.read(131073)
        if len(data) > 131072:
            raise ConfigError('PROFILE_TOO_LARGE')
        return profile_from_dict(json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique_object))
    except ConfigError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        raise ConfigError('PROFILE_READ_OR_JSON_ERROR') from None
