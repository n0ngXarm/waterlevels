"""Offline CLI, also used by the packaged Windows console executable."""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone

from . import __version__
from .config import ConfigError, load_profile
from .exporter import ExportError
from .importer import InputError
from .ledger import Ledger, LedgerError
from .paths import local_path
from .session import Session, default_data_dir, demo_csv
from .telegram_test import get_machine_id, run_test


def parser():
    root = argparse.ArgumentParser(description='AQUA COMMAND Mini — offline PoC / DRY-RUN')
    root.add_argument('--version', action='version', version='AQUA COMMAND Mini ' + __version__)
    commands = root.add_subparsers(dest='command')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--config', help='non-secret JSON policy profile')
    common.add_argument('--data-dir', help='local dry-run history directory')
    common.add_argument('--json', action='store_true', help='structured local output')
    for command in ('preview', 'dry-run'):
        action = commands.add_parser(command, parents=[common])
        action.add_argument('file')
        action.add_argument('--export', metavar='NEW_CSV')
    demo = commands.add_parser('demo', help='create a new synthetic file with current timestamps')
    demo.add_argument('--output', required=True)
    demo.add_argument('--encoding', choices=['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be'], default='utf-8-sig')
    demo.add_argument('--delimiter', choices=['comma', 'semicolon', 'tab'], default='comma')
    telegram = commands.add_parser('telegram-test', parents=[common], help='fixed synthetic TEST; dry-run unless --send')
    telegram.add_argument('--send', action='store_true')
    telegram.add_argument('--confirm-test', action='store_true')
    commands.add_parser('gui', parents=[common])
    commands.add_parser('machine-id')
    commands.add_parser('recipient-hash', help='hash AQUA_TELEGRAM_CHAT_ID locally; never prints the ID')
    return root


def _row_dict(item):
    return {'source_row': item.raw.source_row, 'tag': item.raw.tag, 'timestamp_raw': item.raw.timestamp_raw,
            'timestamp_utc': item.timestamp.isoformat() if item.timestamp else None,
            'value_raw': item.raw.value_raw, 'quality_raw': item.raw.quality_raw, 'state': item.state,
            'reasons': list(item.reasons), 'decision': item.decision}


def _display(value):
    return str(value).replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')[:120]


def main(argv=None):
    # Piped output on Windows may otherwise inherit an ANSI console encoding.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    args = parser().parse_args(argv)
    try:
        command = args.command or 'gui'
        if command == 'machine-id':
            print(get_machine_id())
            return 0
        if command == 'recipient-hash':
            chat = os.environ.get('AQUA_TELEGRAM_CHAT_ID', '').strip()
            if not re.fullmatch(r'-?\d{1,20}', chat):
                raise ValueError('CHAT_ID_ENV_MISSING_OR_INVALID')
            print(hashlib.sha256(chat.encode()).hexdigest())
            return 0
        if command == 'demo':
            target = local_path(args.output)
            if target.suffix.casefold() not in ('.csv', '.txt'):
                raise InputError('TXT_OR_CSV_REQUIRED')
            data = demo_csv(delimiter={'comma': ',', 'semicolon': ';', 'tab': '\t'}[args.delimiter], encoding=args.encoding)
            with target.open('xb') as handle:
                handle.write(data)
            print('SIMULATED FILE CREATED: ' + str(target))
            return 0
        config = getattr(args, 'config', None)
        data_dir = getattr(args, 'data_dir', None)
        if command == 'gui':
            from .gui import launch
            return launch(config, data_dir)
        if command == 'telegram-test':
            profile = load_profile(config)
            if args.send:
                directory = local_path(data_dir) if data_dir else default_data_dir()
                with Ledger(directory / 'history.sqlite3') as ledger:
                    result = run_test(profile, ledger, send=True, confirmed=args.confirm_test)
            else:
                result = run_test(profile)
            payload = asdict(result)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(result.outcome + ' | ' + ', '.join(result.reasons))
                print(result.message)
            return {'BLOCKED': 3, 'FAILED_UNKNOWN': 4}.get(result.outcome, 0)
        session = Session(config, data_dir)
        source = session.open_file(args.file)
        now = datetime.now(timezone.utc)
        rows = session.rows(commit=command == 'dry-run', now=now)
        if args.export:
            from .exporter import export_csv
            export_csv(source, rows, args.export)
        report = {'version': __version__, 'mode': 'DRY_RUN', 'kind': source.kind, 'source_name': source.name,
                  'source_sha256': source.sha256, 'encoding': source.encoding, 'delimiter': source.delimiter,
                  'profile_id': session.profile.profile_id, 'policy_id': session.profile.policy_id,
                  'evaluated_at_utc': now.isoformat(), 'history_committed': command == 'dry-run',
                  'note': source.note, 'counts': dict(Counter(item.state for item in rows)),
                  'rows': [_row_dict(item) for item in rows]}
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print('DRY_RUN | FILE SNAPSHOT | ' + source.kind + ' | ' + source.encoding)
            print(source.note + ' | SHA256=' + source.sha256)
            if source.kind == 'tag_configuration':
                print('Tag Configuration: ไม่มีข้อมูลสถานะจริง — ไม่แปลงเป็น ON/OFF')
            for item in rows[:200]:
                print(' | '.join(_display(value) for value in (item.tag, item.raw.value_raw, item.state, item.decision, ';'.join(item.reasons) or 'OK')))
            if len(rows) > 200:
                print('แสดง 200 แถวแรก; JSON และ structured CSV มีทุกแถว')
            if command == 'dry-run':
                print('บันทึกประวัติ dry-run ในเครื่องแล้ว; ไม่มีการส่ง Telegram')
        return 0
    except (ConfigError, InputError, ExportError, LedgerError, ValueError, OSError) as error:
        code = str(error) if isinstance(error, (ValueError, LedgerError)) else 'LOCAL_FILE_OR_DIRECTORY_ERROR'
        if getattr(args, 'json', False):
            print(json.dumps({'error': code, 'mode': 'DRY_RUN'}, ensure_ascii=False))
        else:
            print('หยุดทำรายการ: ' + code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
