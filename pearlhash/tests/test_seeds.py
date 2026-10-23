"""Expected outputs are upstream pinned values, not locally generated goldens."""

import json
from pathlib import Path
import unittest

from reference.seeds import dense_noise_seeds


class SeedTests(unittest.TestCase):
    def test_upstream_pinned_dense_vectors(self):
        fixture = json.loads((Path(__file__).parent / "vectors" / "dense-seeds.json").read_text())
        for vector in fixture["vectors"]:
            for version in vector["cert_versions"]:
                with self.subTest(cert_version=version):
                    b_seed, a_seed = dense_noise_seeds(
                        bytes.fromhex(vector["job_key"]),
                        bytes.fromhex(vector["hash_a"]),
                        bytes.fromhex(vector["hash_b"]),
                        vector["m"], vector["n"], cert_version=version,
                    )
                    self.assertEqual(b_seed.hex(), vector["b_noise_seed"])
                    self.assertEqual(a_seed.hex(), vector["a_noise_seed"])

    def test_v3_binds_dimensions(self):
        args = (bytes([0x11]) * 32, bytes([0xAA]) * 32, bytes([0xBB]) * 32)
        original = dense_noise_seeds(*args, 192, 320, cert_version=3)
        self.assertNotEqual(original, dense_noise_seeds(*args, 193, 320, cert_version=3))
        self.assertNotEqual(original, dense_noise_seeds(*args, 192, 321, cert_version=3))

    def test_unknown_version_rejected(self):
        for version in (None, 0, 4, True, "3"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                dense_noise_seeds(bytes(32), bytes(32), bytes(32), 192, 320, cert_version=version)

    def test_bad_inputs_rejected(self):
        with self.assertRaises(ValueError):
            dense_noise_seeds(bytes(31), bytes(32), bytes(32), 192, 320, cert_version=3)
        for dim in (0, -1, 2**32, True):
            with self.subTest(dim=dim), self.assertRaises(ValueError):
                dense_noise_seeds(bytes(32), bytes(32), bytes(32), dim, 320, cert_version=3)


if __name__ == "__main__":
    unittest.main()
