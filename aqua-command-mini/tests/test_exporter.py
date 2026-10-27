"""Failures caught: original file overwritten and spreadsheet formula injection."""
import csv
import tempfile
import unittest
from pathlib import Path

from aqua_command.config import load_profile
from aqua_command.exporter import ExportError, export_csv
from aqua_command.importer import import_file, import_bytes
from aqua_command.policy import evaluate
from tests.helpers import NOW, imported, row


class ExporterTests(unittest.TestCase):
    def test_structured_csv_preserves_source_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.csv'
            data = b'tag,timestamp,value,quality\nDEMO_PUMP_01,2026-10-27T03:00:00Z,1,GOOD\n'
            source.write_bytes(data)
            snapshot = import_file(source)
            rows = evaluate(snapshot, load_profile(), NOW)
            target = Path(tmp) / 'result.csv'
            export_csv(snapshot, rows, target)
            self.assertEqual(source.read_bytes(), data)
            self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbf'))
            with target.open(encoding='utf-8-sig', newline='') as handle:
                result = list(csv.DictReader(handle))
            self.assertEqual(result[0]['state'], 'ON')
            self.assertEqual(result[0]['source_sha256'], snapshot.sha256)
            self.assertEqual(result[0]['mode'], 'DRY_RUN')

    def test_no_existing_file_is_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'source.csv'
            data = b'original'
            target.write_bytes(data)
            snapshot = imported([row()])
            with self.assertRaises(ExportError):
                export_csv(snapshot, evaluate(snapshot, load_profile(), NOW), target)
            self.assertEqual(target.read_bytes(), data)

    def test_formula_cells_are_neutralized(self):
        snapshot = imported([row(tag='=HYPERLINK("bad")', value='+1', quality='@SUM(1)', stamp='\t=1')])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'safe.csv'
            export_csv(snapshot, evaluate(snapshot, load_profile(), NOW), target)
            with target.open(encoding='utf-8-sig', newline='') as handle:
                result = next(csv.DictReader(handle))
            for field in ('tag', 'value_raw', 'quality_raw', 'timestamp_raw'):
                self.assertTrue(result[field].startswith("'"), (field, result[field]))

    def test_configuration_and_unknown_have_no_status_export(self):
        for data in (b'DmTag\tTags\tTag', b'unknown'):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ExportError):
                    export_csv(import_bytes(data, 'x.txt'), [], Path(tmp) / 'x.csv')
