"""No real credentials or network: only the HTTP boundary is replaced."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aqua_command.config import default_profile_dict, profile_from_dict
from aqua_command.ledger import Ledger
from aqua_command.telegram_test import TEST_MESSAGE, run_test, post_test
from tests.helpers import NOW

# Deliberately fabricated token; not a real bot credential.
FAKE_TOKEN = '123456789:' + 'A' * 35
FAKE_CHAT = '-1000000000001'
MACHINE = 'a' * 64


def approved_dict():
    data = default_profile_dict()
    data['telegram'].update(enabled=True, approved_machine_ids=[MACHINE], approval_reference='POC-APPROVED-TEST',
                            approved_chat_id_sha256=hashlib.sha256(FAKE_CHAT.encode()).hexdigest())
    return data


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger(Path(self.tmp.name) / 'history.sqlite3')
        self.addCleanup(self.ledger.close)
        self.env = patch.dict('os.environ', {'AQUA_TELEGRAM_BOT_TOKEN': FAKE_TOKEN, 'AQUA_TELEGRAM_CHAT_ID': FAKE_CHAT}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.system = patch('aqua_command.telegram_test.platform.system', return_value='Windows')
        self.system.start()
        self.addCleanup(self.system.stop)
        self.machine = patch('aqua_command.telegram_test.get_machine_id', return_value=MACHINE)
        self.machine.start()
        self.addCleanup(self.machine.stop)

    def test_default_dry_run_never_contacts_network_or_reserves(self):
        with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('network forbidden')):
            result = run_test(profile_from_dict(approved_dict()), self.ledger, now=NOW)
        self.assertEqual(result.outcome, 'DRY_RUN')
        self.assertEqual(result.message, TEST_MESSAGE)
        self.assertTrue(self.ledger.reserve_test('2026-10-27'))

    def test_each_gate_blocks_real_send(self):
        mutations = [lambda d: d['telegram'].update(enabled=False),
                     lambda d: d['telegram'].update(approved_machine_ids=[]),
                     lambda d: d['telegram'].update(approval_reference=''),
                     lambda d: d['telegram'].update(approved_chat_id_sha256='b' * 64)]
        for mutate in mutations:
            data = approved_dict()
            mutate(data)
            with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('network forbidden')):
                result = run_test(profile_from_dict(data), self.ledger, send=True, confirmed=True, now=NOW)
            self.assertEqual(result.outcome, 'BLOCKED')
            self.assertFalse(result.network_attempted)

    def test_confirmation_and_windows_required(self):
        profile = profile_from_dict(approved_dict())
        self.assertEqual(run_test(profile, self.ledger, send=True, now=NOW).outcome, 'BLOCKED')
        with patch('aqua_command.telegram_test.platform.system', return_value='Linux'):
            self.assertEqual(run_test(profile, self.ledger, send=True, confirmed=True, now=NOW).outcome, 'BLOCKED')

    def test_missing_or_invalid_env_fails_without_secret_echo(self):
        for token, chat in [('', FAKE_CHAT), ('bad token secret', FAKE_CHAT), (FAKE_TOKEN, '@someone'), (FAKE_TOKEN, '')]:
            with patch.dict('os.environ', {'AQUA_TELEGRAM_BOT_TOKEN': token, 'AQUA_TELEGRAM_CHAT_ID': chat}, clear=True):
                result = run_test(profile_from_dict(approved_dict()), self.ledger, send=True, confirmed=True, now=NOW)
            self.assertEqual(result.outcome, 'BLOCKED')
            self.assertNotIn(FAKE_TOKEN, repr(result))
            self.assertNotIn('bad token secret', repr(result))

    def test_success_fixed_payload_and_duplicate_on_restart(self):
        sent = []
        def fake_post(token, chat):
            sent.append((token, chat))
        with patch('aqua_command.telegram_test.post_test', side_effect=fake_post):
            profile = profile_from_dict(approved_dict())
            first = run_test(profile, self.ledger, send=True, confirmed=True, now=NOW)
            self.ledger.close()
            self.ledger = Ledger(Path(self.tmp.name) / 'history.sqlite3')
            self.addCleanup(self.ledger.close)
            second = run_test(profile, self.ledger, send=True, confirmed=True, now=NOW)
        self.assertEqual(first.outcome, 'SENT')
        self.assertEqual(second.outcome, 'DUPLICATE')
        self.assertEqual(len(sent), 1)
        self.assertNotIn(FAKE_TOKEN, repr(first))

    def test_timeout_reserves_before_call_and_never_retries(self):
        profile = profile_from_dict(approved_dict())
        def failure(token, chat):
            with Ledger(Path(self.tmp.name) / 'history.sqlite3') as separate:
                self.assertFalse(separate.reserve_test('2026-10-27'))
            raise OSError('https://api.telegram.org/bot' + token)
        with patch('aqua_command.telegram_test.post_test', side_effect=failure):
            result = run_test(profile, self.ledger, send=True, confirmed=True, now=NOW)
        self.assertEqual(result.outcome, 'FAILED_UNKNOWN')
        self.assertNotIn(FAKE_TOKEN, repr(result))
        with patch('aqua_command.telegram_test.post_test', side_effect=AssertionError('retry forbidden')):
            result = run_test(profile, self.ledger, send=True, confirmed=True, now=NOW)
        self.assertEqual(result.outcome, 'DUPLICATE')

    def test_http_boundary_uses_only_synthetic_text_and_checks_ok(self):
        captured = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, limit): return b'{"ok":true,"result":{"message_id":7}}'
        class Opener:
            def open(self, request, timeout):
                captured.append((request, timeout))
                return Response()
        with patch('aqua_command.telegram_test.urllib.request.build_opener', return_value=Opener()):
            post_test(FAKE_TOKEN, FAKE_CHAT)
        request, timeout = captured[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.telegram.org/bot' + FAKE_TOKEN + '/sendMessage')
        self.assertEqual(payload['text'], TEST_MESSAGE)
        self.assertEqual(payload['chat_id'], FAKE_CHAT)
        self.assertNotIn('parse_mode', payload)
        self.assertLessEqual(timeout, 15)

    def test_redirects_are_rejected(self):
        from aqua_command.telegram_test import NoRedirect
        from urllib.request import Request
        self.assertIsNone(NoRedirect().redirect_request(Request('https://api.telegram.org/'), None, 302, 'Found', {}, 'https://bad.test/'))

    def test_credentials_cannot_change_after_recipient_approval(self):
        original_reserve = self.ledger.reserve_test
        captured = []
        def changed_environment(day):
            os.environ['AQUA_TELEGRAM_CHAT_ID'] = '-9999999999'
            return original_reserve(day)
        import os
        with patch.object(self.ledger, 'reserve_test', side_effect=changed_environment), patch('aqua_command.telegram_test.post_test', side_effect=lambda token, chat: captured.append(chat)):
            result = run_test(profile_from_dict(approved_dict()), self.ledger, send=True, confirmed=True, now=NOW)
        self.assertEqual(result.outcome, 'SENT')
        self.assertEqual(captured, [FAKE_CHAT])
