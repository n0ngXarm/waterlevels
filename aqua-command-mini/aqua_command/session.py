"""Shared application actions. Recheck the captured snapshot at each explicit action."""
import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import load_profile
from .exporter import export_csv
from .importer import InputError, import_bytes, import_file
from .ledger import Ledger
from .paths import local_path
from .policy import evaluate


def default_data_dir():
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA')
        if not base:
            raise ValueError('LOCALAPPDATA_REQUIRED_OR_SET_DATA_DIR')
        return local_path(base) / 'AQUA_COMMAND_Mini'
    return local_path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'AQUA_COMMAND_Mini'


def demo_csv(now=None, delimiter=',', encoding='utf-8-sig'):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('NOW_MUST_HAVE_TIMEZONE')
    stamp = now.astimezone(timezone.utc).isoformat(timespec='seconds')
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(['tag', 'timestamp', 'value', 'quality'])
    writer.writerow(['DEMO_PUMP_01', stamp, '1', 'GOOD'])
    writer.writerow(['DEMO_VALVE_01', stamp, '0', 'GOOD'])
    return output.getvalue().encode(encoding)


class Session:
    def __init__(self, config_path=None, data_dir=None):
        self.profile = load_profile(config_path)
        self.data_dir = local_path(data_dir) if data_dir is not None else default_data_dir()
        self.ledger_path = self.data_dir / 'history.sqlite3'
        self.source = None

    def select_profile(self, path):
        self.source = None
        self.profile = load_profile(path)

    def open_file(self, path):
        self.source = None
        self.source = import_file(path)
        return self.source

    def open_bytes(self, data, name):
        self.source = None
        self.source = import_bytes(data, name)
        return self.source

    def rows(self, commit=False, now=None):
        if self.source is None:
            raise InputError('NO_FILE_SELECTED')
        rows = evaluate(self.source, self.profile, now)
        if self.source.kind != 'runtime_values':
            return rows
        with Ledger(self.ledger_path) as ledger:
            if commit:
                return ledger.commit_dry_run(rows, self.profile.policy_id)
            return ledger.plan(rows, self.profile.policy_id)

    def export(self, target, now=None):
        rows = self.rows(now=now)
        return export_csv(self.source, rows, target), rows
