import csv
import io
from datetime import datetime, timezone

from aqua_command.importer import import_bytes

NOW = datetime(2026, 10, 27, 3, 0, 0, tzinfo=timezone.utc)


def imported(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['tag', 'timestamp', 'value', 'quality'])
    writer.writerows(rows)
    return import_bytes(stream.getvalue().encode('utf-8'), 'synthetic.csv')


def row(value='1', stamp='2026-10-27T10:00:00+07:00', quality='GOOD', tag='DEMO_PUMP_01'):
    return [tag, stamp, value, quality]
