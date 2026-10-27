"""Failures caught: configuration interpreted as values, guessing schema, silent decoding loss."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from aqua_command.importer import InputError, import_bytes, import_file


class ImporterTests(unittest.TestCase):
    def test_encodings_and_delimiters(self):
        for encoding in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be'):
            for delimiter in ('\t', ';', ','):
                with self.subTest(encoding=encoding, delimiter=repr(delimiter)):
                    text = delimiter.join(('tag', 'timestamp', 'value', 'quality')) + '\n'
                    text += delimiter.join(('DEMO_PUMP_01', '2026-10-27T10:00:00+07:00', '1', 'GOOD')) + '\n'
                    data = text.encode(encoding)
                    result = import_bytes(data, 'sample.csv')
                    self.assertEqual(result.kind, 'runtime_values')
                    self.assertEqual(result.delimiter, delimiter)
                    self.assertEqual(result.records[0].tag, 'DEMO_PUMP_01')
                    self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())

    def test_configuration_wins_even_with_runtime_header(self):
        for prefix in ('DmTag\tTags\tTag\n', 'DmTag/Tags/Tag\n', '[NAME][100][1]\t[TYPE][101][1]\n'):
            data = (prefix + 'tag,timestamp,value,quality\nA,2026-10-27T00:00:00Z,1,GOOD\n').encode('utf-16')
            result = import_bytes(data, 'Export all(1).txt')
            self.assertEqual(result.kind, 'tag_configuration')
            self.assertEqual(result.records, ())

    def test_configuration_metadata_and_xml(self):
        for data in (b'TagName;DataType;Connection;Address\nP;Bool;C;DB1\n', b'<DmTag><Tags><Tag>abc</Tag></Tags></DmTag>'):
            self.assertEqual(import_bytes(data, 'x.txt').kind, 'tag_configuration')

    def test_archive_aliases_and_quoted_delimiter(self):
        result = import_bytes(b'VarName;TimeString;VarValue;Validity\n"DEMO;PUMP";2026-10-27T00:00:00Z;0;GOOD\n', 'archive.txt')
        self.assertEqual(result.kind, 'runtime_values')
        self.assertEqual(result.records[0].tag, 'DEMO;PUMP')

    def test_unknown_schema_does_not_guess(self):
        for data in (b'A,2026-10-27,1,GOOD\n', b'tag,value\nA,1\n', b'Name,Address,Comment\nA,DB1,test\n', b''):
            result = import_bytes(data, 'x.csv')
            self.assertEqual(result.records, ())
            self.assertNotEqual(result.kind, 'runtime_values')

    def test_duplicate_semantic_columns_rejected(self):
        with self.assertRaises(InputError):
            import_bytes(b'tag,TagName,timestamp,value,quality\nA,A,2026-01-01,1,GOOD', 'x.csv')

    def test_malformed_row_retained_as_error(self):
        result = import_bytes(b'tag,timestamp,value,quality\nA,now,1\nB,now,0,GOOD,EXTRA\n', 'x.csv')
        self.assertEqual(len(result.records), 2)
        self.assertTrue(all(r.error == 'COLUMN_COUNT' for r in result.records))

    def test_invalid_encoding_binary_and_bad_quotes_rejected(self):
        for data in (b'\xffbad', b'tag,value\x00\x01', b'tag,timestamp,value,quality\n"unterminated', 'abc'.encode('utf-32')):
            with self.subTest(data=repr(data)):
                with self.assertRaises(InputError):
                    import_bytes(data, 'x.txt')

    def test_limits_and_extensions(self):
        for data, name in ((b'a' * (10 * 1024 * 1024 + 1), 'x.txt'), (b'abc', 'x.exe'), (b'tag,timestamp,value,quality\n' + b'A' * 9000, 'x.csv')):
            with self.assertRaises(InputError):
                import_bytes(data, name)

    def test_file_is_read_only_and_unc_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.csv'
            data = b'tag,timestamp,value,quality\nA,now,1,GOOD\n'
            path.write_bytes(data)
            result = import_file(path)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(result.source_path, path.resolve())
        with self.assertRaises(InputError):
            import_file(r'\\ot-server\share\values.csv')

    def test_thai_utf16_be_bom(self):
        text = 'tag\ttimestamp\tvalue\tquality\nปั๊มจำลอง\t2026-10-27T00:00:00Z\t1\tGOOD\n'
        result = import_bytes(b'\xfe\xff' + text.encode('utf-16-be'), 'thai.txt')
        self.assertEqual(result.records[0].tag, 'ปั๊มจำลอง')


if __name__ == '__main__':
    unittest.main()
