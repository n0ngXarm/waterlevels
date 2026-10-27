"""The only network feature: an explicit, approved, fixed synthetic Telegram TEST."""
import hashlib
import json
import os
import platform
import re
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ledger import LedgerError

TEST_MESSAGE = ('[TEST] AQUA COMMAND Mini v0.1\n'
                'SIMULATED DATA ONLY\n'
                'DEMO_PUMP_01: ON\n'
                'DEMO_VALVE_01: OFF\n'
                'No plant data included. File import does not send notifications.')


@dataclass(frozen=True)
class TestResult:
    outcome: str
    reasons: tuple[str, ...]
    message: str = TEST_MESSAGE
    network_attempted: bool = False


def get_machine_id():
    """Read local OS identity and return only a digest. No network/MAC discovery."""
    try:
        if platform.system() == 'Windows':
            import winreg
            flags = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0, flags) as key:
                identity = winreg.QueryValueEx(key, 'MachineGuid')[0]
        else:
            identity = Path('/etc/machine-id').read_text(encoding='ascii').strip()
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError
        return hashlib.sha256(('AQUA-MINI-v1:' + platform.system() + ':' + identity.strip()).encode()).hexdigest()
    except (OSError, ValueError, ImportError):
        raise ValueError('MACHINE_ID_UNAVAILABLE') from None


def _credentials():
    return (os.environ.get('AQUA_TELEGRAM_BOT_TOKEN', '').strip(),
            os.environ.get('AQUA_TELEGRAM_CHAT_ID', '').strip())


def readiness(profile, credentials=None):
    reasons = []
    settings = profile.telegram
    if not settings['enabled']:
        reasons.append('TELEGRAM_DISABLED')
    if platform.system() != 'Windows':
        reasons.append('APPROVED_WINDOWS_TEST_MACHINE_REQUIRED')
    try:
        if get_machine_id() not in settings['approved_machine_ids']:
            reasons.append('MACHINE_NOT_APPROVED')
    except ValueError:
        reasons.append('MACHINE_ID_UNAVAILABLE')
    if not settings['approval_reference'].strip():
        reasons.append('APPROVAL_REFERENCE_REQUIRED')
    token, chat = credentials if credentials is not None else _credentials()
    if not re.fullmatch(r'\d{6,15}:[A-Za-z0-9_-]{20,100}', token):
        reasons.append('TOKEN_ENV_MISSING_OR_INVALID')
    if not re.fullmatch(r'-?\d{1,20}', chat):
        reasons.append('CHAT_ID_ENV_MISSING_OR_INVALID')
    chat_hash = hashlib.sha256(chat.encode()).hexdigest()
    if not settings['approved_chat_id_sha256'] or chat_hash != settings['approved_chat_id_sha256']:
        reasons.append('RECIPIENT_NOT_APPROVED')
    return tuple(reasons)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_test(token, chat):
    # Fixed host and fixed text. Never pass imported data or arbitrary message text here.
    payload = json.dumps({'chat_id': chat, 'text': TEST_MESSAGE, 'protect_content': True}, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage', data=payload,
                                     headers={'Content-Type': 'application/json'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(request, timeout=10) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('TELEGRAM_RESPONSE_INVALID')
    reply = json.loads(raw)
    if (not isinstance(reply, dict) or reply.get('ok') is not True
            or not isinstance(reply.get('result'), dict) or type(reply['result'].get('message_id')) is not int):
        raise ValueError('TELEGRAM_RESPONSE_INVALID')


def run_test(profile, ledger=None, send=False, confirmed=False, now=None):
    credentials = _credentials()
    reasons = readiness(profile, credentials)
    if not send:
        return TestResult('DRY_RUN', reasons)
    if not confirmed:
        reasons += ('EXPLICIT_TEST_CONFIRMATION_REQUIRED',)
    if ledger is None:
        reasons += ('DURABLE_LEDGER_REQUIRED',)
    if reasons:
        return TestResult('BLOCKED', reasons)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('NOW_MUST_HAVE_TIMEZONE')
    day = now.astimezone(timezone.utc).date().isoformat()
    if not ledger.reserve_test(day):
        return TestResult('DUPLICATE', ('TEST_ALREADY_RESERVED_TODAY_UTC_NO_RETRY',))
    try:
        post_test(*credentials)
    except Exception:
        # Exceptions may contain the credential-bearing URL. Never expose response/exception text.
        try:
            ledger.finish_test(day, 'FAILED_UNKNOWN')
        except LedgerError:
            return TestResult('FAILED_UNKNOWN', ('SEND_AND_LEDGER_RESULT_UNKNOWN_NO_RETRY',), network_attempted=True)
        return TestResult('FAILED_UNKNOWN', ('TELEGRAM_RESULT_UNKNOWN_NO_AUTOMATIC_RETRY',), network_attempted=True)
    try:
        ledger.finish_test(day, 'SENT')
    except LedgerError:
        return TestResult('FAILED_UNKNOWN', ('TEST_SENT_LEDGER_RESULT_UNKNOWN_NO_RETRY',), network_attempted=True)
    return TestResult('SENT', (), network_attempted=True)
