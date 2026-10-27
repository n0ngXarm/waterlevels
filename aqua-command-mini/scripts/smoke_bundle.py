"""Exercise a built Windows package with synthetic files and NO Telegram send."""
import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    cli = bundle / 'AQUA_COMMAND_Mini_CLI.exe'
    gui = bundle / 'AQUA_COMMAND_Mini.exe'
    checks = []
    def call(*arguments):
        result = subprocess.run([str(cli), *map(str, arguments)], capture_output=True, text=True,
                                encoding='utf-8', timeout=60)
        if result.returncode != 0:
            raise RuntimeError('BUNDLE_COMMAND_FAILED: ' + str(arguments[0]))
        return result.stdout
    assert '0.1.0' in call('--version')
    checks.append('packaged_cli_version')
    with tempfile.TemporaryDirectory(prefix='aqua-synthetic-') as tmp:
        root = Path(tmp)
        source, target = root / 'demo.csv', root / 'structured.csv'
        call('demo', '--output', source)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        common = [source, '--data-dir', root / 'state', '--json']
        preview = json.loads(call('preview', *common, '--export', target))
        assert [r['state'] for r in preview['rows']] == ['ON', 'OFF']
        assert target.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        checks.extend(['synthetic_on_off', 'structured_csv_export', 'source_unchanged'])
        first = json.loads(call('dry-run', *common))
        second = json.loads(call('dry-run', *common))
        assert all(r['decision'] == 'CANDIDATE' for r in first['rows'])
        assert all(r['decision'] == 'DUPLICATE_HISTORY' for r in second['rows'])
        checks.append('durable_duplicate_suppression')
        test = json.loads(call('telegram-test', '--json', '--data-dir', root / 'state'))
        assert test['outcome'] == 'DRY_RUN' and test['network_attempted'] is False
        checks.append('packaged_telegram_default_dry_run')
    process = subprocess.Popen([str(gui)], cwd=bundle)
    try:
        # A bounded startup observation, not a production watcher or plant polling loop.
        time.sleep(3)
        assert process.poll() is None, 'GUI_EXITED_DURING_STARTUP'
        checks.append('packaged_gui_startup_alive_3s')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'python': platform.python_version(), 'checks_passed': checks, 'telegram_network_attempted': False,
              'data': 'SYNTHETIC_ONLY', 'windows_11_native_acceptance': 'NOT_ESTABLISHED_BY_THIS_SCRIPT'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
