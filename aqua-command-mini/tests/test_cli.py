"""Exercise real CLI flows and snapshot refresh, without contacting external systems."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from aqua_command.cli import main
from aqua_command.session import Session, demo_csv
from tests.helpers import NOW


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def call(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def test_demo_preview_export_dryrun_duplicate(self):
        source = self.root / 'demo.csv'
        code, _, _ = self.call(['demo', '--output', str(source)])
        self.assertEqual(code, 0)
        original = source.read_bytes()
        args = [str(source), '--data-dir', str(self.root / 'state'), '--json']
        with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('network forbidden')):
            code, out, _ = self.call(['preview', *args, '--export', str(self.root / 'structured.csv')])
            self.assertEqual(code, 0)
            result = json.loads(out)
            self.assertEqual([r['state'] for r in result['rows']], ['ON', 'OFF'])
            self.assertEqual(result['mode'], 'DRY_RUN')
            code, out, _ = self.call(['dry-run', *args])
            self.assertEqual(code, 0)
            self.assertEqual([r['decision'] for r in json.loads(out)['rows']], ['CANDIDATE', 'CANDIDATE'])
            code, out, _ = self.call(['dry-run', *args])
            self.assertEqual(code, 0)
            self.assertEqual([r['decision'] for r in json.loads(out)['rows']], ['DUPLICATE_HISTORY', 'DUPLICATE_HISTORY'])
        self.assertEqual(source.read_bytes(), original)

    def test_configuration_preview_no_status(self):
        source = self.root / 'Export all(1).txt'
        source.write_text('DmTag\tTags\tTag\n[NAME][100][1]\t[TYPE][101][1]', encoding='utf-16')
        code, out, _ = self.call(['preview', str(source), '--data-dir', str(self.root / 'state'), '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['kind'], 'tag_configuration')
        self.assertEqual(json.loads(out)['rows'], [])

    def test_telegram_default_dry_run(self):
        with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('network forbidden')):
            code, out, _ = self.call(['telegram-test', '--json', '--data-dir', str(self.root / 'state')])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['outcome'], 'DRY_RUN')

    def test_unapproved_send_is_blocked(self):
        with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('network forbidden')):
            code, out, _ = self.call(['telegram-test', '--send', '--confirm-test', '--json', '--data-dir', str(self.root / 'state')])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)['outcome'], 'BLOCKED')

    def test_bad_input_and_existing_demo_not_overwritten(self):
        source = self.root / 'keep.csv'
        source.write_bytes(b'keep')
        self.assertEqual(self.call(['demo', '--output', str(source)])[0], 2)
        self.assertEqual(source.read_bytes(), b'keep')
        self.assertEqual(self.call(['preview', str(self.root / 'missing.csv'), '--data-dir', str(self.root / 'state')])[0], 2)

    def test_session_rechecks_freshness_at_action_time(self):
        session = Session(data_dir=self.root / 'state')
        session.open_bytes(demo_csv(NOW), 'demo.csv')
        self.assertEqual(session.rows(now=NOW)[0].state, 'ON')
        self.assertEqual(session.rows(now=NOW + timedelta(seconds=301))[0].state, 'UNKNOWN')

    def test_failed_open_clears_previous_snapshot(self):
        session = Session(data_dir=self.root / 'state')
        session.open_bytes(demo_csv(NOW), 'demo.csv')
        with self.assertRaises(ValueError):
            session.open_file(self.root / 'missing.csv')
        self.assertIsNone(session.source)

    def test_module_entrypoint_is_runnable(self):
        result = subprocess.run([sys.executable, '-m', 'aqua_command', '--version'], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertIn('0.1.0', result.stdout)

    def test_thai_json_is_utf8_even_when_console_encoding_is_ascii(self):
        source = self.root / 'thai.csv'
        source.write_bytes(demo_csv().decode('utf-8-sig').replace('DEMO_PUMP_01', 'ปั๊มจำลอง').encode('utf-8'))
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        result = subprocess.run([sys.executable, '-m', 'aqua_command', 'preview', str(source),
                                 '--data-dir', str(self.root / 'state'), '--json'],
                                env=environment, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))
        self.assertEqual(json.loads(result.stdout)['rows'][0]['tag'], 'ปั๊มจำลอง')
