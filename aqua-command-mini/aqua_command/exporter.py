"""Create a new, spreadsheet-safe structured CSV. Never write to an input file."""
import csv
from datetime import timezone

from .paths import local_path

FIELDS = ('schema_version', 'source_kind', 'source_name', 'source_sha256', 'source_encoding', 'source_delimiter',
          'source_row', 'tag', 'timestamp_raw', 'timestamp_utc', 'value_raw', 'quality_raw', 'state', 'reason',
          'notification_decision', 'mode')


class ExportError(ValueError):
    pass


def _cell(value):
    text = str(value)
    stripped = text.lstrip(' \t\r\n')
    if text.startswith(('\t', '\r', '\n')) or stripped.startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def export_csv(imported, rows, target):
    if imported.kind != 'runtime_values':
        raise ExportError('NO_RUNTIME_STATUS_TO_EXPORT')
    created = False
    try:
        destination = local_path(target)
        if destination.suffix.casefold() != '.csv':
            raise ExportError('CSV_TARGET_REQUIRED')
        if imported.source_path is not None and destination.resolve() == imported.source_path.resolve():
            raise ExportError('SOURCE_OVERWRITE_BLOCKED')
        with destination.open('x', encoding='utf-8-sig', newline='') as handle:
            created = True
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for item in rows:
                stamp = item.timestamp.astimezone(timezone.utc).isoformat() if item.timestamp else ''
                values = (1, imported.kind, imported.name, imported.sha256, imported.encoding,
                          {'\t': 'TAB', ';': 'SEMICOLON', ',': 'COMMA'}.get(imported.delimiter, ''),
                          item.raw.source_row, item.raw.tag, item.raw.timestamp_raw, stamp,
                          item.raw.value_raw, item.raw.quality_raw, item.state, ';'.join(item.reasons) or 'OK', item.decision, 'DRY_RUN')
                writer.writerow({key: _cell(value) for key, value in zip(FIELDS, values)})
        return destination
    except (OSError, ValueError) as error:
        if created:
            try:
                destination.unlink()
            except OSError:
                pass
        if isinstance(error, ExportError):
            raise
        raise ExportError('EXPORT_FAILED_NEW_LOCAL_FILE_REQUIRED') from None
