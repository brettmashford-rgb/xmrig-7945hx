import json
from pathlib import Path
import unittest
from reference.dense import verify_opened_math


class DenseOracleTests(unittest.TestCase):
    def test_official_v2_and_v3_intermediates(self):
        for version in (2, 3):
            with self.subTest(version=version):
                fixture = json.loads((Path(__file__).parent / 'vectors' / f'official-v{version}.json').read_text())
                verify_opened_math(fixture)

    def test_changed_signal_fails(self):
        fixture = json.loads((Path(__file__).parent / 'vectors' / 'official-v3.json').read_text())
        fixture['opened_a'][0][0] = 100
        with self.assertRaisesRegex(ValueError, 'signal outside'):
            verify_opened_math(fixture)

    def test_wrong_seed_version_fails(self):
        fixture = json.loads((Path(__file__).parent / 'vectors' / 'official-v3.json').read_text())
        fixture['cert_version'] = 2
        with self.assertRaisesRegex(ValueError, 'noise seed'):
            verify_opened_math(fixture)
