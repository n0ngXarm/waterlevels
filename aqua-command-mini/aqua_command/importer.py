"""Fail-closed TXT/CSV importer. Configuration exports never become process values."""
import csv
import hashlib
import io
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .paths import local_path

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000
MAX_FIELD = 8192
MAX_COLUMNS = 64
ALIASES = {
    'tag': {'tag', 'tagname', 'tag_name', 'variablename', 'varname'},
    'timestamp': {'timestamp', 'datetime', 'date_time', 'timestring', 'time_stamp'},
    'value': {'value', 'processvalue', 'realvalue', 'varvalue'},
    'quality': {'quality', 'qualitycode', 'quality_code', 'validity'},
}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class RawRecord:
    source_row: int
    tag: str
    timestamp_raw: str
    value_raw: str
    quality_raw: str
    error: str = ''


@dataclass(frozen=True)
class Imported:
    name: str
    source_path: Path | None
    sha256: str
    encoding: str
    delimiter: str
    kind: str
    records: tuple[RawRecord, ...]
    note: str


def _decode(data):
    try:
        if data.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
            raise InputError('UTF32_UNSUPPORTED')
        if data.startswith(b'\xef\xbb\xbf'):
            return data.decode('utf-8-sig', errors='strict'), 'UTF-8 BOM'
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            name = 'UTF-16 LE BOM' if data.startswith(b'\xff\xfe') else 'UTF-16 BE BOM'
            return data.decode('utf-16', errors='strict'), name
        probe = data[:256]
        if len(probe) >= 8:
            pairs = len(probe) // 2
            even = probe[0:pairs * 2:2].count(0) / pairs
            odd = probe[1:pairs * 2:2].count(0) / pairs
            if odd > .3 and even < .1:
                return data.decode('utf-16-le', errors='strict'), 'UTF-16 LE (inferred)'
            if even > .3 and odd < .1:
                return data.decode('utf-16-be', errors='strict'), 'UTF-16 BE (inferred)'
        return data.decode('utf-8', errors='strict'), 'UTF-8'
    except UnicodeError:
        raise InputError('ENCODING_ERROR_UTF8_OR_UTF16_REQUIRED') from None


def _is_configuration(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()][:10]
    for line in lines:
        low = line.casefold().lstrip('\ufeff')
        if re.match(r'^<?dmtag(?:[\s/,;>]|$)', low):
            return True
        if '[name][100]' in low and ('[type][101]' in low or '[connection]' in low):
            return True
    if lines:
        cells = {c.strip(' "').casefold() for c in re.split(r'[\t;,]', lines[0])}
        if cells & {'tag', 'tagname', 'name'} and cells & {'datatype', 'type', 'connection'} and 'address' in cells:
            return True
    return False


def _schema(header):
    normalized = [value.strip().casefold() for value in header]
    columns = {}
    duplicates = False
    for semantic, aliases in ALIASES.items():
        matches = [i for i, value in enumerate(normalized) if value in aliases]
        if len(matches) > 1:
            duplicates = True
        if len(matches) == 1:
            columns[semantic] = matches[0]
    return columns, duplicates


def import_bytes(data, name, source_path=None):
    if Path(name).suffix.casefold() not in {'.txt', '.csv'}:
        raise InputError('TXT_OR_CSV_REQUIRED')
    if len(data) > MAX_BYTES:
        raise InputError('FILE_TOO_LARGE_10MIB_MAX')
    text, encoding = _decode(data)
    if any(ord(c) < 32 and c not in '\t\r\n' for c in text):
        raise InputError('BINARY_OR_CONTROL_CHARACTERS')
    base = dict(name=Path(name).name, source_path=source_path, sha256=hashlib.sha256(data).hexdigest(), encoding=encoding)
    if _is_configuration(text):
        return Imported(**base, delimiter='', kind='tag_configuration', records=(), note='CONFIGURATION_ONLY_NO_PROCESS_STATUS')
    first = next((line for line in text.splitlines() if line.strip()), '')
    candidates = []
    for delimiter in ('\t', ';', ','):
        try:
            header = next(csv.reader([first], delimiter=delimiter, strict=True))
        except (csv.Error, StopIteration):
            continue
        columns, duplicates = _schema(header)
        if duplicates:
            raise InputError('DUPLICATE_SEMANTIC_COLUMNS')
        if len(columns) == 4:
            candidates.append((delimiter, columns, len(header)))
    if len(candidates) > 1:
        raise InputError('AMBIGUOUS_DELIMITER')
    if not candidates:
        return Imported(**base, delimiter='', kind='unknown', records=(), note='UNSUPPORTED_HEADER_NO_STATUS_INFERRED')
    delimiter, columns, width = candidates[0]
    if width > MAX_COLUMNS:
        raise InputError('TOO_MANY_COLUMNS')
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    records = []
    header_seen = False
    try:
        while True:
            source_row = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) > MAX_COLUMNS or any(len(value) > MAX_FIELD for value in row):
                raise InputError('ROW_OR_FIELD_TOO_LARGE')
            if not header_seen:
                header_seen = True
                continue
            if len(records) >= MAX_ROWS:
                raise InputError('TOO_MANY_ROWS_50000_MAX')
            values = {key: row[index] if index < len(row) else '' for key, index in columns.items()}
            records.append(RawRecord(source_row, values['tag'], values['timestamp'], values['value'], values['quality'],
                                     '' if len(row) == width else 'COLUMN_COUNT'))
    except csv.Error:
        raise InputError('MALFORMED_CSV') from None
    return Imported(**base, delimiter=delimiter, kind='runtime_values', records=tuple(records), note='FILE_SNAPSHOT_NOT_LIVE')


def import_file(path):
    try:
        source = local_path(path)
        if not stat.S_ISREG(source.stat().st_mode):
            raise InputError('REGULAR_LOCAL_FILE_REQUIRED')
        with source.open('rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        return import_bytes(data, source.name, source.resolve())
    except InputError:
        raise
    except (OSError, ValueError):
        raise InputError('LOCAL_FILE_READ_ERROR') from None
