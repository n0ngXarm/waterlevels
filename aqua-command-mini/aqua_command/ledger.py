"""Transactional local dry-run history and at-most-once Telegram TEST reservations."""
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

from .paths import local_path


class LedgerError(RuntimeError):
    pass


class Ledger:
    def __init__(self, path):
        self.db = None
        try:
            self.path = local_path(path)
            if self.path.suffix != '.sqlite3':
                raise LedgerError('LEDGER_SQLITE3_SUFFIX_REQUIRED')
            existed = self.path.exists()
            if existed:
                with self.path.open('rb') as handle:
                    if handle.read(16) != b'SQLite format 3\x00':
                        raise LedgerError('LEDGER_CORRUPT_DO_NOT_RESET')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=3, isolation_level=None)
            self.db.execute('PRAGMA busy_timeout = 3000')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1) or (existed and version == 0):
                raise LedgerError('LEDGER_SCHEMA_UNSUPPORTED')
            if self.db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise LedgerError('LEDGER_CORRUPT_DO_NOT_RESET')
            self.db.execute('CREATE TABLE IF NOT EXISTS tag_history ('
                            'policy TEXT NOT NULL, tag TEXT NOT NULL, stamp TEXT NOT NULL, state TEXT NOT NULL, '
                            'PRIMARY KEY(policy,tag))')
            self.db.execute('CREATE TABLE IF NOT EXISTS test_reservations ('
                            'day TEXT PRIMARY KEY, status TEXT NOT NULL)')
            self.db.execute('PRAGMA user_version = 1')
        except (OSError, ValueError, sqlite3.Error, LedgerError) as error:
            if self.db is not None:
                self.db.close()
            if isinstance(error, LedgerError):
                raise
            raise LedgerError('LEDGER_UNAVAILABLE_DO_NOT_RESET') from None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    @contextmanager
    def _transaction(self, write=False):
        try:
            self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield
            self.db.execute('COMMIT')
        except Exception as error:
            try:
                self.db.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            if isinstance(error, sqlite3.Error):
                raise LedgerError('LEDGER_LOCKED_OR_CORRUPT_DO_NOT_RESET') from None
            raise

    def _plan(self, rows, policy_id):
        result = []
        for item in rows:
            if item.decision != 'CANDIDATE':
                result.append(item)
                continue
            previous = self.db.execute('SELECT stamp,state FROM tag_history WHERE policy=? AND tag=?',
                                       (policy_id, item.tag)).fetchone()
            if previous is None:
                result.append(item)
                continue
            try:
                stamp = datetime.fromisoformat(previous[0])
                if stamp.tzinfo is None or previous[1] not in ('ON', 'OFF'):
                    raise ValueError
            except (ValueError, TypeError):
                raise LedgerError('LEDGER_HISTORY_INVALID_DO_NOT_RESET') from None
            if item.timestamp == stamp and item.state != previous[1]:
                item = replace(item, state='UNKNOWN', reasons=item.reasons + ('HISTORY_CONFLICT',), decision='BLOCKED')
            elif item.timestamp == stamp:
                item = replace(item, decision='DUPLICATE_HISTORY')
            elif item.timestamp < stamp:
                item = replace(item, decision='OUT_OF_ORDER')
            elif item.state == previous[1]:
                item = replace(item, decision='UNCHANGED')
            result.append(item)
        return result

    def plan(self, rows, policy_id):
        with self._transaction():
            return self._plan(rows, policy_id)

    def commit_dry_run(self, rows, policy_id):
        with self._transaction(write=True):
            planned = self._plan(rows, policy_id)
            for item in planned:
                if item.decision in ('CANDIDATE', 'UNCHANGED'):
                    self.db.execute('INSERT INTO tag_history(policy,tag,stamp,state) VALUES (?,?,?,?) '
                                    'ON CONFLICT(policy,tag) DO UPDATE SET stamp=excluded.stamp,state=excluded.state',
                                    (policy_id, item.tag, item.timestamp.astimezone(timezone.utc).isoformat(timespec='microseconds'), item.state))
            return planned

    def reserve_test(self, day):
        with self._transaction(write=True):
            cursor = self.db.execute('INSERT OR IGNORE INTO test_reservations(day,status) VALUES (?,?)', (day, 'RESERVED'))
            return cursor.rowcount == 1

    def finish_test(self, day, status):
        if status not in ('SENT', 'FAILED_UNKNOWN'):
            raise LedgerError('TEST_RESULT_INVALID')
        with self._transaction(write=True):
            self.db.execute('UPDATE test_reservations SET status=? WHERE day=?', (status, day))
