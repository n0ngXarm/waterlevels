"""Run the real unittest suite with Python outbound socket connections denied."""
import argparse
import io
import json
import os
import platform
import socket
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Permit running as a script from the project root, without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--graphical', action='store_true')
    args = parser.parse_args()
    if args.graphical:
        os.environ['AQUA_RUN_GUI_TESTS'] = '1'
    stream = io.StringIO()
    denied = []
    def deny(*_args, **_kwargs):
        denied.append('DENIED')
        raise AssertionError('OUTBOUND_NETWORK_FORBIDDEN_DURING_TESTS')
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'python': platform.python_version(), 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'python_outbound_connection_attempts': len(denied), 'telegram': 'HTTP_BOUNDARY_REPLACED_NO_REAL_SEND',
              'data': 'SYNTHETIC_ONLY', 'successful': result.wasSuccessful() and not denied}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    with args.report.with_suffix('.txt').open('x', encoding='utf-8') as handle:
        handle.write(stream.getvalue())
    print(json.dumps(report, indent=2))
    return 0 if report['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
