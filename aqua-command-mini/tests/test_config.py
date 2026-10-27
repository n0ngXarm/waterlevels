"""Failures caught: permissive defaults, hidden secret fields, invalid mapping accepted."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from aqua_command.config import ConfigError, default_profile_dict, load_profile, profile_from_dict


class ConfigTests(unittest.TestCase):
    def test_defaults_are_demo_only_and_sending_disabled(self):
        profile = load_profile()
        self.assertEqual(set(profile.tags), {'DEMO_PUMP_01', 'DEMO_VALVE_01'})
        self.assertFalse(profile.telegram['enabled'])
        self.assertEqual(profile.telegram['approved_machine_ids'], [])
        self.assertIsNone(profile.source_utc_offset)

    def test_explicit_mapping_and_policy_fingerprint(self):
        data = default_profile_dict()
        first = profile_from_dict(data)
        data['tags']['DEMO_PUMP_01']['mapping'] = {'0': 'ON', '1': 'OFF'}
        second = profile_from_dict(data)
        self.assertNotEqual(first.policy_id, second.policy_id)
        self.assertEqual(second.tags['DEMO_PUMP_01']['mapping']['0'], 'ON')

    def test_invalid_profiles_fail_closed(self):
        mutations = [
            lambda d: d.update(freshness_seconds=0),
            lambda d: d.update(freshness_seconds=True),
            lambda d: d.update(future_tolerance_seconds=61),
            lambda d: d.update(source_utc_offset='Asia/Bangkok'),
            lambda d: d.update(source_utc_offset='+25:00'),
            lambda d: d.update(unknown_option=True),
            lambda d: d['tags']['DEMO_PUMP_01'].update(mapping={'1': 'ON'}),
            lambda d: d['tags']['DEMO_PUMP_01'].update(mapping={'0': 'ON', '1': 'ON'}),
            lambda d: d['tags']['DEMO_PUMP_01'].update(mapping={'0': [], '1': 'ON'}),
            lambda d: d['tags']['DEMO_PUMP_01'].update(good_quality=[]),
            lambda d: d['telegram'].update(token='secret'),
            lambda d: d['telegram'].update(enabled='false'),
            lambda d: d['telegram'].update(approved_machine_ids=['anything']),
        ]
        for mutate in mutations:
            data = copy.deepcopy(default_profile_dict())
            mutate(data)
            with self.subTest(data=str(data)[:90]):
                with self.assertRaises(ConfigError):
                    profile_from_dict(data)

    def test_empty_allowlist_blocks_everything(self):
        data = default_profile_dict()
        data['tags'] = {}
        self.assertEqual(profile_from_dict(data).tags, {})

    def test_duplicate_json_keys_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile.json'
            for content in ('{"schema_version":1,"schema_version":1}', ' ' * 131073):
                path.write_text(content)
                with self.assertRaises(ConfigError):
                    load_profile(path)

    def test_load_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile.json'
            path.write_text(json.dumps(default_profile_dict()), encoding='utf-8-sig')
            self.assertEqual(load_profile(path).profile_id, 'DEMO_ONLY')
