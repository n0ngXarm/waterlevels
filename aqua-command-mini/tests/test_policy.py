"""Failures caught: unsafe coercion, stale/bad samples shown ON, earlier sample wins."""
import unittest
from datetime import datetime

from aqua_command.config import default_profile_dict, load_profile, profile_from_dict
from aqua_command.importer import import_bytes
from aqua_command.policy import evaluate
from tests.helpers import NOW, imported, row


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()

    def evaluate_one(self, **kwargs):
        return evaluate(imported([row(**kwargs)]), self.profile, NOW)[0]

    def test_explicit_zero_one_only(self):
        for value, expected in [('0', 'OFF'), ('1', 'ON')]:
            result = self.evaluate_one(value=value)
            self.assertEqual(result.state, expected)
            self.assertEqual(result.decision, 'CANDIDATE')
        for value in ('', 'true', 'ON', '1.0', '-1', 'NaN', '=1+1', '01'):
            result = self.evaluate_one(value=value)
            self.assertEqual(result.state, 'UNKNOWN')
            self.assertIn('VALUE_NOT_MAPPED', result.reasons)

    def test_inverted_mapping_is_respected(self):
        data = default_profile_dict()
        data['tags']['DEMO_PUMP_01']['mapping'] = {'0': 'ON', '1': 'OFF'}
        results = evaluate(imported([row(value='0')]), profile_from_dict(data), NOW)
        self.assertEqual(results[0].state, 'ON')

    def test_tag_and_quality_fail_closed(self):
        for kwargs, reason in [({'tag': 'ACTUAL_PUMP'}, 'TAG_NOT_ALLOWED'), ({'tag': 'demo_pump_01'}, 'TAG_NOT_ALLOWED'),
                               ({'quality': '192'}, 'QUALITY_NOT_ACCEPTED'), ({'quality': 'BAD'}, 'QUALITY_NOT_ACCEPTED'),
                               ({'quality': ''}, 'QUALITY_NOT_ACCEPTED')]:
            result = self.evaluate_one(**kwargs)
            self.assertEqual(result.state, 'UNKNOWN')
            self.assertEqual(result.decision, 'BLOCKED')
            self.assertIn(reason, result.reasons)
        self.assertEqual(self.evaluate_one(quality=' good ').state, 'ON')

    def test_freshness_boundaries_and_future(self):
        cases = [('2026-10-27T02:55:00Z', 'ON', None),
                 ('2026-10-27T02:54:59Z', 'UNKNOWN', 'STALE'),
                 ('2026-10-27T03:00:05Z', 'ON', None),
                 ('2026-10-27T03:00:06Z', 'UNKNOWN', 'FUTURE_TIMESTAMP')]
        for stamp, state, reason in cases:
            result = self.evaluate_one(stamp=stamp)
            self.assertEqual(result.state, state)
            if reason:
                self.assertIn(reason, result.reasons)

    def test_timestamp_requires_explicit_timezone_or_profile_offset(self):
        result = self.evaluate_one(stamp='2026-10-27T10:00:00')
        self.assertEqual(result.state, 'UNKNOWN')
        self.assertIn('TIMEZONE_REQUIRED', result.reasons)
        data = default_profile_dict()
        data['source_utc_offset'] = '+07:00'
        result = evaluate(imported([row(stamp='2026-10-27 10:00:00')]), profile_from_dict(data), NOW)[0]
        self.assertEqual(result.state, 'ON')
        self.assertEqual(result.timestamp.isoformat(), '2026-10-27T03:00:00+00:00')

    def test_invalid_and_ambiguous_dates_block(self):
        for stamp in ('', '27/10/2026 10:00', '10/11/26', 'now', '2026-10-32T00:00:00Z', '20261027T030000Z', '2026-10-27'):
            self.assertEqual(self.evaluate_one(stamp=stamp).state, 'UNKNOWN')
        with self.assertRaises(ValueError):
            evaluate(imported([row()]), self.profile, datetime(2026, 10, 27, 3))

    def test_latest_bad_quality_does_not_fall_back_to_older_good(self):
        result = evaluate(imported([row(stamp='2026-10-27T02:59:00Z'), row(value='0', quality='BAD')]), self.profile, NOW)
        self.assertEqual(result[0].decision, 'SUPERSEDED')
        self.assertEqual(result[1].state, 'UNKNOWN')
        self.assertFalse(any(r.decision == 'CANDIDATE' for r in result))

    def test_conflicting_same_timestamp_blocks_all(self):
        result = evaluate(imported([row(value='1'), row(value='0')]), self.profile, NOW)
        self.assertTrue(all(r.state == 'UNKNOWN' and 'CONFLICTING_SAMPLES' in r.reasons for r in result))

    def test_duplicate_in_file_and_sorting(self):
        result = evaluate(imported([row(), row(), row(value='0', stamp='2026-10-27T02:59:00Z')]), self.profile, NOW)
        self.assertEqual([r.decision for r in result], ['CANDIDATE', 'DUPLICATE_IN_FILE', 'SUPERSEDED'])

    def test_unorderable_sample_blocks_same_tag_but_not_other_tag(self):
        result = evaluate(imported([row(), row(stamp='bad'), row(tag='DEMO_VALVE_01')]), self.profile, NOW)
        self.assertEqual(result[0].state, 'UNKNOWN')
        self.assertIn('UNORDERED_SAMPLE', result[0].reasons)
        self.assertEqual(result[2].decision, 'CANDIDATE')

    def test_malformed_row_is_error(self):
        source = import_bytes(b'tag,timestamp,value,quality\nDEMO_PUMP_01,now,1\n', 'bad.csv')
        result = evaluate(source, self.profile, NOW)
        self.assertEqual(result[0].state, 'ERROR')
        self.assertIn('COLUMN_COUNT', result[0].reasons)

    def test_non_runtime_never_evaluated(self):
        for data in (b'DmTag\tTags\tTag\n', b'foo,bar\n1,1\n'):
            self.assertEqual(evaluate(import_bytes(data, 'x.txt'), self.profile, NOW), [])
