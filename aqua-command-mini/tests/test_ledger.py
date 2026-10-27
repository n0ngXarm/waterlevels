"""Failures caught: preview consumes events, duplicate on restart, high-water rollback, races."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aqua_command.config import load_profile
from aqua_command.ledger import Ledger, LedgerError
from aqua_command.policy import evaluate
from tests.helpers import NOW, imported, row


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'history.sqlite3'
        self.profile = load_profile()

    def rows(self, **kwargs):
        return evaluate(imported([row(**kwargs)]), self.profile, NOW)

    def test_preview_does_not_consume_and_restart_suppresses(self):
        with Ledger(self.path) as ledger:
            for _ in range(2):
                self.assertEqual(ledger.plan(self.rows(), self.profile.policy_id)[0].decision, 'CANDIDATE')
            self.assertEqual(ledger.commit_dry_run(self.rows(), self.profile.policy_id)[0].decision, 'CANDIDATE')
        with Ledger(self.path) as ledger:
            self.assertEqual(ledger.plan(self.rows(), self.profile.policy_id)[0].decision, 'DUPLICATE_HISTORY')

    def test_unchanged_advances_high_water_only_on_commit(self):
        with Ledger(self.path) as ledger:
            ledger.commit_dry_run(self.rows(stamp='2026-10-27T02:58:00Z'), self.profile.policy_id)
            result = ledger.commit_dry_run(self.rows(), self.profile.policy_id)
            self.assertEqual(result[0].decision, 'UNCHANGED')
            result = ledger.plan(self.rows(value='0', stamp='2026-10-27T02:59:00Z'), self.profile.policy_id)
            self.assertEqual(result[0].decision, 'OUT_OF_ORDER')
            result = ledger.plan(self.rows(value='0', stamp='2026-10-27T03:00:01Z'), self.profile.policy_id)
            self.assertEqual(result[0].decision, 'CANDIDATE')

    def test_bad_quality_does_not_create_history(self):
        with Ledger(self.path) as ledger:
            ledger.commit_dry_run(self.rows(quality='BAD'), self.profile.policy_id)
            self.assertEqual(ledger.plan(self.rows(), self.profile.policy_id)[0].decision, 'CANDIDATE')

    def test_same_timestamp_different_state_conflict(self):
        with Ledger(self.path) as ledger:
            ledger.commit_dry_run(self.rows(), self.profile.policy_id)
            result = ledger.plan(self.rows(value='0'), self.profile.policy_id)[0]
            self.assertEqual(result.state, 'UNKNOWN')
            self.assertIn('HISTORY_CONFLICT', result.reasons)

    def test_two_process_equivalent_commits_cannot_duplicate(self):
        with Ledger(self.path):
            pass
        def commit(_):
            with Ledger(self.path) as ledger:
                return ledger.commit_dry_run(self.rows(), self.profile.policy_id)[0].decision
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(commit, [1, 2]))
        self.assertCountEqual(decisions, ['CANDIDATE', 'DUPLICATE_HISTORY'])

    def test_test_reservation_is_durable(self):
        with Ledger(self.path) as ledger:
            self.assertTrue(ledger.reserve_test('2026-10-27'))
        with Ledger(self.path) as ledger:
            self.assertFalse(ledger.reserve_test('2026-10-27'))
            ledger.finish_test('2026-10-27', 'FAILED_UNKNOWN')
            self.assertFalse(ledger.reserve_test('2026-10-27'))

    def test_corrupt_history_fails_closed_and_does_not_overwrite(self):
        data = b'not a database: keep for investigation'
        self.path.write_bytes(data)
        with self.assertRaises(LedgerError):
            Ledger(self.path)
        self.assertEqual(self.path.read_bytes(), data)

    def test_ledger_cannot_be_csv_or_network_path(self):
        for path in (Path(self.tmp.name) / 'values.csv', r'\\ot\share\x.sqlite3'):
            with self.assertRaises(LedgerError):
                Ledger(path)
